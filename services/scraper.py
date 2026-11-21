import re
import os
import time
import random
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict
import httpx
from scrapling.fetchers import Fetcher, StealthyFetcher
from scrapling.parser import Adaptor

import config
from validators.url import validate_safe_url
from validators.domain import get_canonical_domain
from services.circuit_breaker import circuit_breaker
from tools import domain_limiter

logger = logging.getLogger("scraper")

_HTTP_CLIENT: Optional[httpx.Client] = None

def get_http_client() -> httpx.Client:
    """Provides a thread-safe, connection-pooled HTTPX client with proxy and modern browser headers."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        proxy = getattr(config, "PROXY_URL", "") or os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
        headers = {
            "User-Agent": config.DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1"
        }
        _HTTP_CLIENT = httpx.Client(
            timeout=config.HTTP_TIMEOUT_SECONDS,
            headers=headers,
            follow_redirects=True,
            proxy=proxy if proxy else None,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
        )
    return _HTTP_CLIENT

SPA_ROOT_INDICATORS = [
    r'<div\s+id=[\'"](?:root|app|__next|__nuxt|main-content|react-root)[\'"]\s*>\s*</div>',
    r'<app-root\b[^>]*>\s*</app-root>',
    r'<noscript>.*?enable javascript.*?</noscript>',
    r'<div\s+class=[\'"](?:app-root|react-container|spa-root)[\'"]\s*>\s*</div>',
    r'id=[\'"](?:__next|__nuxt)[\'"]',
    r'data-reactroot',
    r'ng-version=',
    r'v-cloak'
]

CHALLENGE_INDICATORS = [
    'cf-browser-verification',
    'challenge-platform',
    'bobcmn',
    'TSPD_',
    'support id is',
    'checking your browser',
    'ray id:',
    'cloudflare-static',
    'what code is in the image',
    'turnstile'
]

@dataclass
class ScrapeResult:
    html: str
    status_code: int
    scraping_mode: str  # 'http' or 'playwright'
    render_fallback_used: bool
    source_url: str
    scraped_at: str
    extraction_status: str  # 'success', 'empty', 'blocked', 'error'
    error_message: Optional[str] = None
    page_adaptor: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("page_adaptor", None)
        return d

def is_anti_bot_challenge(html: str, status_code: int) -> bool:
    """Detects anti-bot firewall challenge pages (Cloudflare, F5, Incapsula, etc.)."""
    if status_code in (403, 429, 503):
        return True
    if not html:
        return True
    html_lower = html.lower()
    for ind in CHALLENGE_INDICATORS:
        if ind.lower() in html_lower:
            return True
    return False

def requires_dynamic_rendering(html: str, body_text: str) -> bool:
    """
    Evaluates whether the page appears dynamically rendered via JavaScript
    and lacks meaningful server-rendered HTML content.
    """
    clean_text = re.sub(r'\s+', ' ', body_text).strip()
    words = clean_text.split()
    
    # 1. Very small body text but contains dynamic frameworks or script tags
    if len(words) < 50:
        for pattern in SPA_ROOT_INDICATORS:
            if re.search(pattern, html, re.IGNORECASE):
                return True
        if len(words) < 20 and ('<script' in html.lower() or '<noscript' in html.lower()):
            return True

    # 2. Explicit JavaScript required notice
    if re.search(r'you need to enable javascript|please enable javascript|javascript is required|enable javascript to run this app', html, re.IGNORECASE):
        return True

    # 3. Dynamic framework indicators with missing contact/person keywords
    if any(m in html.lower() for m in ['id="__next"', 'id="root"', 'id="app"', 'id="__nuxt"', '<app-root', 'data-reactroot']):
        # If the page has fewer than 150 words or lacks key contact cues
        if len(words) < 150 or not re.search(r'\b(?:phone|tel|mobile|email|contact|office|manager|director|executive|secretary|president)\b', clean_text, re.IGNORECASE):
            return True

    return False

def extract_response_html(page: Any) -> str:
    """Safely extracts HTML string from Scrapling Response or page object."""
    if hasattr(page, 'html_content') and page.html_content:
        return page.html_content
    if hasattr(page, 'body') and page.body:
        b = page.body
        return b.decode('utf-8', errors='ignore') if isinstance(b, bytes) else str(b)
    if hasattr(page, 'text') and page.text:
        return page.text
    return str(page)

def fetch_http_mode(url: str, timeout: float = 10.0) -> Tuple[Optional[str], int, Optional[str]]:
    """
    Mode A: Fast HTTP fetch using Scrapling's Fetcher (Chrome TLS impersonation)
    with connection-pooled httpx fallback.
    """
    # 1. Try Scrapling Fetcher with Chrome impersonation
    try:
        page = Fetcher.get(url, impersonate='chrome', timeout=int(timeout))
        html = extract_response_html(page)
        status = getattr(page, 'status', 200) or 200
        return html, status, None
    except Exception as e:
        logger.debug(f"Fetcher.get failed for {url}: {e}, falling back to pooled httpx client")

    # 2. Fallback to pooled connection client
    try:
        client = get_http_client()
        resp = client.get(url, timeout=timeout)
        return resp.text, resp.status_code, None
    except Exception as e:
        return None, 0, str(e)

def fetch_playwright_mode(
    url: str,
    timeout: int = 20000,
    wait_ms: int = 2500,
    scroll_down: bool = True
) -> Tuple[Optional[str], int, Optional[str]]:
    """
    Mode B: Headless stealth browser dynamic scraping using Playwright.
    Executes full client-side JavaScript, handles React/Vue/Angular DOM hydration,
    scrolls to trigger lazy loading, and extracts the fully rendered DOM.
    """
    def dynamic_js_action(page):
        if not scroll_down:
            return
        try:
            # Scroll progressively to trigger lazy loading and dynamic AJAX requests
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3);")
            page.wait_for_timeout(400)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight * 2 / 3);")
            page.wait_for_timeout(400)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            page.wait_for_timeout(600)
            page.evaluate("window.scrollTo(0, 0);")
        except Exception as e:
            logger.debug(f"dynamic_js_action scroll exception: {e}")

    try:
        page = StealthyFetcher.fetch(
            url,
            headless=True,
            timeout=timeout,
            wait=wait_ms,
            network_idle=False,
            load_dom=True,
            page_action=dynamic_js_action
        )
        if page:
            html = extract_response_html(page)
            status = getattr(page, 'status', 200) or 200
            return html, status, None
        return None, 0, "StealthyFetcher returned empty page"
    except Exception as e:
        return None, 0, str(e)

def adaptive_scrape(
    url: str,
    force_browser: bool = False,
    mode: str = "auto",
    max_retries: int = 2
) -> ScrapeResult:
    """
    Intelligent dual-mode scraper with automatic detection, retry logic,
    and fallback mechanism.
    
    Modes:
    - 'auto': Attempts fast HTTP first; automatically upgrades to Playwright if
              anti-bot challenge or dynamic JavaScript SPA is detected.
    - 'dynamic': Forces Headless Chromium with full JavaScript execution and DOM rendering.
    - 'http': Forces HTTP-only mode.
    """
    now_iso = datetime.utcnow().isoformat() + "Z"

    # Step 1: SSRF Validation
    is_safe, clean_url, ssrf_err = validate_safe_url(url)
    if not is_safe:
        return ScrapeResult(
            html="",
            status_code=400,
            scraping_mode="http",
            render_fallback_used=False,
            source_url=url,
            scraped_at=now_iso,
            extraction_status="blocked",
            error_message=f"SSRF Protection: {ssrf_err}"
        )

    # Step 1b: Circuit Breaker Validation
    if not circuit_breaker.can_request(clean_url):
        domain = get_canonical_domain(clean_url)
        return ScrapeResult(
            html="",
            status_code=503,
            scraping_mode="http",
            render_fallback_used=False,
            source_url=clean_url,
            scraped_at=now_iso,
            extraction_status="blocked",
            error_message=f"Circuit Breaker is OPEN for '{domain}' due to repeated blocks/failures"
        )

    # Step 1c: Polite Per-Domain Rate Limiting
    domain_limiter.wait_for_domain(clean_url)

    # If force_browser or mode == 'dynamic' requested explicitly
    if force_browser or mode == "dynamic":
        html, status, err = fetch_playwright_mode(clean_url, timeout=config.PLAYWRIGHT_TIMEOUT_MS)
        if html:
            circuit_breaker.record_success(clean_url)
            adaptor = Adaptor(html)
            return ScrapeResult(
                html=html,
                status_code=status,
                scraping_mode="playwright",
                render_fallback_used=False,
                source_url=clean_url,
                scraped_at=now_iso,
                extraction_status="success",
                page_adaptor=adaptor
            )
        circuit_breaker.record_failure(clean_url, f"Playwright failure: {err}")
        return ScrapeResult(
            html="",
            status_code=status or 500,
            scraping_mode="playwright",
            render_fallback_used=False,
            source_url=clean_url,
            scraped_at=now_iso,
            extraction_status="error",
            error_message=err
        )

    # Step 2: Mode A (HTTP) with exponential backoff & jitter
    last_err = None
    http_html = None
    http_status = 0

    for attempt in range(1, max_retries + 1):
        http_html, http_status, last_err = fetch_http_mode(clean_url, timeout=config.HTTP_TIMEOUT_SECONDS)
        if http_html:
            break
        backoff_sleep = (0.5 * (2 ** (attempt - 1))) + random.uniform(0.1, 0.3)
        time.sleep(backoff_sleep)

    # If mode is strictly 'http', return result without upgrading to Playwright
    if mode == "http":
        if http_html:
            circuit_breaker.record_success(clean_url)
            adaptor = Adaptor(http_html)
            return ScrapeResult(
                html=http_html,
                status_code=http_status,
                scraping_mode="http",
                render_fallback_used=False,
                source_url=clean_url,
                scraped_at=now_iso,
                extraction_status="success",
                page_adaptor=adaptor
            )
        circuit_breaker.record_failure(clean_url, f"HTTP failure: {last_err}")
        return ScrapeResult(
            html="",
            status_code=http_status or 500,
            scraping_mode="http",
            render_fallback_used=False,
            source_url=clean_url,
            scraped_at=now_iso,
            extraction_status="error",
            error_message=f"HTTP failed: {last_err}"
        )

    # Step 3: Evaluate HTTP response
    if http_html:
        adaptor = Adaptor(http_html)
        body_text = adaptor.get_all_text(ignore_tags=('script', 'style'))

        is_challenge = is_anti_bot_challenge(http_html, http_status)
        is_spa = requires_dynamic_rendering(http_html, body_text)

        # Step 4: If server-rendered content is complete, return HTTP result immediately!
        if not is_challenge and not is_spa:
            circuit_breaker.record_success(clean_url)
            return ScrapeResult(
                html=http_html,
                status_code=http_status,
                scraping_mode="http",
                render_fallback_used=False,
                source_url=clean_url,
                scraped_at=now_iso,
                extraction_status="success",
                page_adaptor=adaptor
            )

        logger.info(f"🔄 Mode switch triggered for {clean_url}: challenge={is_challenge}, spa={is_spa}")

    # Step 5: Fallback to Mode B (Playwright Dynamic Scraping)
    pw_html, pw_status, pw_err = fetch_playwright_mode(clean_url, timeout=config.PLAYWRIGHT_TIMEOUT_MS)
    if pw_html:
        circuit_breaker.record_success(clean_url)
        pw_adaptor = Adaptor(pw_html)
        return ScrapeResult(
            html=pw_html,
            status_code=pw_status,
            scraping_mode="playwright",
            render_fallback_used=True,
            source_url=clean_url,
            scraped_at=now_iso,
            extraction_status="success",
            page_adaptor=pw_adaptor
        )

    # Record failure if both failed
    circuit_breaker.record_failure(clean_url, f"Scrape failed (HTTP: {last_err}, PW: {pw_err})")

    # If both modes failed or returned empty
    if http_html:
        return ScrapeResult(
            html=http_html,
            status_code=http_status,
            scraping_mode="http",
            render_fallback_used=False,
            source_url=clean_url,
            scraped_at=now_iso,
            extraction_status="empty",
            error_message="Fallback to Playwright failed, returning initial HTTP content",
            page_adaptor=adaptor
        )

    return ScrapeResult(
        html="",
        status_code=http_status or 500,
        scraping_mode="http",
        render_fallback_used=True,
        source_url=clean_url,
        scraped_at=now_iso,
        extraction_status="error",
        error_message=f"HTTP failed ({last_err}), Playwright failed ({pw_err})"
    )
