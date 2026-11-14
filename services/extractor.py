import re
import json
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
from validators.phone import normalize_bd_phone, extract_and_normalize_bd_phones

ORG_KEYWORDS = {
    'ltd', 'limited', 'inc', 'corp', 'corporation', 'llc', 'agency', 'agencies',
    'travel', 'travels', 'tour', 'tours', 'holidays', 'tourism', 'aviation',
    'airlines', 'hotel', 'resort', 'club', 'association', 'bank', 'enterprise',
    'enterprises', 'solutions', 'services', 'group', 'company', 'co', 'pvt',
    'private', 'international', 'hospital', 'clinic', 'college', 'university',
    'department', 'ministry', 'division', 'office', 'foundation', 'authority',
    'bureau', 'federation', 'chamber', 'society', 'network', 'center', 'centre'
}

PERSON_PREFIXES = [
    r'\b(?:mr|mrs|ms|dr|engr|md|mohammad|mohammed|prof|professor|advocate|barrister|sheikh|syed|haji|alhaj|capt|captain)\b\.?'
]

DESIGNATIONS = [
    'managing director', 'director', 'deputy director', 'executive director',
    'chief executive officer', 'ceo', 'founder', 'co-founder', 'proprietor', 'owner',
    'general manager', 'gm', 'head of hr', 'hr manager', 'admin manager',
    'event manager', 'tour coordinator', 'tour manager', 'branch manager',
    'president', 'vice president', 'secretary general', 'secretary', 'chairman',
    'contact person', 'representative', 'executive', 'officer', 'governor'
]

LABEL_WORDS = {
    'name', 'name:', 'designation', 'designation:', 'phone', 'phone:',
    'phone (office):', 'mobile', 'mobile:', 'email', 'email:', 'contact',
    'contact:', 'address', 'address:', 'call', 'details', 'view',
    'read more', 'profile', 'home', 'back', 'next', 'previous', 'about',
    'contact us', 'about us', 'organization', 'company', 'agency'
}

TRAILING_JUNK_WORDS = {
    'phone', 'email', 'managing', 'director', 'flat', 'road', 'house', 'plot',
    'contact', 'cell', 'tel', 'mobile', 'office', 'avenue', 'block', 'sector',
    'profile', 'details', 'executive', 'officer', 'owner', 'proprietor'
}

