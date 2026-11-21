import re
import difflib
from typing import Dict, Any, Tuple, Optional, Set, List
from .database import is_duplicate_lead
from validators.domain import get_canonical_domain

def token_similarity(s1: str, s2: str) -> float:
    """
    Calculates token-sort sequence similarity between two strings (0.0 to 1.0).
    Normalizes punctuation and sorts word tokens before comparison to match
    variations like 'Apex Footwear Ltd' and 'Apex Footwear Limited'.
    """
    if not s1 or not s2:
        return 0.0
    tokens1 = sorted(re.findall(r'\w+', s1.lower()))
    tokens2 = sorted(re.findall(r'\w+', s2.lower()))
    if not tokens1 or not tokens2:
        return 0.0
    joined1 = ' '.join(tokens1)
    joined2 = ' '.join(tokens2)
    return difflib.SequenceMatcher(None, joined1, joined2).ratio()

class DuplicateDetector:
    """
    Session-aware and Database-backed multi-tier duplicate detector.
    
    Tiers:
    1. Exact normalized phone numbers (E.164 digits).
    2. Exact normalized emails (case-insensitive).
    3. Exact canonical domain uniqueness.
    4. Exact Person Name + Organization / Domain uniqueness.
    5. Fuzzy organization name similarity (>88%) on the same domain or city.
    """

    def __init__(self, fuzzy_threshold: float = 0.88):
        self.fuzzy_threshold = fuzzy_threshold
        self.seen_phones: Set[str] = set()
        self.seen_emails: Set[str] = set()
        self.seen_domains: Set[str] = set()
        self.seen_person_org: Set[Tuple[str, str]] = set()
        self.session_leads: List[Dict[str, str]] = []

    def check_duplicate(self, lead: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        phone = str(lead.get("phone") or "").strip()
        email = str(lead.get("email") or "").strip().lower()
        person = str(lead.get("contact_person") or lead.get("name") or "").strip()
        org = str(lead.get("business_name") or lead.get("organization") or "").strip()
        website = str(lead.get("website") or lead.get("source_url") or "").strip()
        domain = get_canonical_domain(website)

        # 1. Exact match on Phone
        if phone and phone != "N/A":
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 8 and digits in self.seen_phones:
                return True, f"Duplicate phone '{phone}' in current session"

        # 2. Exact match on Email
        if email and email not in ('n/a', 'none', ''):
            if email in self.seen_emails:
                return True, f"Duplicate email '{email}' in current session"

        # 3. Exact match on Person Name + Organization
        if person and len(person) > 3 and person.lower() not in ('contact person', 'representative', 'n/a'):
            key = (person.lower().strip(), org.lower().strip())
            if key in self.seen_person_org:
                return True, f"Duplicate person '{person}' at '{org}' in current session"

        # 4. Fuzzy match on Business Name within the same session
        if org and len(org) >= 4 and org.lower() not in ('business', 'organization', 'company', 'n/a', 'direct url lead'):
            for existing in self.session_leads:
                ex_org = existing.get("org", "")
                ex_domain = existing.get("domain", "")
                # If domains match or one domain is present
                if domain and ex_domain and domain == ex_domain:
                    sim = token_similarity(org, ex_org)
                    if sim >= self.fuzzy_threshold:
                        return True, f"Duplicate organization: '{org}' is similar ({int(sim*100)}%) to existing '{ex_org}' on {domain}"
                elif not domain or not ex_domain:
                    sim = token_similarity(org, ex_org)
                    if sim >= 0.94: # Stricter threshold if no domain cross-reference
                        return True, f"Fuzzy duplicate business name '{org}' ({int(sim*100)}% match to '{ex_org}')"

        # 5. Persistent Database Check
        is_db_dup, reason = is_duplicate_lead(
            phone=phone,
            email=email,
            website=website,
            business_name=org,
            contact_person=person
        )
        if is_db_dup:
            return True, reason

        return False, None

    def record_lead(self, lead: Dict[str, Any]):
        """Adds lead attributes to in-memory deduplication set."""
        phone = str(lead.get("phone") or "").strip()
        email = str(lead.get("email") or "").strip().lower()
        person = str(lead.get("contact_person") or lead.get("name") or "").strip()
        org = str(lead.get("business_name") or lead.get("organization") or "").strip()
        website = str(lead.get("website") or lead.get("source_url") or "").strip()
        domain = get_canonical_domain(website)

        if phone and phone != "N/A":
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 8:
                self.seen_phones.add(digits)

        if email and email not in ('n/a', 'none', ''):
            self.seen_emails.add(email)

        if domain:
            self.seen_domains.add(domain)

        if person and len(person) > 3 and person.lower() not in ('contact person', 'representative', 'n/a'):
            key = (person.lower().strip(), org.lower().strip())
            self.seen_person_org.add(key)

        if org:
            self.session_leads.append({
                "org": org,
                "person": person,
                "domain": domain
            })
