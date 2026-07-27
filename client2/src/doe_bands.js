// ── DOE band model (M3) — value-set bands with typed FROM ──────────────────────
//
// THE INVERSION. A band no longer belongs to a value; a band REFERENCES A SET of
// values. `ALL 1→1`, `A 2→15`, `B,C 2→15` are three rows, and the last two are not an
// overlap because they apply to different dies.
//
// THE CONSEQUENCE, and the rule everything else depends on:
//
//     EVERY RULE IS EVALUATED PER VALUE, NEVER PER ROW.
//
// A row is expanded to its values first, and each value gets its own coverage map.
// Skip that expansion and `A 2→15` beside `B,C 2→15` reads as a double-covered layer -
// the validator would block a correct plan, and (worse, the same mistake in the other
// direction) a genuine overlap inside one value would slip through.
//
// TYPED FROM. `from = prevTo + 1` is dead: two bands legitimately share `2→15`, so
// position in an array no longer means anything and there is nothing to walk. What the
// derivation used to GUARANTEE is now CHECKED instead - B5+B6 together say the bands
// covering a value partition `1 … max` exactly once each, which is precisely the
// contiguity the walk produced by construction. The strictness did not change; it moved
// from derivation to validation.
//
// This module is pure: no DOM, no fetch, no module state. Declarations first with the
// export list at the bottom, because the contract harness slices `function NAME(` bodies
// out of this file's TEXT - an `export` prefix on the declaration breaks extraction and
// the harness exits 2 rather than silently passing.
//   → contracts/doe_band_rules/{vectors.json,client_harness.mjs}
//   → docs/spec/DOE_BAND_MODEL.md is the authority for the rule numbers below.

import { bandToState } from './transfer_plan.js';

// The scope token that means "every value defined in table ①".
const SCOPE_ALL = 'ALL';

// A boundary (`from` or `to`) is classified by the SAME judge as `to` always was.
// A second classifier here would let a value be readable in one column and not the
// other, and coverage would be computed from a number the panel never displayed.
function boundState(raw) {
  return bandToState({ to: raw });
}

// Row -> the values it actually applies to. `ALL` expands to every defined value, so a
// plan built entirely from `ALL` rows still validates per value like any other.
// Unknown names are RETURNED, not dropped: B4 has to be able to name them.
function expandBandValues(band, definedValues) {
  const defined = (definedValues || []).map(String);
  const raw = (band && band.values) || [];
  const list = Array.isArray(raw) ? raw : String(raw).split(',');
  const out = [];
  let sawAll = false;
  list.forEach(v => {
    const s = String(v === null || v === undefined ? '' : v).trim();
    if (s === '') return;
    if (s.toUpperCase() === SCOPE_ALL) { sawAll = true; return; }
    if (out.indexOf(s) < 0) out.push(s);
  });
  if (sawAll) defined.forEach(v => { if (out.indexOf(v) < 0) out.push(v); });
  return out;
}

// [13,14,15,19] -> "13–15층, 19층". The user is told WHICH layers, never just "gap".
function formatLayerRuns(layers) {
  const xs = [...new Set(layers)].sort((a, b) => a - b);
  const runs = [];
  let i = 0;
  while (i < xs.length) {
    let j = i;
    while (j + 1 < xs.length && xs[j + 1] === xs[j] + 1) j++;
    runs.push(xs[i] === xs[j] ? `${xs[i]}층` : `${xs[i]}–${xs[j]}층`);
    i = j + 1;
  }
  return runs.join(', ');
}

function bandLabel(band, idx) {
  const scope = (band && Array.isArray(band.values) && band.values.length)
    ? band.values.join(',') : SCOPE_ALL;
  const f = band ? band.from : '';
  const t = band ? band.to : '';
  return `${idx + 1}행 [${scope} ${f}→${t}]`;
}

