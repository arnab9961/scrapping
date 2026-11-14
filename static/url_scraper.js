let currentLeads = [];
let activeUrl = '';
let activeEventSource = null;

// DOM Elements
const urlScrapeForm = document.getElementById('urlScrapeForm');
const urlInput = document.getElementById('urlInput');
const crawlPagination = document.getElementById('crawlPagination');
const maxPagesInput = document.getElementById('maxPagesInput');
const scrapeBtn = document.getElementById('scrapeBtn');
const stopBtn = document.getElementById('stopBtn');
const stopStreamBtn = document.getElementById('stopStreamBtn');
const statusBadge = document.getElementById('statusBadge');

const loadingState = document.getElementById('loadingState');
const loadingSubtitle = document.getElementById('loadingSubtitle');
const liveCounterBadge = document.getElementById('liveCounterBadge');

const errorState = document.getElementById('errorState');
const errorTitle = document.getElementById('errorTitle');
const errorMessage = document.getElementById('errorMessage');
const dismissErrorBtn = document.getElementById('dismissErrorBtn');

const emptyState = document.getElementById('emptyState');
const resultsSection = document.getElementById('resultsSection');
const resultsCount = document.getElementById('resultsCount');
const phoneCountPill = document.getElementById('phoneCountPill');
const emailCountPill = document.getElementById('emailCountPill');
const sourcePill = document.getElementById('sourcePill');

const filterInput = document.getElementById('filterInput');
const copyAllBtn = document.getElementById('copyAllBtn');
const exportCsvBtn = document.getElementById('exportCsvBtn');
const leadsTableBody = document.getElementById('leadsTableBody');

// Preset URLs
document.querySelectorAll('.preset-url').forEach(btn => {
  btn.addEventListener('click', () => {
    urlInput.value = btn.getAttribute('data-url') || '';
    urlScrapeForm.dispatchEvent(new Event('submit'));
  });
});

dismissErrorBtn.addEventListener('click', () => {
  errorState.style.display = 'none';
});

function stopActiveStream() {
  if (activeEventSource) {
    activeEventSource.close();
    activeEventSource = null;
  }
  showLoading(false);
  statusBadge.innerHTML = '<span class="dot" style="background-color: #64748b;"></span> Stopped';
  if (currentLeads.length > 0) {
    resultsCount.textContent = `${currentLeads.length} Qualified Leads (Stopped)`;
  }
}

stopBtn.addEventListener('click', stopActiveStream);
stopStreamBtn.addEventListener('click', stopActiveStream);

// Form Submit Handler (SSE Stream)
urlScrapeForm.addEventListener('submit', (e) => {
  e.preventDefault();

  let targetUrl = urlInput.value.trim();
  if (!targetUrl) return;

  if (!targetUrl.startsWith('http://') && !targetUrl.startsWith('https://')) {
    targetUrl = 'https://' + targetUrl;
    urlInput.value = targetUrl;
  }

  const shouldCrawlPag = crawlPagination ? crawlPagination.checked : true;
  const maxPages = shouldCrawlPag ? (parseInt(maxPagesInput.value, 10) || 5) : 0;

  activeUrl = targetUrl;

  if (activeEventSource) {
    activeEventSource.close();
  }

  currentLeads = [];
  leadsTableBody.innerHTML = '';
  filterInput.value = '';

  showLoading(true);
  errorState.style.display = 'none';
  emptyState.style.display = 'none';
  resultsSection.style.display = 'flex';
  resultsCount.textContent = `Scraping & validating ${targetUrl}...`;
  phoneCountPill.textContent = `📞 0 with phone`;
  emailCountPill.textContent = `📧 0 with email`;

  try {
    const parsed = new URL(targetUrl);
    sourcePill.textContent = `🌐 ${parsed.hostname}`;
  } catch (err) {
    sourcePill.textContent = `🌐 Direct URL`;
  }

  const streamUrl = `/api/scrape-url/stream?url=${encodeURIComponent(targetUrl)}&crawl_pagination=${shouldCrawlPag}&max_pages=${maxPages}`;
  activeEventSource = new EventSource(streamUrl);

  activeEventSource.onmessage = (event) => {
    if (!event.data) return;
    try {
      const msg = JSON.parse(event.data);

      if (msg.type === 'progress') {
        loadingSubtitle.textContent = msg.message || 'Scraping target webpage...';
        if (msg.count !== undefined) {
          liveCounterBadge.textContent = `${msg.count} Leads Found`;
        }
      } else if (msg.type === 'lead' && msg.data) {
        appendLead(msg.data);
      } else if (msg.type === 'done') {
        stopActiveStream();
        statusBadge.innerHTML = '<span class="dot" style="background-color: #10b981;"></span> Done';
        if (currentLeads.length === 0) {
          resultsSection.style.display = 'none';
          emptyState.style.display = 'block';
        } else {
          resultsCount.textContent = `${currentLeads.length} AI-Qualified Leads Collected`;
        }
      } else if (msg.type === 'error') {
        showError('Extraction Error', msg.message || 'An error occurred while scraping the webpage.');
        stopActiveStream();
      }
    } catch (parseErr) {
      console.error('SSE JSON parse error:', parseErr);
    }
  };

  activeEventSource.onerror = (err) => {
    console.warn('SSE stream closed.');
    stopActiveStream();
  };
});

