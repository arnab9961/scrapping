import re
import csv
import sys
import json
from urllib.parse import urlparse, urljoin, unquote
from scrapling.fetchers import Fetcher, StealthyFetcher

# Priority keywords for discovering leads and directories
PRIORITY_KEYWORDS = [
    # Business & Directory listings
    'description', 'industry', 'category', 'subcategory', 'type', 
    'listing', 'companies', 'company', 'business', 'catalog', 'store', 
    'services', 'cityguide', 'city', 'location',
    # People & Team pages
    'executives', 'executive', 'governors', 'director', 'deputygovernor',
    'contact', 'about', 'team', 'staff', 'leadership', 
    'people', 'directory', 'management', 'board', 'member', 'profile', 
    'doctor', 'lawyer', 'agent', 'officer', 'faculty',
    # Pagination
    'page', 'p='
]

# File extensions to ignore
IGNORE_EXTENSIONS = (
    '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', 
    '.zip', '.rar', '.doc', '.docx', '.xls', '.xlsx', '.ppt', 
    '.pptx', '.mp3', '.mp4', '.avi', '.mov', '.css', '.js'
)

# Words that are labels, not names
LABEL_WORDS = {
    'name', 'name:', 'designation', 'designation:', 'phone', 'phone:', 
    'phone (office):', 'mobile', 'mobile:', 'email', 'email:', 'contact', 
    'contact:', 'address', 'address:', 'call', 'details', 'view', 
    'read more', 'profile', 'home', 'back', 'next', 'previous'
}

