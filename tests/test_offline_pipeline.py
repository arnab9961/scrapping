from pathlib import Path
import pytest
from services.extractor import extract_leads_from_html
from services.scorer import compute_lead_score
from services.deduplicator import DuplicateDetector
from services.database import save_qualified_lead, get_leads, init_db

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

def test_offline_corporate_directory_pipeline():
    init_db()
    html_file = FIXTURES_DIR / "corporate_directory.html"
    assert html_file.exists()
    html_content = html_file.read_text(encoding="utf-8")

    leads = extract_leads_from_html(html_content, "https://bttoa.org.bd/members")
    assert len(leads) >= 3

    detector = DuplicateDetector()

    # Lead 1: Local BD company
    lead1 = leads[0]
    assert "Meghna" in lead1["business_name"]
    assert lead1["contact_person"] == "Md. Kamrul Hasan"
    assert "Managing Director" in lead1["designation"]
    assert lead1["phone"] == "+8801799887766"
    assert lead1["phone_type"] == "MOBILE"
    assert lead1["email"] == "kamrul@meghnaaviation.com"
    assert lead1["linkedin_url"] == "https://www.linkedin.com/company/bttoa-official"

    score1, _, _ = compute_lead_score(lead1)
    assert score1 >= 80

    is_dup1, _ = detector.check_duplicate(lead1)
    assert is_dup1 is False
    detector.record_lead(lead1)

    # Lead 3: International entry (+1 US phone)
    intl_lead = next(l for l in leads if "+14155552671" in l["phone"])
    assert intl_lead["business_name"] == "International Tour Coordinators Corp"
    assert intl_lead["contact_person"] == "David Miller"
    assert intl_lead["phone"] == "+14155552671"
    assert intl_lead["email"] == "david.miller@intltourcoordinators.com"
    assert intl_lead["email_type"] == "DIRECT"

    # Verify saving international lead into database
    lead_id = save_qualified_lead(intl_lead)
    assert lead_id > 0

def test_offline_hotel_profile_pipeline():
    init_db()
    html_file = FIXTURES_DIR / "hotel_profile.html"
    assert html_file.exists()
    html_content = html_file.read_text(encoding="utf-8")

    leads = extract_leads_from_html(html_content, "https://sunsetseabreeze.com")
    assert len(leads) >= 1
    lead = leads[0]

    assert lead["business_name"] == "Sunset Sea Breeze Resort"
    assert "Engr. Subhash Barua" in lead["contact_person"]
    assert lead["phone"] == "+8801755667788"
    assert lead["linkedin_url"] == "https://www.linkedin.com/company/sunsetseabreeze"
    assert lead["twitter_url"] == "https://twitter.com/sunsetseabreeze"
    assert lead["instagram_url"] == "https://instagram.com/sunsetseabreeze"

    # Multi-contact secondary channels
    assert len(lead["secondary_phones"]) >= 1
    assert len(lead["secondary_emails"]) >= 1

    score, breakdown, issues = compute_lead_score(lead)
    assert score >= 85
    assert "social_links" in breakdown
