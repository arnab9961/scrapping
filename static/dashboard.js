let currentLeads = [];
let currentPage = 1;
let totalPages = 1;
let currentSortBy = 'created_at';
let currentSortOrder = 'desc';
let currentSearch = '';

let rejectedPage = 1;
let totalRejectedPages = 1;

// DOM Elements: Metrics
const statTotalScraped = document.getElementById('statTotalScraped');
const statQualified = document.getElementById('statQualified');
const statRejected = document.getElementById('statRejected');
const statDuplicates = document.getElementById('statDuplicates');
const statAiRate = document.getElementById('statAiRate');
const statJobs = document.getElementById('statJobs');
const refreshStatsBtn = document.getElementById('refreshStatsBtn');

// DOM Elements: Sub-tabs
const tabQualifiedBtn = document.getElementById('tabQualifiedBtn');
const tabRejectedBtn = document.getElementById('tabRejectedBtn');
const tabJobsBtn = document.getElementById('tabJobsBtn');
const qualifiedCountBadge = document.getElementById('qualifiedCountBadge');
const rejectedCountBadge = document.getElementById('rejectedCountBadge');
const jobsCountBadge = document.getElementById('jobsCountBadge');

const qualifiedLeadsView = document.getElementById('qualifiedLeadsView');
const rejectedLeadsView = document.getElementById('rejectedLeadsView');
const jobsView = document.getElementById('jobsView');
const leadsControls = document.getElementById('leadsControls');

// DOM Elements: Table Bodies
const dashLeadsTableBody = document.getElementById('dashLeadsTableBody');
const dashRejectedTableBody = document.getElementById('dashRejectedTableBody');
const dashJobsTableBody = document.getElementById('dashJobsTableBody');

// DOM Elements: Controls
const dashSearchInput = document.getElementById('dashSearchInput');
const dashSortSelect = document.getElementById('dashSortSelect');
const dashExportCsvBtn = document.getElementById('dashExportCsvBtn');

// DOM Elements: Pagination
const currentPageNum = document.getElementById('currentPageNum');
const totalPagesNum = document.getElementById('totalPagesNum');
const totalLeadsCount = document.getElementById('totalLeadsCount');
const prevPageBtn = document.getElementById('prevPageBtn');
const nextPageBtn = document.getElementById('nextPageBtn');

const prevRejectedBtn = document.getElementById('prevRejectedBtn');
const nextRejectedBtn = document.getElementById('nextRejectedBtn');
const totalRejectedCount = document.getElementById('totalRejectedCount');

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
  fetchDashboardMetrics();
  loadQualifiedLeads();
  loadJobs();
});

refreshStatsBtn.addEventListener('click', () => {
  fetchDashboardMetrics();
  loadQualifiedLeads();
  loadJobs();
});

// Sub-Tab Switching
tabQualifiedBtn.addEventListener('click', () => {
  qualifiedLeadsView.style.display = 'block';
  rejectedLeadsView.style.display = 'none';
  jobsView.style.display = 'none';
  leadsControls.style.display = 'flex';
  setActiveSubTab(tabQualifiedBtn);
});

tabRejectedBtn.addEventListener('click', () => {
  qualifiedLeadsView.style.display = 'none';
  rejectedLeadsView.style.display = 'block';
  jobsView.style.display = 'none';
  leadsControls.style.display = 'none';
  setActiveSubTab(tabRejectedBtn);
  loadRejectedLeads();
});

tabJobsBtn.addEventListener('click', () => {
  qualifiedLeadsView.style.display = 'none';
  rejectedLeadsView.style.display = 'none';
  jobsView.style.display = 'block';
  leadsControls.style.display = 'none';
  setActiveSubTab(tabJobsBtn);
  loadJobs();
});

function setActiveSubTab(activeBtn) {
  [tabQualifiedBtn, tabRejectedBtn, tabJobsBtn].forEach(b => {
    b.style.backgroundColor = 'white';
    b.style.borderColor = 'var(--border-color)';
    b.style.color = 'var(--text-secondary)';
  });
  activeBtn.style.backgroundColor = 'var(--primary-light)';
  activeBtn.style.borderColor = 'var(--primary-border)';
  activeBtn.style.color = 'var(--primary-hover)';
}

