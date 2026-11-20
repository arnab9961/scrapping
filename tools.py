import re
import time
import base64
import urllib.parse
import urllib.robotparser
from typing import List, Dict, Any, Tuple
import httpx
from scrapling.fetchers import Fetcher
from scrapling.parser import Adaptor

import config
from validators.url import validate_safe_url

_ROBOTS_CACHE: Dict[str, urllib.robotparser.RobotFileParser] = {}
_LAST_REQUEST_TIME: float = 0.0

SKIP_DOMAINS = {
    'whatsapp.com', 'facebook.com', 'fb.com', 'm.me', 'messenger.com',
    'twitter.com', 'x.com', 'instagram.com', 'tiktok.com', 'youtube.com',
    'google.com', 'bing.com', 'microsoft.com', 'apple.com', 'play.google.com',
    'pinterest.com', 't.me', 'reddit.com', 'wikipedia.org', 'wikimedia.org',
    'wikihow.com', 'britannica.com', 'github.com', 'quora.com',
    'tasteatlas.com', 'qr.io', 'zilita.com', 'linkedin.com',
    'stackoverflow.com', 'stackexchange.com', 'superuser.com',
    'scribd.com', 'slideshare.net', 'issuu.com', 'academia.edu', 'researchgate.net',
    'amazon.com', 'daraz.com.bd', 'bikroy.com'
}

def clean_text(text: Any) -> str:
    """Normalize whitespace and strip text."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip()

def is_skippable_url(url: str) -> bool:
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
        if not netloc:
            return True
        for d in SKIP_DOMAINS:
            if netloc == d or netloc.endswith('.' + d):
                return True
        return False
    except Exception:
        return False

def respect_rate_limit():
    """Polite rate limiting delay between outbound requests."""
    global _LAST_REQUEST_TIME
    elapsed = time.time() - _LAST_REQUEST_TIME
    if elapsed < config.RATE_LIMIT_DELAY:
        time.sleep(config.RATE_LIMIT_DELAY - elapsed)
    _LAST_REQUEST_TIME = time.time()

def check_robots_txt(url: str, user_agent: str = config.DEFAULT_USER_AGENT) -> bool:
    """Verifies if scraping this URL is permitted by the domain's robots.txt."""
    try:
        is_safe, clean_url, _ = validate_safe_url(url)
        if not is_safe:
            return False

        parsed = urllib.parse.urlparse(clean_url)
        if not parsed.netloc:
            return True
        domain_root = f"{parsed.scheme}://{parsed.netloc}"

        if domain_root in _ROBOTS_CACHE:
            rp = _ROBOTS_CACHE[domain_root]
        else:
            robots_url = f"{domain_root}/robots.txt"
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(robots_url)
            try:
                with httpx.Client(timeout=4.0, headers={"User-Agent": user_agent}) as client:
                    resp = client.get(robots_url)
                    if resp.status_code == 200:
                        rp.parse(resp.text.splitlines())
                    else:
                        rp.allow_all = True
            except Exception:
                rp.allow_all = True
            _ROBOTS_CACHE[domain_root] = rp

        return rp.can_fetch(user_agent, clean_url)
    except Exception:
        return True

def decode_bing_url(bing_ck_url: str) -> str:
    """Decodes destination URL from Bing redirect query parameter."""
    try:
        parsed = urllib.parse.urlparse(bing_ck_url)
        params = urllib.parse.parse_qs(parsed.query)
        u_param = params.get('u', [''])[0]
        if u_param and u_param.startswith('a1'):
            raw = u_param[2:]
            pad = len(raw) % 4
            if pad:
                raw += '=' * (4 - pad)
            return base64.b64decode(raw).decode('utf-8', errors='ignore')
    except Exception:
        pass
    return bing_ck_url