function appendLead(lead) {
  currentLeads.push(lead);
  const index = currentLeads.length;

  liveCounterBadge.textContent = `${index} Leads Found`;
  resultsCount.textContent = `${index} Qualified Leads`;

  const withPhone = currentLeads.filter(l => l.phone && l.phone !== 'N/A').length;
  const withEmail = currentLeads.filter(l => l.email && l.email !== 'N/A').length;
  phoneCountPill.textContent = `📞 ${withPhone} with phone`;
  emailCountPill.textContent = `📧 ${withEmail} with email`;

  const score = lead.ai_confidence_score || 90;
  const scoreBadgeClass = score >= 85 ? 'badge-score-high' : (score >= 60 ? 'badge-score-mid' : 'badge-score-low');
  const modeClass = lead.scraping_mode === 'playwright' ? 'badge-mode-playwright' : 'badge-mode-http';
  const modeLabel = lead.scraping_mode === 'playwright' ? '⚡ Playwright' : '🌐 HTTP';

  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td><strong>${index}</strong></td>
    <td style="font-weight: 600;">${escapeHtml(lead.business_name || lead.organization || 'Business')}</td>
    <td>👤 ${escapeHtml(lead.name || lead.contact_person || 'N/A')}</td>
    <td><span class="badge-role">${escapeHtml(lead.designation || 'Executive')}</span></td>
    <td>${renderPhone(lead.phone)}</td>
    <td>${renderEmail(lead.email)}</td>
    <td><span class="badge-score ${scoreBadgeClass}">AI: ${score}%</span></td>
    <td><span class="badge-mode ${modeClass}">${modeLabel}</span></td>
    <td>${renderLink(lead.source_url, 'Source')}</td>
  `;
  leadsTableBody.appendChild(tr);
}

function showLoading(isLoading) {
  if (isLoading) {
    loadingState.style.display = 'flex';
    scrapeBtn.disabled = true;
    stopBtn.style.display = 'inline-flex';
    statusBadge.innerHTML = '<span class="dot" style="background-color: #d97706;"></span> Scraping...';
    scrapeBtn.querySelector('.spinner').style.display = 'inline-block';
  } else {
    loadingState.style.display = 'none';
    scrapeBtn.disabled = false;
    stopBtn.style.display = 'none';
    scrapeBtn.querySelector('.spinner').style.display = 'none';
    statusBadge.innerHTML = '<span class="dot" style="background-color: #10b981;"></span> Ready';
  }
}

function showError(title, message) {
  errorTitle.textContent = title;
  errorMessage.textContent = message;
  errorState.style.display = 'flex';
}

// In-table Live Filter
filterInput.addEventListener('input', (e) => {
  const query = e.target.value.toLowerCase().trim();
  const rows = leadsTableBody.querySelectorAll('tr');

  rows.forEach((row, idx) => {
    const lead = currentLeads[idx];
    if (!lead) return;
    const match = !query || (
      (lead.business_name && lead.business_name.toLowerCase().includes(query)) ||
      (lead.name && lead.name.toLowerCase().includes(query)) ||
      (lead.designation && lead.designation.toLowerCase().includes(query)) ||
      (lead.phone && lead.phone.toLowerCase().includes(query)) ||
      (lead.email && lead.email.toLowerCase().includes(query))
    );
    row.style.display = match ? '' : 'none';
  });
});

copyAllBtn.addEventListener('click', () => {
  if (currentLeads.length === 0) return;
  const text = currentLeads.map((l, i) => 
    `[${i + 1}] ${l.business_name || l.organization} | ${l.name || l.contact_person} (${l.designation})\nPhone: ${l.phone} | Email: ${l.email} | AI Score: ${l.ai_confidence_score}%\nSource: ${l.source_url}`
  ).join('\n\n');

  navigator.clipboard.writeText(text).then(() => {
    const orig = copyAllBtn.textContent;
    copyAllBtn.textContent = '✅ Copied!';
    setTimeout(() => { copyAllBtn.textContent = orig; }, 2000);
  });
});

exportCsvBtn.addEventListener('click', () => {
  if (currentLeads.length === 0) return;

  const headers = ['#', 'Business Name', 'Contact Person', 'Designation', 'Phone', 'Email', 'AI Confidence', 'Scraping Mode', 'Source URL'];
  const csvRows = [headers.join(',')];

  currentLeads.forEach((l, i) => {
    const row = [
      i + 1,
      escapeCsv(l.business_name || l.organization),
      escapeCsv(l.name || l.contact_person),
      escapeCsv(l.designation),
      escapeCsv(l.phone),
      escapeCsv(l.email),
      escapeCsv(l.ai_confidence_score || 90),
      escapeCsv(l.scraping_mode || 'http'),
      escapeCsv(l.source_url)
    ];
    csvRows.push(row.join(','));
  });

  const blob = new Blob([csvRows.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `url_leads_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
});

function renderPhone(phone) {
  if (!phone || phone === 'N/A') return '<span style="color: var(--text-muted);">N/A</span>';
  const clean = phone.replace(/[^0-9+]/g, '');
  return `<a href="tel:${clean}" class="phone-link">📞 ${escapeHtml(phone)}</a>`;
}

function renderEmail(email) {
  if (!email || email === 'N/A') return '<span style="color: var(--text-muted);">N/A</span>';
  return `<a href="mailto:${email}" class="email-link">📧 ${escapeHtml(email)}</a>`;
}

function renderLink(url, label) {
  if (!url || url === 'N/A') return '<span style="color: var(--text-muted);">N/A</span>';
  return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="website-link">${label} ↗</a>`;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function escapeCsv(str) {
  if (!str) return '""';
  const clean = String(str).replace(/"/g, '""');
  return `"${clean}"`;
}
