import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from .database import create_scraping_job, update_scraping_job, get_scraping_job, get_db_connection

class JobManager:
    """Manages background scraping jobs, status updates, and progress counters."""

    @staticmethod
    def create_job(job_type: str, target: str) -> str:
        job_id = f"job_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        create_scraping_job(job_id, job_type, target)
        return job_id

    @staticmethod
    def update_progress(
        job_id: str,
        total_scraped: Optional[int] = None,
        qualified_count: Optional[int] = None,
        rejected_count: Optional[int] = None,
        duplicate_count: Optional[int] = None,
        http_count: Optional[int] = None,
        playwright_count: Optional[int] = None
    ):
        kwargs = {}
        if total_scraped is not None: kwargs["total_scraped"] = total_scraped
        if qualified_count is not None: kwargs["qualified_count"] = qualified_count
        if rejected_count is not None: kwargs["rejected_count"] = rejected_count
        if duplicate_count is not None: kwargs["duplicate_count"] = duplicate_count
        if http_count is not None: kwargs["http_count"] = http_count
        if playwright_count is not None: kwargs["playwright_count"] = playwright_count

        if kwargs:
            update_scraping_job(job_id, **kwargs)

    @staticmethod
    def complete_job(job_id: str, status: str = "completed", error_message: Optional[str] = None):
        finished_at = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        update_scraping_job(
            job_id,
            status=status,
            finished_at=finished_at,
            error_message=error_message
        )

    @staticmethod
    def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
        return get_scraping_job(job_id)

    @staticmethod
    def get_recent_jobs(limit: int = 10) -> List[Dict[str, Any]]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM scraping_jobs
            ORDER BY started_at DESC
            LIMIT ?
            """, (limit,))
            return [dict(r) for r in cursor.fetchall()]

