"""
Backward-compatible CLI and contact scraping wrapper for Sunset Group.
Consolidates with services.extractor and services.scraper.
"""
import sys
from typing import List, Dict, Any, Tuple
from services.scraper import adaptive_scrape
from services.extractor import (
    extract_leads_from_html,
    is_person_name,
    clean_person_name,
    clean_text,
    DESIGNATIONS,
    ORG_KEYWORDS,
    LABEL_WORDS
)
from validators.phone import normalize_bd_phone

def smart_fetch(url: str, force_browser: bool = False, timeout: int = 8000) -> Tuple[Any, bool]:
    """Backward-compatible fetcher wrapping adaptive_scrape."""
    res = adaptive_scrape(url, force_browser=force_browser)
    used_browser = (res.scraping_mode == "playwright")
    return res.page_adaptor, used_browser

def extract_leads_from_page(page, url: str) -> List[Dict[str, Any]]:
    """Backward-compatible extractor wrapping extract_leads_from_html."""
    if not page:
        return []
    html = page.text if hasattr(page, 'text') else str(page)
    raw_leads = extract_leads_from_html(html, url)
    
    # Map to legacy format expected by any older callers
    legacy_leads = []
    for l in raw_leads:
        legacy_leads.append({
            'Name': l.get('contact_person') or l.get('name') or 'N/A',
            'Designation': l.get('designation') or 'Executive',
            'Organization': l.get('business_name') or l.get('organization') or 'N/A',
            'Phone': l.get('phone') or 'N/A',
            'Email': l.get('email') or 'N/A',
            'Website': l.get('website') or url,
            'Address': l.get('address') or 'N/A',
            'Page_URL': url
        })
    return legacy_leads

if __name__ == "__main__":
    target = sys.argv[1].strip() if len(sys.argv) > 1 else input("Enter URL to scrape: ").strip()
    if not target.startswith(('http://', 'https://')):
        target = "https://" + target
    print(f"\n🔍 Scraping URL: {target}")
    res = adaptive_scrape(target)
    print(f"Scraping Mode: {res.scraping_mode} (Fallback used: {res.render_fallback_used})")
    results = extract_leads_from_html(res.html, target)
    print(f"\n✅ Found {len(results)} lead(s):\n")
    for idx, r in enumerate(results, 1):
        print(f"[{idx:02d}] 🏢 {r['business_name']} | 👤 {r['contact_person']} ({r['designation']}) | 📞 {r['phone']} | 📧 {r['email']}")
