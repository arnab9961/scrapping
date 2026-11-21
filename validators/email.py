import re
import socket
from typing import Optional, Tuple, List, Dict, Any, Set
from email_validator import validate_email, EmailNotValidError

# Common disposable email provider domains
DISPOSABLE_DOMAINS: Set[str] = {
    "mailinator.com", "guerrillamail.com", "tempmail.com", "10minutemail.com",
    "throwawaymail.com", "getairmail.com", "dispostable.com", "trashmail.com",
    "yopmail.com", "sharklasers.com", "grr.la", "guerrillamail.biz",
    "guerrillamail.de", "guerrillamail.net", "guerrillamail.org", "fakeinbox.com",
    "inboxkitten.com", "burnermail.io", "temp-mail.org", "mohmal.com",
    "crazymailing.com", "mytemp.email", "nada.ltd", "emailondeck.com",
    "tempinbox.com", "maildrop.cc", "getnada.com", "dropmail.me"
}

# Common generic role-based / department email prefixes
ROLE_BASED_PREFIXES: Set[str] = {
    "info", "contact", "support", "sales", "help", "admin", "office",
    "general", "service", "billing", "inquiry", "inquiries", "mail",
    "marketing", "press", "media", "team", "careers", "jobs", "hr",
    "hello", "frontdesk", "reservation", "reservations", "booking", "bookings",
    "feedback", "webmaster", "security", "accounting", "finance"
}

EMAIL_REGEX = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
)

# In-memory cache for domain DNS validation (domain -> is_valid_dns)
_DNS_CACHE: Dict[str, bool] = {}

def check_domain_dns(domain: str, timeout: float = 3.0) -> bool:
    """Verifies that the email domain actually resolves to an IP address."""
    clean_domain = domain.strip().lower()
    if clean_domain in _DNS_CACHE:
        return _DNS_CACHE[clean_domain]

    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        socket.getaddrinfo(clean_domain, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        _DNS_CACHE[clean_domain] = True
        return True
    except Exception:
        _DNS_CACHE[clean_domain] = False
        return False
    finally:
        socket.setdefaulttimeout(old_timeout)

def validate_email_address(
    raw_email: str,
    check_dns: bool = False,
    allow_disposable: bool = False
) -> Tuple[bool, Optional[str], Optional[str], str]:
    """
    Validates and normalizes an email address.
    
    Checks:
    1. Basic syntax and length restrictions.
    2. RFC compliance via email_validator.
    3. Disposable email domain detection.
    4. Optional domain DNS existence check.
    5. Role-based vs Direct personal email classification.
    
    Returns:
        (is_valid: bool, normalized_email: str or None, error_reason: str or None, email_type: str)
        where email_type is 'DIRECT', 'ROLE_BASED', or 'DISPOSABLE'
    """
    if not raw_email or str(raw_email).strip().lower() in ('n/a', 'none', 'null', ''):
        return False, None, "Email address is empty or N/A", "UNKNOWN"

    clean_em = str(raw_email).strip().lower()

    # Strip prefixes like 'email:', 'mailto:'
    clean_em = re.sub(r'^(?:mailto|email|e-mail|mail)\:?', '', clean_em).strip(' /:,')

    # Basic sanity regex check
    if not EMAIL_REGEX.match(clean_em):
        return False, None, f"Invalid email format: '{clean_em}'", "UNKNOWN"

    # RFC validation via email_validator
    try:
        val = validate_email(clean_em, check_deliverability=False)
        normalized = val.normalized.lower()
        domain = val.domain.lower()
        local_part = val.local_part.lower()
    except EmailNotValidError as e:
        # Fallback to normalized regex
        if '@' in clean_em:
            parts = clean_em.split('@', 1)
            normalized = clean_em
            local_part = parts[0]
            domain = parts[1]
        else:
            return False, None, f"Email syntax error: {e}", "UNKNOWN"

    # Check disposable domain
    if domain in DISPOSABLE_DOMAINS:
        if not allow_disposable:
            return False, None, f"Rejected: disposable email provider '{domain}'", "DISPOSABLE"
        return True, normalized, None, "DISPOSABLE"

    # Check domain DNS if requested
    if check_dns and not check_domain_dns(domain):
        return False, None, f"Domain '{domain}' does not resolve to an active host", "UNKNOWN"

    # Classify email type
    email_type = "DIRECT"
    if local_part in ROLE_BASED_PREFIXES or any(local_part.startswith(p + ".") or local_part.startswith(p + "-") for p in ROLE_BASED_PREFIXES):
        email_type = "ROLE_BASED"

    return True, normalized, None, email_type

def is_valid_email(raw_email: str, check_dns: bool = False) -> bool:
    """Convenience boolean check for email validity."""
    is_val, _, _, _ = validate_email_address(raw_email, check_dns=check_dns)
    return is_val

def extract_and_normalize_emails(
    text: str,
    check_dns: bool = False,
    allow_disposable: bool = False
) -> List[Dict[str, Any]]:
    """
    Extracts all candidate email addresses from arbitrary text and normalizes them.
    Returns a deduplicated list of dicts:
    [{'email': 'contact@example.com', 'type': 'ROLE_BASED', 'domain': 'example.com'}]
    """
    if not text:
        return []

    raw_matches = EMAIL_REGEX.findall(text)
    found = []
    seen = set()

    for raw in raw_matches:
        is_val, norm, _, em_type = validate_email_address(
            raw,
            check_dns=check_dns,
            allow_disposable=allow_disposable
        )
        if is_val and norm and norm not in seen:
            seen.add(norm)
            domain = norm.split('@')[1] if '@' in norm else ""
            found.append({
                "email": norm,
                "type": em_type,
                "domain": domain
            })

    return found
