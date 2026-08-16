// R&D Trend Workbench — defect-subtype charts + a wide, shared-marking table.
//
// This module deliberately owns no network request. The integration layer pages data
// and calls update(); the workbench never turns a bounded response into a client-side
// full scan. Every cross-view selection is keyed by the stable wafer identity.

const DEFAULTS = Object.freeze({
  rowHeight: 34,
  overscan: 6,
  downsampleLimit: 600,
  pageSize: 250,
  columns: [
    { key: 'waferId', label: '웨이퍼', width: 142 },
    { key: 'lot', label: '랏', width: 112 },
    { key: 'slot', label: '슬롯', width: 62 },
    { key: 'voidRate', label: '보이드율', width: 86, format: percent },
    { key: 'edgeVoidRate', label: '에지 보이드', width: 96, format: percent },
    { key: 'centerVoidRate', label: '센터 보이드', width: 104, format: percent },
    { key: 'producedAt', label: '생산 시각', width: 138 },
  ],
});

const CHART_PAD = Object.freeze({ l: 58, r: 14, t: 14, b: 46 });

function percent(value) {
  return Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(2)}%` : '기록 없음';
}

function text(value) {
  return value === null || value === undefined || value === '' ? '기록 없음' : String(value);
}

function element(doc, tag, className, value) {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined) node.textContent = value;
  return node;
}

function requireWaferId(item, context) {
  const value = item && (item.waferId ?? item.wafer_id);
  if (value === null || value === undefined || String(value).trim() === '') {
    throw new TypeError(`${context}: stable waferId is required`);
  }
  return String(value);
}

/**
 * Min/max bucket sampling preserves local extremes and the first/last observation.
 * The seam is exported for a worker/server implementation when series become larger.
 */
export function downsampleSeries(points, limit = DEFAULTS.downsampleLimit) {
  if (!Array.isArray(points) || points.length <= limit || limit < 4) return Array.isArray(points) ? points.slice() : [];
  const bodyBudget = Math.max(2, limit - 2);
  const buckets = Math.max(1, Math.floor(bodyBudget / 2));
  const source = points.slice(1, -1);
  const width = source.length / buckets;
  const picked = [points[0]];
  for (let bucket = 0; bucket < buckets; bucket += 1) {
    const start = Math.floor(bucket * width);
    const end = Math.max(start + 1, Math.floor((bucket + 1) * width));
    const window = source.slice(start, end);
    if (!window.length) continue;
    let min = window[0];
    let max = window[0];
    for (const point of window) {
      if (Number(point.y) < Number(min.y)) min = point;
      if (Number(point.y) > Number(max.y)) max = point;
    }
    const ordered = window.indexOf(min) <= window.indexOf(max) ? [min, max] : [max, min];
    for (const point of ordered) if (picked.length < limit - 1 && !picked.includes(point)) picked.push(point);
  }
  picked.push(points[points.length - 1]);
  return picked;
}

function normalizeData(input = {}) {
  const rows = Array.isArray(input.rows) ? input.rows.map((row) => ({ ...row, waferId: requireWaferId(row, 'row') })) : [];
  const charts = Array.isArray(input.charts) ? input.charts.map((chart, index) => ({
    id: text(chart.id || `chart-${index + 1}`),
    title: text(chart.title || `Defect ${index + 1}`),
    unit: text(chart.unit || ''),
    xLabel: String(chart.xLabel || chart.x_label || '날짜 - BASE WAFER-ID'),
    yLabel: String(chart.yLabel || chart.y_label || '불량 Die 수'),
    yMetric: String(chart.yMetric || chart.y_metric || 'found_chip_count'),
    points: Array.isArray(chart.points) ? chart.points.map((point, pointIndex) => ({
      ...point,
      waferId: requireWaferId(point, `chart ${index + 1} point ${pointIndex + 1}`),
      _seriesIndex: pointIndex,
      x: point.x ?? pointIndex,
      y: Number(point.y),
    })).filter((point) => Number.isFinite(point.y)) : [],
  })) : [];
  return { rows, charts, totalRows: Number.isFinite(Number(input.totalRows)) ? Number(input.totalRows) : rows.length, cursor: input.cursor ?? null };
}

function ensureStylesheet(doc) {
  if (doc.querySelector('link[data-rnd-trend-workbench]')) return;
  const link = doc.createElement('link');
  link.rel = 'stylesheet';
  link.href = new URL('./trend_workbench.css', import.meta.url).href;
  link.dataset.rndTrendWorkbench = 'true';
  doc.head.appendChild(link);
}

function normalizeMarkingGroups(groups) {
  return (Array.isArray(groups) ? groups : []).map((group, index) => ({
    id: String(group?.id || `group-${index + 1}`),
    label: String(group?.label || group?.id || `Group ${index + 1}`),
    color: String(group?.color || '#e77b20'),
    role: String(group?.role || 'analysis'),
    ids: new Set((group?.ids || []).map(String)),
    regions: (group?.regions || []).map((region) => {
      const selector = region.selector || region;
      return {
        ...region, ...selector,
        seriesId: String(selector.seriesId || selector.series_id || ''),
        ids: new Set((selector.ids || []).map(String)),
      };
    }),
  }));
}

function markingStripe(groups) {
  if (!groups.length) return 'none';
  const span = 100 / groups.length;
  const stops = groups.flatMap((group, index) => [
    `${group.color} ${(index * span).toFixed(2)}%`,
    `${group.color} ${((index + 1) * span).toFixed(2)}%`,
  ]);
  return `linear-gradient(to right, ${stops.join(', ')})`;
}

function shortWaferId(value) {
  let label = String(value || '').replace(/^wafer:/, '');
  try { label = decodeURIComponent(label); } catch { /* retain the stable key */ }
  const compact = label.match(/(?:^|-)(BW-[A-Z0-9-]+)$/i);
  return compact ? compact[1] : label;
}

function unitLabel(item) {
  const wafer = shortWaferId(item?.wafer || item?.baseWafer || item?.base_wafer || item?.waferId);
  const leg = String(item?.bondingLeg || item?.bonding_leg || '').trim();
  return leg ? `${wafer} · ${leg}` : wafer;
}

function conditionScale(rows, column) {
  if (column.kind === 'trace') return { kind: 'trace' };
  const values = rows.map((row) => Number(row[column.key])).filter(Number.isFinite);
  if (!values.length) return { kind: 'none' };
  return { kind: 'number', min: Math.min(...values), max: Math.max(...values) };
}

function applyCondition(cell, value, scale) {
  if (scale.kind === 'trace') {
    const state = String(value?.state || value || 'unknown');
    cell.dataset.condition = state;
    return;
  }
  if (scale.kind !== 'number' || !Number.isFinite(Number(value))) {
    if (value === null || value === undefined || value === '') cell.dataset.condition = 'missing';
    return;
  }
  const span = scale.max - scale.min;
  const ratio = span > 0 ? (Number(value) - scale.min) / span : 0.5;
  const hue = Math.round(210 - ratio * 198);
  const alpha = (0.10 + ratio * 0.24).toFixed(3);
  cell.style.setProperty('--rwb-cell-condition', `hsla(${hue}, 78%, 50%, ${alpha})`);
  cell.dataset.condition = ratio >= 0.67 ? 'high' : ratio <= 0.33 ? 'low' : 'mid';
}

class TrendWorkbench {
  constructor(mount, options = {}) {
    if (!mount || !mount.ownerDocument) throw new TypeError('init: a DOM mount element is required');
    this.mount = mount;
    this.doc = mount.ownerDocument;
    this.options = { ...DEFAULTS, ...options };
    this.markingGroups = normalizeMarkingGroups(options.markingGroups);
    this.activeGroupId = String(options.activeGroupId || this.markingGroups[0]?.id || '');
    this.selection = this.markingGroups.length
      ? new Set(this.markingGroups.flatMap((group) => [...group.ids]))
      : new Set((options.selection || []).map(String));
    this.data = normalizeData(options.data);
    this.visibleChartIds = new Set((options.visibleChartIds || this.data.charts.slice(0, 2).map((chart) => chart.id)).map(String));
    this.chartStates = [];
    this.rowStart = 0;
    this.pageRequestPending = false;
    this.resizeObserver = null;
    this.intersectionObserver = null;
    this.raf = 0;
    ensureStylesheet(this.doc);
    this.render();
  }

  update(input = {}) {
    const previousScrollTop = this.tableViewport?.scrollTop || 0;
    const previousScrollLeft = this.tableViewport?.scrollLeft || 0;
    const focusedWaferId = this.doc.activeElement?.closest?.('[data-wafer-id]')?.dataset.waferId || '';
    const focusedColumnKey = this.doc.activeElement?.closest?.('[data-column-key]')?.dataset.columnKey || '';
    const requiresRender = Boolean(input.data || input.rows || input.charts || input.columns
      || Object.prototype.hasOwnProperty.call(input, 'visibleChartIds'));
    if (Object.prototype.hasOwnProperty.call(input, 'markingGroups')) {
      this.markingGroups = normalizeMarkingGroups(input.markingGroups);
      this.selection = new Set(this.markingGroups.flatMap((group) => [...group.ids]));
    } else if (Object.prototype.hasOwnProperty.call(input, 'selection')) {
      this.selection = new Set((input.selection || []).map(String));
    }
    if (Object.prototype.hasOwnProperty.call(input, 'activeGroupId')) this.activeGroupId = String(input.activeGroupId || '');
    if (input.columns) this.options.columns = input.columns;
    if (input.data || input.rows || input.charts) this.data = normalizeData(input.data || input);
    if (Object.prototype.hasOwnProperty.call(input, 'visibleChartIds')) {
      this.visibleChartIds = new Set((input.visibleChartIds || []).map(String).slice(0, 2));
    }
    this.pageRequestPending = false;
    if (!requiresRender && this.root) {
      this.paintSelection();
      return this;
    }
    this.render();
    if (this.tableViewport) {
      this.tableViewport.scrollTop = previousScrollTop;
      this.tableViewport.scrollLeft = previousScrollLeft;
      this.doc.defaultView?.requestAnimationFrame(() => {
        if (!this.tableViewport) return;
        this.tableViewport.scrollTop = previousScrollTop;
        this.tableViewport.scrollLeft = previousScrollLeft;
        if (focusedWaferId) [...this.root.querySelectorAll('[data-wafer-id]')]
          .find((node) => node.dataset.waferId === focusedWaferId
            && (!focusedColumnKey || node.dataset.columnKey === focusedColumnKey))?.focus();
      });
    }
    return this;
  }

  getSelection() { return Array.from(this.selection); }

  activeSelection() {
    const group = this.markingGroups.find((item) => item.id === this.activeGroupId);
    return group ? [...group.ids] : this.getSelection();
  }

  groupFor(waferId) {
    return this.markingGroups.find((group) => group.role === 'overlay' && group.ids.has(waferId))
      || this.markingGroups.find((group) => group.id === this.activeGroupId && group.ids.has(waferId))
      || this.markingGroups.find((group) => group.ids.has(waferId)) || null;
  }

  groupsFor(waferId) {
    return this.markingGroups.filter((group) => group.ids.has(waferId)).sort((left, right) =>
      (left.role === 'overlay' ? -1 : 1) - (right.role === 'overlay' ? -1 : 1));
  }

  destroy() {
    if (this.resizeObserver) this.resizeObserver.disconnect();
    if (this.intersectionObserver) this.intersectionObserver.disconnect();
    if (this.raf) this.doc.defaultView.cancelAnimationFrame(this.raf);
    this.mount.replaceChildren();
  }

  setSelection(ids, source = 'external', detail = {}) {
    const normalized = [...new Set(ids.map(String))];
    const active = this.markingGroups.find((group) => group.id === this.activeGroupId);
    if (active) {
      active.ids = new Set(normalized);
      this.selection = new Set(this.markingGroups.flatMap((group) => [...group.ids]));
    } else this.selection = new Set(normalized);
    this.paintSelection();
    if (typeof this.options.onSelectionChange === 'function') {
      this.options.onSelectionChange(normalized, {
        source, groupId: active?.id || this.activeGroupId || null,
        globalSelection: this.getSelection(), ...detail,
      });
    }
  }

  toggle(waferId, source, detail = {}) {
    const next = new Set(this.activeSelection());
    if (next.has(waferId)) next.delete(waferId); else next.add(waferId);
    this.setSelection(Array.from(next), source, detail);
  }

  render() {
    if (this.resizeObserver) this.resizeObserver.disconnect();
    this.chartStates = [];
    const root = element(this.doc, 'section', 'rwb');
    root.setAttribute('aria-label', 'R&D 트렌드 조사');

    const head = element(this.doc, 'header', 'rwb__head');
    const titleBox = element(this.doc, 'div');
    titleBox.append(element(this.doc, 'h2', 'rwb__title', 'Trend Workbench'));
    titleBox.append(element(this.doc, 'p', 'rwb__subtitle', '불량 유형별 흐름과 웨이퍼 상세를 같은 마킹으로 조사합니다.'));
    head.append(titleBox);
    this.selectionText = element(this.doc, 'span', 'rwb__selection');
    head.append(this.selectionText);
    const clear = element(this.doc, 'button', 'rwb__clear', '마킹 해제');
    clear.type = 'button';
    clear.addEventListener('click', () => this.setSelection([], 'clear'));
    head.append(clear);
    root.append(head);

    const grid = element(this.doc, 'div', 'rwb__grid');
    const charts = element(this.doc, 'div', 'rwb__charts');
    const visibleCharts = this.data.charts.filter((chart) => this.visibleChartIds.has(chart.id)).slice(0, 2);
    const shownCharts = visibleCharts.length ? visibleCharts : this.data.charts.slice(0, 2);
    charts.classList.toggle('is-single', shownCharts.length === 1);
    shownCharts.forEach((chart) => charts.append(this.renderChart(chart, this.data.charts.indexOf(chart))));
    grid.append(charts);
    grid.append(this.renderTable());
    if (!this.data.charts.length) charts.append(element(this.doc, 'p', 'rwb__empty', '표시할 불량 유형 추세가 없습니다.'));
    root.append(grid);
    this.mount.replaceChildren(root);
    this.root = root;

    const ResizeObserverImpl = this.doc.defaultView && this.doc.defaultView.ResizeObserver;
    if (ResizeObserverImpl) {
      this.resizeObserver = new ResizeObserverImpl(() => this.scheduleChartPaint());
      for (const state of this.chartStates) this.resizeObserver.observe(state.wrap);
    } else {
      this.doc.defaultView?.addEventListener('resize', () => this.scheduleChartPaint(), { once: true });
    }
    const IntersectionObserverImpl = this.doc.defaultView && this.doc.defaultView.IntersectionObserver;
    if (IntersectionObserverImpl) {
      this.intersectionObserver = new IntersectionObserverImpl((entries) => {
        for (const entry of entries) {
          const state = this.chartStates.find((candidate) => candidate.wrap === entry.target);
          if (!state) continue;
          state.visible = entry.isIntersecting;
          if (state.visible) this.paintChart(state);
        }
      }, { rootMargin: '180px' });
      for (const state of this.chartStates) {
        state.visible = false;
        this.intersectionObserver.observe(state.wrap);
      }
    } else {
      for (const state of this.chartStates) state.visible = true;
    }
    this.scheduleChartPaint();
    this.paintSelection();
  }

  renderChart(chart, index) {
    const card = element(this.doc, 'article', 'rwb-chart');
    card.style.setProperty('--rwb-chart-index', index);
    const heading = element(this.doc, 'div', 'rwb-chart__head');
    heading.append(element(this.doc, 'h3', 'rwb-chart__title', chart.title));
    heading.append(element(this.doc, 'span', 'rwb-chart__count', `${chart.points.length.toLocaleString('ko-KR')}개 기록`));
    card.append(heading);
    const wrap = element(this.doc, 'div', 'rwb-chart__plot');
    const canvas = element(this.doc, 'canvas', 'rwb-chart__canvas');
    canvas.setAttribute('aria-label', `${chart.title} 추세 그래프`);
    canvas.setAttribute('aria-label', `${chart.title}; X축 ${chart.xLabel}; Y축 ${chart.yLabel}`);
    wrap.append(canvas);
    card.append(wrap);
    const state = { chart, wrap, canvas, hits: [], allHits: [], points: [], localRegion: null };
    const pointerPosition = (event) => {
      const rect = canvas.getBoundingClientRect();
      return {
        x: Math.max(0, Math.min(rect.width, event.clientX - rect.left)),
        y: Math.max(0, Math.min(rect.height, event.clientY - rect.top)),
        rect,
      };
    };
    canvas.addEventListener('pointerdown', (event) => {
      const point = pointerPosition(event);
      state.dragStart = { x: point.x, y: point.y, pointerId: event.pointerId };
      state.dragCurrent = { x: point.x, y: point.y };
      canvas.setPointerCapture?.(event.pointerId);
      this.scheduleChartPaint();
    });
    canvas.addEventListener('pointermove', (event) => {
      if (!state.dragStart) return;
      const point = pointerPosition(event);
      state.dragCurrent = { x: point.x, y: point.y };
      this.scheduleChartPaint();
    });
    canvas.addEventListener('pointerup', (event) => {
      const point = pointerPosition(event);
      const { x, y, rect } = point;
      const start = state.dragStart || { x, y };
      if (Math.abs(x - start.x) >= 6 || Math.abs(y - start.y) >= 6) {
        const box = {
          left: Math.max(CHART_PAD.l, Math.min(start.x, x)),
          right: Math.min(rect.width - CHART_PAD.r, Math.max(start.x, x)),
          top: Math.max(CHART_PAD.t, Math.min(start.y, y)),
          bottom: Math.min(rect.height - CHART_PAD.b, Math.max(start.y, y)),
        };
        const chosen = state.allHits.filter((hit) => hit.x >= box.left && hit.x <= box.right
          && hit.y >= box.top && hit.y <= box.bottom);
        const ids = [...new Set(chosen.map((hit) => hit.waferId))];
        const next = event.shiftKey ? [...new Set([...this.activeSelection(), ...ids])] : ids;
        const indexed = chosen.map((hit) => hit.point).sort((left, right) => left._seriesIndex - right._seriesIndex);
        state.localRegion = { chartId: chart.id, ids, box };
        state.dragStart = null; state.dragCurrent = null;
        this.setSelection(next, `chart:${chart.id}`, {
          mark: {
            kind: 'metric_region',
            chartId: chart.id,
            metricId: chart.yMetric,
            from: indexed[0]?.x ?? null,
            to: indexed.at(-1)?.x ?? null,
            yMin: indexed.length ? Math.min(...indexed.map((item) => item.y)) : null,
            yMax: indexed.length ? Math.max(...indexed.map((item) => item.y)) : null,
            ids,
          },
        });
        return;
      }
      state.dragStart = null; state.dragCurrent = null; state.localRegion = null;
      let best = null;
      let distance = Infinity;
      for (const hit of state.hits) {
        const d = Math.hypot(hit.x - x, hit.y - y);
        if (d < distance) { distance = d; best = hit; }
      }
      if (best && distance <= 14) this.toggle(best.waferId, `chart:${chart.id}`);
      else this.scheduleChartPaint();
    });
    canvas.addEventListener('pointercancel', () => {
      state.dragStart = null; state.dragCurrent = null; this.scheduleChartPaint();
    });
    this.chartStates.push(state);
    return card;
  }

  scheduleChartPaint() {
    if (this.raf) return;
    const win = this.doc.defaultView;
    if (!win) return;
    this.raf = win.requestAnimationFrame(() => {
      this.raf = 0;
      for (const state of this.chartStates) if (state.visible !== false) this.paintChart(state);
    });
  }

  paintChart(state) {
    const { canvas, wrap, chart } = state;
    const width = Math.max(220, Math.floor(wrap.clientWidth));
    const height = Math.max(160, Math.floor(wrap.clientHeight));
    const dpr = Math.min(2, this.doc.defaultView?.devicePixelRatio || 1);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const styles = this.doc.defaultView.getComputedStyle(this.root);
    const color = (name, fallback) => styles.getPropertyValue(name).trim() || fallback;
    const sampled = downsampleSeries(chart.points, this.options.downsampleLimit);
    // A marked wafer must remain visible in every chart even when the background
    // series is downsampled. This adds no semantic selection ceiling.
    const marked = chart.points.filter((point) => this.selection.has(point.waferId));
    const points = Array.from(new Set([...sampled, ...marked])).sort((a, b) => a._seriesIndex - b._seriesIndex);
    state.points = points;
    if (!points.length) {
      ctx.fillStyle = color('--rwb-muted', '#78859a');
      ctx.font = '13px sans-serif';
      ctx.fillText('표시할 기록이 없습니다.', 16, 28);
      state.hits = [];
      return;
    }
    const pad = CHART_PAD;
    const values = chart.points.map((point) => point.y);
    let min = Math.min(...values);
    let max = Math.max(...values);
    if (min === max) { min -= 1; max += 1; }
    ctx.strokeStyle = color('--rwb-grid', '#d8dee8');
    ctx.lineWidth = 1;
    for (let i = 0; i <= 3; i += 1) {
      const y = pad.t + ((height - pad.t - pad.b) * i / 3);
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(width - pad.r, y); ctx.stroke();
    }
    const dx = Math.max(1, chart.points.length - 1);
    const hitOf = (point) => ({
      waferId: point.waferId,
      seriesIndex: point._seriesIndex,
      x: pad.l + ((width - pad.l - pad.r) * point._seriesIndex / dx),
      y: pad.t + ((max - point.y) / (max - min)) * (height - pad.t - pad.b),
      point,
    });
    state.allHits = chart.points.map(hitOf);
    state.hits = points.map(hitOf);
    ctx.strokeStyle = color('--rwb-line', '#4f6bed');
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    state.hits.forEach((hit, i) => i ? ctx.lineTo(hit.x, hit.y) : ctx.moveTo(hit.x, hit.y));
    ctx.stroke();
    for (const hit of state.hits) {
      const groups = this.groupsFor(hit.waferId);
      const group = groups[0];
      const marked = Boolean(group);
      ctx.beginPath();
      ctx.arc(hit.x, hit.y, marked ? 5.5 : 3, 0, Math.PI * 2);
      ctx.fillStyle = marked ? group.color : color('--rwb-line', '#4f6bed');
      ctx.fill();
      if (marked) {
        ctx.strokeStyle = color('--rwb-surface', '#fff'); ctx.lineWidth = 1.5; ctx.stroke();
        groups.slice(1, 4).forEach((context, contextIndex) => {
          ctx.beginPath();
          ctx.arc(hit.x, hit.y, 7 + contextIndex * 2, 0, Math.PI * 2);
          ctx.strokeStyle = context.color; ctx.lineWidth = 1.5; ctx.stroke();
        });
      }
    }
    const activeGroup = this.markingGroups.find((group) => group.id === this.activeGroupId);
    const boxForIds = (ids) => {
      const hits = state.allHits.filter((hit) => ids.has(hit.waferId));
      if (!hits.length) return null;
      return {
        left: Math.max(pad.l, Math.min(...hits.map((hit) => hit.x)) - 5),
        right: Math.min(width - pad.r, Math.max(...hits.map((hit) => hit.x)) + 5),
        top: Math.max(pad.t, Math.min(...hits.map((hit) => hit.y)) - 5),
        bottom: Math.min(height - pad.b, Math.max(...hits.map((hit) => hit.y)) + 5),
      };
    };
    const drawBox = (box, stroke) => {
      if (!box || box.right < box.left || box.bottom < box.top) return;
      ctx.save();
      ctx.globalAlpha = 0.12; ctx.fillStyle = stroke;
      ctx.fillRect(box.left, box.top, box.right - box.left, box.bottom - box.top);
      ctx.restore();
      ctx.save();
      ctx.strokeStyle = stroke; ctx.lineWidth = 1.5; ctx.setLineDash([5, 3]);
      ctx.strokeRect(box.left, box.top, box.right - box.left, box.bottom - box.top);
      ctx.restore();
    };
    for (const group of this.markingGroups) {
      for (const region of group.regions.filter((item) => item.seriesId === chart.id)) {
        drawBox(boxForIds(region.ids), group.color);
      }
    }
    if (state.localRegion) {
      drawBox(boxForIds(new Set(state.localRegion.ids)) || state.localRegion.box,
        activeGroup?.color || color('--rwb-mark', '#e77b20'));
    }
    if (state.dragStart && state.dragCurrent) {
      drawBox({
        left: Math.max(pad.l, Math.min(state.dragStart.x, state.dragCurrent.x)),
        right: Math.min(width - pad.r, Math.max(state.dragStart.x, state.dragCurrent.x)),
        top: Math.max(pad.t, Math.min(state.dragStart.y, state.dragCurrent.y)),
        bottom: Math.min(height - pad.b, Math.max(state.dragStart.y, state.dragCurrent.y)),
      }, activeGroup?.color || color('--rwb-mark', '#e77b20'));
    }
    ctx.fillStyle = color('--rwb-muted', '#78859a');
    ctx.font = '11px sans-serif';
    ctx.fillText(max.toFixed(2), 2, pad.t + 4);
    ctx.fillText(min.toFixed(2), 2, height - pad.b + 4);
    const axisTick = (point) => {
      const value = point?.x ? new Date(point.x) : null;
      const date = value && Number.isFinite(value.getTime())
        ? value.toLocaleDateString('ko-KR', { month: '2-digit', day: '2-digit' }) : '';
      return [date, unitLabel(point)].filter(Boolean).join(' · ');
    };
    ctx.textAlign = 'left';
    ctx.fillText(axisTick(chart.points[0]), pad.l, height - 23);
    ctx.textAlign = 'right';
    ctx.fillText(axisTick(chart.points.at(-1)), width - pad.r, height - 23);
    ctx.textAlign = 'center';
    ctx.fillStyle = color('--rwb-text', '#172033');
    ctx.font = '600 11px sans-serif';
    ctx.fillText(`X: ${chart.xLabel}`, pad.l + (width - pad.l - pad.r) / 2, height - 7);
    ctx.save();
    ctx.translate(11, pad.t + (height - pad.t - pad.b) / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText(`Y: ${chart.yLabel}`, 0, 0);
    ctx.restore();
    ctx.textAlign = 'start';
  }

  renderTable() {
    const card = element(this.doc, 'section', 'rwb-table');
    const head = element(this.doc, 'div', 'rwb-table__head');
    head.append(element(this.doc, 'h3', 'rwb-table__title', 'Trend Table'));
    const metricColumns = this.options.columns.filter((column) => !['wafer', 'waferId', 'bondingLeg', 'bonding_leg'].includes(column.key));
    head.append(element(this.doc, 'span', 'rwb-table__count', `${this.data.rows.length.toLocaleString('ko-KR')} 실험단위 · ${metricColumns.length.toLocaleString('ko-KR')} 항목`));
    card.append(head);
    const viewport = element(this.doc, 'div', 'rwb-table__viewport');
    viewport.tabIndex = 0;
    viewport.setAttribute('aria-label', '본딩 실험단위 추세 표');
    const template = `180px repeat(${this.data.rows.length}, 140px)`;
    const header = element(this.doc, 'div', 'rwb-table__columns');
    header.style.gridTemplateColumns = template;
    header.append(element(this.doc, 'span', 'rwb-table__column rwb-table__corner', '항목'));
    for (const row of this.data.rows) {
      const wafer = element(this.doc, 'button', 'rwb-table__column rwb-table__wafer');
      wafer.type = 'button';
      wafer.dataset.waferId = row.waferId;
      wafer.title = unitLabel(row);
      wafer.append(element(this.doc, 'span', 'rwb-table__wafer-id', shortWaferId(row.wafer || row.waferId)));
      const leg = String(row.bondingLeg || row.bonding_leg || '').trim();
      if (leg) wafer.append(element(this.doc, 'span', 'rwb-table__leg', leg));
      wafer.setAttribute('aria-label', `${row.waferId} 웨이퍼 마킹`);
      wafer.addEventListener('click', () => this.toggle(row.waferId, 'table:wafer', {
        mark: { kind: 'entity_set', chartId: null, columnKind: 'identity', columnKey: 'wafer' },
      }));
      header.append(wafer);
    }
    viewport.append(header);
    const body = element(this.doc, 'div', 'rwb-table__body');
    body.style.width = 'max-content';
    body.style.minWidth = '100%';
    for (const column of metricColumns) {
      body.append(this.renderTableMetricRow(column, conditionScale(this.data.rows, column), template));
    }
    viewport.append(body);
    this.tableViewport = viewport;
    this.tableBody = body;
    viewport.addEventListener('scroll', () => {
      const remaining = viewport.scrollWidth - viewport.scrollLeft - viewport.clientWidth;
      if (!this.pageRequestPending && remaining < 140 * 5 && this.data.rows.length < this.data.totalRows && typeof this.options.onPageRequest === 'function') {
        this.pageRequestPending = true;
        this.options.onPageRequest({ cursor: this.data.cursor, limit: this.options.pageSize });
      }
    }, { passive: true });
    card.append(viewport);
    return card;
  }

  renderTableMetricRow(column, scale, template) {
    const node = element(this.doc, 'div', 'rwb-table__row');
    node.style.gridTemplateColumns = template;
    node.style.height = `${this.options.rowHeight}px`;
    const chartSelectable = !column.kind && String(column.key).includes(':');
    const label = element(this.doc, chartSelectable ? 'button' : 'span',
      `rwb-table__metric${chartSelectable ? ' rwb-table__metric--selectable' : ''}`, column.label);
    label.title = column.label;
    if (chartSelectable) {
      label.type = 'button';
      label.dataset.trendItem = column.key;
      label.setAttribute('aria-pressed', String(this.visibleChartIds.has(column.key)));
      label.addEventListener('click', () => {
        const next = [String(column.key)];
        if (typeof this.options.onVisibleChartsChange === 'function') {
          this.options.onVisibleChartsChange(next, { source: 'table:item', seriesId: column.key });
        }
        this.update({ visibleChartIds: next });
      });
    }
    node.append(label);
    for (const [index, row] of this.data.rows.entries()) {
      const formatter = typeof column.format === 'function' ? column.format : text;
      const formattedValue = formatter(row[column.key], row, index);
      const cell = element(this.doc, 'button', 'rwb-table__cell');
      cell.type = 'button';
      cell.append(element(this.doc, 'span', 'rwb-table__cell-value', formattedValue));
      cell.dataset.waferId = row.waferId;
      cell.dataset.columnKey = column.key;
      if (column.kind) cell.dataset.columnKind = column.kind;
      if (String(column.key).includes(':')) cell.dataset.seriesId = column.key;
      applyCondition(cell, row[column.key], scale);
      cell.setAttribute('aria-label', `${column.label} · ${unitLabel(row)} · ${formattedValue}`);
      cell.addEventListener('click', () => {
        const seriesId = cell.dataset.seriesId || '';
        const columnKind = cell.dataset.columnKind || '';
        this.toggle(row.waferId, `table:${column.key}`, {
        mark: {
          kind: columnKind === 'trace' ? 'trace_dimension' : 'entity_set',
            chartId: seriesId || null, columnKind, columnKey: column.key,
        },
      });
      });
      node.append(cell);
    }
    return node;
  }

  paintSelection() {
    if (!this.root) return;
    this.root.querySelectorAll('[data-wafer-id]').forEach((node) => {
      const marked = this.selection.has(node.dataset.waferId);
      const groups = this.groupsFor(node.dataset.waferId);
      const group = groups[0];
      node.classList.toggle('is-marked', marked);
      if (group) node.style.setProperty('--rwb-row-mark', group.color);
      else node.style.removeProperty('--rwb-row-mark');
      if (groups.length) node.style.setProperty('--rwb-row-mark-stack', markingStripe(groups));
      else node.style.removeProperty('--rwb-row-mark-stack');
      node.setAttribute('aria-pressed', String(marked));
    });
    const activeCount = this.activeSelection().length;
    this.selectionText.textContent = this.selection.size
      ? `${this.activeGroupId || 'Group'} ${activeCount.toLocaleString('ko-KR')} · 전체 ${this.selection.size.toLocaleString('ko-KR')}`
      : '마킹 없음';
    for (const state of this.chartStates) if (state.visible !== false) this.paintChart(state);
  }
}

let defaultInstance = null;

/** Initialize the default integration instance. Returns its controller. */
export function init(mount, options = {}) {
  if (defaultInstance) defaultInstance.destroy();
  defaultInstance = new TrendWorkbench(mount, options);
  return defaultInstance;
}

/** Update rows/charts/selection without replacing the integration contract. */
export function update(input = {}) {
  if (!defaultInstance) throw new Error('update: call init first');
  defaultInstance.update(input);
  return defaultInstance;
}

/** Return a copy of the stable wafer-id marking set. */
export function getSelection() {
  return defaultInstance ? defaultInstance.getSelection() : [];
}

export { TrendWorkbench };
