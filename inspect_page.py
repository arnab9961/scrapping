from scrapling.fetchers import StealthyFetcher

page = StealthyFetcher.fetch(
    'https://www.bb.org.bd/en/index.php/about/executives',
    headless=True,
    network_idle=True
)

html = page.html

# Save full HTML for inspection
with open('page_dump.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Total HTML length: {len(html)}")

# Look for name/phone/email patterns
import re

# Try to find emails
emails = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', html)
print(f"\nEmails in HTML: {emails[:10]}")

# Dump a snippet around 'governor' or 'executive'
for keyword in ['governor', 'executive', 'phone', 'email', 'name', 'designation']:
    idx = html.lower().find(keyword)
    if idx != -1:
        print(f"\n--- snippet around '{keyword}' ---")
        print(html[max(0, idx-100):idx+500])
        break

