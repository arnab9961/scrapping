# Sunset Group — Lead Scraping & AI Validation Platform

A reliable, intelligent, production-ready lead collection and AI validation system built for **Sunset Group** (**Sunset Kuakata Hotel & Resort**). 

The platform discovers high-value business prospects, decision-makers, tour coordinators, travel agencies, and corporate clients across Bangladesh and international markets using an adaptive dual-mode scraping engine, strict Bangladesh phone normalization, SSRF protection, multi-tier deduplication, and Groq-powered AI lead qualification.

---

## 🏛️ System Architecture & Data Flow

```mermaid
flowchart TD
    UI[Frontend: Vanilla HTML5 / CSS3 / ES6] -->|Search Query / Direct URL / Dashboard| API[FastAPI Backend: app.py]
    
    subgraph Security & Validation
        API -->|SSRF Check & Protocol Filtering| URLVal[validators/url.py]
        API -->|Bangladesh Phone (+880) Normalization| PhoneVal[validators/phone.py]
    end

    subgraph Scraping Engine
        URLVal --> DualEngine[services/scraper.py: Dual-Mode Engine]
        DualEngine -->|Mode A: Default| HTTPFetch[Scrapling Fetcher / httpx]
        HTTPFetch -->|Challenge / SPA Detected| Fallback[Mode B: Playwright Stealth Browser]
        HTTPFetch -->|Static HTML| Extractor[services/extractor.py: Multi-Technique Extractor]
        Fallback -->|Rendered DOM| Extractor
    end

    subgraph Extraction Pipeline
        Extractor -->|JSON-LD, Meta, Semantic tel/mailto, Tables| RawLeads[Candidate Leads]
    end

    subgraph Deduplication & AI Qualification
        RawLeads --> Dedup[services/deduplicator.py: Multi-Tier Detection]
        Dedup -->|Phone / Email / Domain / Similarity| DupRejected[Rejected: Duplicate]
        Dedup -->|Unique Candidate| PreRule[services/ai_validator.py: Rule Screening]
        PreRule -->|Malformed / Missing Contacts| RuleRejected[Rejected: Rule Failure]
        PreRule -->|Passed| GroqAI[Groq Cloud AI Model: openai/gpt-oss-120b]
        GroqAI -->|Strict JSON Schema & Confidence >= 60| Qualified[Qualified Leads]
        GroqAI -->|Confidence < 60 / Irrelevant| AIRejected[Rejected: AI Filter]
    end

    subgraph Database Storage & Audit
        Qualified -->|Saved to 'leads' Table| SQLite[(SQLite: data/sunset_leads.db)]
        DupRejected -->|Saved to 'rejected_leads' Table| SQLite
        RuleRejected -->|Saved to 'rejected_leads' Table| SQLite
        AIRejected -->|Saved to 'rejected_leads' Table| SQLite
        GroqAI -->|All Decisions Logged| History[(validation_history Table)]
        API -->|Job Status & Counters| Jobs[(scraping_jobs Table)]
    end

    subgraph Real-Time Streaming & Dashboard
        Qualified -->|Live SSE Stream| UI
        SQLite -->|REST API Analytics| Dashboard[Dashboard View]
    end
```

---

## 🌟 Key Features

1. **Intelligent Dual-Mode Scraping Engine (`services/scraper.py`)**:
   - **Mode A (HTTP)**: High-speed default mode using Scrapling's Chrome TLS impersonation and `httpx`.
   - **Mode B (Playwright Stealth Browser)**: Headless dynamic browser automation for JavaScript SPAs, lazy-loaded DOMs, and anti-bot challenge pages.
   - **Auto-Detection**: Dynamically analyzes page body length, SPA root markers (`<div id="root">`, `<div id="app">`), and challenge indicators to automatically upgrade to Playwright without manual intervention.

2. **Strict Bangladesh Phone Normalization (`validators/phone.py`)**:
   - All accepted Bangladesh numbers are standardized to international format: `+880XXXXXXXXXX`.
   - Supports mobile prefixes (`013`, `014`, `015`, `016`, `017`, `018`, `019`) and landline area codes (`02` for Dhaka, `031` for Chittagong, etc.).
   - Automatically cleans formatting spaces, dashes, dots, and parentheses.
   - Rejects fake numbers, year ranges (e.g. `2024-2026`), invalid lengths, and malformed prefixes.

3. **Groq-Powered AI Lead Validation (`services/ai_validator.py`)**:
   - Every lead is evaluated by Groq AI (`openai/gpt-oss-120b`) using a strict JSON schema.
   - Evaluates business legitimacy, industry relevance, phone validity, and contact completeness.
   - Conservative uncertainty handling: API errors or malformed AI outputs are **never** auto-accepted.
   - Rejections are logged to a separate audit table (`rejected_leads`) with stages and reasonings.

4. **Multi-Tier Duplicate Detection (`services/deduplicator.py`)**:
   - In-memory session tracking and SQLite database constraints.
   - Deduplicates by normalized phone, lowercase email, canonical domain, and business name similarity (>88%).

5. **Security & SSRF Prevention (`validators/url.py`)**:
   - Restricts schemes strictly to HTTP and HTTPS.
   - Resolves hostnames to verify IP addresses and blocks localhost (`127.0.0.1`), private subnets (`10.0.0.0/8`, `192.168.0.0/16`, `172.16.0.0/12`), and cloud metadata services (`169.254.169.254`).