// ── 자재 토큰 (BIN 차원) ────────────────────────────────────────────────────────
//
//   토큰 ::= 식별자 [ ":" BIN ]
//   식별자 ::= lot "_" slot   (특정 슬롯)  |  lot   (로트 전체 — 모든 슬롯)
//   BIN 생략 → 1
//
// A DT map is NOT one pool: it is partitioned by BIN, and two values can draw different
// BINs from the same map without competing. So the rollup's row identity is
// (lot, slot, bin) - collapse BIN and 잔여 comes out low with no visible cause.
//
// ⚠️ THIS REVERSES A RULE SETTLED EARLIER TODAY. `splitMaterialId` refuses an id with no
//    separator ("never guess"), and contracts/band_arithmetic pins that refusal. Under
//    this grammar a bare `MID1` is not unresolvable - it MEANS the whole lot. The
//    never-guess principle is untouched and still applies to every genuinely malformed
//    token (`ABC_`, `_01`, `_`, blank, and every BIN failure below), which is why those
//    all still refuse. Exactly one legacy case changes meaning; see
//    contracts/doe_band_rules/vectors.json → material_token_cases.
//
// ⚠️ `parseMaterialToken` SUPERSEDES `splitMaterialId`. When the model lands, the old one
//    is DELETED, not left beside it - two readers of material identity is precisely the
//    "한 화면에 두 개의 가용치" defect that function's own comment warns about.
//
// Returns {ok, lot, slot, bin, scope, raw, reason}. On failure every field is null (not
// '') so a caller cannot forget to check, and `reason` is user-facing Korean.
function parseMaterialToken(raw) {
  const bad = reason => ({ ok: false, lot: null, slot: null, bin: null, scope: null, raw: String(raw ?? ''), reason });
  const s = String(raw === null || raw === undefined ? '' : raw).trim();
  if (s === '') return bad('빈 값입니다.');

  // `:` splits from the RIGHT - a lot name may legitimately contain a colon.
  let idPart = s;
  let bin = 1;
  const ci = s.lastIndexOf(':');
  if (ci >= 0) {
    idPart = s.slice(0, ci).trim();
    const binPart = s.slice(ci + 1).trim();
    if (binPart === '') return bad("':' 뒤에 BIN이 없습니다.");
    // Same integer reader as the layer boundaries. A second number parser here is how
    // '0x10' became 16 on one side and 0 on the other.
    const st = boundState(binPart);
    if (st.state !== 'ok') return bad(`BIN '${binPart}'을(를) 정수로 읽을 수 없습니다.`);
    if (st.value < 1) return bad(`BIN은 1 이상이어야 합니다 (지금 ${st.value}).`);
    bin = st.value;
  }
  if (idPart === '') return bad('자재 식별자가 비어 있습니다.');

  // `_` also splits from the RIGHT, so the FIRST field absorbs extras: LOT_A_01 -> LOT_A + 01.
  const ui = idPart.lastIndexOf('_');
  if (ui < 0) {
    return { ok: true, lot: idPart, slot: null, bin, scope: 'lot', raw: s, reason: '' };
  }
  const lot = idPart.slice(0, ui).trim();
  const slot = idPart.slice(ui + 1).trim();
  // A dangling separator is a typo, not a scope. Reading `ABC_` as "the whole lot ABC"
  // would be the guess this grammar still refuses to make.
  if (!lot || !slot) return bad(`'${idPart}'을(를) lot_slot으로 나눌 수 없습니다.`);
  return { ok: true, lot, slot, bin, scope: 'slot', raw: s, reason: '' };
}

// Stable identity of one rollup row.
//
// Built with JSON.stringify rather than by joining on a separator, and that is not
// stylistic. Concatenation needs a character that cannot occur in a lot name; the obvious
// candidates are either legal in a lot name ('|', '_', ':') or invisible control codes
// that tooling silently strips - which is exactly what happened here: an earlier version
// of this line joined on U+001F, the characters were dropped on write, and
// `MID1_12:3` and `MID11_2:3` both produced "MID1123". Two unrelated material pools
// merged into one rollup row and their 사용 was summed.
//
// JSON.stringify has no such failure mode: it escapes the components itself, it survives
// any editor, it is readable in a debug dump, and `null` (whole lot) is structurally
// distinct from the string "null" (a slot literally named that).
function materialPoolKey(tok) {
  if (!tok || !tok.ok) return null;
  return JSON.stringify([tok.lot, tok.scope === 'lot' ? null : tok.slot, tok.bin]);
}

// Layers a band covers, or null when either boundary is unreadable. Callers must treat
// null as "cannot be computed" and never as an empty range - an unreadable boundary that
// silently contributed zero layers is how a 16-layer stack becomes a 15-layer stack.
function bandLayerSpan(band) {
  const f = boundState(band && band.from);
  const t = boundState(band && band.to);
  if (f.state !== 'ok' || t.state !== 'ok') return null;
  if (f.value < 1) return null;
  if (f.value > t.value) return null;
  const out = [];
  for (let L = f.value; L <= t.value; L++) out.push(L);
  return out;
}

