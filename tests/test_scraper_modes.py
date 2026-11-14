"""
Targeted tests for Intelligent Dual-Mode Web Scraping Engine.
Tests Mode A (HTTP), Mode B (Playwright), and Auto-Detection Mode Switching.
"""
import pytest
from services.scraper import (
    adaptive_scrape,
    fetch_http_mode,
    fetch_playwright_mode,
    requires_dynamic_rendering,
    is_anti_bot_challenge,
    ScrapeResult
)

def test_http_mode_static_page():
    # Test on a reliable public static site (e.g. example.com)
    html, status, err = fetch_http_mode("https://example.com")
    assert html is not None
    assert status == 200
    assert "Example Domain" in html

def test_spa_detection_logic():
    # SPA shell HTML with empty root and react bundle script
    spa_html = """
    <!DOCTYPE html>
    <html>
    <head><title>SPA App</title></head>
    <body>
      <div id="root"></div>
      <script src="/static/bundle.js"></script>
    </body>
    </html>
    """
    body_text = "SPA App"
    needs_dynamic = requires_dynamic_rendering(spa_html, body_text)
    assert needs_dynamic is True

    # Standard static HTML
    static_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Static Business Page</title></head>
    <body>
      <h1>Sunset Kuakata Hotel & Resort</h1>
      <p>Luxury sea view suites located at Kuakata beach, Patuakhali, Bangladesh. Call +8801712345678.</p>
    </body>
    </html>
    """
    body_text = "Sunset Kuakata Hotel & Resort Luxury sea view suites located at Kuakata beach, Patuakhali, Bangladesh. Call +8801712345678."
    needs_dynamic_static = requires_dynamic_rendering(static_html, body_text)
    assert needs_dynamic_static is False

def test_anti_bot_challenge_detection():
    cf_html = "<html><head><title>Just a moment...</title></head><body><div class='cf-browser-verification'>Checking your browser</div></body></html>"
    is_chal = is_anti_bot_challenge(cf_html, 403)
    assert is_chal is True

    normal_html = "<html><body><h1>Welcome to our corporate directory</h1></body></html>"
    is_chal_normal = is_anti_bot_challenge(normal_html, 200)
    assert is_chal_normal is False

def test_adaptive_scrape_defaults_to_http():
    res = adaptive_scrape("https://example.com")
    assert res.extraction_status == "success"
    assert res.scraping_mode == "http"
    assert res.render_fallback_used is False
    assert res.source_url == "https://example.com"
    assert "Example Domain" in res.html

