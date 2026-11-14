import sqlite3
import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import config

def get_db_connection() -> sqlite3.Connection:
    """Creates a sqlite3 connection with Row factory and proper pragmas."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """Initializes database tables, columns, and indexes."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Main Qualified Leads Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT NOT NULL,
            contact_person TEXT,
            designation TEXT,
            industry TEXT,
            phone TEXT NOT NULL,
            email TEXT,
            website TEXT,
            canonical_domain TEXT,
            address TEXT,
            city TEXT,
            country TEXT DEFAULT 'Bangladesh',
            ai_confidence_score INTEGER,
            ai_validation_reason TEXT,
            ai_recommended_action TEXT,
            scraping_mode TEXT DEFAULT 'http',
            render_fallback_used INTEGER DEFAULT 0,
            source_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 2. Rejection Log Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rejected_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT,
            contact_person TEXT,
            phone TEXT,
            email TEXT,
            website TEXT,
            source_url TEXT,
            rejection_stage TEXT NOT NULL,
            reason TEXT NOT NULL,
            issues TEXT,
            ai_confidence_score INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 3. AI Validation History Table (Audit Trail)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS validation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_identifier TEXT,
            prompt_summary TEXT,
            raw_ai_response TEXT,
            is_valid INTEGER NOT NULL,
            confidence_score INTEGER,
            recommended_action TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 4. Scraping Jobs Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS scraping_jobs (
            job_id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            target TEXT NOT NULL,
            status TEXT DEFAULT 'running',
            total_scraped INTEGER DEFAULT 0,
            qualified_count INTEGER DEFAULT 0,
            rejected_count INTEGER DEFAULT 0,
            duplicate_count INTEGER DEFAULT 0,
            http_count INTEGER DEFAULT 0,
            playwright_count INTEGER DEFAULT 0,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP,
            error_message TEXT
        );
        """)

        # Indexes for fast duplicate lookups & querying
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_domain ON leads(canonical_domain);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_business ON leads(business_name);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at);")

        conn.commit()

def extract_canonical_domain(url: str) -> str:
    """Extracts lowercase clean domain name (e.g. 'example.com')."""
    if not url or url.strip().lower() in ('n/a', 'none', ''):
        return ""
    try:
        clean = url.strip()
        if not clean.startswith(('http://', 'https://')):
            clean = 'http://' + clean
        from urllib.parse import urlparse
        netloc = urlparse(clean).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc.split(':')[0]
    except Exception:
        return ""

def is_duplicate_lead(
    phone: Optional[str] = None,
    email: Optional[str] = None,
    website: Optional[str] = None,
    business_name: Optional[str] = None,
    contact_person: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Checks if this lead is already in the database using:
    - Normalized phone match
    - Normalized email match
    - Person Name + Business Name / Domain match
    
    Returns (is_dup, reason_string)
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Match by Phone
        if phone and phone != "N/A":
            digits = re.sub(r'\D', '', phone)
            if len(digits) >= 8:
                cursor.execute("SELECT id, business_name, contact_person FROM leads WHERE phone = ? LIMIT 1", (phone,))
                row = cursor.fetchone()
                if row:
                    return True, f"Duplicate phone '{phone}' already registered for '{row['contact_person']}' at '{row['business_name']}' (ID #{row['id']})"

        # 2. Match by Email
        if email and email.strip().lower() not in ('n/a', 'none', ''):
            clean_email = email.strip().lower()
            cursor.execute("SELECT id, business_name, contact_person FROM leads WHERE LOWER(email) = ? LIMIT 1", (clean_email,))
            row = cursor.fetchone()
            if row:
                return True, f"Duplicate email '{clean_email}' already registered for '{row['contact_person']}' at '{row['business_name']}' (ID #{row['id']})"

        # 3. Match by Person Name + Business Name or Domain (prevents duplicate person records)
        clean_pname = (contact_person or "").strip().lower()
        clean_bname = (business_name or "").strip().lower()
        domain = extract_canonical_domain(website or "")

        if clean_pname and len(clean_pname) > 3 and clean_pname not in ('contact person', 'representative', 'n/a'):
            if clean_bname and clean_bname not in ('organization', 'direct url lead', 'n/a', 'company', 'lead'):
                cursor.execute("SELECT id FROM leads WHERE LOWER(contact_person) = ? AND LOWER(business_name) = ? LIMIT 1", (clean_pname, clean_bname))
                row = cursor.fetchone()
                if row:
                    return True, f"Duplicate record: '{contact_person}' at '{business_name}' already exists (ID #{row['id']})"

            if domain and len(domain) > 4:
                cursor.execute("SELECT id FROM leads WHERE LOWER(contact_person) = ? AND canonical_domain = ? LIMIT 1", (clean_pname, domain))
                row = cursor.fetchone()
                if row:
                    return True, f"Duplicate record: '{contact_person}' on domain '{domain}' already exists (ID #{row['id']})"

    return False, None

def save_qualified_lead(data: Dict[str, Any]) -> int:
    """Inserts a qualified, AI-validated lead into the 'leads' table."""
    canonical_domain = extract_canonical_domain(data.get("website") or data.get("source_url") or "")
    
    # Enforce strict phone validation at the database boundary
    raw_phone = data.get("phone") or "N/A"
    clean_phone = "N/A"
    if raw_phone and str(raw_phone).strip().lower() not in ("n/a", "none", "null", ""):
        from validators.phone import normalize_bd_phone
        is_val, norm_p, _ = normalize_bd_phone(raw_phone)
        if is_val and norm_p:
            clean_phone = norm_p

    clean_email = data.get("email") or "N/A"
    if clean_phone == "N/A" and (not clean_email or clean_email == "N/A" or "@" not in clean_email):
        raise ValueError("Cannot save lead without valid Bangladesh mobile phone (+8801...) or email")
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO leads (
            business_name, contact_person, designation, industry,
            phone, email, website, canonical_domain, address, city, country,
            ai_confidence_score, ai_validation_reason, ai_recommended_action,
            scraping_mode, render_fallback_used, source_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("business_name") or data.get("organization") or "Business",
            data.get("contact_person") or data.get("name") or "Contact Person",
            data.get("designation") or "Executive",
            data.get("industry") or data.get("category") or "Hospitality & Corporate",
            clean_phone,
            clean_email,
            data.get("website") or "N/A",
            canonical_domain,
            data.get("address") or "N/A",
            data.get("city") or "Dhaka",
            data.get("country") or "Bangladesh",
            int(data.get("ai_confidence_score", data.get("confidence_score", 0))),
            data.get("ai_validation_reason") or data.get("reason") or "",
            data.get("ai_recommended_action") or data.get("recommended_action") or "accept",
            data.get("scraping_mode") or "http",
            1 if data.get("render_fallback_used") else 0,
            data.get("source_url") or ""
        ))
        conn.commit()
        return cursor.lastrowid

def log_rejected_lead(data: Dict[str, Any]) -> int:
    """Logs a rejected lead into the 'rejected_leads' table for debugging and audits."""
    issues = data.get("issues", [])
    issues_str = json.dumps(issues, ensure_ascii=False) if isinstance(issues, (list, dict)) else str(issues)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO rejected_leads (
            business_name, contact_person, phone, email, website, source_url,
            rejection_stage, reason, issues, ai_confidence_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("business_name") or data.get("organization") or "N/A",
            data.get("contact_person") or data.get("name") or "N/A",
            data.get("phone") or "N/A",
            data.get("email") or "N/A",
            data.get("website") or "N/A",
            data.get("source_url") or "",
            data.get("rejection_stage") or "validation",
            data.get("reason") or "Failed validation rules",
            issues_str,
            int(data.get("ai_confidence_score") or data.get("confidence_score") or 0)
        ))
        conn.commit()
        return cursor.lastrowid

def log_validation_history(data: Dict[str, Any]) -> int:
    """Logs AI validation call result into 'validation_history'."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO validation_history (
            lead_identifier, prompt_summary, raw_ai_response,
            is_valid, confidence_score, recommended_action
        ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            data.get("lead_identifier") or "",
            data.get("prompt_summary") or "",
            data.get("raw_ai_response") or "",
            1 if data.get("is_valid") else 0,
            int(data.get("confidence_score") or 0),
            data.get("recommended_action") or ""
        ))
        conn.commit()
        return cursor.lastrowid

