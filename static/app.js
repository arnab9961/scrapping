let currentLeads = [];
let activeCity = '';
let activeCategory = '';
let activeEventSource = null;

// DOM Elements
const searchForm = document.getElementById('searchForm');
const categoryInput = document.getElementById('categoryInput');
const countryInput = document.getElementById('countryInput');
const cityInput = document.getElementById('cityInput');
const areaInput = document.getElementById('areaInput');
const targetGoalInput = document.getElementById('targetGoalInput');
const searchBtn = document.getElementById('searchBtn');
const stopBtn = document.getElementById('stopBtn');
const stopStreamBtn = document.getElementById('stopStreamBtn');
const statusBadge = document.getElementById('statusBadge');

const loadingState = document.getElementById('loadingState');
const loadingTitle = document.getElementById('loadingTitle');
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

const filterInput = document.getElementById('filterInput');
const copyAllBtn = document.getElementById('copyAllBtn');
const exportCsvBtn = document.getElementById('exportCsvBtn');
const leadsTableBody = document.getElementById('leadsTableBody');

// Preset buttons
document.querySelectorAll('.preset-tag').forEach(tag => {
  tag.addEventListener('click', () => {
    categoryInput.value = tag.getAttribute('data-cat') || '';
    cityInput.value = tag.getAttribute('data-city') || '';
    if (areaInput) areaInput.value = tag.getAttribute('data-area') || '';
    searchForm.dispatchEvent(new Event('submit'));
  });
});

// Dismiss Error
dismissErrorBtn.addEventListener('click', () => {
  errorState.style.display = 'none';
});

// Stop Stream
function stopActiveStream() {
  if (activeEventSource) {
    activeEventSource.close();
    activeEventSource = null;
  }
  showLoading(false);
  statusBadge.innerHTML = '<span class="dot" style="background-color: #64748b;"></span> Stopped';
  if (currentLeads.length > 0) {
    resultsCount.textContent = `${currentLeads.length} Qualified Leads (Harvest Stopped)`;
  }
}

stopBtn.addEventListener('click', stopActiveStream);
stopStreamBtn.addEventListener('click', stopActiveStream);

// Form Submit Handler (SSE Stream)
searchForm.addEventListener('submit', (e) => {
  e.preventDefault();

  const category = categoryInput.value.trim();
  const city = cityInput.value.trim();
  const country = countryInput ? countryInput.value.trim() : 'Bangladesh';
  const area = areaInput ? areaInput.value.trim() : '';
  const targetGoal = parseInt(targetGoalInput.value, 10) || 50;

  if (!category || !city) return;

  activeCategory = category;
  activeCity = area ? `${area}, ${city}` : city;

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
  resultsCount.textContent = `0 / ${targetGoal} Leads Found...`;
  phoneCountPill.textContent = `📞 0 phone`;
  emailCountPill.textContent = `📧 0 email`;

  let streamUrl = `/api/search/stream?category=${encodeURIComponent(category)}&city=${encodeURIComponent(city)}&country=${encodeURIComponent(country)}&target=${targetGoal}`;
  if (area) {
    streamUrl += `&area=${encodeURIComponent(area)}`;
  }
  activeEventSource = new EventSource(streamUrl);

  activeEventSource.onmessage = (event) => {
    if (!event.data) return;
    try {
      const msg = JSON.parse(event.data);

      if (msg.type === 'progress') {
        loadingSubtitle.textContent = msg.message || 'Harvesting & validating leads...';
        liveCounterBadge.textContent = `${msg.count || currentLeads.length} Qualified Leads`;
        resultsCount.textContent = `${msg.count || currentLeads.length} / ${targetGoal} Leads Validated...`;
      } 
      else if (msg.type === 'lead') {
        const lead = msg.data;
        currentLeads.push(lead);
        appendLeadRow(lead, currentLeads.length);
        updateMetrics(currentLeads);
      } 
      else if (msg.type === 'done') {
        stopActiveStream();
        statusBadge.innerHTML = '<span class="dot" style="background-color: #10b981;"></span> Completed';
        resultsCount.textContent = `${currentLeads.length} AI-Qualified Leads Collected`;
        if (currentLeads.length === 0) {
          emptyState.style.display = 'block';
          resultsSection.style.display = 'none';
        }
      } 
      else if (msg.type === 'error') {
        stopActiveStream();
        errorTitle.textContent = "Search Error";
        errorMessage.textContent = msg.message || "An error occurred during search.";
        errorState.style.display = 'flex';
      }
    } catch (err) {
      console.error("SSE parse error:", err);
    }
  };

  activeEventSource.onerror = (err) => {
    console.warn("SSE stream closed or disconnected.");
    stopActiveStream();
  };
});

function showLoading(isLoading) {
  if (isLoading) {
    loadingState.style.display = 'flex';
    searchBtn.disabled = true;
    stopBtn.style.display = 'inline-block';
    searchBtn.querySelector('.spinner').style.display = 'inline-block';
    statusBadge.innerHTML = '<span class="dot" style="background-color: #d97706;"></span> Scraping & Validating...';
  } else {
    loadingState.style.display = 'none';
    searchBtn.disabled = false;
    stopBtn.style.display = 'none';
    searchBtn.querySelector('.spinner').style.display = 'none';
    statusBadge.innerHTML = '<span class="dot" style="background-color: #10b981;"></span> Ready';
  }
}

