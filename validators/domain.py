import urllib.parse
import re
from typing import Optional, Tuple
from tld import get_fld
from tld.exceptions import TldDomainNotFound, TldBadUrl

TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'fbclid', 'gclid', 'gclsrc', 'dclid', 'zanpid', 'msclkid', 'mc_cid', 'mc_eid',
    '_ga', '_gl', 'ref', 'source', 'campaign', 'affiliate', 'sp_ref'
}

def clean_url(url: str) -> str:
    """Strips whitespace and normalizes scheme."""
    if not url:
        return ""
    cleaned = str(url).strip()
    if not cleaned.startswith(('http://', 'https://')):
        cleaned = 'https://' + cleaned
    return cleaned

def normalize_url(url: str, strip_tracking: bool = True) -> str:
    """
    Normalizes a URL by:
    1. Ensuring valid HTTP/HTTPS scheme.
    2. Lowercasing scheme and netloc.
    3. Stripping marketing tracking parameters (utm_*, fbclid, etc.).
    4. Stripping fragments (#section).
    5. Stripping redundant trailing slashes from domain root.
    """
    if not url:
        return ""

    target = clean_url(url)
    try:
        parsed = urllib.parse.urlparse(target)
    except Exception:
        return target

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"

    # Strip default ports
    if netloc.endswith(':80') and scheme == 'http':
        netloc = netloc[:-3]
    elif netloc.endswith(':443') and scheme == 'https':
        netloc = netloc[:-4]

    # Filter query parameters
    query_str = ""
    if parsed.query:
        if strip_tracking:
            q_dict = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
            filtered = {k: v for k, v in q_dict.items() if k.lower() not in TRACKING_PARAMS}
            if filtered:
                query_str = urllib.parse.urlencode(filtered, doseq=True)
        else:
            query_str = parsed.query

    # Reconstruct normalized URL
    result = f"{scheme}://{netloc}{path}"
    if query_str:
        result += f"?{query_str}"

    # Clean root URL trailing slash (e.g. https://example.com/ -> https://example.com)
    if result.endswith('/') and path == '/':
        result = result[:-1]

    return result

def get_canonical_domain(url: str) -> str:
    """
    Extracts the root registered domain (e.g. 'example.com', 'site.co.uk')
    using TLD (Top Level Domain) parser with fallback to hostname regex.
    """
    if not url or str(url).strip().lower() in ('n/a', 'none', 'null', ''):
        return ""

    target = clean_url(url)
    try:
        fld = get_fld(target, fail_silently=True)
        if fld:
            return fld.lower()
    except Exception:
        pass

    try:
        parsed = urllib.parse.urlparse(target)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        host = netloc.split(':')[0]
        return host
    except Exception:
        return ""

def is_valid_domain(domain: str) -> bool:
    """Validates domain format."""
    if not domain or len(domain) < 3 or len(domain) > 253:
        return False
    if '..' in domain or domain.startswith('.') or domain.endswith('.'):
        return False
    pattern = r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    return bool(re.match(pattern, domain))