def create_scraping_job(job_id: str, job_type: str, target: str):
    """Initializes a new scraping job record."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO scraping_jobs (
            job_id, job_type, target, status, started_at
        ) VALUES (?, ?, ?, 'running', CURRENT_TIMESTAMP)
        """, (job_id, job_type, target))
        conn.commit()

def update_scraping_job(job_id: str, **kwargs):
    """Updates job progress and counts."""
    if not kwargs:
        return
    fields = []
    values = []
    for k, v in kwargs.items():
        fields.append(f"{k} = ?")
        values.append(v)
    values.append(job_id)
    query = f"UPDATE scraping_jobs SET {', '.join(fields)} WHERE job_id = ?"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(values))
        conn.commit()

def get_scraping_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves job status."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scraping_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_dashboard_stats() -> Dict[str, Any]:
    """Computes comprehensive dashboard metrics."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Qualified leads count
        cursor.execute("SELECT COUNT(*) FROM leads")
        qualified_leads = cursor.fetchone()[0]

        # Rejected leads count
        cursor.execute("SELECT COUNT(*) FROM rejected_leads")
        rejected_leads = cursor.fetchone()[0]

        # Duplicate count from rejected_leads
        cursor.execute("SELECT COUNT(*) FROM rejected_leads WHERE rejection_stage = 'duplicate'")
        duplicate_leads = cursor.fetchone()[0]

        # Total scraped prospects
        total_scraped = qualified_leads + rejected_leads

        # AI validation success rate
        cursor.execute("SELECT COUNT(*) FROM validation_history")
        total_ai_checks = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM validation_history WHERE is_valid = 1")
        valid_ai_checks = cursor.fetchone()[0]
        ai_success_rate = round((valid_ai_checks / total_ai_checks * 100), 1) if total_ai_checks > 0 else 0.0

        # Scraping mode counts
        cursor.execute("SELECT COUNT(*) FROM leads WHERE scraping_mode = 'http'")
        http_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM leads WHERE scraping_mode = 'playwright'")
        playwright_count = cursor.fetchone()[0]

        # Jobs metrics
        cursor.execute("SELECT COUNT(*) FROM scraping_jobs WHERE status = 'running'")
        current_jobs = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM scraping_jobs WHERE status = 'failed'")
        failed_jobs = cursor.fetchone()[0]

        return {
            "total_scraped": total_scraped,
            "qualified_leads": qualified_leads,
            "rejected_leads": rejected_leads,
            "duplicate_leads": duplicate_leads,
            "ai_validation_rate": ai_success_rate,
            "http_scraping_count": http_count,
            "playwright_scraping_count": playwright_count,
            "current_scraping_jobs": current_jobs,
            "failed_scraping_jobs": failed_jobs
        }

def get_leads(
    page: int = 1,
    page_size: int = 25,
    search: str = "",
    industry: str = "",
    sort_by: str = "created_at",
    sort_order: str = "desc"
) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves paginated qualified leads with search and sort."""
    offset = max(0, (page - 1) * page_size)
    allowed_sort_fields = {"created_at", "business_name", "ai_confidence_score", "city", "industry"}
    sort_field = sort_by if sort_by in allowed_sort_fields else "created_at"
    sort_direction = "ASC" if sort_order.lower() == "asc" else "DESC"

    conditions = []
    params = []

    if search.strip():
        term = f"%{search.strip()}%"
        conditions.append("(business_name LIKE ? OR contact_person LIKE ? OR phone LIKE ? OR email LIKE ? OR city LIKE ?)")
        params.extend([term, term, term, term, term])

    if industry.strip():
        conditions.append("industry LIKE ?")
        params.append(f"%{industry.strip()}%")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get total count
        cursor.execute(f"SELECT COUNT(*) FROM leads {where_clause}", tuple(params))
        total = cursor.fetchone()[0]

        # Get rows
        query = f"""
        SELECT * FROM leads
        {where_clause}
        ORDER BY {sort_field} {sort_direction}
        LIMIT ? OFFSET ?
        """
        cursor.execute(query, tuple(params + [page_size, offset]))
        rows = [dict(r) for r in cursor.fetchall()]

        return rows, total

def get_rejected_leads(page: int = 1, page_size: int = 25) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieves paginated rejected leads."""
    offset = max(0, (page - 1) * page_size)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM rejected_leads")
        total = cursor.fetchone()[0]

        cursor.execute("""
        SELECT * FROM rejected_leads
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """, (page_size, offset))
        rows = [dict(r) for r in cursor.fetchall()]
        return rows, total

# Initialize DB on module import
init_db()

