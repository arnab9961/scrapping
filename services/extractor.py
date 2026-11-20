import re
import json
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
from validators.phone import normalize_bd_phone, extract_and_normalize_bd_phones

ORG_KEYWORDS = {
    # Business entities & suffixes
    'ltd', 'limited', 'inc', 'corp', 'corporation', 'llc', 'pvt', 'private',
    'co', 'company', 'group', 'holdings', 'holding', 'enterprise', 'enterprises',
    'solutions', 'services', 'ventures', 'capital', 'global', 'worldwide', 'international',
    # Engineering, Construction & Real Estate
    'engineer', 'engineers', 'engineering', 'builder', 'builders', 'building',
    'constructions', 'construction', 'properties', 'property', 'realtors', 'realtor',
    'real estate', 'developers', 'developer', 'development', 'architects', 'architecture',
    # Tech & Media
    'technology', 'technologies', 'tech', 'software', 'systems', 'digital', 'telecom',
    'telecommunications', 'network', 'networks', 'data', 'cyber', 'cloud', 'web', 'online',
    'portal', 'media', 'press', 'studio', 'advertising', 'agency', 'agencies',
    # Healthcare & Pharma
    'hospital', 'hospitals', 'clinic', 'clinics', 'diagnostic', 'diagnostics',
    'pharma', 'pharmaceuticals', 'pharmacy', 'medical', 'healthcare', 'lab', 'labs', 'laboratory',
    # Hospitality & Tourism
    'travel', 'travels', 'tour', 'tours', 'tourism', 'holidays', 'aviation',
    'airline', 'airlines', 'airways', 'hotel', 'hotels', 'resort', 'resorts',
    'retreat', 'retreats', 'motel', 'inn', 'suites', 'restaurant', 'cafe', 'catering',
    'convention', 'guest house', 'motels', 'cottage', 'cottages', 'palace',
    # Garments, Textile, Manufacturing & Trade
    'garments', 'garment', 'textile', 'textiles', 'apparel', 'apparels', 'fashion',
    'fabrics', 'knitwear', 'industries', 'industry', 'industrial', 'manufacturing',
    'manufacturers', 'mills', 'factory', 'logistics', 'shipping', 'freight', 'cargo',
    'courier', 'transport', 'traders', 'trading', 'trade', 'exports', 'export',
    'imports', 'import', 'bazaar', 'supermarket', 'mart', 'store', 'shop', 'retail', 'wholesale',
    # Finance, Banking & Corporate
    'bank', 'banking', 'insurance', 'financial', 'finance', 'investments', 'securities',
    'associates', 'consulting', 'consultants', 'advisory',
    # Education, Government & Institutions
    'school', 'college', 'university', 'academy', 'institute', 'institution',
    'department', 'ministry', 'division', 'authority', 'board', 'bureau', 'council',
    'commission', 'federation', 'chamber', 'association', 'society', 'foundation',
    'trust', 'union', 'committee', 'center', 'centre', 'club'
}

NON_PERSON_WORDS = {
    # Metadata, Licensing & Directory words
    'member', 'since', 'membership', 'id', 'license', 'licence', 'status', 'voter',
    'representative', 'validity', 'expiry', 'reg', 'registration', 'tin', 'bin',
    'code', 'sl', 'no', 'serial', 'type', 'category', 'date', 'incorporation',
    'inception', 'depz', 'aepz', 'air', 'icd', 'pangaon', 'ref', 'fee', 'dues',
    'voter/representative', 'representative/voter',
    # Address, Property & Location words
    'house', 'road', 'flat', 'plot', 'floor', 'room', 'block', 'sector', 'avenue',
    'bazar', 'mansion', 'bhaban', 'tower', 'plaza', 'building', 'centre', 'center',
    'dhaka', 'motijheel', 'gulshan', 'banani', 'uttara', 'dhanmondi', 'kamalapur',
    'paltan', 'chattogram', 'chittagong', 'sylhet', 'khulna', 'rajshahi', 'barishal',
    'bangladesh', 'address', 'location', 'office', 'branch', 'suite', 'lane',
    # UI & Web words
    'website', 'web', 'email', 'phone', 'mobile', 'tel', 'fax', 'call', 'details',
    'view', 'profile', 'home', 'back', 'next', 'previous', 'click', 'here', 'more',
    'read', 'about', 'contact', 'info', 'all', 'sorting'
}

PERSON_PREFIXES = [
    r'\b(?:mr|mrs|ms|miss|dr|engr|engineer|prof|professor|advocate|adv|barrister|sheikh|syed|haji|alhaj|al-haj|kazi|begum|capt|captain|md|mohammad|mohammed|muhammad|mohd|janab)\b\.?',
    r'(?:মোঃ|মো:|মোহাম্মদ|মুহাম্মদ|ড\.|ডঃ|ইঞ্জিঃ|ইঞ্জিনিয়ার|অধ্যাপক|ব্যরিস্টার|অ্যাডভোকেট|শেখ|সৈয়দ|কাজী|বেগম|হাজী|আলহাজ্ব|জনাব)'
]