// Per value -> per layer -> how many bands cover it. The single structure B5, B6 and B8
// all read, so "covered" cannot mean two different things in two rules.
function buildCoverage(plan) {
  const defined = ((plan && plan.values) || []).map(v => String(v && v.value !== undefined ? v.value : v));
  const bands = (plan && plan.bands) || [];
  const cover = new Map();               // value -> Map(layer -> [band indexes])
  defined.forEach(v => cover.set(v, new Map()));
  bands.forEach((band, idx) => {
    const span = bandLayerSpan(band);
    if (span === null) return;           // B1/B2/B3 report it; it contributes nothing
    expandBandValues(band, defined).forEach(v => {
      if (!cover.has(v)) return;         // B4 reports it; it covers no defined value
      const byLayer = cover.get(v);
      span.forEach(L => {
        if (!byLayer.has(L)) byLayer.set(L, []);
        byLayer.get(L).push(idx);
      });
    });
  });
  return cover;
}

// The whole rule set. Returns { ok, blocks[], warns[] }; `ok` is false iff blocks exist.
// Each entry carries { rule, message, value?, band? } so the panel can name the reason
// on screen instead of saying "저장 실패".
//
// plan = { values: [{value, desc, color}], bands: [{seq, values[], from, to, materials[], knobs[]}] }
function validateBandPlan(plan) {
  const blocks = [];
  const warns = [];
  const valueRows = (plan && plan.values) || [];
  const bands = (plan && plan.bands) || [];
  const defined = valueRows.map(v => String(v && v.value !== undefined ? v.value : v));
  const definedSet = new Set(defined);
  const add = (list, rule, message, extra) => list.push({ rule, message, ...(extra || {}) });

  // ── row-level rules ─────────────────────────────────────────────────────────
  bands.forEach((band, idx) => {
    const label = bandLabel(band, idx);
    const f = boundState(band && band.from);
    const t = boundState(band && band.to);

    // B3 first: with an unreadable boundary nothing downstream can be computed at all.
    // blank and invalid are ONE case here on purpose - both mean "no number".
    if (f.state !== 'ok' || t.state !== 'ok') {
      const which = f.state !== 'ok' ? 'FROM' : 'TO';
      add(blocks, 'B3', `${label} ${which} 값을 정수로 읽을 수 없습니다 — 층 범위를 계산할 수 없습니다.`, { band: idx });
    } else {
      if (f.value < 1) add(blocks, 'B2', `${label} FROM은 1 이상이어야 합니다 (지금 ${f.value}).`, { band: idx });
      if (f.value > t.value) add(blocks, 'B1', `${label} FROM ${f.value}이(가) TO ${t.value}보다 큽니다.`, { band: idx });
    }

    // B4 - a reference to a value table ① does not define
    const named = expandBandValues(band, defined).filter(v => !definedSet.has(v));
    if (named.length > 0) {
      add(blocks, 'B4', `${label} 값 정의에 없는 값을 참조합니다: ${named.join(', ')}`, { band: idx });
    }

    // B7 - a band with no material
    const mats = (band && Array.isArray(band.materials)) ? band.materials.map(m => String(m).trim()).filter(Boolean) : [];
    if (mats.length === 0) {
      add(blocks, 'B7', `${label} 자재가 없습니다.`, { band: idx });
    } else {
      const dup = mats.filter((m, i) => mats.indexOf(m) !== i);
      if (dup.length > 0) add(warns, 'W-DUP-MAT', `${label} 같은 자재가 중복 지정됐습니다: ${[...new Set(dup)].join(', ')}`, { band: idx });
      // An unparseable material token blocks. It cannot be looked up, so its 가용 could
      // only ever be reported as 0 - and 0 reads as "all consumed" when the truth is
      // "we never resolved it". Refuse rather than guess.
      mats.forEach(raw => {
        const t = parseMaterialToken(raw);
        if (!t.ok) add(blocks, 'B7', `${label} 자재 '${raw}'을(를) 읽을 수 없습니다 — ${t.reason}`, { band: idx });
      });
    }

    // B9 - a band that scopes to nothing covers nothing. It has to block, because B6
    // cannot see it when it is the TOP range: max(V) is derived from COVERED layers, so
    // an unassigned top range simply lowers max and all eight other rules pass. The same
    // mistake one row lower IS caught. That position-dependent asymmetry is how a
    // 16-layer stack silently becomes 15.
    if (expandBandValues(band, defined).length === 0) {
      add(blocks, 'B9', `${label} 적용할 값이 없습니다 — 이 층 범위는 어떤 값에도 반영되지 않습니다.`, { band: idx });
    }
  });

  // ── B10: a whole lot and one of its own slots, in the same BIN ──────────────
  // `MID1:2` covers every slot of MID1 at BIN 2; `MID1_03:2` covers slot 03 at BIN 2.
  // Together they count slot 03 twice, and inflated demand shows up as a shortage at the
  // worst moment. Same lot at a DIFFERENT bin is a different pool and is fine.
  {
    const lotScoped = new Map();     // "lotbin" -> raw token
    const slotScoped = new Map();
    bands.forEach((band, idx) => {
      ((band && band.materials) || []).forEach(raw => {
        const t = parseMaterialToken(raw);
        if (!t.ok) return;           // B7/W-MAT report it; do not double-report here
        const key = `${t.lot}${t.bin}`;
        (t.scope === 'lot' ? lotScoped : slotScoped).set(key, { raw: t.raw, band: idx });
      });
    });
    lotScoped.forEach((lotHit, key) => {
      const slotHit = slotScoped.get(key);
      if (!slotHit) return;
      add(blocks, 'B10', `자재 '${lotHit.raw}'(로트 전체)와 '${slotHit.raw}'(그 로트의 슬롯)이 같은 BIN에 함께 지정됐습니다 — 그 슬롯이 두 번 계산됩니다.`,
        { band: slotHit.band });
    });
  }

  // ── per-value rules. Everything below reads ONE coverage structure. ──────────
  const cover = buildCoverage(plan);
  defined.forEach(v => {
    const byLayer = cover.get(v) || new Map();
    const layers = [...byLayer.keys()];

    // B8 - defined in ① and covered by nothing
    if (layers.length === 0) {
      add(blocks, 'B8', `값 '${v}'을(를) 덮는 구간이 없습니다.`, { value: v });
      return;                       // max is undefined; B5/B6 have nothing to say
    }

    // B5 - overlap, per (value, layer)
    const doubled = layers.filter(L => byLayer.get(L).length > 1).sort((a, b) => a - b);
    if (doubled.length > 0) {
      const rows = [...new Set(doubled.flatMap(L => byLayer.get(L)))].map(i => i + 1).sort((a, b) => a - b);
      add(blocks, 'B5', `값 '${v}'의 ${formatLayerRuns(doubled)}이(가) 두 번 이상 덮였습니다 (${rows.join('·')}행).`, { value: v });
    }

    // B6 - gap inside 1 … max(V). NOTE: max is the highest COVERED layer for this value,
    // so a range above it that nobody assigned is invisible here. That is the hole the
    // W-NO-SCOPE warning above exists to surface.
    const max = Math.max(...layers);
    const missing = [];
    for (let L = 1; L <= max; L++) if (!byLayer.has(L)) missing.push(L);
    if (missing.length > 0) {
      add(blocks, 'B6', `값 '${v}'의 ${formatLayerRuns(missing)}이(가) 비어 있습니다 (1–${max}층 중).`, { value: v });
    }
  });

  return { ok: blocks.length === 0, blocks, warns };
}

