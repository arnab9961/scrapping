import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import time
import json
from services.extractor import extract_leads_from_html
from services.scorer import compute_lead_score
from services.deduplicator import DuplicateDetector
from services.database import init_db, save_qualified_lead
from validators.phone import normalize_phone
from validators.email import validate_email_address

def run_verification():
    init_db()
    print("=" * 70)
    print("🚀 PHASE 4: LEAD PIPELINE VERIFICATION RUN (Sample: 25 Leads)")
    print("=" * 70)

    fixtures_dir = Path("tests/fixtures")
    corp_html = (fixtures_dir / "corporate_directory.html").read_text(encoding="utf-8")
    hotel_html = (fixtures_dir / "hotel_profile.html").read_text(encoding="utf-8")

    # Generate test corpus combining multi-format fixtures and realistic test pages
    raw_pages = [
        ("https://bttoa.org.bd/members", corp_html),
        ("https://grandpalacekuakata.com/contact", hotel_html),
    ]

    detector = DuplicateDetector()
    all_raw_leads = []

    start_time = time.perf_counter()

    for url, html in raw_pages:
        extracted = extract_leads_from_html(html, url)
        all_raw_leads.extend(extracted)

    # Add additional synthetic diverse variations to reach 25 leads representing diverse industries
    synthetic_corpus = [
        {
            "business_name": "Bengal Horizon Eco Tourism",
            "contact_person": "Engr. Mahmudur Rahman",
            "designation": "Managing Director",
            "phone": "+8801711224466",
            "email": "mahmud@bengalhorizon.com",
            "website": "https://bengalhorizon.com",
            "address": "Banani, Dhaka",
            "city": "Dhaka",
            "country": "Bangladesh",
            "source_url": "https://bengalhorizon.com",
            "linkedin_url": "https://linkedin.com/company/bengalhorizon"
        },
        {
            "business_name": "Bengal Horizon Eco Tourism Ltd", # Intentional fuzzy duplicate
            "contact_person": "Mahmud Rahman",
            "designation": "MD",
            "phone": "+8801711224466", # Exact phone dup
            "email": "mahmud@bengalhorizon.com",
            "website": "https://bengalhorizon.com",
            "address": "Dhaka",
            "city": "Dhaka",
            "country": "Bangladesh",
            "source_url": "https://bengalhorizon.com"
        },
        {
            "business_name": "Dhaka Premier Travels & Leisure",
            "contact_person": "Nusrat Jahan",
            "designation": "Director Operations",
            "phone": "+88029530427", # BTCL Landline
            "email": "info@dhakapremier.com",
            "website": "https://dhakapremier.com",
            "address": "Motijheel C/A, Dhaka",
            "city": "Dhaka",
            "country": "Bangladesh",
            "source_url": "https://dhakapremier.com",
            "facebook_url": "https://facebook.com/dhakapremier"
        },
        {
            "business_name": "Pacific Gateway Tour Logistics Pte Ltd",
            "contact_person": "Tan Wei Ming",
            "designation": "Regional Vice President",
            "phone": "+6567891234", # Singapore Landline/Corp
            "email": "weiming.tan@pacificgateway.sg",
            "website": "https://pacificgateway.sg",
            "address": "Marina Bay, Singapore",
            "city": "Singapore",
            "country": "Singapore",
            "source_url": "https://pacificgateway.sg",
            "linkedin_url": "https://linkedin.com/company/pacific-gateway"
        },
        {
            "business_name": "Pacific Gateway Tour Logistics Pte", # Fuzzy duplicate
            "contact_person": "Tan Wei Ming",
            "designation": "VP",
            "phone": "+6567891234",
            "email": "weiming.tan@pacificgateway.sg",
            "website": "https://pacificgateway.sg",
            "address": "Singapore",
            "city": "Singapore",
            "country": "Singapore",
            "source_url": "https://pacificgateway.sg"
        },
        {
            "business_name": "Spam Lead Junk Generator",
            "contact_person": "Contact Person",
            "designation": "Executive",
            "phone": "00000000000", # Invalid dummy phone
            "email": "invalid@@junk..com", # Invalid email
            "website": "http://junk.com",
            "address": "Nowhere",
            "city": "Unknown",
            "country": "Bangladesh",
            "source_url": "http://junk.com"
        },
        {
            "business_name": "Disposable Lead Inc",
            "contact_person": "Bot User",
            "designation": "Tester",
            "phone": "N/A",
            "email": "tempuser@10minutemail.com", # Disposable email
            "website": "http://disposable.com",
            "address": "N/A",
            "city": "Dhaka",
            "country": "Bangladesh",
            "source_url": "http://disposable.com"
        },
        {
            "business_name": "Kuakata Ocean Sands Resort",
            "contact_person": "Md. Tariqul Islam",
            "designation": "General Manager",
            "phone": "+8801733445566",
            "email": "gm@oceansandskuakata.com",
            "website": "https://oceansandskuakata.com",
            "address": "Kuakata Beach Road",
            "city": "Kuakata",
            "country": "Bangladesh",
            "source_url": "https://oceansandskuakata.com",
            "facebook_url": "https://facebook.com/oceansands"
        },
        {
            "business_name": "Cox's Bazar Sea Breeze Suites",
            "contact_person": "Syed Farhan Ali",
            "designation": "Managing Director",
            "phone": "+8801844556677",
            "email": "farhan@seabreezesuites.com",
            "website": "https://seabreezesuites.com",
            "address": "Marine Drive, Cox's Bazar",
            "city": "Cox's Bazar",
            "country": "Bangladesh",
            "source_url": "https://seabreezesuites.com",
            "linkedin_url": "https://linkedin.com/company/seabreeze-suites"
        },
        {
            "business_name": "Sundarbans Eco Cruise Lines",
            "contact_person": "Captain Anisur Rahman",
            "designation": "CEO",
            "phone": "+8801955667788",
            "email": "anis@sundarbansecocruise.com",
            "website": "https://sundarbansecocruise.com",
            "address": "Mongla Port, Khulna",
            "city": "Khulna",
            "country": "Bangladesh",
            "source_url": "https://sundarbansecocruise.com"
        },
        {
            "business_name": "Apex Global Travel Network Ltd",
            "contact_person": "Shahidul Karim",
            "designation": "Director",
            "phone": "+8801766778899",
            "email": "shahid@apexglobaltravel.com",
            "website": "https://apexglobaltravel.com",
            "address": "Gulshan-1, Dhaka",
            "city": "Dhaka",
            "country": "Bangladesh",
            "source_url": "https://apexglobaltravel.com",
            "linkedin_url": "https://linkedin.com/company/apex-global-travel"
        },
        {
            "business_name": "Sylhet Tea Garden Resort & Spa",
            "contact_person": "Dr. Humayun Kabir",
            "designation": "Founder & Chairman",
            "phone": "+8801877889900",
            "email": "humayun@sylhettearesort.com",
            "website": "https://sylhettearesort.com",
            "address": "Sreemangal, Sylhet",
            "city": "Sylhet",
            "country": "Bangladesh",
            "source_url": "https://sylhettearesort.com"
        },
        {
            "business_name": "UK Corporate Heritage Tours Ltd",
            "contact_person": "Robert Sterling",
            "designation": "Managing Director",
            "phone": "+442079460912", # UK London Landline
            "email": "r.sterling@ukcorporateheritage.co.uk",
            "website": "https://ukcorporateheritage.co.uk",
            "address": "Fleet Street, London",
            "city": "London",
            "country": "United Kingdom",
            "source_url": "https://ukcorporateheritage.co.uk",
            "linkedin_url": "https://linkedin.com/company/uk-corporate-heritage"
        },
        {
            "business_name": "Euro-Asia Travel Link GmbH",
            "contact_person": "Klaus Schneider",
            "designation": "Head of Partnerships",
            "phone": "+4930123456", # German Landline
            "email": "schneider@euroasiatravel.de",
            "website": "https://euroasiatravel.de",
            "address": "Friedrichstraße, Berlin",
            "city": "Berlin",
            "country": "Germany",
            "source_url": "https://euroasiatravel.de",
            "linkedin_url": "https://linkedin.com/company/euro-asia-travel"
        },
        {
            "business_name": "Middle East Express Holidays LLC",
            "contact_person": "Rashid Al-Falasi",
            "designation": "General Manager",
            "phone": "+97143123456", # Dubai Landline
            "email": "falasi@meexpressholidays.ae",
            "website": "https://meexpressholidays.ae",
            "address": "Sheikh Zayed Road, Dubai",
            "city": "Dubai",
            "country": "UAE",
            "source_url": "https://meexpressholidays.ae"
        },
        {
            "business_name": "Chittagong Maritime Travel Corp",
            "contact_person": "M. A. Matin",
            "designation": "Managing Director",
            "phone": "+88031612345", # Chittagong Landline
            "email": "matin@ctgmaritime.com",
            "website": "https://ctgmaritime.com",
            "address": "Agrabad C/A, Chittagong",
            "city": "Chittagong",
            "country": "Bangladesh",
            "source_url": "https://ctgmaritime.com"
        },
        {
            "business_name": "Padma River Luxury Cruises",
            "contact_person": "Nasim Akhtar",
            "designation": "Chief Operating Officer",
            "phone": "+8801555667788",
            "email": "nasim@padmacruises.com",
            "website": "https://padmacruises.com",
            "address": "Sadarghat, Dhaka",
            "city": "Dhaka",
            "country": "Bangladesh",
            "source_url": "https://padmacruises.com"
        },
        {
            "business_name": "Golden Bengal Hospitality Services",
            "contact_person": "Abul Kashem",
            "designation": "Managing Partner",
            "phone": "+8801666778899",
            "email": "kashem@goldenbengalhospitality.com",
            "website": "https://goldenbengalhospitality.com",
            "address": "Uttara, Dhaka",
            "city": "Dhaka",
            "country": "Bangladesh",
            "source_url": "https://goldenbengalhospitality.com"
        },
        {
            "business_name": "Himalayan Treks & Expedition Nepal",
            "contact_person": "Pemba Sherpa",
            "designation": "Lead Expedition Director",
            "phone": "+97714412345", # Nepal
            "email": "pemba@himalayantreks.np",
            "website": "https://himalayantreks.np",
            "address": "Thamel, Kathmandu",
            "city": "Kathmandu",
            "country": "Nepal",
            "source_url": "https://himalayantreks.np"
        },
        {
            "business_name": "Aroma Tea Valley Cottages",
            "contact_person": "Monira Begum",
            "designation": "Proprietor",
            "phone": "+8801788990011",
            "email": "monira@aromateavalley.com",
            "website": "https://aromateavalley.com",
            "address": "Jaflong, Sylhet",
            "city": "Sylhet",
            "country": "Bangladesh",
            "source_url": "https://aromateavalley.com"
        },
        {
            "business_name": "Barisal Riverine Eco Lodge",
            "contact_person": "Jashim Uddin",
            "designation": "Resident Manager",
            "phone": "+8801899001122",
            "email": "jashim@barisalecolodge.com",
            "website": "https://barisalecolodge.com",
            "address": "Kirtankhola, Barisal",
            "city": "Barisal",
            "country": "Bangladesh",
            "source_url": "https://barisalecolodge.com"
        }
    ]

    all_raw_leads.extend(synthetic_corpus)
    total_input = len(all_raw_leads)

    qualified = []
    duplicates = []
    invalid_records = []

    for lead in all_raw_leads:
        # Check duplicate
        is_dup, dup_reason = detector.check_duplicate(lead)
        if is_dup:
            duplicates.append((lead, dup_reason))
            continue
        detector.record_lead(lead)

        # Phone validation (E.164 + BD mobile + landline)
        raw_p = lead.get("phone", "N/A")
        val_p, norm_p, _, p_type = normalize_phone(raw_p, allow_landline=True)
        if val_p:
            lead["phone"] = norm_p
            lead["phone_type"] = p_type
        else:
            lead["phone_type"] = "INVALID"

        # Email validation
        raw_e = lead.get("email", "N/A")
        val_e, norm_e, _, e_type = validate_email_address(raw_e)
        if val_e:
            lead["email"] = norm_e
            lead["email_type"] = e_type
        else:
            lead["email_type"] = "INVALID"

        # Filter out records where both phone and email are unusable or disposable
        if (not val_p and not val_e) or e_type == "DISPOSABLE":
            invalid_records.append((lead, "Both phone & email unusable or disposable"))
            continue

        # Score completeness
        score, breakdown, _ = compute_lead_score(lead)
        lead["completeness_score"] = score
        lead["completeness_breakdown"] = breakdown

        qualified.append(lead)

    duration = time.perf_counter() - start_time
    leads_per_min = (total_input / duration) * 60 if duration > 0 else 0

    # Calculate column completeness on qualified leads
    N = len(qualified)
    completeness = {
        "business_name": sum(1 for l in qualified if l.get("business_name") and l["business_name"] != "N/A") / N * 100,
        "contact_person": sum(1 for l in qualified if l.get("contact_person") and l["contact_person"] not in ("N/A", "Contact Person")) / N * 100,
        "designation": sum(1 for l in qualified if l.get("designation") and l["designation"] not in ("N/A", "Executive")) / N * 100,
        "phone (usable E.164)": sum(1 for l in qualified if l.get("phone") and l["phone"].startswith("+")) / N * 100,
        "phone_type (classified)": sum(1 for l in qualified if l.get("phone_type") in ("MOBILE", "FIXED_LINE", "VOIP")) / N * 100,
        "email (valid RFC)": sum(1 for l in qualified if l.get("email") and "@" in l["email"]) / N * 100,
        "email_type (classified)": sum(1 for l in qualified if l.get("email_type") in ("DIRECT", "ROLE_BASED")) / N * 100,
        "website / domain": sum(1 for l in qualified if l.get("website") and l["website"].startswith("http")) / N * 100,
        "social_links (any)": sum(1 for l in qualified if l.get("linkedin_url") or l.get("facebook_url")) / N * 100,
    }

    avg_score = sum(l["completeness_score"] for l in qualified) / N if N else 0

    print(f"\n📊 EXECUTION BENCHMARKS:")
    print(f"Total Leads Processed:     {total_input}")
    print(f"Processing Time:           {duration:.2f} seconds")
    print(f"Throughput Speed:          {leads_per_min:.0f} leads/minute")
    print(f"Qualified Usable Leads:    {len(qualified)} ({len(qualified)/total_input*100:.1f}%)")
    print(f"Duplicates Detected:       {len(duplicates)} (Fuzzy & Exact)")
    print(f"Invalid/Junk Rejected:     {len(invalid_records)} (Dummy numbers, disposable emails)")
    print(f"Average Completeness Score:{avg_score:.1f} / 100")

    print(f"\n📋 FIELD COMPLETENESS PERCENTAGES:")
    for col, pct in completeness.items():
        bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
        print(f"  {col:<26} [{bar}] {pct:>5.1f}%")

    print(f"\n🔍 DUPLICATE EXAMPLES DETECTED:")
    for dup, r in duplicates[:3]:
        print(f"  - Rejected '{dup.get('business_name')}': {r}")

    print(f"\n🚫 INVALID/JUNK EXAMPLES DETECTED:")
    for inv, r in invalid_records[:3]:
        print(f"  - Rejected '{inv.get('business_name')}' (Phone: {inv.get('phone')}, Email: {inv.get('email')}): {r}")

if __name__ == "__main__":
    run_verification()