def search_via_brave(query: str, max_results: int = 20) -> List[Dict[str, str]]:
    """
    Searches via official Brave Search API as the primary lead discovery provider.
    Handles rate limits, timeouts, and empty search results gracefully.
    """
    if not config.has_brave_credentials():
        print("⚠️ Brave Search API key is not configured in environment.")
        return []

    try:
        respect_rate_limit()
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": config.BRAVE_SEARCH_API_KEY
        }
        # Brave Search API max count per request is 20
        count = min(max(1, max_results), 20)
        params = {
            "q": query,
            "count": count,
            "text_decorations": False,
            "search_lang": "en"
        }
        with httpx.Client(timeout=15.0, headers=headers) as client:
            resp = client.get("https://api.search.brave.com/res/v1/web/search", params=params)
            if resp.status_code == 200:
                data = resp.json()
                results = []
                web_results = data.get("web", {}).get("results", [])
                for item in web_results[:count]:
                    url = item.get("url", "").strip()
                    title = clean_text(item.get("title", ""))
                    snippet = clean_text(item.get("description", ""))
                    if url and not is_skippable_url(url):
                        results.append({
                            "title": title,
                            "url": url,
                            "snippet": snippet
                        })
                print(f"✅ Brave Search discovered {len(results)} candidate URLs for: '{query}'")
                return results
            elif resp.status_code == 429:
                print(f"⚠️ Brave Search rate limit reached (HTTP 429) for '{query}'")
            elif resp.status_code in (401, 403):
                print(f"❌ Brave Search API authentication failed (HTTP {resp.status_code}): Check BRAVE_SEARCH_API_KEY")
            else:
                print(f"⚠️ Brave Search API returned HTTP {resp.status_code}: {resp.text[:150]}")
    except httpx.TimeoutException:
        print(f"⚠️ Brave Search request timed out for query: '{query}'")
    except Exception as e:
        print(f"❌ Brave Search exception for query '{query}': {e}")
    return []

def search_fallback(query: str, max_results: int = 25) -> List[Dict[str, str]]:
    """Polite fallback search combining DuckDuckGo HTML & Scrapling Fetcher."""
    respect_rate_limit()
    results = []
    seen_urls = set()

    # 1. DuckDuckGo HTML Search
    try:
        ddg_headers = {
            'User-Agent': config.DEFAULT_USER_AGENT,
            'Accept-Language': 'en-US,en;q=0.9'
        }
        with httpx.Client(timeout=10.0, headers=ddg_headers, follow_redirects=True) as client:
            resp = client.post('https://html.duckduckgo.com/html/', data={'q': query})
            if resp.status_code == 200:
                page = Adaptor(resp.text)
                for r in page.css('.result'):
                    title = clean_text(r.css('.result__title a::text').get() or '')
                    raw_href = r.css('.result__title a::attr(href)').get() or ''
                    snippet = clean_text(r.css('.result__snippet::text').get() or '')

                    target_url = raw_href
                    if 'uddg=' in raw_href:
                        try:
                            parsed_u = urllib.parse.urlparse(raw_href)
                            target_url = urllib.parse.parse_qs(parsed_u.query).get('uddg', [raw_href])[0]
                        except Exception:
                            target_url = raw_href

                    if title and target_url.startswith(('http://', 'https://')):
                        if not is_skippable_url(target_url) and target_url not in seen_urls:
                            seen_urls.add(target_url)
                            results.append({
                                "title": title,
                                "url": target_url.strip(),
                                "snippet": snippet
                            })
                    if len(results) >= max_results:
                        break
    except Exception as e:
        print(f"⚠️ DuckDuckGo search error: {e}")

    # 2. Bing Search fallback if needed
    if not results:
        try:
            pages_to_crawl = max(1, (max_results - len(results) + 9) // 10)
            for p_idx in range(min(pages_to_crawl, 3)):
                first_param = p_idx * 10 + 1
                search_url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(query)}&first={first_param}"
                page = Fetcher.get(search_url, impersonate='chrome')
                items = page.css('li.b_algo')
                if not items:
                    break
                for li in items:
                    title = li.css('h2 a::text').get() or ''
                    raw_link = li.css('h2 a::attr(href)').get() or ''
                    snippet = li.css('.b_caption p::text').get() or li.css('.b_snippet::text').get() or ''
                    clean_link = decode_bing_url(raw_link) if "bing.com/ck/a" in raw_link else raw_link
                    if title.strip() and clean_link.startswith(('http://', 'https://')):
                        if not is_skippable_url(clean_link) and clean_link not in seen_urls:
                            seen_urls.add(clean_link)
                            results.append({
                                "title": clean_text(title),
                                "url": clean_link.strip(),
                                "snippet": clean_text(snippet)
                            })
                    if len(results) >= max_results:
                        break
                if len(results) >= max_results:
                    break
        except Exception as e:
            print(f"⚠️ Bing search error: {e}")

    return results

