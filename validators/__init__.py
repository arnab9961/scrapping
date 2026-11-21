"""
Lead Validation and Normalization Package.
Provides validators for Phone (global E.164 + BD), Email (RFC, DNS, Disposable, Role),
Domain & URL normalization, and SSRF security defense.
"""
from .phone import (
    normalize_bd_phone,
    is_valid_bd_phone,
    extract_and_normalize_bd_phones,
    normalize_phone,
    extract_and_normalize_phones
)
from .email import (
    validate_email_address,
    is_valid_email,
    extract_and_normalize_emails
)
from .domain import (
    normalize_url,
    get_canonical_domain,
    is_valid_domain
)
from .url import validate_safe_url, is_safe_url

__all__ = [
    "normalize_bd_phone",
    "is_valid_bd_phone",
    "extract_and_normalize_bd_phones",
    "normalize_phone",
    "extract_and_normalize_phones",
    "validate_email_address",
    "is_valid_email",
    "extract_and_normalize_emails",
    "normalize_url",
    "get_canonical_domain",
    "is_valid_domain",
    "validate_safe_url",
    "is_safe_url"
]