// Fetch Metrics
async function fetchDashboardMetrics() {
  try {
    const res = await fetch('/api/stats');
    if (!res.ok) return;
    const stats = await res.json();

    statTotalScraped.textContent = Number(stats.total_scraped || 0).toLocaleString();
    statQualified.textContent = Number(stats.qualified_leads || 0).toLocaleString();
    statRejected.textContent = Number(stats.rejected_leads || 0).toLocaleString();
    statDuplicates.textContent = Number(stats.duplicate_leads || 0).toLocaleString();
    statAiRate.textContent = `${stats.ai_validation_rate || 0}%`;
    statJobs.textContent = `${stats.current_scraping_jobs || 0} / ${stats.failed_scraping_jobs || 0}`;

    qualifiedCountBadge.textContent = stats.qualified_leads || 0;
    rejectedCountBadge.textContent = stats.rejected_leads || 0;
  } catch (err) {
    console.error('Error fetching dashboard stats:', err);
  }
}

// Fetch Qualified Leads
async function loadQualifiedLeads() {
  try {
    dashLeadsTableBody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 24px; color: var(--text-muted);">Loading qualified leads...</td></tr>`;

    const url = `/api/leads?page=${currentPage}&page_size=25&search=${encodeURIComponent(currentSearch)}&sort_by=${currentSortBy}&sort_order=${currentSortOrder}`;
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();

    currentLeads = data.leads || [];
    totalPages = data.total_pages || 1;

    currentPageNum.textContent = data.page || 1;
    totalPagesNum.textContent = totalPages;
    totalLeadsCount.textContent = data.total || 0;

    prevPageBtn.disabled = currentPage <= 1;
    nextPageBtn.disabled = currentPage >= totalPages;

    renderLeadsTable(currentLeads);
  } catch (err) {
    dashLeadsTableBody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 24px; color: var(--danger);">Failed to load leads.</td></tr>`;
  }
}

function renderLeadsTable(leads) {
  dashLeadsTableBody.innerHTML = '';
  if (!leads || leads.length === 0) {
    dashLeadsTableBody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 32px; color: var(--text-muted);">No qualified leads found. Try searching or scraping new leads!</td></tr>`;
    return;
  }

  leads.forEach(l => {
    const tr = document.createElement('tr');
    const dateFormatted = l.created_at ? l.created_at.slice(0, 16) : 'N/A';

    tr.innerHTML = `
      <td><strong>#${l.id}</strong></td>
      <td style="font-weight: 600;">${escapeHtml(l.business_name || 'N/A')}</td>
      <td>👤 ${escapeHtml(l.contact_person || 'N/A')}</td>
      <td><span class="badge-role">${escapeHtml(l.designation || 'Executive')}</span></td>
      <td><span class="badge-tag">${escapeHtml(l.industry || 'General')}</span></td>
      <td>${renderPhone(l.phone)}</td>
      <td>${renderEmail(l.email)}</td>
      <td>${escapeHtml(l.city || 'Dhaka')}</td>
      <td><small style="color: var(--text-muted);">${dateFormatted}</small></td>
      <td>${renderLink(l.source_url || l.website, 'Link')}</td>
    `;
    dashLeadsTableBody.appendChild(tr);
  });
}

// Fetch Rejected Leads
async function loadRejectedLeads() {
  try {
    dashRejectedTableBody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 24px; color: var(--text-muted);">Loading rejection log...</td></tr>`;
    const res = await fetch(`/api/rejected-leads?page=${rejectedPage}&page_size=25`);
    if (!res.ok) return;
    const data = await res.json();

    const rejected = data.rejected_leads || [];
    totalRejectedPages = data.total_pages || 1;
    totalRejectedCount.textContent = data.total || 0;

    prevRejectedBtn.disabled = rejectedPage <= 1;
    nextRejectedBtn.disabled = rejectedPage >= totalRejectedPages;

    dashRejectedTableBody.innerHTML = '';
    if (rejected.length === 0) {
      dashRejectedTableBody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 32px; color: var(--text-muted);">No rejected leads logged yet.</td></tr>`;
      return;
    }

    rejected.forEach(r => {
      const tr = document.createElement('tr');
      const dateFormatted = r.created_at ? r.created_at.slice(0, 16) : 'N/A';
      tr.innerHTML = `
        <td><strong>#${r.id}</strong></td>
        <td>${escapeHtml(r.business_name || r.contact_person || 'N/A')}</td>
        <td>${escapeHtml(r.phone || 'N/A')}</td>
        <td>${escapeHtml(r.email || 'N/A')}</td>
        <td><span class="badge-tag" style="background: #fee2e2; color: #991b1b;">${escapeHtml(r.rejection_stage || 'validation')}</span></td>
        <td style="color: #b91c1c; font-size: 12px;">${escapeHtml(r.reason || 'Failed')}</td>
        <td><small style="color: var(--text-muted);">${escapeHtml(r.issues || '')}</small></td>
        <td><small style="color: var(--text-muted);">${dateFormatted}</small></td>
      `;
      dashRejectedTableBody.appendChild(tr);
    });
  } catch (err) {
    dashRejectedTableBody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 24px; color: var(--danger);">Failed to load rejection log.</td></tr>`;
  }
}

