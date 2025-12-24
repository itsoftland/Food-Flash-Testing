let ctx;
let configs = [];
let filteredConfigs = [];
let currentPage = 1;
const itemsPerPage = 4;

let el = {};

export function initCore(context) {
  ctx = context;

  el = {
    configTable: document.getElementById('config-table'),
    configTbody: document.getElementById('config-tbody'),
    paginationContainer: document.getElementById('pagination-container'),
    emptyState: document.getElementById('empty-state'),
    orientationFilter: document.getElementById('orientation-filter'),
    qrStatusFilter: document.getElementById('qr-filter'),
    actionMenu: document.getElementById('action-menu'),
    actionMenuList: document.getElementById('action-menu-list')
  };

  el.orientationFilter?.addEventListener('change', applyFilters);
  el.qrStatusFilter?.addEventListener('change', applyFilters);

  document.addEventListener('click', e => {
    if (!e.target.closest('.action-btn') && !e.target.closest('.action-menu')) {
      el.actionMenu.style.display = 'none';
    }
  });
}

export async function loadConfigurations() {
  try {
    const res = await ctx.fetchWithAutoRefresh(
      ctx.apiEndpoints.GET_TV_CONFIG,
      { headers: { 'X-CSRFToken': AppUtils.getCSRFToken() } }
    );

    const data = await res.json();
    console.log(data);
    configs = data.configs || data.results || data;
    filteredConfigs = [...configs];
    currentPage = 1;

    renderTable();
    renderPagination();
  } catch(error) {
    console.error('Error loading configurations', error);
    ctx.ModalService.showError('Failed to load configurations');
  }
}

function applyFilters() {
  const o = el.orientationFilter.value;
  const q = el.qrStatusFilter.value;

  filteredConfigs = configs.filter(c => {
    if (o !== 'all' && c.screen_orientation !== o) return false;
    if (q !== 'all' && c.show_qr !== (q === 'enabled')) return false;
    return true;
  });

  currentPage = 1;
  renderTable();
  renderPagination();
}

function renderTable() {
    if (!el.configTable) {
        console.error('Element with ID "configTable" not found');
        return;
    }
    if (!filteredConfigs.length) {
        el.configTable.style.display = 'none';
        el.emptyState.style.display = 'block';
        return;
    }

    el.configTable.style.display = 'table';
    el.emptyState.style.display = 'none';

    const start = (currentPage - 1) * itemsPerPage;
    const pageData = filteredConfigs.slice(start, start + itemsPerPage);

    el.configTbody.innerHTML = pageData.map(rowTemplate).join('');

    el.configTbody.querySelectorAll('.action-btn').forEach(btn => {
        btn.addEventListener('click', e => showActionMenu(e, btn));
    });
}

function rowTemplate(c) {
  return `
    <tr>
      <td>${escapeHtml(c.utility_name_mode)}</td>

      <td>
        <span class="config-items">
          ${c.items_to_show}
        </span>
      </td>

      <td>
        <span class="qr-badge ${c.show_qr ? 'enabled' : 'disabled'}">
          ${c.show_qr ? 'Enabled' : 'Disabled'}
        </span>
      </td>

      <td>
        <span class="orientation-badge">
          ${escapeHtml(c.screen_orientation)}
        </span>
      </td>

      <td>
        <span class="utilities-count">
          ${c.utilities.length}
        </span>
      </td>

      <td class="date-created">
        ${new Date(c.created_at).toLocaleDateString()}
      </td>

      <td>
        <button class="action-btn" data-id="${c.id}">⋮</button>
      </td>
    </tr>
  `;
}

function showActionMenu(e, btn) {
  e.stopPropagation();
  const rect = btn.getBoundingClientRect();

  el.actionMenu.style.display = 'block';
  el.actionMenu.style.top = `${rect.bottom + 5}px`;
  el.actionMenu.style.left = `${rect.left}px`;

  el.actionMenuList.querySelectorAll('.action-menu-item')
    .forEach(item => item.onclick = ev => {
      window.dispatchEvent(new CustomEvent('tv-config-action', {
        detail: {
          action: ev.target.dataset.action,
          id: btn.dataset.id
        }
      }));
    });
}

function renderPagination() {
  const pages = Math.ceil(filteredConfigs.length / itemsPerPage);
  if (pages <= 1) return el.paginationContainer.innerHTML = '';

  el.paginationContainer.innerHTML = [...Array(pages)].map((_, i) =>
    `<button
        class="page-btn ${currentPage === i + 1 ? 'active' : ''}"
        onclick="window.goToTVPage(${i + 1})">
        ${i + 1}
    </button>`
    ).join('');

}

window.goToTVPage = p => {
  currentPage = p;
  renderTable();
};

function escapeHtml(t) {
  return t?.replace(/[&<>"']/g, m =>
    ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;' }[m])
  );
}
