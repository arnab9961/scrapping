import json
import urllib.parse
from typing import List, Dict, Any, Tuple, Generator, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import config
from tools import web_search, is_skippable_url, check_robots_txt, extract_pagination_links, extract_contact_subpages
from validators.phone import normalize_bd_phone, normalize_phone
from validators.url import validate_safe_url
from services.scraper import adaptive_scrape
from services.extractor import extract_leads_from_html
from services.deduplicator import DuplicateDetector
from services.ai_validator import validate_lead_with_ai
from services.job_manager import JobManager
from services.database import log_rejected_lead
from services.checkpoint import save_checkpoint, get_checkpoint, clear_checkpoint
from services.scorer import compute_lead_score

def generate_search_matrix(category: str, city: str, area: str = "", country: str = "Bangladesh") -> List[str]:
    """
    Constructs a highly focused, vertical-aware search matrix targeting business prospects,
    executives, and corporate decision-makers for Sunset Kuakata Hotel & Resort.
    """
    area_clean = (area or "").strip()
    city_clean = (city or "").strip()
    country_clean = (country or "Bangladesh").strip()

    local_target = f"{area_clean} {city_clean}".strip() if area_clean else city_clean
    is_bd = country_clean.lower() in ('bangladesh', 'bd')
    cat_lower = category.lower()

    # Core high-yield queries targeting decision makers and business contacts
    matrix = [
        f'{category} owner managing director {local_target} phone email',
        f'{category} companies in {local_target} {country_clean} contact phone',
        f'{category} directory member list {city_clean} {country_clean}',
        f'{category} corporate office {local_target} contact details',
    ]

    if is_bd:
        # Category-specific vertical directories
        if any(w in cat_lower for w in ['travel', 'tour', 'tourism', 'aviation', 'holiday', 'trip']):
            matrix.extend([
                f'travel agency association ATAB member list {local_target} contact phone',
                f'tour operators association TOAB directory {local_target} contact phone',
                f'site:atab.org.bd member list {city_clean}',
            ])
        elif any(w in cat_lower for w in ['garment', 'textile', 'apparel', 'buying house', 'fashion']):
            matrix.extend([
                f'garments buying house in {local_target} managing director phone',
                f'BGMEA member directory {local_target} phone',
            ])
        elif any(w in cat_lower for w in ['doctor', 'hospital', 'clinic', 'medical', 'pharma', 'health']):
            matrix.extend([
                f'specialist doctor directory in {local_target} contact mobile',
                f'hospital clinic chamber in {local_target} contact details phone',
            ])
        else:
            matrix.extend([
                f'site:bdtradeinfo.com {category} {local_target}',
                f'site:bangladeshbusinessdir.com {category} {local_target}',
                f'chamber of commerce DCCI member directory {city_clean} {category} phone',
            ])
    else:
        matrix.extend([
            f'{category} association member directory {local_target} {country_clean}',
            f'top {category} agencies {local_target} phone email website',
        ])

    return matrix