def clean_text(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip()

def is_bot_challenge(page):
    """Detect if response is an anti-bot challenge (F5 BIG-IP, Cloudflare, etc.)."""
    body = getattr(page, 'text', '') or ''
    raw = getattr(page, 'body', b'') or getattr(page, '_raw_body', b'') or b''
    raw_str = raw.decode('utf-8', errors='ignore') if isinstance(raw, bytes) else str(raw)
    
    if len(body.strip()) < 50:
        return True
    if any(sig in raw_str for sig in ['bobcmn', 'TSPD_', 'support id is', 'What code is in the image', 'cf-browser-verification']):
        return True
    return False

def smart_fetch(url, force_browser=False):
    """
    Smart fetcher:
    Tries fast HTTP first. If the website triggers bot-protection (like Bangladesh Bank's F5 firewall),
    it automatically switches to StealthyFetcher (Headless Chrome).
    """
    if force_browser:
        return StealthyFetcher.fetch(url, headless=True, network_idle=True), True

    try:
        page = Fetcher.get(url, impersonate='chrome')
        if is_bot_challenge(page):
            print("   🛡️ Anti-bot firewall detected. Switching to Stealth Browser...")
            page = StealthyFetcher.fetch(url, headless=True, network_idle=True)
            return page, True
        return page, False
    except Exception:
        print("   🛡️ HTTP error. Switching to Stealth Browser...")
        page = StealthyFetcher.fetch(url, headless=True, network_idle=True)
        return page, True

def is_valid_internal_link(base_domain, url):
    """Ensure the link stays within the target website domain."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
            
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        clean_base = base_domain.lower()
        if clean_base.startswith('www.'):
            clean_base = clean_base[4:]
            
        if domain != clean_base and not domain.endswith('.' + clean_base):
            return False
            
        path = parsed.path.lower()
        if any(path.endswith(ext) for ext in IGNORE_EXTENSIONS):
            return False
            
        return True
    except Exception:
        return False

def link_priority(url):
    """Score links so company profiles and directory pages are visited first."""
    url_lower = url.lower()
    score = 0
    
    # Direct profiles
    if any(p in url_lower for p in ['/description/', '/company/', '/profile/', '/listing/', '/executives', '/deputygovernor']):
        score += 50
    # Directory categories
    elif any(p in url_lower for p in ['/industry/', '/category/', '/type/', '/cityguide/']):
        score += 25
    # Standard contact/about
    elif any(p in url_lower for p in ['/contact', '/about', '/team', '/directory']):
        score += 20
        
    for kw in PRIORITY_KEYWORDS:
        if kw in url_lower:
            score += 5
            
    return score

def extract_emails(text, html_str=""):
    """Extract and validate clean email addresses."""
    combined = f"{text} {html_str}"
    raw = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', combined)
    mailto = re.findall(r'mailto:([^"?\s>]+)', combined, re.IGNORECASE)
    all_found = raw + [unquote(m) for m in mailto]
    
    valid = set()
    for e in all_found:
        e = e.strip().lower().rstrip('.,;:)]}')
        if any(e.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.css', '.js']):
            continue
        if any(x in e for x in ['example.com', 'yourname@', 'domain.com', 'email@', 'sentry', 'wixpress']):
            continue
        if len(e) >= 6 and '.' in e.split('@')[-1]:
            valid.add(e)
    return sorted(list(valid))

def extract_phones(text, html_str=""):
    """Extract telephone/mobile numbers including BD and international formats."""
    combined = f"{text} {html_str}"
    phones = []
    
    # 1. tel: links
    tel_links = re.findall(r'tel:([^"?\s>]+)', combined, re.IGNORECASE)
    phones.extend([clean_text(unquote(p)) for p in tel_links])
    
    # 2. Labeled numbers
    labeled = re.findall(r'(?:Mobile|Phone|Call|Tel|Hotline|Cell|WhatsApp)[\s:]*([+\d\s\-(),Off.]{7,35})', text, re.IGNORECASE)
    for p in labeled:
        phones.append(p.strip())

    # 3. Bangladesh 11-digit mobile format (013-019)
    bd_pattern = r'(?:\+?880[\s.-]?|0)1[3-9](?:[\s.-]?\d){8}'
    phones.extend(re.findall(bd_pattern, text))
    
    # 4. Standard Landline / Int'l numbers (7 to 15 digits)
    intl_pattern = r'(?:(?:\+|00)\d{1,3}[\s.-]?)?(?:\(?\d{2,5}\)?[\s.-]?)?\d{3,5}[\s.-]?\d{3,7}'
    for m in re.findall(intl_pattern, text):
        digits = re.sub(r'\D', '', m)
        if 7 <= len(digits) <= 15 and len(set(digits)) > 2:
            phones.append(m)

    # Clean and deduplicate
    seen = set()
    cleaned = []
    for p in phones:
        digits = re.sub(r'\D', '', p)
        if digits not in seen and 7 <= len(digits) <= 15:
            seen.add(digits)
            cleaned.append(clean_text(p))
            
    return cleaned

def extract_website(text):
    match = re.search(r'Website:\s*(https?://[^\s]+)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return "N/A"

def extract_address(text):
    match = re.search(r'Address:\s*([^\n\r]+)', text, re.IGNORECASE)
    if match:
        addr = clean_text(match.group(1))
        if len(addr) > 5 and not addr.startswith(('http', 'Call', 'Mobile')):
            return addr
    return "N/A"

def extract_from_json_ld(html_str, page_url):
    leads = []
    scripts = re.findall(r'<script[^>]*type=[\'"]application/ld\+json[\'"][^>]*>(.*?)</script>', html_str, re.DOTALL | re.IGNORECASE)
    for script in scripts:
        try:
            data = json.loads(script.strip())
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                sub_items = item.get('@graph', [item])
                for sub in sub_items:
                    if not isinstance(sub, dict):
                        continue
                    name = sub.get('name') or sub.get('legalName')
                    tel = sub.get('telephone') or sub.get('phone')
                    email = sub.get('email')
                    web = sub.get('url') or 'N/A'
                    if email or tel:
                        leads.append({
                            'Name': clean_text(name) or 'N/A',
                            'Phone': clean_text(tel) or 'N/A',
                            'Email': clean_text(email) or 'N/A',
                            'Website': clean_text(web),
                            'Address': 'N/A',
                            'Page_URL': page_url
                        })
        except Exception:
            continue
    return leads

def extract_leads_from_page(page, url):
    """Extracts leads (Name, Phone, Email, Website, Address) from any page structure."""
    body_text = page.get_all_text(ignore_tags=('script', 'style'))
    html_content = getattr(page, '_raw_body', '')
    if isinstance(html_content, bytes):
        html_content = html_content.decode('utf-8', errors='ignore')
    elif not html_content:
        html_content = page.text if hasattr(page, 'text') else str(page)

    page_leads = []

    # 1. Schema.org JSON-LD
    json_leads = extract_from_json_ld(html_content, url)
    if json_leads:
        page_leads.extend(json_leads)

    # 2. Check for structured table/card items (e.g. Bangladesh Bank, Bootstrap cards)
    card_selectors = ['tr.d-flex', 'table tbody tr', '.card', '.profile-card', '.directory-item', '.member', '.company-item']
    for sel in card_selectors:
        elements = page.css(sel)
        if len(elements) >= 2:
            for el in elements:
                c_text = el.get_all_text(ignore_tags=('script', 'style'))
                c_html = str(el)
                c_emails = extract_emails(c_text, c_html)
                c_phones = extract_phones(c_text, c_html)
                
                # Check for hidden/protected email (Bangladesh Bank onselectstart div)
                div_email = el.css('div[onselectstart]::text').get()
                if div_email and '@' in div_email and div_email.strip() not in c_emails:
                    c_emails.append(div_email.strip())

                if c_emails or c_phones:
                    # Smart name extraction: avoid "Name:", "Designation:", etc.
                    name = None
                    
                    # Special check: font tags (common in government/table sites like BB)
                    font_texts = [clean_text(t) for t in el.css('font::text').getall() if clean_text(t)]
                    for i, t in enumerate(font_texts):
                        if 'name' in t.lower() and i + 1 < len(font_texts):
                            candidate = font_texts[i + 1]
                            if candidate.lower() not in LABEL_WORDS:
                                name = candidate
                                break
                                
                    if not name:
                        for name_sel in ['h1::text', 'h2::text', 'h3::text', 'h4::text', 'strong::text', 'font::text', 'a::text']:
                            for txt in el.css(name_sel).getall():
                                cleaned = clean_text(txt)
                                if cleaned and cleaned.lower() not in LABEL_WORDS and len(cleaned) > 2:
                                    name = cleaned
                                    break
                            if name:
                                break

                    page_leads.append({
                        'Name': name or 'N/A',
                        'Phone': ', '.join(c_phones) if c_phones else 'N/A',
                        'Email': ', '.join(c_emails) if c_emails else 'N/A',
                        'Website': 'N/A',
                        'Address': 'N/A',
                        'Page_URL': url
                    })
            if page_leads:
                break

    # 3. Single business profile page fallback (e.g. bdyellowpages.net/description/...)
    if not page_leads:
        emails = extract_emails(body_text, html_content)
        phones = extract_phones(body_text, html_content)
        
        h1 = page.css('h1::text').get()
        title = page.css('title::text').get()
        name = clean_text(h1) or clean_text(title) or 'N/A'
        
        if ' - ' in name:
            name = name.split(' - ')[0].strip()
        elif ' | ' in name:
            name = name.split(' | ')[0].strip()

        website = extract_website(body_text)
        address = extract_address(body_text)

        if emails or phones:
            page_leads.append({
                'Name': name,
                'Phone': ', '.join(phones) if phones else 'N/A',
                'Email': ', '.join(emails) if emails else 'N/A',
                'Website': website,
                'Address': address,
                'Page_URL': url
            })

    return page_leads

def crawl_and_extract_leads(start_url, max_pages=100, force_browser=False):
    """
    Crawls pages starting from `start_url`, automatically prioritizing 
    companies, directories, industries, and categories.
    """
    parsed_start = urlparse(start_url)
    base_domain = parsed_start.netloc

    print("=" * 70)
    print(f"🚀 Multi-Page Lead Crawler Started")
    print(f"🌐 Domain       : {base_domain}")
    print(f"🔗 Starting URL : {start_url}")
    print(f"📑 Page Limit   : {max_pages} pages")
    print("=" * 70)

    visited = set()
    queue = [(100, start_url)]

    all_leads = []
    seen_contacts = set()
    pages_visited_count = 0
    current_force_browser = force_browser

    while queue and pages_visited_count < max_pages:
        queue.sort(key=lambda x: x[0], reverse=True)
        _, current_url = queue.pop(0)

        clean_url = current_url.split('#')[0].rstrip('/')
        if clean_url in visited:
            continue

        visited.add(clean_url)
        pages_visited_count += 1

        print(f"\n[{pages_visited_count}/{max_pages}] Visiting: {current_url}")

        try:
            page, used_browser = smart_fetch(current_url, force_browser=current_force_browser)
            if used_browser:
                current_force_browser = True # Keep using browser for this domain
        except Exception as e:
            print(f"   ⚠️  Could not fetch: {e}")
            continue

        # Extract leads from page
        leads = extract_leads_from_page(page, current_url)
        new_count = 0

        for lead in leads:
            sig = f"{lead['Phone']}|{lead['Email']}"
            if sig != "N/A|N/A" and sig not in seen_contacts:
                seen_contacts.add(sig)
                all_leads.append(lead)
                new_count += 1
                print(f"   🎯 Lead: {lead['Name']}")
                if lead['Phone'] != 'N/A':
                    print(f"      📞 Phone   : {lead['Phone']}")
                if lead['Email'] != 'N/A':
                    print(f"      📧 Email   : {lead['Email']}")
                if lead.get('Website') and lead['Website'] != 'N/A':
                    print(f"      🌐 Website : {lead['Website']}")
                if lead.get('Address') and lead['Address'] != 'N/A':
                    print(f"      📍 Address : {lead['Address']}")

        if new_count == 0:
            print("   ℹ️  (No new leads on this page, queued internal links)")

        # Collect internal links
        for a_tag in page.css('a'):
            href = a_tag.attrib.get('href')
            if href:
                full_url = urljoin(current_url, href)
                full_clean = full_url.split('#')[0].rstrip('/')
                if full_clean not in visited and is_valid_internal_link(base_domain, full_url):
                    score = link_priority(full_url)
                    if not any(item[1] == full_url for item in queue):
                        queue.append((score, full_url))

    # Save to CSV
    csv_file = "all_leads.csv"
    fieldnames = ['Name', 'Phone', 'Email', 'Website', 'Address', 'Page_URL']
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_leads)

    print("\n" + "=" * 70)
    print(f"🏁 Finished Crawling! Visited {pages_visited_count} pages.")
    print(f"🎉 Total Unique Leads Gathered: {len(all_leads)}")
    print(f"💾 File updated: '{csv_file}'")
    print("=" * 70)

    return all_leads

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1].strip()
    else:
        target = input("Enter website or category URL to crawl: ").strip()

    if not target.startswith(('http://', 'https://')):
        target = "https://" + target

    crawl_and_extract_leads(target, max_pages=50)
