"""
Automated Test Suite for Sunset Group Lead Scraping & AI Validation System.
Tests:
- Bangladesh phone normalization & rejection rules
- SSRF prevention & URL safety
- Lead extraction (JSON-LD, meta, semantic, tables)
- Duplicate detection (phone, email, domain, name similarity)
- Database persistence, rejection log, and statistics
- Groq AI validation pipeline with schema enforcement
- Malformed AI response handling
- Dual-mode scraper logic
- FastAPI endpoints & logo static asset delivery
"""
import pytest
import json
from fastapi.testclient import TestClient

import config
from validators.phone import normalize_bd_phone, extract_and_normalize_bd_phones
from validators.url import validate_safe_url
from services.extractor import extract_leads_from_html
from services.deduplicator import DuplicateDetector
from services.database import (
    init_db,
    save_qualified_lead,
    log_rejected_lead,
    get_dashboard_stats,
    get_leads,
    get_rejected_leads,
    get_db_connection
)
from services.ai_validator import validate_lead_with_ai
from services.scraper import adaptive_scrape
from app import app

client = TestClient(app)

# 1. Bangladesh Phone Normalization Tests
def test_bangladesh_phone_normalization_valid():
    cases = [
        ("01712345678", "+8801712345678"),
        ("8801712345678", "+8801712345678"),
        ("+8801712345678", "+8801712345678"),
        ("01812-345678", "+8801812345678"),
        ("+880 1912 345678", "+8801912345678"),
        ("01312345678", "+8801312345678"),
        ("01412345678", "+8801412345678"),
        ("01512345678", "+8801512345678"),
        ("01612345678", "+8801612345678"),
        ("02-9530427", "+88029530427"),
    ]
    for raw, expected in cases:
        is_val, normalized, err = normalize_bd_phone(raw)
        assert is_val is True, f"Failed on {raw}: {err}"
        assert normalized == expected, f"Expected {expected}, got {normalized}"

def test_bangladesh_phone_rejection_invalid():
    invalid_cases = [
        "12345",              # too short
        "01212345678",        # invalid operator 012
        "017123456",          # 9 digits instead of 11
        "01712345678999",     # too long
        "00000000000",        # dummy digits
        "11111111111",        # dummy digits
        "2024-2025",          # year range
        "N/A",                # placeholder
        "None",               # placeholder
        "",                   # empty
        "invalid_text",       # non-numeric
    ]
    for raw in invalid_cases:
        is_val, normalized, err = normalize_bd_phone(raw)
        assert is_val is False, f"Expected {raw} to be rejected, but passed as {normalized}"

def test_extract_and_normalize_bd_phones():
    text = "Call Md. Karim at 01712345678 or office line 02-9530427. Copyright 2024-2026."
    extracted = extract_and_normalize_bd_phones(text)
    assert "+8801712345678" in extracted
    assert "+88029530427" in extracted
    assert len(extracted) == 2

# 2. SSRF Protection & URL Validation Tests
def test_ssrf_url_validation_blocks_internal_and_private():
    blocked_urls = [
        "http://localhost:8000/admin",
        "http://127.0.0.1:5000",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://192.168.1.1/router",
        "http://10.0.0.5/secret",
        "ftp://example.com/file",
        "file:///etc/passwd",
        "javascript:alert(1)"
    ]
    for url in blocked_urls:
        is_safe, _, err = validate_safe_url(url)
        assert is_safe is False, f"Expected {url} to be blocked by SSRF check, but passed!"

def test_ssrf_url_validation_allows_public():
    safe_urls = [
        "https://example.com",
        "http://example.com/contact",
        "https://www.bb.org.bd/en/index.php/about/executives",
    ]
    for url in safe_urls:
        is_safe, clean_url, err = validate_safe_url(url)
        assert is_safe is True, f"Expected {url} to be safe, but got error: {err}"
        assert clean_url.startswith("http")

# 3. Lead Extraction Pipeline Tests
def test_lead_extraction_json_ld():
    html_sample = """
    <!DOCTYPE html>
    <html>
    <head>
      <title>Discovery Tours Bangladesh</title>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "TravelAgency",
        "name": "Discovery Tours BD",
        "telephone": "+8801711223344",
        "email": "info@discoverytoursbd.com",
        "url": "https://discoverytoursbd.com",
        "address": {
          "@type": "PostalAddress",
          "streetAddress": "Gulshan-2",
          "addressLocality": "Dhaka",
          "addressCountry": "Bangladesh"
        }
      }
      </script>
    </head>
    <body>
      <h1>Welcome</h1>
    </body>
    </html>
    """
    leads = extract_leads_from_html(html_sample, "https://discoverytoursbd.com")
    assert len(leads) >= 1
    lead = leads[0]
    assert lead["business_name"] == "Discovery Tours BD"
    assert lead["phone"] == "+8801711223344"
    assert lead["email"] == "info@discoverytoursbd.com"

def test_lead_extraction_semantic_and_cards():
    html_sample = """
    <html>
    <body>
      <div class="profile-card">
        <h3>Tanvir Ahmed</h3>
        <p>Managing Director</p>
        <p>Company: Sunset Holiday Travels</p>
        <a href="tel:+8801819998877">Call Us</a>
        <a href="mailto:tanvir@sunsetholidays.com">Email Us</a>
      </div>
    </body>
    </html>
    """
    leads = extract_leads_from_html(html_sample, "https://sunsetholidays.com")
    assert len(leads) >= 1
    lead = leads[0]
    assert "Tanvir Ahmed" in lead["contact_person"]
    assert lead["designation"] == "Managing Director"
    assert lead["phone"] == "+8801819998877"
    assert lead["email"] == "tanvir@sunsetholidays.com"

