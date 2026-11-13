from scrapling.fetchers import StealthyFetcher
import re

page = StealthyFetcher.fetch(
    'https://www.bb.org.bd/en/index.php/about/executives',
    headless=True,
    network_idle=True,
)

# _raw_body has the original HTML
html = page._raw_body
if isinstance(html, bytes):
    html = html.decode('utf-8', errors='ignore')

with open('dump.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Saved {len(html)} bytes to dump.html")

# Print all unique class names
classes = re.findall(r'class=["\']([^"\']+)["\']', html)
all_classes = sorted(set(c for group in classes for c in group.split()))

print(f"\nFound {len(all_classes)} unique CSS classes:")
for c in all_classes:
    print(" ", c)
