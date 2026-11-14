"""
Sunset Group Core Services
"""
from .database import (
    init_db,
    save_qualified_lead,
    log_rejected_lead,
    log_validation_history,
    is_duplicate_lead,
    get_dashboard_stats,
    get_leads,
    get_rejected_leads
)
from .deduplicator import DuplicateDetector
from .scraper import adaptive_scrape, ScrapeResult
from .extractor import extract_leads_from_html
from .ai_validator import validate_lead_with_ai
from .job_manager import JobManager

__all__ = [
    "init_db",
    "save_qualified_lead",
    "log_rejected_lead",
    "log_validation_history",
    "is_duplicate_lead",
    "get_dashboard_stats",
    "get_leads",
    "get_rejected_leads",
    "DuplicateDetector",
    "adaptive_scrape",
    "ScrapeResult",
    "extract_leads_from_html",
    "validate_lead_with_ai",
    "JobManager"
]