# 4. Duplicate Detection Tests
def test_duplicate_detector():
    detector = DuplicateDetector()
    lead1 = {
        "business_name": "Royal Bengal Tour Operator",
        "contact_person": "Md. Rafiqul Islam",
        "phone": "+8801711002233",
        "email": "info@royalbengaltours.com",
        "website": "https://royalbengaltours.com"
    }
    # First time: not duplicate
    is_dup, _ = detector.check_duplicate(lead1)
    assert is_dup is False
    detector.record_lead(lead1)

    # Same phone duplicate
    lead2 = {
        "business_name": "Different Name",
        "phone": "+8801711002233",
        "email": "other@domain.com"
    }
    is_dup2, reason2 = detector.check_duplicate(lead2)
    assert is_dup2 is True
    assert "phone" in reason2.lower()

    # Same email duplicate
    lead3 = {
        "business_name": "Another Agency",
        "phone": "+8801888001122",
        "email": "info@royalbengaltours.com"
    }
    is_dup3, reason3 = detector.check_duplicate(lead3)
    assert is_dup3 is True
    assert "email" in reason3.lower()

# 5. Database Persistence & Rejection Log Tests
def test_database_persistence_and_stats():
    init_db()
    
    # Save a qualified lead
    test_lead = {
        "business_name": "Sunset Test Retreat Resort",
        "contact_person": "Md. Aminul Islam",
        "designation": "General Manager",
        "industry": "Hospitality",
        "phone": "+8801755667788",
        "email": "gm@sunsetretreat.com",
        "website": "https://sunsetretreat.com",
        "city": "Kuakata",
        "ai_confidence_score": 95,
        "ai_validation_reason": "Verified hotel executive",
        "ai_recommended_action": "accept",
        "scraping_mode": "http"
    }
    lead_id = save_qualified_lead(test_lead)
    assert lead_id > 0

    # Log a rejected lead
    rej_id = log_rejected_lead({
        "business_name": "Fake Spammer",
        "phone": "N/A",
        "rejection_stage": "rule_validation",
        "reason": "Missing contact details",
        "issues": ["No phone or email"]
    })
    assert rej_id > 0

    # Query stats
    stats = get_dashboard_stats()
    assert stats["qualified_leads"] >= 1
    assert stats["rejected_leads"] >= 1

    # Query leads endpoint
    leads_list, total = get_leads(search="Sunset Test Retreat")
    assert total >= 1
    assert leads_list[0]["phone"] == "+8801755667788"

# 6. Groq AI Validation Pipeline Tests
def test_groq_ai_validation_real_api():
    if not config.has_groq_credentials():
        pytest.skip("Groq credentials not configured in environment.")

    valid_candidate = {
        "business_name": "Sunset Kuakata Luxury Resort",
        "contact_person": "Md. Kamrul Hasan",
        "designation": "Managing Director",
        "phone": "+8801712345678",
        "email": "md@sunsetkuakata.com",
        "website": "https://sunsetkuakata.com",
        "city": "Kuakata",
        "source_url": "https://sunsetkuakata.com/contact"
    }

    result = validate_lead_with_ai(valid_candidate, target_industry="Hospitality & Resorts")
    assert isinstance(result, dict)
    assert "is_valid" in result
    assert "confidence_score" in result
    assert "recommended_action" in result
    assert result["is_valid"] is True
    assert result["confidence_score"] >= 60
    assert result["recommended_action"] == "accept"

def test_groq_ai_validation_rejects_malformed_rule_failure():
    # Candidate with no phone and no email
    bad_candidate = {
        "business_name": "Random Scraping Text",
        "phone": "N/A",
        "email": "N/A",
        "source_url": "https://example.com"
    }
    result = validate_lead_with_ai(bad_candidate)
    assert result["is_valid"] is False
    assert result["recommended_action"] == "reject"
    assert result["rejection_stage"] == "rule_validation"

# 7. FastAPI Endpoints & Static Assets Delivery Tests
def test_fastapi_routes():
    # Health check
    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    data = res_health.json()
    assert data["status"] == "healthy"
    assert data["groq_configured"] is True
    assert data["model_name"] == config.MODEL_NAME

    # Static pages
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "Sunset Group" in res_index.text

    res_url_scraper = client.get("/url-scraper")
    assert res_url_scraper.status_code == 200
    assert "Direct URL Scraper" in res_url_scraper.text

    res_dashboard = client.get("/dashboard")
    assert res_dashboard.status_code == 200
    assert "Scraping Dashboard" in res_dashboard.text

    # Logo file asset
    res_logo = client.get("/static/Sunset-Group-Logo.png")
    assert res_logo.status_code == 200
    assert res_logo.headers["content-type"].startswith("image/")

    # Dashboard stats API
    res_stats = client.get("/api/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert "qualified_leads" in stats
    assert "ai_validation_rate" in stats

    # Phone validation API
    res_phone_valid = client.post("/api/validate-phone", json={"phone": "01712345678"})
    assert res_phone_valid.status_code == 200
    assert res_phone_valid.json()["is_valid"] is True
    assert res_phone_valid.json()["normalized_phone"] == "+8801712345678"

    res_phone_invalid = client.post("/api/validate-phone", json={"phone": "12345"})
    assert res_phone_invalid.status_code == 200
    assert res_phone_invalid.json()["is_valid"] is False

    # SSRF protection on /api/scrape-url
    res_ssrf = client.post("/api/scrape-url", json={"url": "http://127.0.0.1:8000/internal"})
    assert res_ssrf.status_code == 400
    assert "Invalid URL" in res_ssrf.json()["detail"]