6. **Sunset Group Branding & Dashboard (`static/`)**:
   - Incorporates the official `Sunset-Group-Logo.png` in the responsive header.
   - Comprehensive Scraping Dashboard showing total prospects, qualified leads, rejected leads, duplicate counts, AI validation rate, HTTP vs Playwright counts, and active jobs.
   - Searchable, sortable, paginated lead tables with CSV export.

---

## 📂 Project Structure

```
c:\projects\Scrapling\
├── .env                          # Local credentials (GROQ_CLOUD_API_KEY, MODEL_NAME)
├── .env.example                  # Environment template
├── Sunset-Group-Logo.png         # Official Sunset Group brand logo
├── requirements.txt              # Production Python dependencies
├── app.py                        # FastAPI application & REST/SSE routes
├── config.py                     # Secure configuration loader
├── agent.py                      # Lead generation orchestration engine
├── tools.py                      # Search, rate limiting, and robots.txt tools
├── scrape_contacts.py            # Backward-compatible CLI scraper utility
├── data/                         # Local database folder (auto-created, gitignored)
│   └── sunset_leads.db           # SQLite database with leads, rejected_leads, jobs
├── validators/
│   ├── __init__.py
│   ├── phone.py                  # Bangladesh phone validation & normalization (+880)
│   └── url.py                    # SSRF prevention & URL scheme validation
├── services/
│   ├── __init__.py
│   ├── database.py               # SQLite storage, CRUD, and dashboard aggregation
│   ├── scraper.py                # Intelligent dual-mode HTTP + Playwright scraper
│   ├── extractor.py              # Advanced JSON-LD, meta, semantic & text extractor
│   ├── deduplicator.py           # Multi-factor duplicate detection
│   ├── ai_validator.py           # Groq AI validation pipeline & audit logger
│   └── job_manager.py            # Job tracking & live counters
├── static/
│   ├── Sunset-Group-Logo.png     # Static brand logo for web pages
│   ├── index.html                # Search Leads page
│   ├── url_scraper.html          # Direct URL Scraper page
│   ├── dashboard.html            # Scraping Analytics & Lead Management Dashboard
│   ├── style.css                 # Clean, modern responsive stylesheet
│   ├── app.js                    # Search page frontend controller
│   ├── url_scraper.js            # URL scraper frontend controller
│   └── dashboard.js              # Dashboard metrics, table, filters, pagination & CSV
└── tests/
    ├── test_sunset_system.py     # 12 automated unit & integration tests
    └── test_scraper_modes.py     # 4 automated tests for dual-mode scraper
```

---

## ⚙️ Environment Variables

Configure your `.env` file in the project root:

```ini
# Groq Cloud API Configuration (Required for AI Lead Validation)
GROQ_CLOUD_API_KEY=gsk_your_groq_api_key_here
MODEL_NAME=openai/gpt-oss-120b
GROQ_BASE_URL=https://api.groq.com/openai/v1

# Optional Search APIs (Falls back to polite DuckDuckGo/Bing)
SERPAPI_API_KEY=
BRAVE_SEARCH_API_KEY=

# Settings
DEFAULT_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36
RATE_LIMIT_DELAY_SECONDS=1.0
MAX_AGENT_ITERATIONS=10
HTTP_TIMEOUT_SECONDS=10.0
PLAYWRIGHT_TIMEOUT_MS=15000
```

---

## 🚀 Installation & Startup Instructions

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
playwright install chromium
```

### 2. Run the Server
```powershell
python app.py
```
Or with Uvicorn:
```powershell
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Open in Browser
- **Search Leads**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Direct URL Scraper**: [http://127.0.0.1:8000/url-scraper](http://127.0.0.1:8000/url-scraper)
- **Scraping Dashboard**: [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard)

---

## 📡 API Endpoints Documentation

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serves Search Leads frontend |
| `GET` | `/url-scraper` | Serves Direct URL Scraper frontend |
| `GET` | `/dashboard` | Serves Scraping Analytics Dashboard |
| `GET` | `/api/health` | Health status and Groq AI model information |
| `GET` | `/api/stats` | Dashboard statistics (totals, qualified, rejected, modes, jobs) |
| `GET` | `/api/leads` | Paginated qualified leads with `search`, `sort_by`, `sort_order` |
| `GET` | `/api/rejected-leads` | Paginated rejected leads and audit logs |
| `GET` | `/api/jobs` | Recent scraping jobs status and execution metrics |
| `GET` | `/api/jobs/{job_id}` | Detailed metrics for a specific scraping job |
| `POST` | `/api/validate-phone` | Utility endpoint to validate and normalize a BD phone number |
| `GET` | `/api/search/stream` | Real-time SSE stream for keyword/matrix lead search |
| `POST` | `/api/search` | Synchronous REST search endpoint |
| `GET` | `/api/scrape-url/stream` | Real-time SSE stream for direct webpage URL scraping |
| `POST` | `/api/scrape-url` | Synchronous REST direct webpage scraping endpoint |

---

## 🧪 Running Automated Tests

Run the complete test suite:
```powershell
python -m pytest tests/test_sunset_system.py tests/test_scraper_modes.py -v
```

All 16 test cases verify:
- Bangladesh phone normalization (`017...` -> `+88017...`) and rejection of invalid prefixes/lengths.
- SSRF prevention blocking localhost, private subnets, and cloud metadata.
- JSON-LD, meta tag, and semantic link extraction.
- Duplicate detection across phone, email, domain, and similarity.
- Groq AI validation pipeline with strict JSON schema verification.
- Database persistence, rejection logs, and statistics queries.
- Dual-mode scraping (Mode A HTTP and Mode B Playwright SPA detection).
- FastAPI endpoints and static logo asset delivery.