// Total demand of ONE band = (sum of painted cells over the values it covers) × layers.
// Per material = ceil(total / material count).
//
// ⚠️ THE CEILING DOES NOT DISTRIBUTE. Computing a per-value share and adding them up
//    gives a different, larger number than one ceiling over the summed total:
//        ceil(3/2) + ceil(3/2) = 4     but     ceil(6/2) = 3
//    A `B,C` band is ONE demand on ONE material set, so the sum happens first and the
//    ceiling exactly once, here. Any second place that computes this is a defect by
//    construction - see the `saveLegendToServer` ceil/round incident.
function bandDemand(band, paintedOf, definedValues) {
  const span = bandLayerSpan(band);
  if (span === null) return { layers: 0, total: 0, share: 0 };
  const layers = span.length;
  const values = expandBandValues(band, definedValues);
  const painted = values.reduce((sum, v) => sum + Number(paintedOf(v) || 0), 0);
  const total = painted * layers;
  const mats = (band && Array.isArray(band.materials)) ? band.materials.filter(m => String(m).trim() !== '') : [];
  const share = mats.length > 0 ? Math.ceil(total / mats.length) : 0;
  return { layers, total, share };
}

// ── ③ 자재 롤업 — 파생 전용 ───────────────────────────────────────────────────
//
// Row identity is the POOL (lot, slot, bin), not the material name.
//   사용 = Σ over bands  ceil(층수 × 그 구간 값들로 칠한 셀 수 ÷ 자재 수)
//
// The per-material ceiling means the shares of one band sum to MORE than that band's
// total. That is deliberate and long-standing: rounding down or to nearest hides a
// shortfall, and a plan that quietly under-orders is worse than one that over-orders.
function materialRollupRows(plan, paintedOf) {
  const defined = ((plan && plan.values) || []).map(v => String(v && v.value !== undefined ? v.value : v));
  const byPool = new Map();
  ((plan && plan.bands) || []).forEach((band, idx) => {
    const d = bandDemand(band, paintedOf, defined);
    if (d.share === 0) return;
    ((band && band.materials) || []).forEach(raw => {
      const tok = parseMaterialToken(raw);
      const key = materialPoolKey(tok);
      if (key === null) return;                 // B7 blocks the save; it is not a row here
      if (!byPool.has(key)) {
        byPool.set(key, { key, lot: tok.lot, slot: tok.slot, bin: tok.bin, scope: tok.scope, raw: tok.raw, used: 0, uses: [] });
      }
      const e = byPool.get(key);
      e.used += d.share;
      e.uses.push({ band: idx, seq: band.seq, from: band.from, to: band.to, qty: d.share });
    });
  });
  return [...byPool.values()].sort((a, b) =>
    String(a.lot).localeCompare(String(b.lot))
    || String(a.slot ?? '').localeCompare(String(b.slot ?? ''))
    || a.bin - b.bin);
}

