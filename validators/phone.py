import re
from typing import Optional, Tuple, List
import phonenumbers
from phonenumbers import PhoneNumberFormat, NumberParseException

# Regex pattern for Bangladesh mobile numbers:
# Country code: +880 or 880 or 0
# Operator prefix: 1 followed by 3-9 (13, 14, 15, 16, 17, 18, 19)
# Subscriber number: 8 digits
BD_MOBILE_REGEX = re.compile(r'^(?:\+?880|880|0)?(1[3-9]\d{8})$')

# Regex for BD Landline (Dhaka 02, etc. typically 6-9 subscriber digits):
BD_LANDLINE_REGEX = re.compile(r'^(?:\+?880|880|0)?([2-9]\d{6,8})$')

# Discard year ranges or copyright dates misparsed as phone numbers
YEAR_RANGE_REGEX = re.compile(r'\b(?:19|20)\d{2}\s*[-–/]\s*(?:19|20)\d{2}\b')

# Dummy numbers like all zeros or all identical digits
DUMMY_DIGITS_REGEX = re.compile(r'^(\d)\1{6,}$')

def clean_phone_input(raw_phone: str) -> str:
    """Strips formatting symbols, spaces, parentheses, hyphens, and dots."""
    if not raw_phone:
        return ""
    # Remove whitespace, hyphens, parentheses, dots
    cleaned = re.sub(r'[\s\-()./,]', '', str(raw_phone)).strip()
    return cleaned

def normalize_bd_phone(raw_phone: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validates and normalizes a Bangladesh phone number.
    Returns:
        (is_valid: bool, normalized_phone: str or None, reason: str or None)
        
    All valid numbers are normalized to '+880XXXXXXXXXX'.
    """
    if not raw_phone or str(raw_phone).strip().lower() in ('n/a', 'none', 'null', ''):
        return False, None, "Phone number is empty or N/A"

    raw_str = str(raw_phone).strip()

    # Reject year ranges (e.g. 2024-2025)
    if YEAR_RANGE_REGEX.search(raw_str):
        return False, None, "Invalid phone number: appears to be a date or year range"

    cleaned = clean_phone_input(raw_str)
    digits_only = re.sub(r'\D', '', cleaned)

    if len(digits_only) < 7:
        return False, None, f"Phone number too short ({len(digits_only)} digits)"
    if len(digits_only) > 15:
        return False, None, f"Phone number too long ({len(digits_only)} digits)"

    # Reject dummy repeating digits
    if DUMMY_DIGITS_REGEX.match(digits_only):
        return False, None, "Invalid dummy phone number (repeating digits)"

    # 1. First priority: Check standard Bangladesh Mobile format
    mobile_match = BD_MOBILE_REGEX.match(digits_only)
    if mobile_match:
        subscriber_part = mobile_match.group(1)  # 1[3-9]XXXXXXXX
        normalized = f"+880{subscriber_part}"
        return True, normalized, None

    # 2. Check standard Bangladesh Landline format
    landline_match = BD_LANDLINE_REGEX.match(digits_only)
    if landline_match:
        subscriber_part = landline_match.group(1)
        normalized = f"+880{subscriber_part}"
        return True, normalized, None

    # 3. Use Google's phonenumbers library for edge-cases & official telecom compliance
    try:
        # Prepend + if not present for international parse attempt
        cand_str = cleaned if cleaned.startswith('+') else f"+{cleaned}"
        parsed = phonenumbers.parse(cand_str, "BD")

        if phonenumbers.is_valid_number(parsed):
            region = phonenumbers.region_code_for_number(parsed)
            if region == "BD":
                formatted = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
                if formatted.startswith("+880"):
                    return True, formatted, None

        # Try parsing assuming local BD if international failed
        parsed_local = phonenumbers.parse(cleaned, "BD")
        if phonenumbers.is_valid_number(parsed_local):
            region = phonenumbers.region_code_for_number(parsed_local)
            if region == "BD":
                formatted = phonenumbers.format_number(parsed_local, PhoneNumberFormat.E164)
                if formatted.startswith("+880"):
                    return True, formatted, None
    except NumberParseException:
        pass

    return False, None, f"Not a valid Bangladesh phone number format: '{raw_str}'"

def is_valid_bd_phone(raw_phone: str) -> bool:
    """Convenience boolean check for BD phone validity."""
    is_valid, _, _ = normalize_bd_phone(raw_phone)
    return is_valid

def extract_and_normalize_bd_phones(text: str) -> List[str]:
    """
    Extracts all candidate phone numbers from text/html and returns
    a deduplicated list of strictly normalized '+880...' numbers.
    """
    if not text:
        return []

    # Regex search for possible phone chunks
    candidates = re.findall(
        r'(?:\+?880[\s.-]?)?0?1[3-9](?:[\s.-]?\d){8}\b|(?:\+?880[\s.-]?)?0?[2-9]\d{0,3}[\s.-]?\d{4,8}\b',
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
