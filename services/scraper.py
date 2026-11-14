import re
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict
import httpx
from scrapling.fetchers import Fetcher, StealthyFetcher
from scrapling.parser import Adaptor

import config
from validators.url import validate_safe_url

logger = logging.getLogger("scraper")

SPA_ROOT_INDICATORS = [
    r'<div\s+id=[\'"](?:root|app|__next)[\'"]\s*>\s*</div>',
    r'<noscript>.*?enable javascript.*?</noscript>',
    r'<div\s+class=[\'"]app-root[\'"]\s*>\s*</div>'
]

CHALLENGE_INDICATORS = [
    'cf-browser-verification',
    'challenge-platform',
    'bobcmn',
    'TSPD_',
    'support id is',
    'checking your browser',
    'ray id:',
    'cloudflare-static'
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
    if len(html.strip()) < 500:
        for ind in CHALLENGE_INDICATORS:
            if ind.lower() in html.lower():
                return True
    return False

def requires_dynamic_rendering(html: str, body_text: str) -> bool:
    """
    Evaluates whether the page appears dynamically rendered via JavaScript
    and lacks meaningful server-rendered HTML content.
    """
    clean_text = re.sub(r'\s+', ' ', body_text).strip()
    
    # 1. Very small body text but contains SPA root containers
    if len(clean_text) < 150:
        for pattern in SPA_ROOT_INDICATORS:
            if re.search(pattern, html, re.IGNORECASE):
                return True

    # 2. Explicit JavaScript required notice
    if re.search(r'you need to enable javascript to run this app', html, re.IGNORECASE):
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
    with httpx fallback.
    """
    # 1. Try Scrapling Fetcher with Chrome impersonation
    try:
        page = Fetcher.get(url, impersonate='chrome', timeout=int(timeout))
        html = extract_response_html(page)
        status = getattr(page, 'status', 200) or 200
        return html, status, None
    except Exception as e:
        logger.debug(f"Fetcher.get failed for {url}: {e}, falling back to httpx")

    # 2. Fallback to standard httpx client
    try:
        headers = {
            "User-Agent": config.DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
            resp = client.get(url)
            return resp.text, resp.status_code, None
    except Exception as e:
        return None, 0, str(e)

def fetch_playwright_mode(url: str, timeout: int = 15000) -> Tuple[Optional[str], int, Optional[str]]:
    """
    Mode B: Headless stealth browser dynamic scraping using Playwright.
    """
    try:
        page = StealthyFetcher.fetch(
            url,
            headless=True,
            timeout=timeout,
            network_idle=False
        )
        if page:
            html = extract_response_html(page)
            status = getattr(page, 'status', 200) or 200
            return html, status, None
        return None, 0, "StealthyFetcher returned empty page"
    except Exception as e:
        return None, 0, str(e)

def adaptive_scrape(url: str, force_browser: bool = False, max_retries: int = 2) -> ScrapeResult:
    """
    Intelligent dual-mode scraper with automatic detection, retry logic,
    and fallback mechanism.
    
    Workflow:
    1. Validate safe URL (SSRF check).
    2. Try HTTP mode (Mode A).
    3. Analyze HTML for meaningful content, anti-bot challenge, or SPA markers.
    4. Automatically upgrade to Playwright (Mode B) if needed.
    5. Return complete ScrapeResult with mode and fallback metadata.
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

    # If force_browser requested explicitly
    if force_browser:
        html, status, err = fetch_playwright_mode(clean_url, timeout=config.PLAYWRIGHT_TIMEOUT_MS)
        if html:
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

    # Step 2: Mode A (HTTP) with retry logic
    last_err = None
    http_html = None
    http_status = 0

    for attempt in range(1, max_retries + 1):
        http_html, http_status, last_err = fetch_http_mode(clean_url, timeout=config.HTTP_TIMEOUT_SECONDS)
        if http_html:
            break
        time.sleep(attempt * 0.5)

    # Step 3: Evaluate HTTP response
    if http_html:
        adaptor = Adaptor(http_html)
        body_text = adaptor.get_all_text(ignore_tags=('script', 'style'))

        is_challenge = is_anti_bot_challenge(http_html, http_status)
        is_spa = requires_dynamic_rendering(http_html, body_text)

        # Step 4: If server-rendered content is complete, return HTTP result immediately!
        if not is_challenge and not is_spa:
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
