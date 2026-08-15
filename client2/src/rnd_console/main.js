import {
  createLedgerApi, LedgerApiError, StaleResponseError,
  normaliseTrendResponse, compositionToWorkspace, markingSnapshotToSelection,
} from './api.js';
import { createMarkingStore } from './state.js';
import { init as initTrend } from './trend_workbench.js';
import { initInvestigationWorkspace } from './investigation_workspace.js';
import './investigation_workspace.css';

const MAX_TABLE_WINDOW = 1000;
const KIND_STORAGE_KEY = 'rnd-console.finding-kinds.v1';
const CHART_STORAGE_KEY = 'rnd-console.visible-charts.v1';
const now = () => new Date().toISOString();

function mergeTrendPages(current, next) {
  if (!current) return next;
  const rows = new Map(current.rows.map((row) => [row.waferId, row]));
  next.rows.forEach((row) => rows.set(row.waferId, row));
  const bounded = [...rows.values()].slice(-MAX_TABLE_WINDOW);
  return { ...next, rows: bounded, totalRows: bounded.length + (next.truncated ? 1 : 0), charts: next.charts.length ? next.charts : current.charts };
}

function identitiesFromTrend(raw) {
  const values = [...(raw.table?.rows || []).map((row) => row.identity),
    ...(raw.series || []).flatMap((series) => (series.points || []).map((point) => point.identity))];
  return new Map(values.filter((identity) => identity?.mark_key).map((identity) => [identity.mark_key, identity]));
}

function physicsCandidate(resolution) {
  const surprise = resolution?.surprise || {};
  const signature = surprise.signature || {};
  if (!Number.isFinite(Number(surprise.score)) || surprise.state !== 'ready') return null;
  const processRows = resolution?.comparisons?.process || [];
  const sameParameter = (row) => row.signature?.step === signature.step
    && row.signature?.parameter === signature.parameter
    && row.signature?.source === signature.source;
  const referencePeer = processRows.find((row) => sameParameter(row)
    && String(row.signature?.value) !== String(signature.value)
    && (row.groups.find((group) => group.groupId === 'B')?.count || 0)
      > (row.groups.find((group) => group.groupId === 'A')?.count || 0));
  const denominators = new Map((surprise.denominators || []).map((item) => [String(item.group_id), Number(item.n || 0)]));
  const formatValue = (value) => signature.parameter?.includes('pressure') && Number.isFinite(Number(value))
    ? Number(value).toFixed(2) : String(value ?? '?');
  const causeValue = formatValue(signature.value);
  const referenceValue = referencePeer?.signature?.value;
  const comparisonText = referenceValue === undefined
    ? causeValue : `${causeValue} ↔ ${formatValue(referenceValue)}`;
  const unit = signature.parameter?.includes('pressure') ? ' MPa' : '';
  return {
    id: `physics:${surprise.facet_id || `${signature.step}:${signature.parameter}`}`,
    rank: 1,
    label: `${signature.step || 'Process'} · ${signature.parameter || 'parameter'} · ${comparisonText}${unit}`,
    sentence: `불량 ${denominators.get('A') || 0}개와 정상 ${denominators.get('B') || 0}개를 분리한 최상위 차이입니다.`,
    evidence_count: [...denominators.values()].reduce((sum, value) => sum + value, 0),
    surprise,
    gates: [
      { label: 'Statistical · 집단 차이 확인', verdict: 'pass' },
      { label: 'Upstream · 원장 근거 연결', verdict: surprise.coverage > 0 ? 'pass' : 'unknown' },
      { label: `Mechanism · ${surprise.mechanism_model_id || '모델 미연결'}`, verdict: surprise.binding_state === 'pass' ? 'pass' : 'unknown' },
    ],
  };
}

