import json
import logging
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import config
from agent import stream_leads_generator, stream_url_leads_generator, fallback_heuristic_search
from validators.phone import normalize_bd_phone
from validators.url import validate_safe_url
from services.database import get_dashboard_stats, get_leads, get_rejected_leads
from services.job_manager import JobManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("app")

app = FastAPI(
    title="Sunset Group - Lead Scraping & AI Validation System",
    description="Intelligent Dual-Mode Scraping, Bangladesh Phone Normalization, and Groq AI Validation Platform",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Request Models
class SearchRequest(BaseModel):
    category: Optional[str] = None
    profession: Optional[str] = None
    city: str = Field(..., min_length=2, max_length=100)
    area: Optional[str] = None
    country: Optional[str] = "Bangladesh"
    target_leads: Optional[int] = Field(default=50, ge=1, le=5000)

class DirectUrlScrapeRequest(BaseModel):
    url: str
    crawl_pagination: Optional[bool] = True
    max_pages: Optional[int] = Field(default=5, ge=0, le=50)
    mode: Optional[str] = Field(default="auto", description="Scraping mode: auto, dynamic, or http")

class PhoneValidationRequest(BaseModel):
    phone: str

# HTML Page Routes
@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse({"message": "Frontend static/index.html not found."})
    return FileResponse(str(index_file))

@app.get("/url-scraper")
def serve_url_scraper():
    scraper_file = STATIC_DIR / "url_scraper.html"
    if not scraper_file.exists():
        return JSONResponse({"message": "Frontend static/url_scraper.html not found."})
    return FileResponse(str(scraper_file))

@app.get("/dashboard")
def serve_dashboard():
    dash_file = STATIC_DIR / "dashboard.html"
    if not dash_file.exists():
        return JSONResponse({"message": "Frontend static/dashboard.html not found."})
    return FileResponse(str(dash_file))

# System Health & Info
@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Sunset Group Lead Scraping & AI Validation System",
        "version": "3.0.0",
        "groq_configured": config.has_groq_credentials(),
        "model_name": config.MODEL_NAME,
        "database_connected": config.DB_PATH.exists()
    }

# Dashboard Analytics API
@app.get("/api/stats")
def get_stats():
    """Returns real-time scraping and validation statistics."""
    return get_dashboard_stats()

# Qualified Leads API
@app.get("/api/leads")
def list_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=5, le=100),
    search: str = Query("", description="Search by name, business, phone, email, or city"),
    industry: str = Query("", description="Filter by industry/category"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc")
):
    """Retrieves paginated qualified leads from the database."""
    leads, total = get_leads(
        page=page,
        page_size=page_size,
        search=search,
        industry=industry,
        sort_by=sort_by,
        sort_order=sort_order
    )
    return {
        "status": "success",
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 1,
        "leads": leads
    }

# Rejection Audit Log API
@app.get("/api/rejected-leads")
def list_rejected_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=5, le=100)
):
    """Retrieves paginated rejected leads and rejection reasons."""
    rejected, total = get_rejected_leads(page=page, page_size=page_size)
    return {
        "status": "success",
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 1,
        "rejected_leads": rejected
    }

# Jobs API
@app.get("/api/jobs")
def list_recent_jobs(limit: int = Query(10, ge=1, le=50)):
    return {
        "status": "success",
        "jobs": JobManager.get_recent_jobs(limit=limit)
    }

@app.get("/api/jobs/{job_id}")
def get_job_detail(job_id: str):
    job = JobManager.get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return {"status": "success", "job": job}

# Bangladesh Phone Validation Utility API
@app.post("/api/validate-phone")
def validate_phone(req: PhoneValidationRequest):
    is_valid, normalized, reason = normalize_bd_phone(req.phone)
    return {
        "input": req.phone,
        "is_valid": is_valid,
        "normalized_phone": normalized,
        "error_reason": reason
    }

