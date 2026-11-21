import pytest
from services.extractor import extract_leads_from_html, extract_social_links
from bs4 import BeautifulSoup

def test_social_links_extraction():
    html = """
    <html>
      <body>
        <a href="https://www.linkedin.com/company/sunset-kuakata">LinkedIn</a>
        <a href="https://www.facebook.com/sunsetkuakatahotel">Facebook</a>
        <a href="https://twitter.com/sunsetkuakata">Twitter</a>
        <a href="https://instagram.com/sunsetkuakata">Instagram</a>
        <a href="https://www.youtube.com/@sunsetkuakata">YouTube</a>
        <!-- Share links should be ignored -->
        <a href="https://www.facebook.com/sharer/sharer.php?u=example.com">Share on FB</a>
      </body>
    </html>
    """
    soup = BeautifulSoup(html, 'html.parser')
    socials = extract_social_links(soup)
    assert socials["linkedin_url"] == "https://www.linkedin.com/company/sunset-kuakata"
    assert socials["facebook_url"] == "https://www.facebook.com/sunsetkuakatahotel"
    assert socials["twitter_url"] == "https://twitter.com/sunsetkuakata"
    assert socials["instagram_url"] == "https://instagram.com/sunsetkuakata"
    assert socials["youtube_url"] == "https://www.youtube.com/@sunsetkuakata"

def test_lead_enrichment_secondary_contacts_and_types():
    html = """
    <html>
      <head>
        <title>Grand Palace Hotel & Resort</title>
      </head>
      <body>
        <a href="https://www.linkedin.com/company/grandpalaceresort">LinkedIn</a>
        <div class="card">
          <div class="company-name">Grand Palace Hotel & Resort</div>
          <div class="person-name">Md. Ashraf Ali</div>
          <div class="designation">General Manager</div>
          <a href="tel:+8801711223344">+8801711223344</a>
          <a href="mailto:gm@grandpalaceresort.com">gm@grandpalaceresort.com</a>
        </div>
        <!-- Secondary contact info on the same page -->
        <footer>
          <p>Front desk: <a href="tel:+8801819998877">+8801819998877</a></p>
          <p>General inquiries: <a href="mailto:info@grandpalaceresort.com">info@grandpalaceresort.com</a></p>
        </footer>
      </body>
    </html>
    """
    leads = extract_leads_from_html(html, "https://grandpalaceresort.com/contact")
    assert len(leads) >= 1
    lead = leads[0]
    assert lead["business_name"] == "Grand Palace Hotel & Resort"
    assert lead["contact_person"] == "Md. Ashraf Ali"
    assert lead["phone"] == "+8801711223344"
    assert lead["phone_type"] == "MOBILE"
    assert lead["email"] == "gm@grandpalaceresort.com"
    assert lead["email_type"] == "DIRECT"
    assert lead["linkedin_url"] == "https://www.linkedin.com/company/grandpalaceresort"
    assert lead["canonical_domain"] == "grandpalaceresort.com"
    assert "+8801819998877" in lead["secondary_phones"]
    assert "info@grandpalaceresort.com" in lead["secondary_emails"]