function updateMetrics(leads) {
  const withPhone = leads.filter(l => l.phone && l.phone !== 'N/A').length;
  const withEmail = leads.filter(l => l.email && l.email !== 'N/A').length;
  phoneCountPill.textContent = `📞 ${withPhone} phone`;
  emailCountPill.textContent = `📧 ${withEmail} email`;
  liveCounterBadge.textContent = `${leads.length} Qualified Leads`;
  resultsCount.textContent = `${leads.length} Qualified Leads Found`;
}

function appendLeadRow(lead, idx) {
  const tr = document.createElement('tr');
  const score = lead.ai_confidence_score || 90;
  const scoreBadgeClass = score >= 85 ? 'badge-score-high' : (score >= 60 ? 'badge-score-mid' : 'badge-score-low');
  const modeClass = lead.scraping_mode === 'playwright' ? 'badge-mode-playwright' : 'badge-mode-http';
  const modeLabel = lead.scraping_mode === 'playwright' ? '⚡ Playwright' : '🌐 HTTP';

  tr.innerHTML = `
    <td><strong>${idx}</strong></td>
    <td style="font-weight: 600;">${escapeHtml(lead.business_name || lead.organization || 'Business')}</td>
    <td>👤 ${escapeHtml(lead.name || lead.contact_person || 'N/A')}</td>
    <td><span class="badge-role">${escapeHtml(lead.designation || 'Executive')}</span></td>
    <td>${renderPhone(lead.phone)}</td>
    <td>${renderEmail(lead.email)}</td>
    <td>${escapeHtml(lead.city || activeCity)}</td>
    <td><span class="badge-score ${scoreBadgeClass}">AI: ${score}%</span></td>
    <td><span class="badge-mode ${modeClass}">${modeLabel}</span></td>
    <td>${renderLink(lead.source_url || lead.website, 'Source')}</td>
  `;
  leadsTableBody.appendChild(tr);
}

// In-table Live Filter
filterInput.addEventListener('input', (e) => {
  const term = e.target.value.toLowerCase().trim();
  const rows = leadsTableBody.querySelectorAll('tr');

  rows.forEach((row, idx) => {
    const lead = currentLeads[idx];
    if (!lead) return;
    const match = !term || (
      (lead.business_name && lead.business_name.toLowerCase().includes(term)) ||
      (lead.name && lead.name.toLowerCase().includes(term)) ||
      (lead.designation && lead.designation.toLowerCase().includes(term)) ||
      (lead.phone && lead.phone.toLowerCase().includes(term)) ||
      (lead.email && lead.email.toLowerCase().includes(term)) ||
      (lead.city && lead.city.toLowerCase().includes(term))
    );
    row.style.display = match ? '' : 'none';
  });
});

// Copy All Handler
copyAllBtn.addEventListener('click', async () => {
  if (currentLeads.length === 0) return;

  const header = ['#', 'Business Name', 'Contact Person', 'Designation', 'Phone', 'Email', 'City', 'AI Score', 'Source'];
  const rows = currentLeads.map((l, i) => [
    i + 1,
    l.business_name || l.organization || '',
    l.name || l.contact_person || '',
    l.designation || 'Executive',
    l.phone || '',
    l.email || '',
    l.city || activeCity,
    `${l.ai_confidence_score || 90}%`,
    l.source_url || ''
  ].join('\t'));

  const textToCopy = [header.join('\t'), ...rows].join('\n');

  try {
    await navigator.clipboard.writeText(textToCopy);
    const originalText = copyAllBtn.textContent;
    copyAllBtn.textContent = '✅ Copied!';
    setTimeout(() => { copyAllBtn.textContent = originalText; }, 2000);
  } catch (err) {
    alert('Failed to copy to clipboard.');
  }
});

// Export CSV Handler
exportCsvBtn.addEventListener('click', () => {
  if (currentLeads.length === 0) return;

  const headers = ['Business Name', 'Contact Person', 'Designation', 'Industry', 'Phone', 'Email', 'City', 'AI Confidence', 'Scraping Mode', 'Source URL'];
  const csvRows = [headers.join(',')];

  currentLeads.forEach(l => {
    const row = [
      escapeCsv(l.business_name || l.organization),
      escapeCsv(l.name || l.contact_person),
      escapeCsv(l.designation || 'Executive'),
      escapeCsv(l.category || activeCategory),
      escapeCsv(l.phone),
      escapeCsv(l.email),
      escapeCsv(l.city || activeCity),
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
  a.download = `sunset_leads_${activeCity.toLowerCase()}_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
});

// Formatting Helpers
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

function escapeCsv(val) {
  if (val === undefined || val === null) return '""';
  const str = String(val).replace(/"/g, '""');
  return `"${str}"`;
}