BD_NAME_COMPONENTS = {
    'ahmed', 'akram', 'akter', 'alam', 'alamgir', 'ali', 'amin', 'aminul', 'anisur', 'anisuzzaman',
    'anwar', 'arif', 'ashraf', 'azad', 'azim', 'aziz', 'bakkar', 'bashar', 'basher', 'bapari', 'bahadur',
    'chowdhury', 'dewan', 'farhad', 'farhana', 'farid', 'habib', 'habibur', 'hafiz', 'haque', 'harun',
    'hasan', 'hassan', 'hasanuzzaman', 'helal', 'hossain', 'hossein', 'huda', 'humayun', 'ibrahim',
    'imtiaz', 'iqbal', 'isa', 'islam', 'jahangir', 'jahan', 'jalal', 'jamal', 'kabir', 'kamal',
    'kamrul', 'karim', 'kashem', 'khan', 'khaleque', 'khatun', 'khondoker', 'laskar', 'mahbub',
    'mahbubur', 'mahfuz', 'mahmood', 'mahmud', 'mamun', 'mannan', 'masud', 'masum', 'miah',
    'mir', 'mizanur', 'mofizur', 'molla', 'monir', 'moniruzzaman', 'morshed', 'mostafa', 'motalib',
    'motin', 'mojibur', 'mujibur', 'mukter', 'mukul', 'munir', 'nasir', 'nasiruddin', 'nayeem',
    'nazmul', 'nazrul', 'nur', 'nuralam', 'nurunnabi', 'palash', 'parvez', 'patwary', 'quader',
    'rafiq', 'rafiqul', 'rahim', 'rahman', 'rana', 'razzaque', 'rashed', 'rashid', 'rayhan', 'raza',
    'reza', 'rezaul', 'ripon', 'robin', 'roni', 'rony', 'rouf', 'roy', 'sabbir', 'sadeq', 'sadiq',
    'saha', 'saidur', 'saiful', 'salahuddin', 'salim', 'samad', 'sarker', 'sayeed', 'sayed',
    'selim', 'sen', 'shafiq', 'shafiqul', 'shah', 'shahid', 'shahidul', 'shahin', 'shahinur',
    'shahriar', 'shahjahan', 'shams', 'shamsul', 'sharif', 'siddique', 'sikder', 'sohel', 'sojib',
    'sultan', 'talukder', 'tapan', 'tareq', 'tariq', 'tanvir', 'tofazzal', 'tuhin', 'uddin',
    'zahid', 'zakir', 'zaman', 'zia', 'ziaur'
}

DESIGNATIONS = [
    'senior vice president', 'sr. vice president', 'sr vice president', 'first vice president',
    'vice president', 'president', 'deputy managing director', 'dmd', 'managing director', 'm/dir',
    'executive director', 'director', 'vice chairman', 'chairman', 'founder', 'co-founder',
    'proprietor', 'prop', 'owner', 'partner', 'general manager', 'gm', 'assistant general manager',
    'agm', 'head of corporate admin', 'head of hr', 'hr manager', 'admin manager',
    'head of sales', 'sales manager', 'marketing manager', 'event manager',
    'tour coordinator', 'tour manager', 'branch manager', 'operations manager',
    'secretary general', 'general secretary', 'joint secretary', 'secretary', 'treasurer',
    'chief executive officer', 'ceo', 'chief operating officer', 'coo', 'chief technology officer',
    'cto', 'chief financial officer', 'cfo', 'contact person', 'representative', 'executive',
    'officer', 'governor', 'manager', 'principal', 'advisor', 'consultant',
    'স্বত্বাধিকারী', 'ব্যবস্থাপনা পরিচালক', 'পরিচালক', 'চেয়ারম্যান', 'সভাপতি', 'সাধারণ সম্পাদক',
    'নির্বাহী কর্মকর্তা', 'প্রধান নির্বাহী', 'ব্যবস্থাপক'
]

LABEL_WORDS = {
    'name', 'name:', 'designation', 'designation:', 'phone', 'phone:',
    'phone (office):', 'mobile', 'mobile:', 'email', 'email:', 'contact',
    'contact:', 'address', 'address:', 'call', 'details', 'view',
    'read more', 'profile', 'home', 'back', 'next', 'previous', 'about',
    'contact us', 'about us', 'organization', 'company', 'agency',
    'sl', 'no', 'serial', 'action', 'status', 'website', 'web', 'fax',
    'image', 'photo', 'actions', 'edit', 'delete',
    'নাম', 'পদবী', 'ফোন', 'মোবাইল', 'ইমেইল', 'যোগাযোগ', 'ঠিকানা'
}

TRAILING_JUNK_WORDS = {
    'phone', 'email', 'flat', 'road', 'house', 'plot', 'contact', 'cell', 'tel',
    'mobile', 'office', 'avenue', 'block', 'sector', 'profile', 'details',
    'call', 'fax', 'website', 'web', 'since', 'id', 'license', 'voter',
    'ফোন', 'মোবাইল', 'ইমেইল', 'যোগাযোগ', 'ঠিকানা', 'নাম'
}

