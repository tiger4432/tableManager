export const MARKING_SCHEMA_VERSION = 4;
export const MARK_KINDS = Object.freeze(['entity_set', 'time_range', 'metric_region', 'map_cells', 'claim_filter']);

const text = (value) => value === null || value === undefined ? '' : String(value);
const unique = (values) => [...new Set((values || []).map(String).filter(Boolean))].sort();
const declaredBoolean = (value) => value === true || value === 1 || value === 'true';
const stableObject = (value) => {
  if (Array.isArray(value)) return value.map(stableObject);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stableObject(value[key])]));
};

function stableKeyOf(mark) {
  if (mark.kind === 'entity_set') return `${mark.groupId}|entity_set|${mark.subjectType}|${mark.selector.findingKind}|${mark.selector.ids.join(',')}`;
  if (mark.kind === 'time_range') return `${mark.groupId}|time_range|${mark.selector.from}|${mark.selector.to}|${mark.selector.timezone}|${mark.selector.seriesId}|${mark.selector.findingKind}|${(mark.selector.ids || []).join(',')}`;
  if (mark.kind === 'metric_region') return `${mark.groupId}|metric_region|${mark.selector.seriesId}|${mark.selector.metricId}|${mark.selector.xFrom}|${mark.selector.xTo}|${mark.selector.yMin}|${mark.selector.yMax}|${mark.selector.findingKind}|${mark.selector.ids.join(',')}`;
  if (mark.kind === 'claim_filter') return `${mark.groupId}|claim_filter|${mark.selector.predicate}|${JSON.stringify(mark.selector.signature)}|${mark.selector.ids.join(',')}|${mark.selector.evidenceIds.join(',')}`;
  const frame = mark.selector.frame;
  const cells = mark.selector.cells.map((cell) => `${cell.x},${cell.y},${cell.bondingLeg || ''},${cell.materialId || ''}`).join(';');
  return `${mark.groupId}|map_cells|${frame.table}|${frame.mapId}|${frame.stage}|${frame.startX}|${frame.startY}|${frame.yInvert}|${mark.selector.layer}|${cells}|${(mark.selector.ids || []).join(',')}`;
}

