import re
from typing import Dict, Any, Tuple, Optional, Set
from .database import is_duplicate_lead

class DuplicateDetector:
    """
    Session-aware and Database-backed duplicate detector.
    Checks:
    1. Normalized phone numbers.
    2. Normalized emails.
    3. Person name + Organization / Domain uniqueness.
    """

    def __init__(self):
        self.seen_phones: Set[str] = set()
        self.seen_emails: Set[str] = set()
        self.seen_person_org: Set[Tuple[str, str]] = set()

    def check_duplicate(self, lead: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        phone = lead.get("phone") or ""
        email = lead.get("email") or ""
        person = lead.get("contact_person") or lead.get("name") or ""
        org = lead.get("business_name") or lead.get("organization") or ""

        # 1. Check in-memory session cache for Phone
        if phone and phone != "N/A":
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 8 and digits in self.seen_phones:
                return True, f"Duplicate phone '{phone}' in current session"

        # 2. Check in-memory session cache for Email
        if email and email.strip().lower() not in ('n/a', 'none', ''):
            clean_email = email.strip().lower()
            if clean_email in self.seen_emails:
                return True, f"Duplicate email '{clean_email}' in current session"

        # 3. Check in-memory session cache for Person Name + Organization
        if person and len(person) > 3 and person.lower() not in ('contact person', 'representative', 'n/a'):
            key = (person.lower().strip(), org.lower().strip())
            if key in self.seen_person_org:
                return True, f"Duplicate person '{person}' at '{org}' in current session"

        # 4. Check persistent Database records
        is_db_dup, reason = is_duplicate_lead(
            phone=phone,
            email=email,
            website=lead.get("website") or lead.get("source_url"),
            business_name=org,
            contact_person=person
        )
        if is_db_dup:
            return True, reason

        return False, None

    def record_lead(self, lead: Dict[str, Any]):
        """Adds lead attributes to in-memory deduplication set."""
        phone = lead.get("phone") or ""
        email = lead.get("email") or ""
        person = lead.get("contact_person") or lead.get("name") or ""
        org = lead.get("business_name") or lead.get("organization") or ""

        if phone and phone != "N/A":
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 8:
                self.seen_phones.add(digits)

        if email and email.strip().lower() not in ('n/a', 'none', ''):
            self.seen_emails.add(email.strip().lower())

        if person and len(person) > 3 and person.lower() not in ('contact person', 'representative', 'n/a'):
            key = (person.lower().strip(), org.lower().strip())
            self.seen_person_org.add(key)

