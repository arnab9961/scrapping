import pytest
from services.scorer import compute_lead_score
from services.deduplicator import DuplicateDetector, token_similarity
from services.database import save_qualified_lead, get_leads, init_db

def test_token_similarity():
    sim = token_similarity("Sunset Kuakata Resort", "Sunset Kuakata Hotel & Resort")
    assert sim >= 0.85
    sim_identical = token_similarity("Apex Footwear Ltd", "Apex Footwear Limited")
    assert sim_identical >= 0.80

def test_lead_completeness_scorer():
    rich_lead = {
        "business_name": "Royal Tulip Sea Pearl Beach Resort",
        "contact_person": "Md. Aminul Islam",
        "designation": "Managing Director",
        "phone": "+8801712345678",
        "phone_type": "MOBILE",
        "email": "md@seapearlbeachresort.com",
        "email_type": "DIRECT",
        "website": "https://seapearlbeachresort.com",
        "address": "Inani, Cox's Bazar",
        "city": "Cox's Bazar",
        "linkedin_url": "https://www.linkedin.com/company/seapearl"
    }
    score, breakdown, issues = compute_lead_score(rich_lead)
    assert score >= 85
    assert "phone" in breakdown
    assert "email" in breakdown
    assert "contact_person" in breakdown
    assert len(issues) == 0

    sparse_lead = {
        "business_name": "Unknown",
        "contact_person": "Contact Person",
        "phone": "N/A",
        "email": "N/A"
    }
    sparse_score, _, sparse_issues = compute_lead_score(sparse_lead)
    assert sparse_score < 30
    assert len(sparse_issues) >= 3

def test_fuzzy_duplicate_detection():
    detector = DuplicateDetector(fuzzy_threshold=0.85)
    lead1 = {
        "business_name": "Cox's Bazar Eco Resort Ltd",
        "contact_person": "Tanvir Rahman",
        "phone": "+8801811223344",
        "email": "tanvir@ecoresortbd.com",
        "website": "https://ecoresortbd.com"
    }
    is_dup1, _ = detector.check_duplicate(lead1)
    assert is_dup1 is False
    detector.record_lead(lead1)

    # Similar organization name on the same domain
    lead2 = {
        "business_name": "Cox's Bazar Eco Resort Limited",
        "contact_person": "Kamal Ahmed",
        "phone": "+8801999887766", # Different phone
        "email": "kamal@ecoresortbd.com", # Different email
        "website": "https://ecoresortbd.com" # Same domain
    }
    is_dup2, reason2 = detector.check_duplicate(lead2)
    assert is_dup2 is True
    assert "similar" in reason2.lower() or "organization" in reason2.lower()

def test_save_qualified_lead_with_international_and_landline():
    init_db()
    # International number saving (previously rejected by old code!)
    us_lead = {
        "business_name": "Global Horizon Tour Agency",
        "contact_person": "Sarah Connor",
        "designation": "Director",
        "phone": "+14155552671",
        "phone_type": "MOBILE",
        "email": "sarah@globalhorizontours.com",
        "website": "https://globalhorizontours.com",
        "city": "San Francisco",
        "country": "United States",
        "linkedin_url": "https://linkedin.com/company/globalhorizon",
        "secondary_phones": ["+14155552672"],
        "secondary_emails": ["info@globalhorizontours.com"]
    }
    lead_id = save_qualified_lead(us_lead)
    assert lead_id > 0

    rows, total = get_leads(search="Global Horizon")
    assert total >= 1
    saved = rows[0]
    assert saved["phone"] == "+14155552671"
    assert saved["completeness_score"] >= 80
