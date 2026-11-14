import re
from difflib import SequenceMatcher
from typing import Dict, Any, Tuple, Optional, Set
from .database import is_duplicate_lead, extract_canonical_domain

def string_similarity(a: str, b: str) -> float:
    """Calculates Levenshtein-like similarity ratio between 0.0 and 1.0."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

class DuplicateDetector:
    """
    Session-aware and Database-backed duplicate detector.
    Checks:
    1. Normalized phone numbers.
    2. Normalized emails.
    3. Canonical website domain.
    4. Business name similarity (>85% matching).
    """

    def __init__(self):
        self.seen_phones: Set[str] = set()
        self.seen_emails: Set[str] = set()
        self.seen_domains: Set[str] = set()
        self.seen_names: Set[str] = set()

    def check_duplicate(self, lead: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        phone = lead.get("phone") or ""
        email = lead.get("email") or ""
        website = lead.get("website") or lead.get("source_url") or ""
        business_name = lead.get("business_name") or lead.get("organization") or lead.get("name") or ""

        # 1. Check in-memory session cache for Phone
        if phone and phone != "N/A":
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 8:
                if digits in self.seen_phones:
                    return True, f"Duplicate phone '{phone}' in current session"

        # 2. Check in-memory session cache for Email
        if email and email.strip().lower() not in ('n/a', 'none', ''):
            clean_email = email.strip().lower()
            if clean_email in self.seen_emails:
                return True, f"Duplicate email '{clean_email}' in current session"

        # 3. Check in-memory session cache for Domain
        domain = extract_canonical_domain(website)
        generic_domains = {'facebook.com', 'google.com', 'linkedin.com', 'youtube.com', 'instagram.com', 'bb.org.bd', 'bdyellowpages.net'}
        if domain and domain not in generic_domains and len(domain) > 4:
            if domain in self.seen_domains:
                return True, f"Duplicate domain '{domain}' in current session"

        # 4. Check in-memory session cache for Business / Person name similarity
        if business_name and len(business_name.strip()) > 3:
            clean_name = business_name.strip().lower()
            if clean_name not in ('organization', 'direct url lead', 'n/a', 'company', 'contact person'):
                for existing in self.seen_names:
                    sim = string_similarity(clean_name, existing)
                    if sim >= 0.88:
                        return True, f"High name similarity ({int(sim*100)}%) with '{existing}' in current session"

        # 5. Check persistent Database records
        is_db_dup, reason = is_duplicate_lead(
            phone=phone,
            email=email,
            website=website,
            business_name=business_name
        )
        if is_db_dup:
            return True, reason

        return False, None

    def record_lead(self, lead: Dict[str, Any]):
        """Adds lead attributes to in-memory deduplication set."""
        phone = lead.get("phone") or ""
        email = lead.get("email") or ""
        website = lead.get("website") or lead.get("source_url") or ""
        business_name = lead.get("business_name") or lead.get("organization") or lead.get("name") or ""

        if phone and phone != "N/A":
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 8:
                self.seen_phones.add(digits)

        if email and email.strip().lower() not in ('n/a', 'none', ''):
            self.seen_emails.add(email.strip().lower())

        domain = extract_canonical_domain(website)
        generic_domains = {'facebook.com', 'google.com', 'linkedin.com', 'youtube.com', 'instagram.com', 'bb.org.bd', 'bdyellowpages.net'}
        if domain and domain not in generic_domains:
            self.seen_domains.add(domain)

        if business_name and len(business_name.strip()) > 3:
            clean_name = business_name.strip().lower()
            if clean_name not in ('organization', 'direct url lead', 'n/a', 'company', 'contact person'):
                self.seen_names.add(clean_name)