export function canonicalMark(raw = {}) {
  const kind = text(raw.kind);
  if (!MARK_KINDS.includes(kind)) throw new TypeError(`지원하지 않는 mark kind: ${kind || 'empty'}`);
  const groupId = text(raw.groupId || raw.group_id || 'A');
  const origin = raw.origin || {};
  const base = {
    id: '', groupId, kind,
    subjectType: text(raw.subjectType || raw.subject_type || (kind === 'entity_set' ? 'Wafer' : '')),
    origin: { viewId: text(origin.viewId || origin.view_id || 'unknown'), source: text(origin.source || 'unknown') },
    createdAt: text(raw.createdAt || raw.created_at || '1970-01-01T00:00:00.000Z'),
  };
  const selector = raw.selector || {};
  if (kind === 'entity_set') {
    const ids = unique(selector.ids);
    if (!ids.length) throw new TypeError('entity_set mark에는 selector.ids가 필요합니다.');
    base.selector = { ids, findingKind: text(selector.findingKind || selector.finding_kind) };
  } else if (kind === 'time_range') {
    const from = text(selector.from);
    const to = text(selector.to);
    if (!from || !to) throw new TypeError('time_range mark에는 selector.from/to가 필요합니다.');
    const fromMs = Date.parse(from);
    const toMs = Date.parse(to);
    if (!Number.isFinite(fromMs) || !Number.isFinite(toMs) || fromMs > toMs) throw new TypeError('time_range mark의 from/to 순서가 올바르지 않습니다.');
    base.selector = { from, to, timezone: text(selector.timezone || 'UTC'), seriesId: text(selector.seriesId), findingKind: text(selector.findingKind || selector.finding_kind), ids: unique(selector.ids) };
  } else if (kind === 'metric_region') {
    const seriesId = text(selector.seriesId || selector.series_id);
    const xFrom = text(selector.xFrom || selector.x_from);
    const xTo = text(selector.xTo || selector.x_to);
    const xFromMs = Date.parse(xFrom);
    const xToMs = Date.parse(xTo);
    const yMin = Number(selector.yMin ?? selector.y_min);
    const yMax = Number(selector.yMax ?? selector.y_max);
    if (!seriesId || !Number.isFinite(xFromMs) || !Number.isFinite(xToMs) || !Number.isFinite(yMin) || !Number.isFinite(yMax)
      || xFromMs > xToMs || yMin > yMax) throw new TypeError('metric_region mark의 series/x/y 범위가 올바르지 않습니다.');
    base.selector = {
      seriesId, metricId: text(selector.metricId || selector.metric_id), xFrom, xTo, yMin, yMax,
      findingKind: text(selector.findingKind || selector.finding_kind), ids: unique(selector.ids),
    };
  } else if (kind === 'claim_filter') {
    const predicate = text(selector.predicate);
    const signature = stableObject(selector.signature || {});
    const ids = unique(selector.ids || selector.wafer_mark_keys);
    const evidenceIds = unique(selector.evidenceIds || selector.evidence_ids);
    if (!predicate || !Object.keys(signature).length) throw new TypeError('claim_filter mark에는 predicate/signature가 필요합니다.');
    base.selector = { predicate, signature, ids, evidenceIds };
  } else {
    const frame = selector.frame || {};
    const mapId = text(frame.mapId || frame.map_id);
    const table = text(frame.table);
    const cells = (selector.cells || []).map((cell) => ({
      x: Number(cell.x), y: Number(cell.y),
      bondingLeg: text(cell.bondingLeg || cell.bonding_leg),
      materialId: text(cell.materialId || cell.material_id),
    }));
    if (cells.some((cell) => !Number.isInteger(cell.x) || !Number.isInteger(cell.y))) throw new TypeError('map_cells mark의 x/y는 정수여야 합니다.');
    cells.sort((a, b) => a.y - b.y || a.x - b.x);
    if (!table || !mapId || !cells.length) throw new TypeError('map_cells mark에는 frame.table/mapId와 정수 cells가 필요합니다.');
    base.selector = {
      frame: {
        table, mapId, stage: text(frame.stage),
        startX: Number.isFinite(Number(frame.startX ?? frame.start_x)) ? Number(frame.startX ?? frame.start_x) : 1,
        startY: Number.isFinite(Number(frame.startY ?? frame.start_y)) ? Number(frame.startY ?? frame.start_y) : 1,
        yInvert: declaredBoolean(frame.yInvert ?? frame.y_invert ?? false),
      },
      cells: cells.filter((cell, index) => index === 0 || cell.x !== cells[index - 1].x || cell.y !== cells[index - 1].y
        || cell.bondingLeg !== cells[index - 1].bondingLeg || cell.materialId !== cells[index - 1].materialId),
      layer: text(selector.layer), ids: unique(selector.ids),
    };
  }
  base.id = text(raw.id) || `mark:${encodeURIComponent(stableKeyOf(base))}`;
  return base;
}

export function deterministicMarkKey(mark) { return stableKeyOf(canonicalMark(mark)); }

function canonicalGroup(raw = {}) {
  return {
    id: text(raw.id), label: text(raw.label || raw.id), color: text(raw.color || '#3259d9'),
    role: text(raw.role || 'analysis'),
    marks: (raw.marks || []).map(canonicalMark),
  };
}

const OVERLAY_PALETTE = Object.freeze(['#7A3E9D', '#007A63', '#A44800', '#0067A3', '#9B2C62', '#4C6B00']);
const overlayHash = (value) => [...String(value)].reduce((hash, char) => ((hash * 33) ^ char.charCodeAt(0)) >>> 0, 5381);

