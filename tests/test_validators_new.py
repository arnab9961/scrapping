import pytest
from validators.phone import normalize_phone, extract_and_normalize_phones, normalize_bd_phone
from validators.email import validate_email_address, extract_and_normalize_emails
from validators.domain import normalize_url, get_canonical_domain, is_valid_domain

def test_global_phone_normalization():
    # US number
    is_val, norm, _, p_type = normalize_phone("+1 415-555-2671", default_country="US")
    assert is_val is True
    assert norm == "+14155552671"

    # UK number
    is_val_uk, norm_uk, _, _ = normalize_phone("+44 20 7183 8750", default_country="GB")
    assert is_val_uk is True
    assert norm_uk == "+442071838750"

    # Bangladesh mobile
    is_val_bd, norm_bd, _, p_type_bd = normalize_phone("01712345678", default_country="BD")
    assert is_val_bd is True
    assert norm_bd == "+8801712345678"
    assert p_type_bd == "MOBILE"

    # Bangladesh landline with allow_landline=True
    is_val_land, norm_land, _, p_type_land = normalize_phone("+88029530427", default_country="BD", allow_landline=True)
    assert is_val_land is True
    assert norm_land == "+88029530427"
    assert p_type_land == "FIXED_LINE"

    # Rejection of IP and invalid
    is_val_ip, _, _, _ = normalize_phone("192.168.1.1", default_country="US")
    assert is_val_ip is False

def test_email_validation():
    # Direct personal email
    is_val, norm, _, em_type = validate_email_address("John.Doe@company.com")
    assert is_val is True
    assert norm == "john.doe@company.com"
    assert em_type == "DIRECT"

    # Role-based email
    is_val_role, norm_role, _, em_type_role = validate_email_address("info@domain.com")
    assert is_val_role is True
    assert norm_role == "info@domain.com"
    assert em_type_role == "ROLE_BASED"

    # Disposable email rejection
    is_val_disp, _, err_disp, em_type_disp = validate_email_address("spammer@mailinator.com")
    assert is_val_disp is False
    assert em_type_disp == "DISPOSABLE"

    # Invalid email syntax
    is_val_inv, _, _, _ = validate_email_address("not-an-email")
    assert is_val_inv is False

def test_domain_normalization():
    # URL normalization and tracking parameter stripping
    url = "https://example.com/contact?utm_source=google&utm_medium=cpc&fbclid=12345&id=99#team"
    cleaned = normalize_url(url, strip_tracking=True)
    assert "utm_source" not in cleaned
    assert "fbclid" not in cleaned
    assert "id=99" in cleaned
    assert "#team" not in cleaned

    # Canonical domain extraction
    assert get_canonical_domain("https://sub.portal.example.co.uk/page") == "example.co.uk"
    assert get_canonical_domain("https://www.google.com/search") == "google.com"
    assert get_canonical_domain("https://hotel-kuakata.com.bd/") == "hotel-kuakata.com.bd"

    # Domain validity
    assert is_valid_domain("example.com") is True
    assert is_valid_domain("sub.example.co.uk") is True
    assert is_valid_domain("invalid_domain..com") is False
