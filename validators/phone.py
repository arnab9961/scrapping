import re
import ipaddress
from typing import Optional, Tuple, List, Dict, Any
import phonenumbers
from phonenumbers import PhoneNumberType, NumberParseException

# Valid BD mobile operator prefixes (without 0): 13, 14, 15, 16, 17, 18, 19
# Note: 010, 011, 012 are invalid / reserved.
BD_MOBILE_PREFIX_REGEX = re.compile(r'^1[3-9]\d{8}$')

# Year ranges or copyright dates misparsed as phone numbers (e.g. 2024-2025)
YEAR_RANGE_REGEX = re.compile(r'\b(?:19|20)\d{2}\s*[-–/]\s*(?:19|20)\d{2}\b')

# Dummy numbers with repeating identical digits
DUMMY_DIGITS_REGEX = re.compile(r'^(\d)\1{7,}$')

PHONE_TYPE_MAP = {
    PhoneNumberType.MOBILE: "MOBILE",
    PhoneNumberType.FIXED_LINE: "FIXED_LINE",
    PhoneNumberType.FIXED_LINE_OR_MOBILE: "MOBILE",
    PhoneNumberType.VOIP: "VOIP",
    PhoneNumberType.TOLL_FREE: "TOLL_FREE",
    PhoneNumberType.PREMIUM_RATE: "PREMIUM_RATE",
    PhoneNumberType.SHARED_COST: "SHARED_COST",
    PhoneNumberType.PERSONAL_NUMBER: "PERSONAL_NUMBER",
    PhoneNumberType.PAGER: "PAGER",
    PhoneNumberType.UAN: "UAN",
    PhoneNumberType.VOICEMAIL: "VOICEMAIL",
    PhoneNumberType.UNKNOWN: "UNKNOWN",
}

def is_ip_address(val: str) -> bool:
    """Detects IPv4 or IPv6 addresses to prevent them from being treated as phone numbers."""
    cleaned = str(val).strip()
    try:
        ipaddress.ip_address(cleaned)
        return True
    except ValueError:
        pass
    # Dotted IPv4 pattern (e.g. 192.168.1.1, 8.8.8.8, 10.0.0.1:8080)
    if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?$', cleaned):
        return True
    # Colon-separated IPv6 pattern
    if ':' in cleaned and re.search(r'[0-9a-fA-F]{1,4}:[0-9a-fA-F]{1,4}', cleaned):
        return True
    return False

def clean_phone_input(raw_phone: str) -> str:
    """Strips formatting symbols, spaces, parentheses, hyphens, and slashes."""
    if not raw_phone:
        return ""
    cleaned = re.sub(r'[\s\-()./,]', '', str(raw_phone)).strip()
    return cleaned