def clean_text(text: Any) -> str:
    """Normalize whitespace and strip text."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip()

def clean_person_name(name: str) -> str:
    """Removes trailing address, phone, or UI words from a candidate person name."""
    if not name:
        return ""
    tokens = name.split()
    while tokens and tokens[-1].lower() in TRAILING_JUNK_WORDS:
        tokens.pop()
    return ' '.join(tokens).strip()

def is_person_name(name: str) -> bool:
    """Checks whether a candidate string resembles an individual human name."""
    clean = clean_person_name(name)
    if not clean or len(clean) < 3 or len(clean) > 60:
        return False
    lower = clean.lower()
    words = re.findall(r'[a-zA-Z]+', lower)
    if not words or len(words) < 2:
        return False
    if any(w in ORG_KEYWORDS for w in words):
        return False
    if any(re.search(pat, lower) for pat in PERSON_PREFIXES):
        return True
    tokens = clean.split()
    if 2 <= len(tokens) <= 5:
        if all(t[0].isupper() for t in tokens if t.isalpha()):
            return True
    return False

def extract_meta_tags(soup: BeautifulSoup) -> Dict[str, str]:
    """Extracts OpenGraph, Twitter, and standard meta tag properties."""
    meta = {}
    for tag in soup.find_all('meta'):
        prop = tag.get('property') or tag.get('name') or ''
        content = tag.get('content') or ''
        if prop and content:
            meta[prop.lower()] = clean_text(content)
    return meta

def extract_json_ld(soup: BeautifulSoup, page_url: str) -> List[Dict[str, Any]]:
    """Extracts Schema.org JSON-LD structured data for Organizations, Businesses, and Persons."""
    leads = []
    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        try:
            content = script.string
            if not content:
                continue
            data = json.loads(content.strip())
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                sub_items = item.get('@graph', [item])
                for sub in sub_items:
                    if not isinstance(sub, dict):
                        continue
                    types = sub.get('@type', '')
                    type_str = str(types).lower()
                    
                    name = clean_text(sub.get('name') or sub.get('legalName'))
                    tel = clean_text(sub.get('telephone') or sub.get('phone'))
                    email = clean_text(sub.get('email'))
                    web = clean_text(sub.get('url') or page_url)
                    job = clean_text(sub.get('jobTitle') or sub.get('roleName'))
                    
                    address_data = sub.get('address')
                    addr_str = "N/A"
                    if isinstance(address_data, dict):
                        street = address_data.get('streetAddress', '')
                        locality = address_data.get('addressLocality', '')
                        country = address_data.get('addressCountry', 'Bangladesh')
                        addr_str = f"{street}, {locality}, {country}".strip(', ')
                    elif isinstance(address_data, str):
                        addr_str = address_data

                    if tel or email:
                        is_val, norm_tel, _ = normalize_bd_phone(tel)
                        p_name = name if is_person_name(name) else "Contact Person"
                        b_name = name if not is_person_name(name) else (sub.get('worksFor', {}).get('name') if isinstance(sub.get('worksFor'), dict) else "Business")

                        leads.append({
                            'business_name': b_name or "Business",
                            'contact_person': p_name,
                            'designation': job or ("Managing Director" if is_person_name(name) else "Representative"),
                            'phone': norm_tel if is_val else (tel or "N/A"),
                            'email': email or "N/A",
                            'website': web,
                            'address': addr_str or "N/A",
                            'source_url': page_url,
                            'extraction_technique': 'json_ld'
                        })
        except Exception:
            continue
    return leads

def extract_semantic_links(soup: BeautifulSoup) -> Tuple[List[str], List[str]]:
    """Extracts tel: and mailto: links directly from DOM without regex bugs."""
    phones = []
    emails = []
    seen_phones = set()
    seen_emails = set()

    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if href.lower().startswith('tel:'):
            raw_phone = href[4:].split('?')[0].strip()
            is_val, norm_p, _ = normalize_bd_phone(raw_phone)
            val = norm_p if is_val else raw_phone
            if val not in seen_phones:
                seen_phones.add(val)
                phones.append(val)
        elif href.lower().startswith('mailto:'):
            raw_email = href[7:].split('?')[0].strip().lower()
            if '@' in raw_email and raw_email not in seen_emails:
                seen_emails.add(raw_email)
                emails.append(raw_email)

    return phones, emails

def extract_leads_from_html(
    html: str,
    page_url: str,
    default_category: str = "Hospitality & Tourism",
    default_city: str = "Dhaka"
) -> List[Dict[str, Any]]:
    """
    Advanced multi-technique extraction pipeline.
    Prioritizes structured JSON-LD data, meta tags, and semantic HTML elements,
    falling back to table/card structures and visible page text.
    """
    if not html or not html.strip():
        return []

    soup = BeautifulSoup(html, 'html.parser')
    leads: List[Dict[str, Any]] = []

    # Derive site organization/brand name
    meta = extract_meta_tags(soup)
    site_title = meta.get('og:site_name') or meta.get('og:title') or ''
    if not site_title and soup.title:
        site_title = clean_text(soup.title.string)

    for sep in [' - ', ' | ', ' – ', ' : ']:
        if sep in site_title:
            site_title = site_title.split(sep)[0].strip()

    try:
        parsed_url = urllib.parse.urlparse(page_url)
        domain_name = parsed_url.netloc.lower().replace('www.', '').split('.')[0].title()
    except Exception:
        domain_name = "Business Organization"

    primary_org = site_title if site_title and len(site_title) < 60 else domain_name

    # 1. Structured JSON-LD extraction
    json_leads = extract_json_ld(soup, page_url)
    if json_leads:
        for jl in json_leads:
            jl['industry'] = default_category
            jl['city'] = default_city
            leads.append(jl)

    # 2. Extract semantic tel: and mailto: links
    semantic_phones, semantic_emails = extract_semantic_links(soup)

    # 3. Table and Profile Card parsing
    card_elements = soup.select('tr.d-flex, table tbody tr, .card, .profile-card, .directory-item, .member, .company-item, .executive-card')
    if card_elements:
        for el in card_elements:
            el_text = clean_text(el.get_text())
            el_html = str(el)

            # Extract phones & emails for this card
            card_phones = extract_and_normalize_bd_phones(el_text)
            card_emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', el_text)
            
            # Check for tel: or mailto: inside the card
            sub_soup = BeautifulSoup(el_html, 'html.parser')
            sub_phones, sub_emails = extract_semantic_links(sub_soup)
            
            all_phones = list(dict.fromkeys(card_phones + sub_phones))
            all_emails = list(dict.fromkeys([e.lower() for e in card_emails + sub_emails]))

            if all_phones or all_emails:
                cand_person = None
                cand_role = None
                cand_org = primary_org

                # Check headings or bold texts
                for heading in el.find_all(['h1', 'h2', 'h3', 'h4', 'strong', 'font']):
                    htext = clean_text(heading.get_text())
                    if htext and htext.lower() not in LABEL_WORDS and len(htext) > 3:
                        if is_person_name(htext):
                            cand_person = clean_person_name(htext)
                            break
                        elif not cand_org or cand_org == primary_org:
                            cand_org = htext

                # Check for designations
                for d in DESIGNATIONS:
                    if re.search(r'\b' + re.escape(d) + r'\b', el_text, re.IGNORECASE):
                        cand_role = d.title()
                        break

                p_name = cand_person or "Contact Person"
                role = cand_role or "Executive / Decision Maker"
                phone_str = all_phones[0] if all_phones else "N/A"
                email_str = all_emails[0] if all_emails else "N/A"

                leads.append({
                    'business_name': cand_org or primary_org,
                    'contact_person': p_name,
                    'designation': role,
                    'industry': default_category,
                    'phone': phone_str,
                    'email': email_str,
                    'website': page_url,
                    'address': default_city,
                    'city': default_city,
                    'country': "Bangladesh",
                    'source_url': page_url,
                    'extraction_technique': 'structured_cards'
                })

    # 4. Fallback to general page text if no structured leads discovered
    if not leads:
        all_text = clean_text(soup.get_text())
        text_phones = extract_and_normalize_bd_phones(all_text)
        text_emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', all_text)

        combined_phones = list(dict.fromkeys(semantic_phones + text_phones))
        combined_emails = list(dict.fromkeys(semantic_emails + [e.lower() for e in text_emails]))

        if combined_phones or combined_emails:
            detected_person = None
            detected_role = None

            role_patterns = [
                r'(?:Proprietor|Managing Director|MD|CEO|Director|Contact Person|Representative|Manager|Founder|Owner)\s*[:\-–]\s*([A-Z][a-zA-Z\.\s]{3,35})',
                r'\b(Md\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b',
                r'\b(Dr\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b',
                r'\b(Mohammad\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b'
            ]
            for pat in role_patterns:
                m = re.search(pat, all_text)
                if m:
                    cand = clean_text(m.group(1))
                    if is_person_name(cand):
                        detected_person = clean_person_name(cand)
                        break

            for d in DESIGNATIONS:
                if re.search(r'\b' + re.escape(d) + r'\b', all_text, re.IGNORECASE):
                    detected_role = d.title()
                    break

            phone_str = combined_phones[0] if combined_phones else "N/A"
            email_str = combined_emails[0] if combined_emails else "N/A"

            leads.append({
                'business_name': primary_org,
                'contact_person': detected_person or "Contact Person",
                'designation': detected_role or "Representative",
                'industry': default_category,
                'phone': phone_str,
                'email': email_str,
                'website': page_url,
                'address': default_city,
                'city': default_city,
                'country': "Bangladesh",
                'source_url': page_url,
                'extraction_technique': 'page_text'
            })

    return leads