def clean_text(text: Any) -> str:
    """Normalize whitespace and strip text."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', str(text)).strip()

def clean_business_name(name: str) -> str:
    """Strips metadata, license numbers, RL numbers, and member IDs from business names."""
    if not name:
        return ""
    text = clean_text(name)
    # Strip suffixes like "RL No: 1034", "License: ...", "Member ID: ...", "Member Since: ..."
    text = re.sub(r'\s*(?:RL\s*No|License|Licence|Member\s*ID|Member\s*Since|Mem\s*No|Reg\s*No|TIN|BIN)\s*[:\-–—#]?\s*[\w\d\(\)/\-]+.*$', '', text, flags=re.IGNORECASE)
    # Strip any trailing role / contact leaks from multi-line text
    text = re.sub(r'\s*(?:Prop|M/Dir|Director|MD|Chairman|Managing\s*Director)\s*[:\-–—].*$', '', text, flags=re.IGNORECASE)
    # Strip address leaks
    text = re.sub(r'\s*(?:Flat\s*#|House\s*No|Road\s*No|Plot\s*#).*$', '', text, flags=re.IGNORECASE)
    return text.strip(' ,-–—|:;')

def split_name_and_designation(raw: str) -> Tuple[str, Optional[str]]:
    """
    Separates a person's name and designation if joined by comma, hyphen, parentheses, or pipe.
    E.g. 'Engr. Subhash Barua, Managing Director' -> ('Engr. Subhash Barua', 'Managing Director')
    E.g. 'Mr. Shafiqul Alam (Director)' -> ('Mr. Shafiqul Alam', 'Director')
    E.g. 'Mr. Abdur Razzaque Sr. Vice President' -> ('Mr. Abdur Razzaque', 'Sr. Vice President')
    """
    if not raw:
        return "", None

    text = clean_text(raw)
    detected_role = None

    # Check parentheses: e.g. "Md. Rafiq (CEO)" or "Atiqur Rahman (Voter)"
    m_paren = re.search(r'\(([^)]+)\)', text)
    if m_paren:
        inside = m_paren.group(1).strip()
        for d in DESIGNATIONS:
            if re.search(r'\b' + re.escape(d) + r'\b', inside, re.IGNORECASE):
                detected_role = d.title()
                break
        # Always strip non-name parentheticals like (Voter), (Representative), (Dir), (MD)
        text = text.replace(m_paren.group(0), '').strip()

    # Check multi-word designation suffixes: e.g. "Mr. Abdur Razzaque Sr. Vice President"
    for d in DESIGNATIONS:
        pat = r'^(.*?)\s+(' + re.escape(d) + r')$'
        m_suf = re.search(pat, text, re.IGNORECASE)
        if m_suf:
            p_cand = m_suf.group(1).strip()
            if is_person_name(p_cand):
                detected_role = d.title()
                text = p_cand
                break

    # Check delimiters: comma, hyphen, pipe, dash
    for sep in [',', ' - ', ' – ', ' — ', ' | ']:
        if sep in text:
            parts = text.split(sep, 1)
            p1, p2 = parts[0].strip(), parts[1].strip()
            # If second part contains a designation
            matched_d = None
            for d in DESIGNATIONS:
                if re.search(r'\b' + re.escape(d) + r'\b', p2, re.IGNORECASE):
                    matched_d = d.title()
                    break
            if matched_d:
                detected_role = matched_d
                text = p1
                break
            # If first part was the designation
            for d in DESIGNATIONS:
                if re.search(r'\b' + re.escape(d) + r'\b', p1, re.IGNORECASE):
                    matched_d = d.title()
                    break
            if matched_d:
                detected_role = matched_d
                text = p2
                break

    return text.strip(', -–—|'), detected_role

def clean_person_name(name: str) -> str:
    """Cleans prefixes, labels, trailing junk, and fixes punctuation spacing."""
    if not name:
        return ""

    text = clean_text(name)

    # Strip parenthetical annotations: (Voter), (Representative), (Dir), (MD)
    text = re.sub(r'\s*\((?:Voter|Representative|Member|Dir|MD|ICD|DEPZ)[^)]*\)', '', text, flags=re.IGNORECASE).strip()

    # Strip leading label prefixes: e.g. "Name: Md. Kamal", "Contact Person - Tanvir", "Prop: ..."
    text = re.sub(
        r'^(?:name|contact\s*person|contact\s*name|contact|person|key\s*person|full\s*name|executive|proprietor|prop|owner|managing\s*director|m/dir|director|ceo|md|chairman|president|নাম|যোগাযোগ|স্বত্বাধিকারী)[\s:\-–—|]+',
        '',
        text,
        flags=re.IGNORECASE
    ).strip()

    # Fix missing spaces after honorific dots: e.g. "Mr.Shamsul" -> "Mr. Shamsul", "Md.Kamrul" -> "Md. Kamrul"
    text = re.sub(r'\b(Mr|Mrs|Ms|Dr|Md|Mohd|Mohammad|Prof|Engr)\.([A-Za-z\u0980-\u09FF])', r'\1. \2', text)

    # Fix fused honorifics: e.g. "Mr.MdShahinur" -> "Mr. Md. Shahinur"
    text = re.sub(r'\b(Mr|Mrs|Ms|Dr|Engr|Prof)\.?(Md)([A-Z\u0980-\u09FF])', r'\1. \2. \3', text)

    # Clean fused trailing designations: e.g. "Nazmul AhmedManaging" -> "Nazmul Ahmed"
    for d in ['Managing', 'Director', 'President', 'Chairman', 'Proprietor']:
        text = re.sub(rf'([a-z]+)({d}\b)', r'\1 \2', text)

    # Clean punctuation tokens and trailing junk words
    tokens = text.split()
    while tokens and (tokens[-1].lower() in TRAILING_JUNK_WORDS or tokens[-1].lower() in [d.lower() for d in DESIGNATIONS]):
        tokens.pop()

    cleaned = ' '.join(tokens).strip(', -–—|:;#')
    return cleaned

def is_person_name(name: str) -> bool:
    """Strictly evaluates whether a candidate string resembles an individual human name."""
    clean = clean_person_name(name)
    if not clean or len(clean) < 3 or len(clean) > 60:
        return False

    clean_no_punct = re.sub(r'[,:\-–—|()#/\\0-9]', ' ', clean)
    clean_no_punct = clean_text(clean_no_punct)
    lower = clean_no_punct.lower()

    # Reject URLs, emails, phone digits
    if '@' in lower or 'http' in lower or '.com' in lower:
        return False

    # Check for Bengali script
    bengali_chars = re.findall(r'[\u0980-\u09FF]+', clean)
    if bengali_chars:
        b_words = [w for w in bengali_chars if w not in TRAILING_JUNK_WORDS and w not in LABEL_WORDS]
        if 1 <= len(b_words) <= 5:
            if any(re.search(pat, clean) for pat in PERSON_PREFIXES) or len(b_words) >= 2:
                return True
        return False

    words = re.findall(r'[a-zA-Z]+', lower)
    if not words or len(words) < 2:
        return False

    # REJECT if ANY word matches NON_PERSON_WORDS (addresses, metadata, UI labels)
    # E.g. "Member Since", "Member ID", "Kamalapur Bazar", "Flat Road", "License 17/13"
    if any(w in NON_PERSON_WORDS for w in words):
        return False

    # REJECT if ANY word matches an organization keyword (it's a company!)
    if any(w in ORG_KEYWORDS for w in words):
        return False

    # Check for person prefixes (Mr, Mrs, Dr, Engr, Md, Mohammad, etc.)
    if any(re.search(pat, lower) for pat in PERSON_PREFIXES):
        return True

    # Check for common Bangladeshi name components
    if any(w in BD_NAME_COMPONENTS for w in words):
        return True

    # Capitalized tokens: 2 to 5 words
    tokens = clean_no_punct.split()
    if 2 <= len(tokens) <= 5:
        alpha_tokens = [t for t in tokens if t.isalpha()]
        if alpha_tokens and (all(t.isupper() for t in alpha_tokens) or all(t[0].isupper() for t in alpha_tokens)):
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

def extract_semantic_links(soup: BeautifulSoup) -> Tuple[List[str], List[str]]:
    """Extracts tel: and mailto: links directly from DOM."""
    phones = []
    emails = []
    seen_phones = set()
    seen_emails = set()

    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        if href.lower().startswith('tel:'):
            raw_target = urllib.parse.unquote(href[4:].split('?')[0]).strip()
            for raw_chunk in re.split(r'[,;/]', raw_target):
                raw_chunk = raw_chunk.strip()
                if not raw_chunk:
                    continue
                is_val, norm_p, _ = normalize_bd_phone(raw_chunk)
                if is_val and norm_p:
                    if norm_p not in seen_phones:
                        seen_phones.add(norm_p)
                        phones.append(norm_p)
        elif href.lower().startswith('mailto:'):
            raw_email = urllib.parse.unquote(href[7:].split('?')[0]).strip().lower()
            for em_chunk in re.split(r'[,;/]', raw_email):
                clean_em = re.sub(r'^(?:email|e-mail|mail)\:?', '', em_chunk.strip(), flags=re.IGNORECASE).strip()
                if '@' in clean_em and clean_em not in seen_emails:
                    seen_emails.add(clean_em)
                    emails.append(clean_em)

    return phones, emails

def extract_json_ld(soup: BeautifulSoup, page_url: str) -> List[Dict[str, Any]]:
    """Extracts Schema.org JSON-LD structured data with nested Person / Founder / ContactPoint parsing."""
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
                    types = str(sub.get('@type', '')).lower()

                    raw_name = clean_business_name(clean_text(sub.get('name') or sub.get('legalName')))
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

                    person_cand = None
                    for key in ['founder', 'founders', 'employee', 'employees', 'member', 'members', 'author']:
                        nested = sub.get(key)
                        if isinstance(nested, dict):
                            n_name = clean_text(nested.get('name'))
                            if n_name and is_person_name(n_name):
                                person_cand = n_name
                                if not job:
                                    job = clean_text(nested.get('jobTitle'))
                                break
                        elif isinstance(nested, list):
                            for n_item in nested:
                                if isinstance(n_item, dict):
                                    n_name = clean_text(n_item.get('name'))
                                    if n_name and is_person_name(n_name):
                                        person_cand = n_name
                                        if not job:
                                            job = clean_text(n_item.get('jobTitle'))
                                        break
                            if person_cand:
                                break

                    # Check contactPoint
                    cp = sub.get('contactPoint')
                    if isinstance(cp, dict):
                        if not tel:
                            tel = clean_text(cp.get('telephone'))
                        if not email:
                            email = clean_text(cp.get('email'))
                        cp_name = clean_text(cp.get('name'))
                        if cp_name and is_person_name(cp_name) and not person_cand:
                            person_cand = cp_name
                        if not job and cp.get('contactType'):
                            job = clean_text(cp.get('contactType')).title()

                    if tel or email:
                        is_val, norm_tel, _ = normalize_bd_phone(tel)
                        is_person_schema = 'person' in types

                        if is_person_schema or (is_person_name(raw_name) and not any(kw in raw_name.lower() for kw in ORG_KEYWORDS)):
                            p_name = raw_name
                            b_name = (sub.get('worksFor', {}).get('name') if isinstance(sub.get('worksFor'), dict) else "Business")
                            if not job:
                                job = "Managing Director"
                        else:
                            p_name = person_cand or "Contact Person"
                            b_name = raw_name or "Business"

                        leads.append({
                            'business_name': b_name,
                            'contact_person': p_name,
                            'designation': job or ("Managing Director" if p_name != "Contact Person" else "Representative"),
                            'phone': norm_tel if is_val else "N/A",
                            'email': email or "N/A",
                            'website': web,
                            'address': addr_str or "N/A",
                            'source_url': page_url,
                            'extraction_technique': 'json_ld'
                        })
        except Exception:
            continue
    return leads

def extract_key_value_profile(
    soup: BeautifulSoup,
    page_url: str,
    default_category: str = "Hospitality & Tourism",
    default_city: str = "Dhaka"
) -> Optional[Dict[str, Any]]:
    """
    Extracts structured data from vertical profile pages formatted with Key-Value tables or definition rows.
    (e.g., REHAB member-details/1337, NBL branch-map, corporate member profiles).
    """
    kv_map: Dict[str, str] = {}
    for tr in soup.find_all('tr'):
        cells = tr.find_all(['th', 'td'])
        if len(cells) in (2, 3):
            label = clean_text(cells[0].get_text()).lower().rstrip(':')
            val = clean_text(cells[-1].get_text())
            if label and val:
                kv_map[label] = val

    # Also check dl, dt, dd
    for dt in soup.find_all('dt'):
        dd = dt.find_next_sibling('dd')
        if dd:
            label = clean_text(dt.get_text()).lower().rstrip(':')
            val = clean_text(dd.get_text())
            if label and val:
                kv_map[label] = val

    if not kv_map:
        return None

    has_company = any(any(w in k for w in ['company', 'agency', 'organization', 'branch', 'প্রতিষ্ঠান']) for k in kv_map)
    has_contact = any(any(w in k for w in ['representative', 'contact', 'owner', 'member', 'key person', 'director', 'proprietor', 'nam', 'নাম']) for k in kv_map if not any(w in k for w in ['company', 'agency', 'branch', 'organization'])) or any(k == 'name' for k in kv_map)
    has_phone = any(any(w in k for w in ['phone', 'mobile', 'tel', 'cell', 'ফোন', 'মোবাইল']) for k in kv_map)

    if not (has_company or (has_contact and has_phone)):
        return None

    des = None
    for k, v in kv_map.items():
        k_clean = k.lower().strip()
        if any(w in k_clean for w in ['designation', 'role', 'title', 'position', 'job title', 'পদবী']):
            val_clean = clean_text(v)
            if val_clean and len(val_clean) <= 40:
                des = val_clean
                break

    p_name = None
    for k, v in kv_map.items():
        k_clean = k.lower().strip()
        if any(w in k_clean for w in ['company', 'agency', 'branch', 'firm', 'organization', 'office', 'type']):
            continue
        if any(w in k_clean for w in ['representative', 'contact person', 'owner', 'member name', 'key person', 'proprietor', 'managing director', 'director name', 'name', 'নাম']):
            cand = v
            if cand and cand.lower() not in ['representative', 'n/a', 'none', '-', 'contact person']:
                nm, maybe_des = split_name_and_designation(cand)
                clean_cand = clean_person_name(nm)
                if is_person_name(clean_cand):
                    p_name = clean_cand
                    if maybe_des and not des:
                        des = maybe_des
                    break

    b_name = None
    for k, v in kv_map.items():
        k_clean = k.lower().strip()
        if any(w in k_clean for w in ['company name', 'agency name', 'name of company', 'organization name', 'firm name', 'business name', 'প্রতিষ্ঠানের নাম']):
            cleaned = clean_business_name(v)
            if cleaned and len(cleaned) >= 3:
                b_name = cleaned
                break

    if not b_name:
        for k, v in kv_map.items():
            k_clean = k.lower().strip()
            if ('company' in k_clean or 'organization' in k_clean) and not any(w in k_clean for w in ['type', 'status', 'category', 'reg']):
                cleaned = clean_business_name(v)
                if cleaned and len(cleaned) >= 3:
                    b_name = cleaned
                    break

    if not b_name:
        for h in soup.find_all(['h1', 'h2', 'h3']):
            htext = clean_business_name(clean_text(h.get_text()))
            if len(htext) >= 4 and not any(w in htext.lower() for w in ['member details', 'welcome', 'home', 'association', 'branch map', 'about us', 'contact us', 'rehab']):
                b_name = htext
                break

    if not b_name and any('branch' in k for k in kv_map):
        branch_val = next((v for k, v in kv_map.items() if 'branch' in k and 'name' in k), None) or next((v for k, v in kv_map.items() if 'branch' in k), None)
        meta = extract_meta_tags(soup)
        site_name = meta.get('og:site_name') or ''
        if not site_name and soup.title:
            site_name = clean_text(soup.title.string).split('|')[0].strip()
            if '-' in site_name:
                site_name = site_name.split('-')[0].strip()
        if branch_val:
            b_name = f"{site_name} - {branch_val}" if site_name else branch_val
            if 'branch' not in b_name.lower():
                b_name = f"{b_name} Branch"

    addr = None
    for k, v in kv_map.items():
        k_clean = k.lower().strip()
        if any(w in k_clean for w in ['address', 'location', 'ঠিকানা']):
            val_clean = clean_text(v)
            if val_clean and len(val_clean) >= 3:
                addr = val_clean
                break

    all_phones = []
    for k, v in kv_map.items():
        if any(w in k for w in ['phone', 'mobile', 'tel', 'cell', 'contact no', 'ফোন', 'মোবাইল']):
            phones = extract_and_normalize_bd_phones(v)
            all_phones.extend(phones)

    # Check semantic links for phones/emails
    sem_phones, sem_emails = extract_semantic_links(soup)
    all_phones = list(dict.fromkeys(all_phones + sem_phones))

    all_emails = []
    for k, v in kv_map.items():
        if any(w in k for w in ['email', 'e-mail', 'mail', 'ইমেইল']):
            ems = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', v)
            all_emails.extend(ems)
    all_emails = list(dict.fromkeys(all_emails + sem_emails))

    if not all_phones and not all_emails:
        return None

    is_branch = 'branch' in str(b_name).lower() or any('branch' in k for k in kv_map)

    return {
        'business_name': b_name or "Business",
        'contact_person': p_name or ("Branch Manager" if is_branch else "Contact Person"),
        'designation': des or ("Branch Manager" if is_branch else ("Managing Director" if p_name else "Representative")),
        'industry': default_category,
        'phone': all_phones[0] if all_phones else "N/A",
        'email': all_emails[0] if all_emails else "N/A",
        'address': addr or default_city,
        'city': default_city,
        'country': "Bangladesh",
        'website': page_url,
        'source_url': page_url,
        'extraction_technique': 'key_value_profile'
    }

def extract_leads_from_tables(
    soup: BeautifulSoup,
    page_url: str,
    primary_org: str,
    default_category: str = "Hospitality & Tourism",
    default_city: str = "Dhaka"
) -> List[Dict[str, Any]]:
    """
    Intelligent HTML <table> extraction.
    Handles <br> tags properly (converting them to newlines so names and designations don't concatenate).
    Maps column headers to Name, Designation, Company, Phone, Email, Address.
    """
    leads = []
    tables = soup.find_all('table')

    for table in tables:
        rows = table.find_all('tr')
        if not rows or len(rows) < 2:
            continue

        # Check if table is a vertical key-value table
        if len(rows) >= 3:
            first_row_cells = rows[0].find_all(['th', 'td'])
            if len(first_row_cells) in (2, 3):
                first_label = clean_text(first_row_cells[0].get_text()).lower().rstrip(':')
                if any(k in first_label for k in ['company', 'name', 'sl', 'member', 'type', 'serial']):
                    pass

        headers = []
        header_tr = table.find('thead')
        if header_tr:
            th_cells = header_tr.find_all(['th', 'td'])
            headers = [clean_text(th.get_text()).lower() for th in th_cells]
        else:
            first_cells = rows[0].find_all(['th', 'td'])
            headers = [clean_text(th.get_text()).lower() for th in first_cells]

        col_name = -1
        col_org = -1
        col_des = -1
        col_phone = -1
        col_email = -1
        col_addr = -1

        for idx, h in enumerate(headers):
            # Check combined header: "Name & Designation" / "Owner Name & Designation"
            is_combined = any(w in h for w in ['name', 'person', 'owner']) and any(w in h for w in ['designation', 'role', 'title'])
            if is_combined:
                if col_name == -1:
                    col_name = idx
                continue

            if any(w in h for w in ['name', 'person', 'contact person', 'member name', 'owner name', 'executive', 'proprietor', 'নাম', 'যোগাযোগ']):
                if col_name == -1:
                    col_name = idx
            if any(w in h for w in ['company', 'organization', 'agency', 'firm', 'business', 'প্রতিষ্ঠানের নাম', 'প্রতিষ্ঠান']):
                if col_org == -1:
                    col_org = idx
            if any(w in h for w in ['designation', 'role', 'title', 'position', 'job', 'পদবী']):
                if col_des == -1:
                    col_des = idx
            if any(w in h for w in ['phone', 'mobile', 'tel', 'cell', 'contact no', 'ফোন', 'মোবাইল']):
                if col_phone == -1:
                    col_phone = idx
            if any(w in h for w in ['email', 'e-mail', 'mail', 'ইমেইল']):
                if col_email == -1:
                    col_email = idx
            if any(w in h for w in ['address', 'location', 'office', 'city', 'ঠিকানা']):
                if col_addr == -1:
                    col_addr = idx

        data_rows = rows[1:] if not header_tr else rows
        for row in data_rows:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue

            row_text = clean_text(row.get_text(separator=' '))
            sub_soup = BeautifulSoup(str(row), 'html.parser')
            sub_phones, sub_emails = extract_semantic_links(sub_soup)
            row_phones = list(dict.fromkeys(extract_and_normalize_bd_phones(row_text) + sub_phones))
            raw_emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', row_text)
            row_emails = list(dict.fromkeys([e.lower() for e in raw_emails + sub_emails]))

            if not row_phones and not row_emails:
                continue

            cand_person = None
            cand_org = None
            cand_role = None
            cand_addr = default_city

            # 1. Use mapped columns if available with newline preservation for <br>
            if col_name != -1 and col_name < len(cells):
                # Extract text splitting on <br> / \n
                cell_lines = [clean_text(l) for l in cells[col_name].get_text(separator='\n').split('\n') if clean_text(l)]
                if cell_lines:
                    first_line = cell_lines[0]
                    nm, des = split_name_and_designation(first_line)
                    c_name = clean_person_name(nm)
                    if is_person_name(c_name):
                        cand_person = c_name
                        if des:
                            cand_role = des
                    # If designation was on line 2 (e.g. Mr. Nazmul Ahmed <br> Managing Director)
                    if len(cell_lines) > 1 and not cand_role:
                        second_line = cell_lines[1]
                        for d in DESIGNATIONS:
                            if re.search(r'\b' + re.escape(d) + r'\b', second_line, re.IGNORECASE):
                                cand_role = d.title()
                                break

            if col_org != -1 and col_org < len(cells):
                cell_lines = [clean_text(l) for l in cells[col_org].get_text(separator='\n').split('\n') if clean_text(l)]
                if cell_lines:
                    cleaned_org = clean_business_name(cell_lines[0])
                    if cleaned_org and len(cleaned_org) >= 3 and cleaned_org.lower() not in LABEL_WORDS:
                        cand_org = cleaned_org

            if col_des != -1 and col_des != col_name and col_des < len(cells) and not cand_role:
                cell_des = clean_text(cells[col_des].get_text())
                if cell_des and len(cell_des) >= 2:
                    for d in DESIGNATIONS:
                        if re.search(r'\b' + re.escape(d) + r'\b', cell_des, re.IGNORECASE):
                            cand_role = d.title()
                            break
                    if not cand_role and len(cell_des) <= 30 and not is_person_name(cell_des):
                        cand_role = cell_des.title()

            if col_addr != -1 and col_addr < len(cells):
                cell_addr = clean_text(cells[col_addr].get_text())
                if cell_addr and len(cell_addr) >= 3:
                    cand_addr = cell_addr

            # 2. Inspect individual cells if name/org not resolved
            if not cand_person or not cand_org:
                for c_idx, cell in enumerate(cells):
                    if c_idx in (col_phone, col_email):
                        continue
                    cell_lines = [clean_text(l) for l in cell.get_text(separator='\n').split('\n') if clean_text(l)]
                    for c_text in cell_lines:
                        if not c_text or c_text.lower() in LABEL_WORDS or len(c_text) < 3:
                            continue

                        nm, des = split_name_and_designation(c_text)
                        clean_nm = clean_person_name(nm)
                        if not cand_person and is_person_name(clean_nm):
                            cand_person = clean_nm
                            if des and not cand_role:
                                cand_role = des
                            continue

                        if not cand_org:
                            cleaned_b = clean_business_name(c_text)
                            if any(w in cleaned_b.lower() for w in ORG_KEYWORDS) and not is_person_name(cleaned_b):
                                cand_org = cleaned_b
                                continue

                        if not cand_role:
                            for d in DESIGNATIONS:
                                if re.search(r'\b' + re.escape(d) + r'\b', c_text, re.IGNORECASE):
                                    cand_role = d.title()
                                    break

            if not cand_role:
                for d in DESIGNATIONS:
                    if re.search(r'\b' + re.escape(d) + r'\b', row_text, re.IGNORECASE):
                        cand_role = d.title()
                        break

            final_person = cand_person or "Contact Person"
            final_org = cand_org or primary_org
            final_role = cand_role or ("Managing Director" if final_person != "Contact Person" else "Representative")
            phone_str = row_phones[0] if row_phones else "N/A"
            email_str = row_emails[0] if row_emails else "N/A"

            leads.append({
                'business_name': clean_business_name(final_org),
                'contact_person': final_person,
                'designation': final_role,
                'industry': default_category,
                'phone': phone_str,
                'email': email_str,
                'website': page_url,
                'address': cand_addr,
                'city': default_city,
                'country': "Bangladesh",
                'source_url': page_url,
                'extraction_technique': 'table'
            })

    return leads

def extract_leads_from_cards(
    soup: BeautifulSoup,
    page_url: str,
    primary_org: str,
    default_category: str = "Hospitality & Tourism",
    default_city: str = "Dhaka"
) -> List[Dict[str, Any]]:
    """
    DOM & Card-based extraction across profile cards, team members, and directory items.
    Handles multi-line blocks with labeled lines (e.g. Prop:, M/Dir:, Managing Director:).
    """
    leads = []
    card_selectors = [
        'tr.d-flex',
        '.profile-card',
        '.directory-item',
        '.member',
        '.member-box',
        '.company-item',
        '.executive-card',
        '.executive-profile',
        '.team-member',
        '.team-item',
        '.contact-card',
        '.card'
    ]

    seen_cards = set()

    for sel in card_selectors:
        elements = soup.select(sel)
        if not elements:
            continue

        for el in elements:
            el_text = clean_text(el.get_text(separator=' '))
            el_html = str(el)

            card_phones = extract_and_normalize_bd_phones(el_text)
            card_emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', el_text)

            # Check protected emails (e.g. Bangladesh Bank div/td with onselectstart)
            for d in el.find_all(['div', 'td', 'span', 'a']):
                if d.get('onselectstart') and '@' in d.get_text():
                    em = clean_text(d.get_text()).lower()
                    if em not in card_emails:
                        card_emails.append(em)

            sub_soup = BeautifulSoup(el_html, 'html.parser')
            sub_phones, sub_emails = extract_semantic_links(sub_soup)

            all_phones = list(dict.fromkeys(card_phones + sub_phones))
            all_emails = list(dict.fromkeys([e.lower() for e in card_emails + sub_emails]))

            if not all_phones and not all_emails:
                continue

            card_sig = (all_phones[0] if all_phones else '') + (all_emails[0] if all_emails else '')
            if card_sig in seen_cards:
                continue
            seen_cards.add(card_sig)

            cand_person = None
            cand_role = None
            cand_org = None
            cand_addr = default_city

            # 1. Multi-line block parsing (vital for dcaadhaka, association listings)
            # Find paragraphs or divs that contain multiple lines
            for block in el.find_all(['p', 'div']):
                block_lines = [clean_text(l) for l in block.get_text(separator='\n').split('\n') if clean_text(l)]
                if len(block_lines) >= 2:
                    for idx, line in enumerate(block_lines):
                        # Line 0: Business Name candidate if not set
                        if idx == 0 and not cand_org:
                            c_org = clean_business_name(line)
                            if len(c_org) >= 3 and not is_person_name(c_org):
                                cand_org = c_org

                        # Check for labeled designation + person line: Prop:, M/Dir:, Managing Director:, Director:, Chairman:
                        m_role = re.search(
                            r'^(?:Prop|Proprietor|M/Dir|MD|Managing\s*Director|Director|Chairman|President|Sr\.?\s*Vice\s*President|Vice\s*President|CEO|Owner|Founder|Representative|Key\s*Person|Contact\s*Person|Name|স্বত্বাধিকারী|ব্যবস্থাপনা পরিচালক)\s*[:\-–—|]+\s*(.*)$',
                            line,
                            re.IGNORECASE
                        )
                        if m_role:
                            label = re.search(r'^(.*?)\s*[:\-–—|]', line).group(1).strip()
                            raw_val = m_role.group(1).strip()
                            raw_val = re.sub(r'\s*\((?:Voter|Representative|Member|Dir|MD)[^)]*\)', '', raw_val, flags=re.IGNORECASE).strip()
                            nm, des = split_name_and_designation(raw_val)
                            c_name = clean_person_name(nm)
                            if is_person_name(c_name) and not cand_person:
                                cand_person = c_name
                                l_lower = label.lower()
                                if 'prop' in l_lower:
                                    cand_role = "Proprietor"
                                elif 'm/dir' in l_lower or l_lower == 'md' or 'managing' in l_lower:
                                    cand_role = "Managing Director"
                                elif 'sr' in l_lower and 'vice' in l_lower:
                                    cand_role = "Sr. Vice President"
                                elif 'vice' in l_lower:
                                    cand_role = "Vice President"
                                elif 'chair' in l_lower:
                                    cand_role = "Chairman"
                                elif 'dir' in l_lower:
                                    cand_role = "Director"
                                elif des:
                                    cand_role = des
                                elif 'ceo' in l_lower:
                                    cand_role = "CEO"
                                else:
                                    cand_role = label.title()

                        # Check if line is address
                        if any(w in line.lower() for w in ['flat', 'house', 'road', 'floor', 'bhaban', 'mansion', 'dhaka', 'motijheel', 'dhanmondi', 'kamalapur', 'bazar', 'avenue']):
                            if not any(w in line.lower() for w in ['license', 'member id', 'member since', 'prop:', 'm/dir:', 'director:']):
                                if cand_addr == default_city and not any(line.lower().startswith(p) for p in ['ph:', 'phone:', 'mobile:', 'e-mail:', 'email:']):
                                    cand_addr = line

            # 2. Check dedicated classes for person name
            if not cand_person:
                name_classes = ['.person-name', '.member-name', '.name', '.executive-name', '.contact-name', '.author', '[itemprop="name"]']
                for nc in name_classes:
                    tag = el.select_one(nc)
                    if tag:
                        raw_val = clean_text(tag.get_text())
                        nm, des = split_name_and_designation(raw_val)
                        c_name = clean_person_name(nm)
                        if is_person_name(c_name):
                            cand_person = c_name
                            if des and not cand_role:
                                cand_role = des
                            break

            # 3. Check dedicated classes for company name
            if not cand_org:
                org_classes = ['.company-name', '.company', '.org', '.organization', '.agency-name', '.business-name']
                for oc in org_classes:
                    tag = el.select_one(oc)
                    if tag:
                        raw_val = clean_business_name(clean_text(tag.get_text()))
                        if raw_val and len(raw_val) >= 3 and raw_val.lower() not in LABEL_WORDS:
                            cand_org = raw_val
                            break

            # 4. Check dedicated classes for designation
            if not cand_role:
                des_classes = ['.designation', '.role', '.position', '.job-title']
                for dc in des_classes:
                    tag = el.select_one(dc)
                    if tag:
                        raw_val = clean_text(tag.get_text())
                        if raw_val and len(raw_val) >= 2:
                            cand_role = raw_val.title()
                            break

            # 5. Regex check for labeled fields like "Contact Person: Md. ...", "Name: ...", "Proprietor: ..."
            if not cand_person:
                m_label = re.search(
                    r'(?:Contact\s*Person|Contact\s*Name|Key\s*Person|Name|Proprietor|Prop|Owner|Founder|Director|Managing\s*Director|M/Dir|MD|CEO|Representative|Executive|নাম|যোগাযোগ|স্বত্বাধিকারী)\s*[:\-–—|]+\s*([^\n\r<]+?)(?=\s+(?:Designation|Phone|Mobile|Email|Tel|Cell|Address|\(Off|$))',
                    el_text,
                    re.IGNORECASE
                )
                if m_label:
                    raw_cand = clean_text(m_label.group(1))
                    nm, des = split_name_and_designation(raw_cand)
                    c_name = clean_person_name(nm)
                    if is_person_name(c_name):
                        cand_person = c_name
                        if des and not cand_role:
                            cand_role = des

            # 6. Check headings or strong tags for person name or org
            for heading in el.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'strong', 'font']):
                htext = clean_text(heading.get_text())
                if not htext or htext.lower() in LABEL_WORDS or len(htext) < 3:
                    continue

                nm, des = split_name_and_designation(htext)
                clean_h = clean_person_name(nm)

                if not cand_person and is_person_name(clean_h):
                    cand_person = clean_h
                    if des and not cand_role:
                        cand_role = des
                elif not cand_org:
                    c_bname = clean_business_name(htext)
                    if any(w in c_bname.lower() for w in ORG_KEYWORDS) and not is_person_name(c_bname):
                        cand_org = c_bname

            # 7. Check for known designations if role not labeled
            if not cand_role:
                for d in DESIGNATIONS:
                    if re.search(r'\b' + re.escape(d) + r'\b', el_text, re.IGNORECASE):
                        cand_role = d.title()
                        break

            p_name = cand_person or "Contact Person"
            b_name = clean_business_name(cand_org or primary_org)
            role = cand_role or ("Managing Director" if p_name != "Contact Person" else "Executive / Decision Maker")
            phone_str = all_phones[0] if all_phones else "N/A"
            email_str = all_emails[0] if all_emails else "N/A"

            leads.append({
                'business_name': b_name,
                'contact_person': p_name,
                'designation': role,
                'industry': default_category,
                'phone': phone_str,
                'email': email_str,
                'website': page_url,
                'address': cand_addr,
                'city': default_city,
                'country': "Bangladesh",
                'source_url': page_url,
                'extraction_technique': f'card_{sel}'
            })

    return leads

def extract_leads_from_html(
    html: str,
    page_url: str,
    default_category: str = "Hospitality & Tourism",
    default_city: str = "Dhaka"
) -> List[Dict[str, Any]]:
    """
    Advanced multi-technique extraction pipeline.
    Prioritizes:
    1. Schema.org JSON-LD structured data (with nested person/founder/contactPoint)
    2. Single-member Key-Value profile structures (e.g. REHAB member-details, NBL branch-map)
    3. Intelligent HTML tables (with column mapping & <br> splitting)
    4. Profile & Member Cards (with multi-line block parsing)
    5. Fallback page text extraction
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

    primary_org = clean_business_name(site_title if site_title and len(site_title) < 60 else domain_name)

    # 1. Structured JSON-LD extraction
    json_leads = extract_json_ld(soup, page_url)
    if json_leads:
        for jl in json_leads:
            jl['industry'] = default_category
            jl['city'] = default_city
            leads.append(jl)

    # 2. Key-Value Profile Extraction (for dedicated member detail / branch pages)
    kv_lead = extract_key_value_profile(soup, page_url, default_category, default_city)
    if kv_lead:
        leads.append(kv_lead)

    # 3. Extract semantic tel: and mailto: links from whole page
    semantic_phones, semantic_emails = extract_semantic_links(soup)

    # 4. HTML Table Extraction (if not already handled by key-value profile)
    if not kv_lead:
        table_leads = extract_leads_from_tables(soup, page_url, primary_org, default_category, default_city)
        if table_leads:
            leads.extend(table_leads)

    # 5. Profile / Card Extraction
    if not kv_lead:
        card_leads = extract_leads_from_cards(soup, page_url, primary_org, default_category, default_city)
        if card_leads:
            leads.extend(card_leads)

    # 6. Fallback to general page text if no structured leads discovered
    if not leads:
        all_text = clean_text(soup.get_text())
        text_phones = extract_and_normalize_bd_phones(all_text)
        text_emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', all_text)

        combined_phones = list(dict.fromkeys(semantic_phones + text_phones))
        combined_emails = list(dict.fromkeys(semantic_emails + [e.lower() for e in text_emails]))

        if combined_phones or combined_emails:
            detected_person = None
            detected_role = None

            # Check author meta tag
            author_meta = meta.get('author') or meta.get('article:author')
            if author_meta and is_person_name(author_meta):
                detected_person = clean_person_name(author_meta)

            # Check regex patterns in text
            if not detected_person:
                role_patterns = [
                    r'(?:Proprietor|Prop|Managing Director|M/Dir|MD|CEO|Director|Chairman|President|Contact Person|Representative|Manager|Founder|Owner|স্বত্বাধিকারী|ব্যবস্থাপনা পরিচালক)\s*[:\-–—|]+\s*([A-Za-z\u0980-\u09FF\.\s]{3,40})(?=\s+(?:Phone|Mobile|Email|Tel|Cell|যোগাযোগ|ফোন|মোবাইল|ইমেইল|ঠিকানা|$))',
                    r'\b((?:Md|Mohammad|Mohammed|Muhammad|Dr|Engr|Prof|Mr|Mrs|Ms)\.?\s+[A-Z][a-zA-Z\.\s]{3,35})\b',
                    r'((?:মোঃ|মো:|মোহাম্মদ|ড\.|ডঃ|ইঞ্জিঃ)\s*[\u0980-\u09FF\s]{4,35})'
                ]
                for pat in role_patterns:
                    m = re.search(pat, all_text, re.IGNORECASE)
                    if m:
                        cand = clean_text(m.group(1))
                        nm, des = split_name_and_designation(cand)
                        c_nm = clean_person_name(nm)
                        if is_person_name(c_nm):
                            detected_person = c_nm
                            if des:
                                detected_role = des
                            break

            if not detected_role:
                for d in DESIGNATIONS:
                    if re.search(r'\b' + re.escape(d) + r'\b', all_text, re.IGNORECASE):
                        detected_role = d.title()
                        break

            phone_str = combined_phones[0] if combined_phones else "N/A"
            email_str = combined_emails[0] if combined_emails else "N/A"

            leads.append({
                'business_name': primary_org,
                'contact_person': detected_person or "Contact Person",
                'designation': detected_role or ("Managing Director" if detected_person else "Representative"),
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

    # Early deduplication by phone/email across leads on the same page
    unique_leads = []
    seen = set()
    for l in leads:
        p = l.get('phone', 'N/A')
        e = l.get('email', 'N/A')
        sig = f"{p}|{e}"
        if sig != "N/A|N/A" and sig in seen:
            continue
        seen.add(sig)
        unique_leads.append(l)

    return unique_leads
