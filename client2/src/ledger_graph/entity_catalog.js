const list = (value) => Array.isArray(value) ? value : [];

export function normalizeEntityCatalog(body) {
  const source = body && typeof body === 'object' ? body : {};
  return {
    type: String(source.entity_type || ''),
    types: list(source.entity_types).filter((entry) => entry?.type).map((entry) => ({
      type: String(entry.type), label: String(entry.label || entry.type),
      keys: list(entry.keys).map(String), entityClass: String(entry.entity_class || ''),
    })),
    items: list(source.items).filter((item) => item?.id).map((item) => ({
      id: String(item.id), type: String(item.type || source.entity_type || 'Unknown'),
      label: String(item.label || item.id),
      keys: item.keys && typeof item.keys === 'object' ? item.keys : {},
      registerClaims: Number(item.register_claims || 0),
    })),
    nextCursor: source.page?.next_cursor ? String(source.page.next_cursor) : null,
    hasMore: Boolean(source.page?.has_more),
    query: String(source.search?.q || ''),
  };
}

export function mergeEntityPages(previous, next) {
  const seen = new Set();
  return [...list(previous), ...list(next)].filter((item) => {
    if (!item?.id || seen.has(item.id)) return false;
    seen.add(item.id); return true;
  });
}

const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (ch) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[ch]));

const color = (type) => {
  const palette = ['#2563eb', '#7c3aed', '#0891b2', '#db2777', '#d97706', '#059669'];
  let hash = 0; for (const ch of String(type)) hash = ((hash * 31) + ch.charCodeAt(0)) >>> 0;
  return palette[hash % palette.length];
};

export function createEntityCatalog(options) {
  const { apiBase, typeSelect, queryInput, section, listElement, countElement,
    statusElement, moreButton, onPick, debounceMs = 220 } = options;
  let aborter = null; let request = 0; let timer = null; let cursor = null;
  let items = []; let types = []; let visible = false; let currentQuery = '';
  let selectedType = typeSelect.value || 'Lot';

  const renderTypes = () => {
    typeSelect.innerHTML = types.map((entry) => `<option value="${escapeHtml(entry.type)}">${escapeHtml(entry.label)} · ${escapeHtml(entry.type)}</option>`).join('');
    if (!types.some((entry) => entry.type === selectedType)) selectedType = types[0]?.type || 'Lot';
    typeSelect.value = selectedType;
  };
  const render = () => {
    countElement.textContent = `${items.length}${cursor ? '+' : ''}`;
    listElement.innerHTML = items.map((item) => `<button type="button" class="lg-node-item" role="option" data-lg-catalog-pick="${escapeHtml(item.id)}" title="${escapeHtml(item.label)}에서 그래프 시작"><i style="--node:${color(item.type)}"></i><span>${escapeHtml(item.label)}</span><small>${escapeHtml(item.type)}</small></button>`).join('') || '<p class="lg-empty-copy">일치하는 등록 개체가 없습니다.</p>';
    moreButton.hidden = !cursor;
  };

  async function load({ append = false } = {}) {
    if (!visible) return;
    const q = String(queryInput.value || '').trim();
    const entityType = selectedType;
    if (!append) { cursor = null; items = []; render(); }
    const requestedCursor = append ? cursor : null;
    aborter?.abort(); aborter = new AbortController(); const mine = ++request;
    statusElement.textContent = '목록 조회 중';
    const params = new URLSearchParams({ type: entityType, limit: '40' });
    if (q) params.set('q', q);
    if (requestedCursor) params.set('after', requestedCursor);
    try {
      const response = await fetch(`${apiBase}/api/ledger/entities?${params}`, { signal: aborter.signal });
      const body = await response.json();
      if (mine !== request) return;
      if (!response.ok) throw new Error(body?.detail?.message || body?.detail || `HTTP ${response.status}`);
      const page = normalizeEntityCatalog(body);
      if (page.type !== entityType || page.query !== q) return;
      if (!types.length && page.types.length) { types = page.types; renderTypes(); }
      items = append ? mergeEntityPages(items, page.items) : page.items;
      cursor = page.hasMore ? page.nextCursor : null; currentQuery = q;
      statusElement.textContent = `${page.type} · ${items.length}${cursor ? '개 이상' : '개 표시'}`;
      render();
    } catch (error) {
      if (error.name === 'AbortError' || mine !== request) return;
      statusElement.textContent = '목록 실패'; cursor = null; items = [];
      listElement.innerHTML = `<p class="lg-empty-copy">${escapeHtml(error.message)}</p>`;
      moreButton.hidden = true;
    }
  }

  const schedule = () => {
    clearTimeout(timer); timer = setTimeout(() => load(), debounceMs);
  };
  queryInput.addEventListener('input', schedule);
  typeSelect.addEventListener('change', () => { selectedType = typeSelect.value || 'Lot'; clearTimeout(timer); load(); });
  moreButton.addEventListener('click', () => load({ append: true }));
  listElement.addEventListener('click', (event) => {
    const button = event.target.closest('[data-lg-catalog-pick]'); if (!button) return;
    const item = items.find((entry) => entry.id === button.dataset.lgCatalogPick);
    if (item) onPick(item);
  });

  return {
    setVisible(next) {
      visible = Boolean(next); section.hidden = !visible;
      if (!visible) { aborter?.abort(); request += 1; return; }
      if (!items.length || currentQuery !== String(queryInput.value || '').trim()) load();
    },
    searchNow() { clearTimeout(timer); return load(); },
    setType(type) { if(type){selectedType=String(type);if(types.some((entry)=>entry.type===selectedType))typeSelect.value=selectedType;if(visible)load();} },
    destroy() { clearTimeout(timer); aborter?.abort(); request += 1; },
  };
}