def stream_leads_generator(
    city: str,
    category: str,
    target_count: int = 100,
    area: str = "",
    country: str = "Bangladesh",
    job_id: Optional[str] = None
) -> Generator[Dict[str, Any], None, None]:
    """
    High-volume real-time lead generation engine with AI validation and dual-mode scraping.
    Streams validated leads directly via SSE.
    """
    loc_display = f"{area.strip()}, {city.strip()}" if area and area.strip() else city.strip()
    full_address = f"{loc_display}, {country.strip()}".strip(', ')

    # Initialize tracking job if not passed
    if not job_id:
        job_id = JobManager.create_job("search", f"{category} in {loc_display}")

    print(f"\n🚀 [Job: {job_id}] Search Lead Generation for '{category}' in '{loc_display}', '{country}' (Target: {target_count})")

    yield {
        "type": "progress",
        "job_id": job_id,
        "count": 0,
        "message": f"Initializing AI-validated lead search for {category} in {loc_display}..."
    }

    detector = DuplicateDetector()
    queries = generate_search_matrix(category, city, area=area, country=country)
    
    total_scraped = 0
    qualified_count = 0
    rejected_count = 0
    duplicate_count = 0
    http_count = 0
    playwright_count = 0

    executed_queries = []
    visited_urls = set()

    # Resume from checkpoint if available
    cp = get_checkpoint(job_id) if job_id else None
    start_q_idx = 1
    if cp:
        start_q_idx = int(cp.get("query_idx", 1))
        visited_urls.update(cp.get("visited_urls", []))
        qualified_count = int(cp.get("qualified_count", 0))
        print(f"⏩ Resuming job '{job_id}' from Query {start_q_idx} with {qualified_count} existing leads")

    for q_idx, q in enumerate(queries, 1):
        if q_idx < start_q_idx:
            continue
        if qualified_count >= target_count:
            break

        executed_queries.append(q)
        yield {
            "type": "progress",
            "job_id": job_id,
            "count": qualified_count,
            "message": f"Query [{q_idx}/{len(queries)}]: '{q}' (Harvested {qualified_count}/{target_count} qualified leads)..."
        }

        search_results = web_search(q, max_results=20)
        target_urls = []

        # Collect candidate URLs from search results
        for r in search_results:
            u = r.get("url", "")
            if u and not is_skippable_url(u) and u not in visited_urls:
                target_urls.append(u)

        # Filter against robots.txt and visited set
        valid_targets = []
        for target_url in target_urls:
            if target_url in visited_urls or is_skippable_url(target_url):
                continue
            visited_urls.add(target_url)
            if check_robots_txt(target_url):
                valid_targets.append(target_url)

        # Concurrently fetch candidate pages using bounded thread pool
        max_workers = min(getattr(config, "MAX_WORKERS", 6), len(valid_targets)) if valid_targets else 1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(adaptive_scrape, tu): tu for tu in valid_targets}
            for future in as_completed(future_to_url):
                if qualified_count >= target_count:
                    break
                target_url = future_to_url[future]
                try:
                    scrape_res = future.result()
                except Exception as e:
                    continue

                if scrape_res.scraping_mode == "playwright":
                    playwright_count += 1
                else:
                    http_count += 1

                if not scrape_res.html:
                    continue

                # Advanced extraction
                extracted = extract_leads_from_html(
                    html=scrape_res.html,
                    page_url=target_url,
                    default_category=category,
                    default_city=loc_display
                )

                # Check contact/about subpages if homepage yielded no leads or lacks person name
                if (len(extracted) == 0 or all(c.get("contact_person") == "Contact Person" for c in extracted)) and scrape_res.html:
                    sub_links = extract_contact_subpages(scrape_res.html, target_url, max_links=2)
                    for sub_u in sub_links:
                        if sub_u in visited_urls or not check_robots_txt(sub_u):
                            continue
                        visited_urls.add(sub_u)
                        sub_scrape = adaptive_scrape(sub_u)
                        if sub_scrape.html:
                            sub_extracted = extract_leads_from_html(
                                html=sub_scrape.html,
                                page_url=sub_u,
                                default_category=category,
                                default_city=loc_display
                            )
                            if sub_extracted:
                                if len(extracted) == 0:
                                    extracted = sub_extracted
                                else:
                                    for se in sub_extracted:
                                        if se.get("contact_person") != "Contact Person":
                                            extracted.append(se)
                                break

                for cand in extracted:
                    total_scraped += 1
                    cand["scraping_mode"] = scrape_res.scraping_mode
                    cand["render_fallback_used"] = scrape_res.render_fallback_used
                    cand["source_url"] = target_url

                    # Step 1: Duplicate check (Exact & Fuzzy)
                    is_dup, dup_reason = detector.check_duplicate(cand)
                    if is_dup:
                        duplicate_count += 1
                        rejected_count += 1
                        cand["rejection_stage"] = "duplicate"
                        cand["reason"] = dup_reason or "Duplicate lead"
                        log_rejected_lead(cand)
                        continue

                    # Record in detector
                    detector.record_lead(cand)

                    # Step 2: AI Validation Pipeline (Groq)
                    ai_eval = validate_lead_with_ai(cand, target_industry=category)

                    if ai_eval.get("is_valid") and ai_eval.get("recommended_action") == "accept":
                        # Multi-standard phone validation (BD mobile + Global E.164)
                        raw_p = cand.get("phone", "N/A")
                        final_phone = "N/A"
                        p_type = cand.get("phone_type", "UNKNOWN")
                        if raw_p and str(raw_p).strip().lower() not in ("n/a", "none", "null", ""):
                            is_v, norm_p, _ = normalize_bd_phone(raw_p)
                            if is_v and norm_p:
                                final_phone = norm_p
                                p_type = "MOBILE"
                            else:
                                is_vg, norm_g, _, g_type = normalize_phone(raw_p, allow_landline=getattr(config, "ALLOW_LANDLINE_PHONES", True))
                                if is_vg and norm_g:
                                    final_phone = norm_g
                                    p_type = g_type

                        final_email = cand.get("email", "N/A")
                        if final_phone == "N/A" and (not final_email or final_email == "N/A" or "@" not in final_email):
                            rejected_count += 1
                            continue

                        comp_score, _, _ = compute_lead_score(cand)
                        cand["completeness_score"] = comp_score

                        qualified_count += 1
                        lead_out = {
                            "name": cand.get("contact_person") or cand.get("name") or "Contact Person",
                            "business_name": cand.get("business_name") or cand.get("organization") or "Business",
                            "designation": cand.get("designation") or "Executive",
                            "organization": cand.get("business_name") or cand.get("organization") or "Business",
                            "category": category,
                            "address": cand.get("address") or full_address,
                            "city": loc_display,
                            "country": country.strip(),
                            "phone": final_phone,
                            "phone_type": p_type,
                            "email": final_email,
                            "email_type": cand.get("email_type", "UNKNOWN"),
                            "website": cand.get("website", target_url),
                            "canonical_domain": cand.get("canonical_domain", ""),
                            "linkedin_url": cand.get("linkedin_url", ""),
                            "facebook_url": cand.get("facebook_url", ""),
                            "twitter_url": cand.get("twitter_url", ""),
                            "secondary_phones": cand.get("secondary_phones", []),
                            "secondary_emails": cand.get("secondary_emails", []),
                            "completeness_score": comp_score,
                            "source_url": target_url,
                            "ai_confidence_score": ai_eval.get("confidence_score", 90),
                            "ai_validation_reason": ai_eval.get("reason", "Verified prospect"),
                            "scraping_mode": scrape_res.scraping_mode,
                            "render_fallback_used": scrape_res.render_fallback_used
                        }

                        JobManager.update_progress(
                            job_id,
                            total_scraped=total_scraped,
                            qualified_count=qualified_count,
                            rejected_count=rejected_count,
                            duplicate_count=duplicate_count,
                            http_count=http_count,
                            playwright_count=playwright_count
                        )

                        yield {
                            "type": "lead",
                            "job_id": job_id,
                            "data": lead_out,
                            "count": qualified_count
                        }

                        if qualified_count >= target_count:
                            break
                    else:
                        rejected_count += 1

        # Checkpoint after each completed query
        if job_id:
            save_checkpoint(job_id, {
                "query_idx": q_idx + 1,
                "visited_urls": list(visited_urls),
                "qualified_count": qualified_count
            })

        JobManager.update_progress(
            job_id,
            total_scraped=total_scraped,
            qualified_count=qualified_count,
            rejected_count=rejected_count,
            duplicate_count=duplicate_count,
            http_count=http_count,
            playwright_count=playwright_count
        )

    if job_id:
        clear_checkpoint(job_id)
    JobManager.complete_job(job_id, status="completed")

    print(f"\n🏁 Lead generation complete for job {job_id}. Qualified: {qualified_count}, Rejected: {rejected_count}, Duplicates: {duplicate_count}")
    yield {
        "type": "done",
        "job_id": job_id,
        "total": qualified_count,
        "rejected": rejected_count,
        "duplicates": duplicate_count,
        "queries": executed_queries
    }