# Real-Time SSE Stream: Search Leads
@app.get("/api/search/stream")
def stream_search(
    category: Optional[str] = Query(None),
    profession: Optional[str] = Query(None),
    city: str = Query(...),
    area: Optional[str] = Query(None),
    country: Optional[str] = Query("Bangladesh"),
    target: int = Query(50, ge=1, le=5000)
):
    target_category = (category or profession or "").strip()
    clean_city = city.strip()
    clean_area = (area or "").strip()
    clean_country = (country or "Bangladesh").strip()

    if not target_category or not clean_city:
        raise HTTPException(status_code=400, detail="Target Category and City are required.")

    loc_label = f"{clean_area}, {clean_city}, {clean_country}" if clean_area else f"{clean_city}, {clean_country}"
    job_id = JobManager.create_job("search", f"{target_category} in {loc_label}")

    def event_stream():
        try:
            for event in stream_leads_generator(
                city=clean_city,
                category=target_category,
                target_count=target,
                area=clean_area,
                country=clean_country,
                job_id=job_id
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Error in search stream: {e}")
            JobManager.complete_job(job_id, status="failed", error_message=str(e))
            err_event = {"type": "error", "job_id": job_id, "message": str(e)}
            yield f"data: {json.dumps(err_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# Real-Time SSE Stream: Direct URL Scraper
@app.get("/api/scrape-url/stream")
def stream_url_scrape(
    url: str = Query(..., description="Target webpage URL to scrape"),
    crawl_pagination: bool = Query(True),
    max_pages: int = Query(5, ge=0, le=50),
    mode: Optional[str] = Query("auto", description="Scraping mode: auto, dynamic, or http")
):
    target_url = url.strip()
    if not target_url:
        raise HTTPException(status_code=400, detail="Target URL is required.")

    is_safe, clean_url, ssrf_err = validate_safe_url(target_url)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {ssrf_err}")

    scrape_mode = (mode or "auto").strip().lower()
    if scrape_mode not in ("auto", "dynamic", "http"):
        scrape_mode = "auto"

    job_id = JobManager.create_job("direct_url", f"{clean_url} [{scrape_mode}]")

    def event_stream():
        try:
            for event in stream_url_leads_generator(
                clean_url,
                crawl_pagination=crawl_pagination,
                max_pages=max_pages,
                mode=scrape_mode,
                job_id=job_id
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Error in URL scrape stream: {e}")
            JobManager.complete_job(job_id, status="failed", error_message=str(e))
            err_event = {"type": "error", "job_id": job_id, "message": str(e)}
            yield f"data: {json.dumps(err_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# Non-Streaming Fallback Endpoints
@app.post("/api/search")
def search_leads_sync(req: SearchRequest):
    target_category = (req.category or req.profession or "").strip()
    clean_city = req.city.strip()
    clean_area = (req.area or "").strip()
    clean_country = (req.country or "Bangladesh").strip()
    target_goal = req.target_leads or 50

    if not target_category or not clean_city:
        raise HTTPException(status_code=400, detail="Target Category and City are required.")

    leads, queries = fallback_heuristic_search(
        city=clean_city,
        category=target_category,
        target_count=target_goal,
        area=clean_area,
        country=clean_country
    )

    return {
        "status": "success",
        "category": target_category,
        "city": clean_city,
        "total_leads": len(leads),
        "leads": leads,
        "queries_executed": queries
    }

@app.post("/api/scrape-url")
def scrape_url_sync(req: DirectUrlScrapeRequest):
    is_safe, clean_url, ssrf_err = validate_safe_url(req.url)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Invalid URL: {ssrf_err}")

    scrape_mode = (req.mode or "auto").strip().lower()
    leads = []
    for event in stream_url_leads_generator(clean_url, crawl_pagination=req.crawl_pagination, max_pages=req.max_pages, mode=scrape_mode):
        if event.get("type") == "lead":
            leads.append(event["data"])

    return {
        "status": "success",
        "url": clean_url,
        "mode": scrape_mode,
        "total_leads": len(leads),
        "leads": leads
    }

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", "8001"))
    print(f"\n🌅 Sunset Group Lead Scraping & AI Validation System: http://127.0.0.1:{port}")
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