export function createMarkingStore({
  groups = [{ id: 'A', label: 'Defect', color: '#d04a52', role: 'analysis', marks: [] }, { id: 'B', label: 'Reference', color: '#3259d9', role: 'analysis', marks: [] }],
  activeGroupId = 'A',
} = {}) {
  let current = groups.map(canonicalGroup);
  let active = current.some((group) => group.id === activeGroupId) ? activeGroupId : current[0]?.id;
  const listeners = new Set();
  const snapshot = () => ({ schemaVersion: MARKING_SCHEMA_VERSION, activeGroupId: active, groups: current.map((group) => ({ ...group, marks: group.marks.map((mark) => structuredClone(mark)) })) });
  const publish = (source) => { const value = snapshot(); listeners.forEach((listener) => listener(value, { source })); };
  const mutate = (mark, mode, source) => {
    const value = canonicalMark({ ...mark, groupId: mark.groupId || active, createdAt: mark.createdAt || new Date().toISOString() });
    if (!current.some((group) => group.id === value.groupId)) throw new TypeError(`알 수 없는 marking group: ${value.groupId}`);
    current = current.map((group) => {
      if (group.id !== value.groupId) return group;
      const key = deterministicMarkKey(value);
      if (mode === 'replace') return { ...group, marks: [value] };
      if (mode === 'subtract') return { ...group, marks: group.marks.filter((candidate) => deterministicMarkKey(candidate) !== key) };
      return group.marks.some((candidate) => deterministicMarkKey(candidate) === key) ? group : { ...group, marks: [...group.marks, value] };
    });
    publish(source);
    return value;
  };
  return Object.freeze({
    snapshot,
    get activeGroupId() { return active; },
    setActiveGroup(groupId, source = 'group') {
      if (!current.some((group) => group.id === groupId) || active === groupId) return false;
      active = groupId; publish(source); return true;
    },
    apply(mark, { mode = 'add', source = 'external' } = {}) { return mutate(mark, mode, source); },
    ensureOverlayGroup(key, label = '비교 마킹', source = 'comparison') {
      const token = text(key);
      if (!token) throw new TypeError('overlay group key가 필요합니다.');
      const id = `overlay:${overlayHash(token).toString(16).padStart(8, '0')}`;
      if (!current.some((group) => group.id === id)) {
        current = [...current, canonicalGroup({ id, label, role: 'overlay', color: OVERLAY_PALETTE[overlayHash(token) % OVERLAY_PALETTE.length], marks: [] })];
        publish(source);
      }
      return id;
    },
    replaceKind(kind, marks, groupId = active, source = 'external') {
      if (!current.some((group) => group.id === groupId)) throw new TypeError(`알 수 없는 marking group: ${groupId}`);
      const values = (marks || []).map((mark) => canonicalMark({ ...mark, kind, groupId,
        createdAt: mark.createdAt || new Date().toISOString() }));
      current = current.map((group) => group.id === groupId
        ? { ...group, marks: [...group.marks.filter((mark) => mark.kind !== kind), ...values] }
        : group);
      publish(source);
    },
    clear(groupId = null, source = 'clear') {
      current = current.map((group) => (!groupId || group.id === groupId) ? { ...group, marks: [] } : group);
      publish(source);
    },
    waferMarkKeys() { return unique(current.flatMap((group) => group.marks.filter((mark) => mark.kind === 'entity_set' || mark.kind === 'claim_filter').flatMap((mark) => mark.selector.ids))); },
    subscribe(listener, { emit = false } = {}) {
      listeners.add(listener); if (emit) listener(snapshot(), { source: 'initial' });
      return () => listeners.delete(listener);
    },
  });
}

// Compatibility facade for legacy callers. New integration code uses createMarkingStore.
export function createSelectionStore(initial = []) {
  const store = createMarkingStore();
  if (initial.length) store.apply({ kind: 'entity_set', groupId: 'A', subjectType: 'Wafer', selector: { ids: initial }, origin: { viewId: 'legacy', source: 'initial' } }, { mode: 'replace', source: 'initial' });
  return Object.freeze({
    get: () => store.waferMarkKeys(), waferMarkKeys: () => store.waferMarkKeys(),
    replace(ids, source = 'external') { store.clear('A', source); if (ids.length) store.apply({ kind: 'entity_set', groupId: 'A', subjectType: 'Wafer', selector: { ids }, origin: { viewId: 'legacy', source } }, { mode: 'replace', source }); return true; },
    replaceWaferMarks(ids, source = 'external') { return this.replace(ids, source); },
    clear(source = 'clear') { store.clear(null, source); },
    subscribe(listener, options) { return store.subscribe((snapshot, meta) => listener(store.waferMarkKeys(), meta), options); },
    snapshot: store.snapshot,
  });
}