def web_search(query: str, max_results: int = 25) -> List[Dict[str, str]]:
    """
    Primary search query dispatcher.
    Brave Search API is the primary discovery provider.
    Falls back gracefully if Brave is unavailable or rate-limited.
    """
    print(f"\n🦁 [Brave Discovery] Query: '{query}' (Target: up to {max_results} results)")
    if config.has_brave_credentials():
        res = search_via_brave(query, max_results)
        if res:
            return res
        print("⚠️ Brave Search returned no results or rate-limited; attempting polite fallback...")
    else:
        print("⚠️ BRAVE_SEARCH_API_KEY not configured; using fallback search...")

    return search_fallback(query, max_results)

def extract_pagination_links(html: str, base_url: str, max_links: int = 15) -> List[str]:
    """Finds next-page and directory pagination links safely."""
    found = []
    seen = {base_url}
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        parsed_base = urllib.parse.urlparse(base_url)

        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            text = clean_text(a.get_text())

            is_pag = (
                re.search(r'(?:[?&](?:page|p|start|offset)=\d+|/page/\d+)', href, re.IGNORECASE) or
                text in {'Next', '>', '»', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'Next Page'}
            )
            if is_pag:
                full_url = urllib.parse.urljoin(base_url, href)
                parsed_target = urllib.parse.urlparse(full_url)
                if parsed_target.netloc == parsed_base.netloc and full_url not in seen:
                    seen.add(full_url)
                    found.append(full_url)
            if len(found) >= max_links:
                break
    except Exception:
        pass
    return found

def extract_contact_subpages(html: str, base_url: str, max_links: int = 3) -> List[str]:
    """
    Discovers contact, about, team, and executive subpages on the same domain
    to uncover direct decision-maker names and mobile numbers.
    """
    found = []
    seen = {base_url.rstrip('/')}
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        parsed_base = urllib.parse.urlparse(base_url)
        if not parsed_base.netloc:
            return []

        contact_patterns = [
            r'/(?:contact|contact-us|contactus|contact_us|get-in-touch|reach-us)\b',
            r'/(?:about|about-us|aboutus|about_us|who-we-are|company-profile)\b',
            r'/(?:team|our-team|management|leadership|board-of-directors|executives|key-personnel|members|directory)\b',
        ]

        # Prioritize matching links
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            text = clean_text(a.get_text()).lower()
            
            # Check href or anchor text
            matches_href = any(re.search(pat, href, re.IGNORECASE) for pat in contact_patterns)
            matches_text = any(t in text for t in ['contact us', 'contact', 'about us', 'about', 'our team', 'management', 'leadership', 'executives', 'directors'])
            
            if matches_href or matches_text:
                full_url = urllib.parse.urljoin(base_url, href).split('#')[0].rstrip('/')
                parsed_target = urllib.parse.urlparse(full_url)
                if parsed_target.netloc.lower() == parsed_base.netloc.lower() and full_url not in seen:
                    # Avoid non-html endpoints (pdf, jpg, etc.)
                    if not re.search(r'\.(?:pdf|png|jpg|jpeg|gif|svg|zip|docx?|xlsx?)$', parsed_target.path, re.IGNORECASE):
                        seen.add(full_url)
                        found.append(full_url)
            if len(found) >= max_links:
                break
    except Exception:
        pass
    return found