export function bootRNDConsole(doc = document, { fetchImpl = globalThis.fetch } = {}) {
  const trendRoot = doc.querySelector('[data-rnd-trend]');
  const investigationRoot = doc.querySelector('[data-rnd-investigation]');
  if (!trendRoot || !investigationRoot) throw new Error('R&D Console mount가 없습니다.');
  const status = doc.querySelector('[data-rnd-status]');
  const banner = doc.querySelector('[data-rnd-banner]');
  const windowInput = doc.querySelector('[data-rnd-window]');
  const apply = doc.querySelector('[data-rnd-apply]');
  const clear = doc.querySelector('[data-rnd-clear]');
  const contextNode = doc.querySelector('[data-rnd-context]');
  const kindOptions = doc.querySelector('[data-rnd-kind-options]');
  const groupButtons = [...doc.querySelectorAll('[data-rnd-group]')];
  const api = createLedgerApi({ fetchImpl });
  const marking = createMarkingStore();
  const identities = new Map();
  let trendModel = null;
  let trendController = null;
  let kindDefinitions = [];
  let selectedKinds = [];
  let visibleChartIds = [];

  const savedKindPreference = (() => {
    try {
      const fromUrl = new URL(doc.defaultView.location.href).searchParams.get('kinds');
      if (fromUrl) return fromUrl.split(',').map((value) => value.trim()).filter(Boolean);
      return JSON.parse(doc.defaultView.localStorage.getItem(KIND_STORAGE_KEY) || '[]');
    } catch { return []; }
  })();
  const savedChartPreference = (() => {
    try {
      const fromUrl = new URL(doc.defaultView.location.href).searchParams.get('charts');
      if (fromUrl) return fromUrl.split(',').map((value) => value.trim()).filter(Boolean);
      return JSON.parse(doc.defaultView.localStorage.getItem(CHART_STORAGE_KEY) || '[]');
    } catch { return []; }
  })();
  const persistKinds = () => {
    try {
      doc.defaultView.localStorage.setItem(KIND_STORAGE_KEY, JSON.stringify(selectedKinds));
      doc.defaultView.localStorage.setItem(CHART_STORAGE_KEY, JSON.stringify(visibleChartIds));
      const url = new URL(doc.defaultView.location.href);
      url.searchParams.set('kinds', selectedKinds.join(','));
      url.searchParams.set('charts', visibleChartIds.join(','));
      doc.defaultView.history.replaceState(null, '', url);
    } catch { /* persistence is optional */ }
  };
  const renderKindOptions = () => {
    if (!kindOptions) return;
    const makeOption = (value, labelText, checked, dataset) => {
      const label = doc.createElement('label');
      const input = doc.createElement('input');
      input.type = 'checkbox'; input.value = value; input.checked = checked; Object.assign(input.dataset, dataset);
      const text = doc.createElement('span'); text.textContent = labelText;
      label.append(input, text);
      return label;
    };
    const data = doc.createElement('fieldset');
    const dataTitle = doc.createElement('legend'); dataTitle.textContent = 'Data'; data.append(dataTitle);
    kindDefinitions.forEach((definition) => data.append(makeOption(definition.id, definition.label || definition.id, selectedKinds.includes(definition.id), { configKind: '' })));
    const charts = doc.createElement('fieldset');
    const chartTitle = doc.createElement('legend'); chartTitle.textContent = 'Charts'; charts.append(chartTitle);
    kindDefinitions.filter((definition) => selectedKinds.includes(definition.id)).flatMap((definition) => definition.series || [])
      .forEach((series) => charts.append(makeOption(series.id, series.label || series.id, visibleChartIds.includes(series.id), { chartSeries: '' })));
    kindOptions.replaceChildren(data, charts);
  };
  const registerKindDefinitions = (raw) => {
    if (kindDefinitions.length) return false;
    kindDefinitions = (raw.selectable_finding_kinds || raw.finding_kinds || []).map((definition) => ({ ...definition, id: String(definition.id) }));
    const declared = kindDefinitions.map((definition) => definition.id);
    const applied = (raw.applied_kinds || []).map((item) => String(item?.id || item)).filter((kind) => declared.includes(kind));
    const preferred = savedKindPreference.filter((kind) => declared.includes(kind));
    selectedKinds = preferred.length ? preferred : applied.length ? applied : declared;
    const availableSeries = kindDefinitions.filter((definition) => selectedKinds.includes(definition.id)).flatMap((definition) => definition.series || []);
    const preferredCharts = savedChartPreference.filter((id) => availableSeries.some((series) => series.id === id));
    visibleChartIds = (preferredCharts.length ? preferredCharts : availableSeries.filter((series) => series.active !== false).map((series) => series.id)).slice(0, 2);
    renderKindOptions();
    return preferred.length > 0 && (preferred.length !== applied.length || preferred.some((kind) => !applied.includes(kind)));
  };
  const findingKindForChart = (chartId) => kindDefinitions.find(
    (definition) => (definition.series || []).some((series) => series.id === chartId))?.id || '';
  const changeVisibleCharts = (next) => {
    visibleChartIds = (next || []).map(String).filter((id, index, values) => values.indexOf(id) === index).slice(0, 2);
    renderKindOptions(); persistKinds(); showBanner();
    void investigation.updateSelection(marking.snapshot());
  };
  const resolverFindingKind = (snapshot) => {
    const relevant = snapshot.groups.filter((group) => group.role !== 'overlay')
      .flatMap((group) => group.marks)
      .filter((mark) => mark.kind === 'entity_set' || mark.kind === 'time_range' || mark.kind === 'metric_region');
    const marked = new Set(relevant.map((mark) => mark.selector.findingKind).filter(Boolean));
    if (marked.size === 1) return [...marked][0];
    if (marked.size === 0 && visibleChartIds.length === 1) return findingKindForChart(visibleChartIds[0]) || undefined;
    if (relevant.length === 0 && selectedKinds.length === 1) return selectedKinds[0];
    return undefined;
  };

  const showBanner = (message = '', tone = 'info') => {
    banner.hidden = !message; banner.textContent = message; banner.dataset.tone = tone;
  };

  const investigation = initInvestigationWorkspace({
    root: investigationRoot,
    adapter: {
      async loadWorkspace({ selection: snapshot, signal }) {
        const populationByChip = {};
        let resolution = { state: 'empty', final_chip_ids: [], wafer_mark_keys: [], groups: [], comparisons: {} };
        const selections = markingSnapshotToSelection(snapshot, identities);
        if (selections.length) {
          const findingKind = resolverFindingKind(snapshot);
          if (!findingKind) showBanner('기전 분석은 Trend 항목 하나를 선택해야 합니다.', 'warning');
          try { resolution = await api.resolveSelection(selections, { window: '365d', findingKind, signal }); }
          catch (error) {
            if (error?.name === 'AbortError' || error instanceof StaleResponseError) throw error;
            resolution = { state: 'unavailable', reason: error.reason || 'selection_resolver_unavailable', final_chip_ids: [], wafer_mark_keys: [], groups: [], comparisons: {} };
          }
        }
        const chips = resolution.final_chip_ids || [];
        Object.assign(populationByChip, resolution.population_by_chip || {});
        if (!chips.length) return {
          ...compositionToWorkspace([], { selection: resolution.wafer_mark_keys || [], finalChipIds: [] }),
          state: resolution.state === 'empty' ? 'idle' : resolution.state,
          groups: resolution.groups, comparisons: resolution.comparisons,
          maps: resolution.maps || [], actions: resolution.actions || [], surprise: resolution.surprise,
          notes: [resolution.reason || '선택 범위를 아직 풀지 못했습니다.'],
        };
        try {
          const payloads = await api.loadCompositions(chips, { window: '365d' }, { signal });
          const workspace = compositionToWorkspace(payloads, { selection: resolution.wafer_mark_keys, finalChipIds: chips, populationByChip });
          const candidate = physicsCandidate(resolution);
          const analysisUnitCount = (resolution.groups || []).reduce((sum, group) => sum + Number(group.count || 0), 0);
          return {
            ...workspace,
            headline: analysisUnitCount ? `${analysisUnitCount}개 WF·LEG 비교` : workspace.headline,
            groups: resolution.groups, comparisons: resolution.comparisons,
            maps: (resolution.maps || []).length ? resolution.maps : workspace.maps,
            actions: [...(resolution.actions || []), ...(workspace.actions || [])],
            candidates: candidate
              ? [candidate, ...(workspace.candidates || []).map((item) => ({ ...item, rank: Number(item.rank || 0) + 1 }))]
              : workspace.candidates,
            surprise: resolution.surprise,
          };
        } catch (error) {
          if (error?.name === 'AbortError' || error instanceof StaleResponseError) throw error;
          return {
            ...compositionToWorkspace([], { selection: resolution.wafer_mark_keys, finalChipIds: chips, populationByChip }),
            state: error instanceof LedgerApiError ? error.reason : 'unavailable',
            headline: error instanceof LedgerApiError ? `구성 추적 불가: ${error.message}` : '구성 추적 응답을 읽지 못했습니다.',
          };
        }
      },
    },
    onSpatialMark(mark) {
      if (!mark.table || !mark.mapId) {
        showBanner('맵 기준 테이블이 없어 마킹을 연결하지 못했습니다.', 'warning');
        return;
      }
      if (mark.markKey) identities.set(mark.markKey, {
        type: 'WaferLeg', mark_key: mark.markKey,
        keys: { wafer: mark.wafer, bonding_leg: mark.bondingLeg },
      });
      marking.apply({
        kind: 'map_cells', groupId: marking.activeGroupId, subjectType: 'WaferLeg',
        selector: {
          frame: {
            table: mark.table, mapId: mark.mapId, stage: mark.stage,
            startX: mark.startX, startY: mark.startY, yInvert: mark.yInvert,
          },
          cells: [{ x: mark.x, y: mark.y, bondingLeg: mark.bondingLeg, materialId: mark.materialId }],
          layer: mark.layer, ids: mark.markKey ? [mark.markKey] : [],
        },
        origin: { viewId: 'layered-maps', source: mark.componentId || 'map' }, createdAt: now(),
      }, { mode: 'add', source: 'map:die' });
    },
    onComparisonMark(mark) {
      const predicate = mark.predicate || mark.category || 'comparison';
      const signature = mark.signature || { id: mark.id || mark.label || predicate };
      const ids = mark.ids || mark.waferMarkKeys || mark.wafer_mark_keys || [];
      const evidenceIds = mark.evidenceIds || mark.evidence_ids || [];
      const key = `${predicate}:${JSON.stringify(signature)}`;
      const groupId = marking.ensureOverlayGroup(key, mark.label || '비교 마킹', 'comparison:group');
      marking.replaceKind('claim_filter', [{
        kind: 'claim_filter', groupId, subjectType: 'WaferLeg',
        selector: { predicate, signature, ids, evidenceIds },
        origin: { viewId: 'investigation-workspace', source: mark.id || predicate }, createdAt: now(),
      }], groupId, 'comparison:mark');
    },
  });

  const paintMapMarks = (snapshot) => {
    const orderedGroups = [...snapshot.groups].sort((left, right) => (left.id === snapshot.activeGroupId ? -1 : right.id === snapshot.activeGroupId ? 1 : 0));
    investigationRoot.querySelectorAll('[data-map-cell]').forEach((cell) => {
      const group = orderedGroups.find((candidate) => candidate.marks.some((mark) => mark.kind === 'map_cells'
        && mark.selector.frame.mapId === cell.dataset.frameMapId
        && mark.selector.cells.some((point) => point.x === Number(cell.dataset.x) && point.y === Number(cell.dataset.y))
        && (!mark.selector.layer || mark.selector.layer === cell.dataset.layer)));
      cell.classList.toggle('is-context-marked', Boolean(group));
      if (group) cell.style.setProperty('--riw-map-mark-color', group.color);
      else cell.style.removeProperty('--riw-map-mark-color');
    });
  };
  const renderContext = (snapshot) => {
    const marks = snapshot.groups.flatMap((group) => group.marks);
    const entities = new Set(marks.filter((mark) => mark.kind === 'entity_set' || mark.kind === 'claim_filter').flatMap((mark) => mark.selector.ids));
    const times = marks.filter((mark) => mark.kind === 'time_range').length;
    const cells = marks.filter((mark) => mark.kind === 'map_cells').reduce((sum, mark) => sum + mark.selector.cells.length, 0);
    const subjects = [...entities].map((id) => identities.get(id)).filter(Boolean).map((identity) => {
      const keys = identity.keys || {};
      return keys.bonding_leg ? `WF ${keys.wafer} / LEG ${keys.bonding_leg}` : `WF ${keys.wafer || '-'}`;
    });
    const subjectText = subjects.length ? `${subjects.slice(0, 2).join(', ')}${subjects.length > 2 ? ` +${subjects.length - 2}` : ''}` : '선택 없음';
    contextNode.textContent = [subjectText, `시간 ${times}`, `다이 ${cells}`].join(' · ');
    groupButtons.forEach((button) => button.classList.toggle('is-active', button.dataset.rndGroup === snapshot.activeGroupId));
  };
  const trendGroups = (snapshot) => snapshot.groups.map((group) => ({
    id: group.id, color: group.color, label: group.label, role: group.role,
    ids: [...new Set(group.marks.filter((mark) => mark.kind === 'entity_set' || mark.kind === 'claim_filter').flatMap((mark) => mark.selector.ids))],
    regions: group.marks.filter((mark) => mark.kind === 'metric_region').map((mark) => ({ id: mark.id, ...mark.selector })),
  }));
  const pushMarking = (snapshot, meta) => {
    renderContext(snapshot);
    const waferIds = marking.waferMarkKeys();
    if (trendController && !String(meta.source).startsWith('trend:') && !String(meta.source).startsWith('chart:') && !String(meta.source).startsWith('table')) {
      trendController.update({ selection: waferIds, markingGroups: trendGroups(snapshot), activeGroupId: snapshot.activeGroupId, visibleChartIds });
    }
    void investigation.updateSelection(snapshot).then(() => paintMapMarks(snapshot));
  };
  const unsubscribe = marking.subscribe(pushMarking, { emit: true });

  const applyTrendMarking = (ids, meta) => {
    const groupId = meta.groupId || marking.activeGroupId;
    const chartId = meta.mark?.chartId || meta.mark?.seriesId || (String(meta.source).startsWith('chart:') ? String(meta.source).slice(6) : '');
    const isTraceMark = meta.columnKind === 'trace' || meta.mark?.kind === 'trace_dimension';
    const visibleFindingKind = visibleChartIds.length === 1 ? findingKindForChart(visibleChartIds[0]) : '';
    const findingKind = isTraceMark ? '' : findingKindForChart(chartId) || visibleFindingKind || (selectedKinds.length === 1 ? selectedKinds[0] : '');
    marking.replaceKind('entity_set', ids.length ? [{
      kind: 'entity_set', groupId, subjectType: 'WaferLeg', selector: { ids, findingKind },
      origin: { viewId: 'trend-workbench', source: meta.source }, createdAt: now(),
    }] : [], groupId, meta.source);
    if (meta.mark?.kind === 'time_range' && meta.mark.from && meta.mark.to) marking.replaceKind('time_range', [{
      kind: 'time_range', groupId, subjectType: 'WaferLeg',
      selector: { from: meta.mark.from, to: meta.mark.to, timezone: 'UTC', seriesId: meta.mark.chartId, findingKind, ids },
      origin: { viewId: 'trend-workbench', source: meta.source }, createdAt: now(),
    }], groupId, meta.source);
    if (meta.mark?.kind === 'metric_region' && meta.mark.from && meta.mark.to) marking.replaceKind('metric_region', [{
      kind: 'metric_region', groupId, subjectType: 'WaferLeg',
      selector: {
        seriesId: meta.mark.chartId, metricId: meta.mark.metricId || meta.mark.chartId,
        xFrom: meta.mark.from, xTo: meta.mark.to, yMin: meta.mark.yMin, yMax: meta.mark.yMax,
        findingKind, ids,
      },
      origin: { viewId: 'trend-workbench', source: meta.source }, createdAt: now(),
    }], groupId, meta.source);
  };

  async function loadTrends({ cursor = null, append = false } = {}) {
    status.textContent = append ? '다음 표 불러오는 중' : 'Trend 불러오는 중';
    if (!append) showBanner();
    try {
      const raw = await api.loadTrends({ window: windowInput?.value || '90d', kinds: kindDefinitions.length ? selectedKinds.join(',') : undefined, cursor, limit: 100, max_points: 300 });
      if (registerKindDefinitions(raw)) { persistKinds(); return loadTrends({ cursor: null, append: false }); }
      identitiesFromTrend(raw).forEach((identity, key) => identities.set(key, identity));
      const page = normaliseTrendResponse(raw);
      trendModel = append ? mergeTrendPages(trendModel, page) : page;
      const data = { charts: trendModel.charts, rows: trendModel.rows, totalRows: trendModel.totalRows, cursor: trendModel.cursor };
      if (!trendController) trendController = initTrend(trendRoot, {
        data, columns: trendModel.columns, selection: marking.waferMarkKeys(),
        markingGroups: trendGroups(marking.snapshot()), activeGroupId: marking.activeGroupId, visibleChartIds,
        onSelectionChange: applyTrendMarking,
        onVisibleChartsChange: changeVisibleCharts,
        onPageRequest: ({ cursor: nextCursor }) => { if (nextCursor) void loadTrends({ cursor: nextCursor, append: true }); },
      });
      else trendController.update({ data, columns: trendModel.columns, selection: marking.waferMarkKeys(), markingGroups: trendGroups(marking.snapshot()), activeGroupId: marking.activeGroupId, visibleChartIds });
      status.textContent = raw.state === 'ready' ? '원장 연결됨' : raw.state === 'empty' ? '관측 없음' : '원장 관계 없음';
      status.dataset.state = raw.state || 'unavailable';
      if (raw.state === 'absent') showBanner('Trend 원장 관계가 없습니다.', 'warning');
    } catch (error) {
      if (error?.name === 'AbortError' || error instanceof StaleResponseError) return;
      status.textContent = 'Trend API 사용 불가'; status.dataset.state = 'unavailable';
      showBanner(error instanceof LedgerApiError ? error.message : 'Trend 데이터를 불러오지 못했습니다.', 'error');
      if (!trendController) trendController = initTrend(trendRoot, {
        data: { charts: [], rows: [], totalRows: 0, cursor: null }, columns: [], selection: marking.waferMarkKeys(),
        markingGroups: trendGroups(marking.snapshot()), activeGroupId: marking.activeGroupId, visibleChartIds,
        onSelectionChange: applyTrendMarking,
        onVisibleChartsChange: changeVisibleCharts,
      });
    }
  }

  const refresh = () => { void loadTrends(); void investigation.updateSelection(marking.snapshot()); };
  const reloadTrendWindow = () => void loadTrends();
  const clearMarks = () => marking.clear(null, 'clear');
  const changeGroup = (event) => marking.setActiveGroup(event.currentTarget.dataset.rndGroup, 'group');
  const changeKinds = (event) => {
    if (!event.target.matches('input[type="checkbox"]')) return;
    if (event.target.dataset.chartSeries !== undefined) {
      const next = [...kindOptions.querySelectorAll('input[data-chart-series]:checked')].map((input) => input.value);
      if (next.length > 2) { event.target.checked = false; showBanner('Chart는 두 개까지 선택할 수 있습니다.', 'warning'); return; }
      changeVisibleCharts(next); trendController?.update({ visibleChartIds });
      return;
    }
    const next = [...kindOptions.querySelectorAll('input[data-config-kind]:checked')].map((input) => input.value);
    if (!next.length) { event.target.checked = true; showBanner('Trend 항목을 하나 이상 선택하세요.', 'warning'); return; }
    selectedKinds = kindDefinitions.map((definition) => definition.id).filter((id) => next.includes(id));
    const available = kindDefinitions.filter((definition) => selectedKinds.includes(definition.id)).flatMap((definition) => definition.series || []).map((series) => series.id);
    visibleChartIds = visibleChartIds.filter((id) => available.includes(id));
    if (!visibleChartIds.length) visibleChartIds = available.slice(0, 2);
    renderKindOptions(); persistKinds(); trendModel = null; void loadTrends();
  };
  apply?.addEventListener('click', refresh);
  clear?.addEventListener('click', clearMarks);
  groupButtons.forEach((button) => button.addEventListener('click', changeGroup));
  kindOptions?.addEventListener('change', changeKinds);
  windowInput?.addEventListener('change', reloadTrendWindow);
  void loadTrends();

  return Object.freeze({
    marking, refresh,
    destroy() {
      unsubscribe(); api.dispose(); trendController?.destroy(); investigation.destroy();
      apply?.removeEventListener('click', refresh); clear?.removeEventListener('click', clearMarks);
      groupButtons.forEach((button) => button.removeEventListener('click', changeGroup));
      kindOptions?.removeEventListener('change', changeKinds);
      windowInput?.removeEventListener('change', reloadTrendWindow);
    },
  });
}

if (typeof document !== 'undefined') bootRNDConsole(document);