// 잔여 = 가용 − 사용, WITH the reliability of 가용 carried through.
//
// 🔴 잔여 must NEVER be a number when 가용 is not trustworthy. A confident figure derived
//    from an untrustworthy input is worse than no figure: `0` reads as "all consumed"
//    when the truth may be "that BIN does not exist in this map" or "we could not ask".
//    `availability` is whatever `availabilityOf` returns - {status, value, reliable, reason}.
// Hiding the number is only half the rule. "이 BIN이 이 맵에 없다", "서버가 답을 못 준다"
// and "아직 안 물어봤다" are three different situations and the user acts differently on
// each - collapsing them into one generic "미상" makes the hiding uninformative.
// `availabilityOf` already computes precise reasons, so its text wins whenever it has
// one; the defaults below only cover statuses it does not describe.
const REMAINING_UNKNOWN_REASON = {
  bin_absent: '이 맵에 해당 BIN이 없습니다 — 소진된 것이 아닙니다.',
  loading: '가용을 조회하는 중입니다.',
  not_queried: '가용을 아직 조회하지 않았습니다.',
};
function remainingState(availability, used) {
  const a = availability || {};
  const unknown = reason => ({ value: null, reliable: false, reason });
  if (a.status === 'bin_absent') return unknown(REMAINING_UNKNOWN_REASON.bin_absent);
  if (a.status === null || a.status === undefined) return unknown(a.reason || REMAINING_UNKNOWN_REASON.not_queried);
  if (a.status === 'loading') return unknown(a.reason || REMAINING_UNKNOWN_REASON.loading);
  if (a.reliable !== true || a.value === null || a.value === undefined) {
    return unknown(a.reason || '가용을 신뢰할 수 없습니다.');
  }
  return { value: Number(a.value) - Number(used || 0), reliable: true, reason: '' };
}

// Renaming a value must follow it into every band that references it. In the old model
// `bands` lived INSIDE the value's row, so a rename carried them along for free; with the
// inversion the reference is by NAME and a rename orphans it. Call this at the same site
// that already remaps the grid cells (`updateLegendRowForPanel` -> `remapGridValues`).
function remapBandValues(bands, oldVal, newVal) {
  const from = String(oldVal), to = String(newVal);
  return (bands || []).map(b => {
    const vals = Array.isArray(b && b.values) ? b.values : [];
    const next = [];
    vals.forEach(v => {
      const s = String(v);
      const mapped = (s === from) ? to : s;
      if (next.indexOf(mapped) < 0) next.push(mapped);   // renaming onto a sibling merges
    });
    return { ...b, values: next };
  });
}

export {
  SCOPE_ALL, boundState, expandBandValues, bandLayerSpan, buildCoverage,
  validateBandPlan, bandDemand, formatLayerRuns,
  parseMaterialToken, materialPoolKey, materialRollupRows, remainingState, remapBandValues,
};
