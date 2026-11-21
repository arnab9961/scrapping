from typing import Dict, Any, List, Tuple
import re

def compute_lead_score(lead: Dict[str, Any]) -> Tuple[int, Dict[str, Any], List[str]]:
    """
    Computes a deterministic completeness and quality score (0 to 100) for a lead record.
    
    Scoring weights:
    - Direct Contact Channels: up to 45 pts
      * Phone (verified/E.164): +25 pts (Mobile: 25, Fixed line: 20, Other: 15)
      * Email (valid RFC/domain): +20 pts (Direct personal: 20, Role-based: 15)
    - Person & Authority: up to 25 pts
      * Named person (not placeholder): +15 pts
      * Explicit designation (Director, MD, Founder, Manager): +10 pts
    - Digital Footprint & Web Presence: up to 15 pts
      * Canonical website / domain: +10 pts
      * Social media presence (LinkedIn, Facebook, etc.): +5 pts
    - Location & Business Identification: up to 15 pts
      * Clean business name: +10 pts
      * Physical address / city: +5 pts
      
    Returns:
        (total_score: int, breakdown: Dict[str, int], issues: List[str])
    """
    score = 0
    breakdown: Dict[str, int] = {}
    issues: List[str] = []

    # 1. Phone scoring
    phone = str(lead.get("phone") or "").strip()
    phone_type = str(lead.get("phone_type") or "").upper()
    if phone and phone != "N/A" and len(re.sub(r'\D', '', phone)) >= 7:
        if phone_type == "MOBILE":
            pts = 25
        elif phone_type == "FIXED_LINE":
            pts = 20
        else:
            pts = 15
        score += pts
        breakdown["phone"] = pts
    else:
        issues.append("Missing or unverified phone number")

    # 2. Email scoring
    email = str(lead.get("email") or "").strip().lower()
    email_type = str(lead.get("email_type") or "").upper()
    if email and email != "N/A" and "@" in email and "." in email:
        if email_type == "DIRECT":
            pts = 20
        elif email_type == "ROLE_BASED":
            pts = 15
        else:
            pts = 10
        score += pts
        breakdown["email"] = pts
    else:
        issues.append("Missing email address")

    # 3. Contact person scoring
    person = str(lead.get("contact_person") or lead.get("name") or "").strip()
    generic_person_words = {"contact person", "representative", "executive", "n/a", "none", "unknown"}
    if person and person.lower() not in generic_person_words and len(person) >= 3:
        score += 15
        breakdown["contact_person"] = 15
    else:
        issues.append("Generic or missing contact person name")

    # 4. Designation scoring
    designation = str(lead.get("designation") or "").strip()
    high_value_roles = {"director", "managing director", "ceo", "founder", "chairman", "president", "proprietor", "manager", "general manager", "head"}
    if designation and designation.lower() not in generic_person_words and len(designation) >= 2:
        if any(role in designation.lower() for role in high_value_roles):
            pts = 10
        else:
            pts = 6
        score += pts
        breakdown["designation"] = pts
    else:
        issues.append("Unspecified or generic designation")

    # 5. Website / Domain presence
    website = str(lead.get("website") or lead.get("canonical_domain") or "").strip()
    if website and website != "N/A" and len(website) >= 4:
        score += 10
        breakdown["website"] = 10
    else:
        issues.append("Missing company website")

    # 6. Social link presence
    has_social = bool(
        lead.get("linkedin_url") or
        lead.get("facebook_url") or
        lead.get("twitter_url") or
        lead.get("instagram_url") or
        lead.get("youtube_url")
    )
    if has_social:
        score += 5
        breakdown["social_links"] = 5

    # 7. Business name
    bname = str(lead.get("business_name") or lead.get("organization") or "").strip()
    generic_orgs = {"business", "organization", "company", "n/a", "none", "direct url lead"}
    if bname and bname.lower() not in generic_orgs and len(bname) >= 3:
        score += 10
        breakdown["business_name"] = 10
    else:
        issues.append("Generic or weak business name")

    # 8. Address / City
    address = str(lead.get("address") or lead.get("city") or "").strip()
    if address and address.lower() not in {"n/a", "none"} and len(address) >= 3:
        score += 5
        breakdown["location"] = 5

    total_score = max(0, min(100, score))
    return total_score, breakdown, issues