// Fetch Jobs
async function loadJobs() {
  try {
    const res = await fetch('/api/jobs?limit=15');
    if (!res.ok) return;
    const data = await res.json();
    const jobs = data.jobs || [];
    jobsCountBadge.textContent = jobs.length;

    dashJobsTableBody.innerHTML = '';
    if (jobs.length === 0) {
      dashJobsTableBody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 32px; color: var(--text-muted);">No recent jobs recorded.</td></tr>`;
      return;
    }

    jobs.forEach(j => {
      const tr = document.createElement('tr');
      const statusColor = j.status === 'completed' ? 'var(--success)' : (j.status === 'running' ? 'var(--primary)' : 'var(--danger)');
      tr.innerHTML = `
        <td><small style="font-family: monospace;">${escapeHtml(j.job_id)}</small></td>
        <td><span class="badge-tag">${escapeHtml(j.job_type)}</span></td>
        <td style="font-weight: 500;">${escapeHtml(j.target)}</td>
        <td><strong style="color: ${statusColor}; text-transform: uppercase; font-size: 12px;">${escapeHtml(j.status)}</strong></td>
        <td>${j.total_scraped || 0}</td>
        <td><span style="color: var(--success); font-weight: 600;">${j.qualified_count || 0}</span></td>
        <td><span style="color: var(--danger);">${j.rejected_count || 0}</span></td>
        <td>${j.duplicate_count || 0}</td>
        <td><small>${j.http_count || 0} HTTP / ${j.playwright_count || 0} Playwright</small></td>
        <td><small style="color: var(--text-muted);">${j.started_at ? j.started_at.slice(0, 16) : 'N/A'}</small></td>
      `;
      dashJobsTableBody.appendChild(tr);
    });
  } catch (err) {
    console.error('Error fetching jobs:', err);
  }
}

// Search & Sort Handlers
dashSearchInput.addEventListener('input', (e) => {
  currentSearch = e.target.value.trim();
  currentPage = 1;
  loadQualifiedLeads();
});

dashSortSelect.addEventListener('change', (e) => {
  const parts = e.target.value.split(':');
  currentSortBy = parts[0];
  currentSortOrder = parts[1] || 'desc';
  currentPage = 1;
  loadQualifiedLeads();
});

// Pagination Handlers
prevPageBtn.addEventListener('click', () => {
  if (currentPage > 1) {
    currentPage--;
    loadQualifiedLeads();
  }
});

nextPageBtn.addEventListener('click', () => {
  if (currentPage < totalPages) {
    currentPage++;
    loadQualifiedLeads();
  }
});

prevRejectedBtn.addEventListener('click', () => {
  if (rejectedPage > 1) {
    rejectedPage--;
    loadRejectedLeads();
  }
});

nextRejectedBtn.addEventListener('click', () => {
  if (rejectedPage < totalRejectedPages) {
    rejectedPage++;
    loadRejectedLeads();
  }
});

// Export CSV
dashExportCsvBtn.addEventListener('click', () => {
  if (currentLeads.length === 0) {
    alert('No qualified leads available to export.');
    return;
  }

  const headers = ['ID', 'Business Name', 'Contact Person', 'Designation', 'Industry', 'Phone', 'Email', 'City', 'Source URL', 'Date'];
  const csvRows = [headers.join(',')];

  currentLeads.forEach(l => {
    const row = [
      l.id,
      escapeCsv(l.business_name),
      escapeCsv(l.contact_person),
      escapeCsv(l.designation),
      escapeCsv(l.industry),
      escapeCsv(l.phone),
      escapeCsv(l.email),
      escapeCsv(l.city),
      escapeCsv(l.source_url),
      escapeCsv(l.created_at)
    ];
    csvRows.push(row.join(','));
  });

  const blob = new Blob([csvRows.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `sunset_group_qualified_leads_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
});

// Helpers
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