def normalize_bd_phone(raw_phone: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Backward-compatible validator and normalizer for Bangladesh mobile phone numbers.
    
    Rules:
    - Accepts ONLY valid Bangladesh mobile numbers in international format (+8801XXXXXXXXX).
    - Valid mobile operator prefixes: 013, 014, 015, 016, 017, 018, 019.
    - Rejects any number starting with 02 or +8802 (landline numbers).
    - Rejects IP addresses (IPv4 and IPv6 like 192.168.1.1, 8.8.8.8).
    - Rejects short codes, incomplete numbers, and invalid prefixes.
    - Normalizes accepted numbers into '+8801XXXXXXXXX' format (14 characters).
    
    Returns:
        (is_valid: bool, normalized_phone: str or None, error_reason: str or None)
    """
    if not raw_phone or str(raw_phone).strip().lower() in ('n/a', 'none', 'null', ''):
        return False, None, "Phone number is empty or N/A"

    raw_str = str(raw_phone).strip()

    # 1. Reject IP addresses
    if is_ip_address(raw_str):
        return False, None, f"Rejected: '{raw_str}' is an IP address, not a phone number"

    # 2. Reject date / year ranges
    if YEAR_RANGE_REGEX.search(raw_str):
        return False, None, "Rejected: appears to be a year range or date"

    # 3. Clean formatting symbols
    cleaned = clean_phone_input(raw_str)

    # 4. Explicitly reject landline numbers starting with 02, +8802, or 8802
    if cleaned.startswith(('02', '+8802', '8802', '+02')):
        return False, None, f"Rejected: landline number '{raw_str}' (only mobile numbers allowed)"

    # 5. Extract subscriber part by checking country code / national prefix
    if cleaned.startswith('+880'):
        subscriber = cleaned[4:]
    elif cleaned.startswith('880'):
        subscriber = cleaned[3:]
    elif cleaned.startswith('0'):
        subscriber = cleaned[1:]
    else:
        return False, None, "Rejected: missing valid Bangladesh country code or prefix (+880 / 01...)"

    # 6. Reject non-digits or invalid length (must be exactly 10 digits starting with 1[3-9])
    if not subscriber.isdigit():
        return False, None, "Rejected: contains non-numeric characters"

    if len(subscriber) != 10:
        return False, None, f"Rejected: invalid length ({len(subscriber)} digits, expected 10 after +880)"

    # 7. Check valid mobile operator prefix: 13, 14, 15, 16, 17, 18, 19
    if not BD_MOBILE_PREFIX_REGEX.match(subscriber):
        prefix = subscriber[:2]
        return False, None, f"Rejected: invalid mobile operator prefix '0{prefix}' (must be 013-019)"

    # 8. Reject dummy numbers with repeating digits (e.g. 00000000)
    if DUMMY_DIGITS_REGEX.match(subscriber[2:]):
        return False, None, "Rejected: dummy or placeholder repeating digits"

    # 9. Successful normalization into +8801XXXXXXXXX
    normalized = f"+880{subscriber}"
    return True, normalized, None

def is_valid_bd_phone(raw_phone: str) -> bool:
    """Convenience boolean check for BD mobile phone validity."""
    is_valid, _, _ = normalize_bd_phone(raw_phone)
    return is_valid

def extract_and_normalize_bd_phones(text: str) -> List[str]:
    """
    Extracts all candidate mobile phone numbers from text/html and returns
    a deduplicated list of strictly normalized '+8801XXXXXXXXX' numbers.
    """
    if not text:
        return []

    candidates = re.findall(
        r'(?:\+?880[\s.-]?)?0?1[3-9](?:[\s.-]?\d){8}\b',
        text
    )

    valid_normalized = []
    seen = set()

    for cand in candidates:
        is_val, norm, _ = normalize_bd_phone(cand)
        if is_val and norm and norm not in seen:
            seen.add(norm)
            valid_normalized.append(norm)

    return valid_normalized

def normalize_phone(
    raw_phone: str,
    default_country: str = "BD",
    allow_landline: bool = True
) -> Tuple[bool, Optional[str], Optional[str], str]:
    """
    Comprehensive Global Phone Number Normalizer using Google's libphonenumber.
    
    Normalizes any valid phone number to international E.164 format (+XXXXXXXXXXX).
    Categorizes number type (MOBILE, FIXED_LINE, VOIP, etc.).
    Supports any country code with fallback to default_country.
    
    Returns:
        (is_valid: bool, e164_phone: str or None, error_reason: str or None, phone_type: str)
    """
    if not raw_phone or str(raw_phone).strip().lower() in ('n/a', 'none', 'null', ''):
        return False, None, "Phone number is empty or N/A", "UNKNOWN"

    raw_str = str(raw_phone).strip()

    # Reject IP addresses
    if is_ip_address(raw_str):
        return False, None, f"Rejected: '{raw_str}' is an IP address", "UNKNOWN"

    # Reject year ranges / copyright dates
    if YEAR_RANGE_REGEX.search(raw_str):
        return False, None, "Rejected: appears to be a year range or date", "UNKNOWN"

    cleaned_digits = clean_phone_input(raw_str)
    # Reject dummy repeating digits
    digits_only = re.sub(r'\D', '', cleaned_digits)
    if len(digits_only) >= 7 and DUMMY_DIGITS_REGEX.match(digits_only[2:]):
        return False, None, "Rejected: dummy or repeating digits", "UNKNOWN"

    # Normalize default_country string (e.g. 'Bangladesh' -> 'BD', 'United States' -> 'US')
    country_code = (default_country or "BD").strip().upper()
    country_alias_map = {
        "BANGLADESH": "BD",
        "UNITED STATES": "US",
        "USA": "US",
        "UNITED KINGDOM": "GB",
        "UK": "GB",
        "CANADA": "CA",
        "INDIA": "IN",
        "AUSTRALIA": "AU",
        "GERMANY": "DE",
        "FRANCE": "FR",
        "UAE": "AE",
        "SINGAPORE": "SG"
    }
    country_code = country_alias_map.get(country_code, country_code[:2] if len(country_code) > 2 else country_code)

    try:
        parsed = phonenumbers.parse(raw_str, country_code)
    except NumberParseException as e:
        return False, None, f"Number parse error: {e}", "UNKNOWN"
    except Exception as e:
        return False, None, f"Invalid phone format: {e}", "UNKNOWN"

    is_valid_num = phonenumbers.is_valid_number(parsed)
    if not is_valid_num:
        # Check if it's a possible number matching national dialling plan
        if phonenumbers.is_possible_number(parsed):
            is_valid_num = True
        elif country_code == "BD":
            is_val_bd, norm_bd, _ = normalize_bd_phone(raw_str)
            if is_val_bd and norm_bd:
                return True, norm_bd, None, "MOBILE"

    if not is_valid_num:
        return False, None, "Invalid phone number according to global numbering plan", "UNKNOWN"

    num_type_enum = phonenumbers.number_type(parsed)
    phone_type = PHONE_TYPE_MAP.get(num_type_enum, "UNKNOWN")

    # Refine classification for known regional prefixes if UNKNOWN
    if phone_type == "UNKNOWN" and parsed.country_code == 880:
        nat_str = str(parsed.national_number)
        if nat_str.startswith(('2', '31', '41', '51', '61', '71', '81', '91')):
            phone_type = "FIXED_LINE"
        elif nat_str.startswith(('13', '14', '15', '16', '17', '18', '19')):
            phone_type = "MOBILE"

    if not allow_landline and phone_type == "FIXED_LINE":
        return False, None, "Landline numbers are excluded by policy", phone_type

    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    return True, e164, None, phone_type

def extract_and_normalize_phones(
    text: str,
    default_country: str = "BD",
    allow_landline: bool = True
) -> List[Dict[str, Any]]:
    """
    Extracts all candidate phone numbers from arbitrary text and normalizes them to E.164.
    Returns a list of dicts: [{'phone': '+88017...', 'type': 'MOBILE', 'raw': '017...'}]
    """
    if not text:
        return []

    found = []
    seen = set()

    country_code = (default_country or "BD").strip().upper()
    if len(country_code) > 2:
        country_code = "BD"

    # 1. Use phonenumbers PhoneNumberMatcher
    try:
        for match in phonenumbers.PhoneNumberMatcher(text, country_code):
            raw = match.raw_string
            is_val, norm, _, p_type = normalize_phone(raw, default_country=country_code, allow_landline=allow_landline)
            if is_val and norm and norm not in seen:
                seen.add(norm)
                found.append({
                    "phone": norm,
                    "type": p_type,
                    "raw": raw
                })
    except Exception:
        pass

    # 2. BD mobile regex fallback if BD country
    if country_code == "BD":
        bd_phones = extract_and_normalize_bd_phones(text)
        for p in bd_phones:
            if p not in seen:
                seen.add(p)
                found.append({
                    "phone": p,
                    "type": "MOBILE",
                    "raw": p
                })

    return found