def stream_url_leads_generator(
    target_url: str,
    crawl_pagination: bool = True,
    max_pages: int = 10,
    mode: str = "auto",
    job_id: Optional[str] = None
) -> Generator[Dict[str, Any], None, None]:
    """
    Direct URL Lead Scraper with SSRF protection, dual-mode scraping,
    pagination discovery, and Groq AI validation.
    
    Supports:
    - mode="auto": Fast HTTP with auto-upgrade to Playwright for SPAs / bot challenges
    - mode="dynamic": Forces Headless Stealth Chromium with full JavaScript execution & DOM hydration
    - mode="http": Fast static HTTP only
    """
    # 1. SSRF Check
    is_safe, clean_url, ssrf_err = validate_safe_url(target_url)
    if not is_safe:
        yield {
            "type": "error",
            "message": f"Security restriction: {ssrf_err}"
        }
        return

    # 1b. Robots.txt Compliance Check
    if not check_robots_txt(clean_url):
        if not job_id:
            job_id = JobManager.create_job("direct_url", clean_url)
        JobManager.complete_job(job_id, status="failed", error_message=f"Access disallowed by robots.txt on {clean_url}")
        yield {
            "type": "error",
            "job_id": job_id,
            "message": f"Crawling disallowed by robots.txt policy on {clean_url}"
        }
        return

    if not job_id:
        job_id = JobManager.create_job("direct_url", clean_url)

    print(f"\n🔗 [Job: {job_id}] Starting Direct URL Scrape for: {clean_url} (Mode: {mode})")

    if mode == "dynamic":
        yield {
            "type": "progress",
            "job_id": job_id,
            "count": 0,
            "message": f"🌐 Launching Headless Stealth Chromium to execute dynamic JavaScript & render DOM for {clean_url}..."
        }
    else:
        yield {
            "type": "progress",
            "job_id": job_id,
            "count": 0,
            "message": f"Connecting to {clean_url}..."
        }

    detector = DuplicateDetector()
    visited_urls = set()
    total_scraped = 0
    qualified_count = 0
    rejected_count = 0
    duplicate_count = 0
    http_count = 0
    playwright_count = 0

    visited_urls.add(clean_url)

    # 1. Scrape main page using adaptive engine
    scrape_res = adaptive_scrape(clean_url, force_browser=(mode == "dynamic"), mode=mode)
    if scrape_res.scraping_mode == "playwright":
        playwright_count += 1
    else:
        http_count += 1

    if not scrape_res.html:
        JobManager.complete_job(job_id, status="failed", error_message=scrape_res.error_message)
        yield {
            "type": "error",
            "job_id": job_id,
            "message": scrape_res.error_message or f"Could not fetch content from: {clean_url}"
        }
        return

    # Extract leads from main page
    main_leads = extract_leads_from_html(scrape_res.html, clean_url)

    # Dynamic fallback: If HTTP yielded 0 leads and mode != 'http', automatically upgrade to Playwright dynamic rendering!
    if len(main_leads) == 0 and scrape_res.scraping_mode != "playwright" and mode != "http":
        yield {
            "type": "progress",
            "job_id": job_id,
            "count": 0,
            "message": "⚡ Dynamic JavaScript SPA or protected content detected — launching Headless Chromium Browser..."
        }
        pw_res = adaptive_scrape(clean_url, force_browser=True, mode="dynamic")
        if pw_res.html:
            scrape_res = pw_res
            playwright_count += 1
            main_leads = extract_leads_from_html(pw_res.html, clean_url)

    if scrape_res.render_fallback_used or scrape_res.scraping_mode == "playwright":
        yield {
            "type": "progress",
            "job_id": job_id,
            "count": 0,
            "message": f"🛡️ Headless Browser rendered dynamic JavaScript successfully ({len(main_leads)} contact candidates detected)..."
        }

    try:
        domain_label = urllib.parse.urlparse(clean_url).netloc.replace('www.', '')
    except Exception:
        domain_label = "Directory"
    target_industry_label = f"Corporate & Commercial Directory ({domain_label})"

    def _evaluate_candidate(
        cand: Dict[str, Any],
        page_url: str,
        scrape_mode: str,
        render_fallback: bool
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        """Processes a lead candidate through deduplication and Groq AI validation."""
        nonlocal total_scraped, rejected_count, duplicate_count
        total_scraped += 1
        cand["scraping_mode"] = scrape_mode
        cand["render_fallback_used"] = render_fallback
        cand["source_url"] = page_url

        is_dup, dup_reason = detector.check_duplicate(cand)
        if is_dup:
            duplicate_count += 1
            if "already registered" in (dup_reason or "").lower():
                raw_p = cand.get("phone", "N/A")
                is_v, norm_p, _ = normalize_bd_phone(raw_p)
                lead_out = {
                    "name": cand.get("contact_person") or cand.get("name") or "Contact Person",
                    "business_name": cand.get("business_name") or cand.get("organization") or "Direct URL Lead",
                    "designation": cand.get("designation") or "Executive",
                    "organization": cand.get("business_name") or cand.get("organization") or "Direct URL Lead",
                    "category": "Direct Scrape",
                    "address": cand.get("address") or "N/A",
                    "city": cand.get("city") or "N/A",
                    "country": cand.get("country") or "Bangladesh",
                    "phone": norm_p if is_v and norm_p else "N/A",
                    "email": cand.get("email", "N/A"),
                    "website": cand.get("website", page_url),
                    "source_url": page_url,
                    "ai_confidence_score": cand.get("ai_confidence_score") or 90,
                    "ai_validation_reason": "Verified corporate lead (already registered in database)",
                    "scraping_mode": scrape_mode,
                    "render_fallback_used": render_fallback
                }
                return lead_out, True

            rejected_count += 1
            cand["rejection_stage"] = "duplicate"
            cand["reason"] = dup_reason or "Duplicate lead"
            log_rejected_lead(cand)
            return None, False

        detector.record_lead(cand)

        ai_eval = validate_lead_with_ai(cand, target_industry=target_industry_label)
        if ai_eval.get("is_valid") and ai_eval.get("recommended_action") == "accept":
            raw_p = cand.get("phone", "N/A")
            final_phone = "N/A"
            p_type = cand.get("phone_type", "UNKNOWN")
            if raw_p and str(raw_p).strip().lower() not in ("n/a", "none", "null", ""):
                is_v, norm_p, _ = normalize_bd_phone(raw_p)
                if is_v and norm_p:
                    final_phone = norm_p
                    p_type = "MOBILE"
                else:
                    is_vg, norm_g, _, g_type = normalize_phone(raw_p, allow_landline=getattr(config, "ALLOW_LANDLINE_PHONES", True))
                    if is_vg and norm_g:
                        final_phone = norm_g
                        p_type = g_type

            final_email = cand.get("email", "N/A")
            if final_phone == "N/A" and (not final_email or final_email == "N/A" or "@" not in final_email):
                rejected_count += 1
                return None, False

            comp_score, _, _ = compute_lead_score(cand)
            cand["completeness_score"] = comp_score

            lead_out = {
                "name": cand.get("contact_person") or cand.get("name") or "Contact Person",
                "business_name": cand.get("business_name") or cand.get("organization") or "Direct URL Lead",
                "designation": cand.get("designation") or "Executive",
                "organization": cand.get("business_name") or cand.get("organization") or "Direct URL Lead",
                "category": "Direct Scrape",
                "address": cand.get("address") or "N/A",
                "city": cand.get("city") or "N/A",
                "country": cand.get("country") or "Bangladesh",
                "phone": final_phone,
                "phone_type": p_type,
                "email": final_email,
                "email_type": cand.get("email_type", "UNKNOWN"),
                "website": cand.get("website", page_url),
                "canonical_domain": cand.get("canonical_domain", ""),
                "linkedin_url": cand.get("linkedin_url", ""),
                "facebook_url": cand.get("facebook_url", ""),
                "twitter_url": cand.get("twitter_url", ""),
                "secondary_phones": cand.get("secondary_phones", []),
                "secondary_emails": cand.get("secondary_emails", []),
                "completeness_score": comp_score,
                "source_url": page_url,
                "ai_confidence_score": ai_eval.get("confidence_score", 90),
                "ai_validation_reason": ai_eval.get("reason", "Verified"),
                "scraping_mode": scrape_mode,
                "render_fallback_used": render_fallback
            }
            return lead_out, True

        rejected_count += 1
        return None, False

    for cand in main_leads:
        lead_out, is_qual = _evaluate_candidate(cand, clean_url, scrape_res.scraping_mode, scrape_res.render_fallback_used)
        if is_qual and lead_out:
            qualified_count += 1
            yield {"type": "lead", "job_id": job_id, "data": lead_out, "count": qualified_count}

    JobManager.update_progress(
        job_id,
        total_scraped=total_scraped,
        qualified_count=qualified_count,
        rejected_count=rejected_count,
        duplicate_count=duplicate_count,
        http_count=http_count,
        playwright_count=playwright_count
    )

    # 2. Crawl pagination links if requested
    if crawl_pagination and max_pages > 0:
        pagination_links = extract_pagination_links(scrape_res.html, clean_url, max_links=max_pages)
        if pagination_links:
            yield {
                "type": "progress",
                "job_id": job_id,
                "count": qualified_count,
                "message": f"Found {len(pagination_links)} pagination sub-pages. Crawling..."
            }

            for idx, sub_url in enumerate(pagination_links, 1):
                if sub_url in visited_urls or not check_robots_txt(sub_url):
                    continue
                visited_urls.add(sub_url)

                yield {
                    "type": "progress",
                    "job_id": job_id,
                    "count": qualified_count,
                    "message": f"Crawling sub-page [{idx}/{len(pagination_links)}]: {sub_url}..."
                }

                sub_res = adaptive_scrape(sub_url, force_browser=(mode == "dynamic"), mode=mode)
                if sub_res.scraping_mode == "playwright":
                    playwright_count += 1
                else:
                    http_count += 1

                if not sub_res.html:
                    continue

                sub_leads = extract_leads_from_html(sub_res.html, sub_url)
                if len(sub_leads) == 0 and sub_res.scraping_mode != "playwright" and mode != "http":
                    pw_sub = adaptive_scrape(sub_url, force_browser=True, mode="dynamic")
                    if pw_sub.html:
                        sub_res = pw_sub
                        playwright_count += 1
                        sub_leads = extract_leads_from_html(pw_sub.html, sub_url)

                for cand in sub_leads:
                    lead_out, is_qual = _evaluate_candidate(cand, sub_url, sub_res.scraping_mode, sub_res.render_fallback_used)
                    if is_qual and lead_out:
                        qualified_count += 1
                        yield {"type": "lead", "job_id": job_id, "data": lead_out, "count": qualified_count}

                JobManager.update_progress(
                    job_id,
                    total_scraped=total_scraped,
                    qualified_count=qualified_count,
                    rejected_count=rejected_count,
                    duplicate_count=duplicate_count,
                    http_count=http_count,
                    playwright_count=playwright_count
                )

    if job_id:
        clear_checkpoint(job_id)
    JobManager.complete_job(job_id, status="completed")

    yield {
        "type": "done",
        "job_id": job_id,
        "total": qualified_count,
        "rejected": rejected_count,
        "duplicates": duplicate_count,
        "message": f"Scrape complete! Total qualified leads: {qualified_count}"
    }

def fallback_heuristic_search(city: str, category: str, target_count: int = 100, area: str = "", country: str = "Bangladesh") -> Tuple[List[Dict[str, Any]], List[str]]:
    """Synchronous execution wrapper."""
    leads = []
    queries = []
    for msg in stream_leads_generator(city, category, target_count=target_count, area=area, country=country):
        if msg.get("type") == "lead":
            leads.append(msg["data"])
        elif msg.get("type") == "done":
            queries = msg.get("queries", [])
    return leads, queries
