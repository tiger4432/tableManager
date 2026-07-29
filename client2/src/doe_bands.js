// ── DOE zone model — STACK + three fixed zones ────────────────────────────────
//
// WHAT REPLACED WHAT. The band model (rows with FROM→TO, value-set scope, `seq` identity)
// is retired. A value's layer structure is now ONE number and THREE zones:
//
//     STACK = 그 값의 총 층수
//     1H    = 1층        — 비면 MID가 1층부터
//     MID   = 그 사이 전부
//     TOP   = STACK층    — 비면 MID가 STACK까지
//
//   MID 구역 = (1H 있으면 2, 없으면 1) … (TOP 있으면 STACK−1, 없으면 STACK)
//
// `dt_map` is the DEGENERATE case, not an incomplete one: STACK = 1, MID only, no 1H, no
// TOP. It must pass in silence. A model that nags at its own degenerate case teaches people
// to ignore the validator, and then they ignore the one that matters.
//
// ── WHY FIVE BLOCKING RULES REPLACED TEN ─────────────────────────────────────
//
// The zones TILE `1 … STACK` BY CONSTRUCTION. There is no arrangement of 1H/MID/TOP that
// covers a layer twice or leaves one uncovered, so the old B5 (overlap) and B6 (gap) were
// not moved or relaxed - THEY BECAME UNSTATEABLE. Same for B1/B2 (FROM>TO, FROM<1: there
// is no FROM) and B4/B9 (a band naming values it does not define / naming none: a zone
// belongs to exactly one value, by position).
//
// 🔴 THE ONE HAZARD THAT SURVIVED THE TRANSLATION, and the reason V5 exists.
//    DOE_BAND_MODEL §3 records why B9 was needed: `max(V)` was derived from COVERED layers,
//    so an unassigned top range simply LOWERED max and all the other rules passed - a
//    16-layer stack silently became 15. Zones do not derive the height from coverage;
//    STACK states it. That is what closes the hole - but only while STACK is READABLE.
//    An unreadable STACK read as 0 (or skipped) reproduces the identical defect: the
//    screen is fine and the number is short. So V5 blocks, and it blocks FIRST, before
//    anything downstream can compute a zone from a height nobody could read.
//
// This module is pure: no DOM, no fetch, no module state. Declarations first with the
// export list at the bottom, because the contract harness slices `function NAME(` bodies
// out of this file's TEXT - an `export` prefix on the declaration breaks extraction and
// the harness exits 2 rather than silently passing.
//   → contracts/doe_band_rules/{vectors.json,client_harness.mjs}
//   → docs/spec/MAP_EDITOR_SPEC.md §6.0-bis is the authority for the rule numbers below.

// `prevTo` is imported rather than re-derived: it is the retired band model's backward
// walk, it is still pinned by contracts/band_arithmetic (the SERVER still runs it), and
// `bandsToZones` below is now its only client caller. Re-typing "the previous band's to"
// here would be a second implementation of a rule a contract file already fixes.
import { bandToState, prevTo } from './transfer_plan.js';

// The three zones, in layer order. An array rather than three named branches: every
// consumer that walks zones walks THIS, so a fourth zone (or a reorder) cannot be added
// in one place and missed in five.
const ZONES = ['mat_1h', 'mat_mid', 'mat_top'];

// Zone id -> the header word the user types in Excel. These strings are the paste
// contract AND the on-screen column headings - deliberately the same strings, because
// name-matching only works if the word the screen shows is the word the parser looks for.
const ZONE_LABEL = { mat_1h: '1H', mat_mid: 'MID', mat_top: 'TOP' };

// A number is classified by the SAME judge the layer boundaries always used. A second
// classifier here would let STACK be readable in one place and not another, and a zone
// would be computed from a height the panel never displayed.
function boundState(raw) {
  return bandToState({ to: raw });
}

// STACK — 4-state, and `blank` is NOT an error. A value being typed has no STACK yet;
// only a value that is being SAVED needs one. Callers distinguish: the renderer shows
// blank as "미정", the validator blocks it (V5) because a plan cannot go out half-typed.
//
// `marker` (U9, user 2026-07-28): an EXPLICIT 0 declares a MARKER value (상태 표시 값) —
// its painted cells state a condition (e.g. BASE FAIL), not a layer assignment. No zones,
// no demand, no rollup row; V6 reports the one contradiction (a marker with zone content).
// Blank is NOT folded into it: blank is absence, 0 is a declaration. Only exactly 0 —
// negatives stay invalid.
function stackState(row) {
  const st = boundState(row && row.stack);
  if (st.state !== 'ok') return { value: null, state: st.state };
  if (st.value === 0) return { value: 0, state: 'marker' };
  if (st.value < 0) return { value: st.value, state: 'invalid' };   // negatives are not heights
  return { value: st.value, state: 'ok' };
}

// [13,14,15,19] -> "13–15층, 19층". Kept from the band model unchanged: the gap message it
// was written for is gone, but "which layers does this zone cover" is asked on every row.
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

// ── 자재 목록 (한 구역의 칸 하나) ──────────────────────────────────────────────
//
// 줄바꿈으로 나눈다 - that is exactly what Excel puts inside a quoted cell, so the raw text
// of this field and the clipboard's are the same bytes and the round trip has nothing to
// convert. 쉼표도 받는다 (총괄 결정): Alt+Enter in Excel is painful, and comma is already
// the separator for tags elsewhere in this design. Accepting both costs one character
// class; refusing one of them costs the user a trip back to Excel.
function parseMaterialList(raw) {
  if (Array.isArray(raw)) {
    const out = [];
    raw.forEach(v => {
      const s = String(v === null || v === undefined ? '' : v).trim();
      if (s && out.indexOf(s) < 0) out.push(s);
    });
    return out;
  }
  const s = String(raw === null || raw === undefined ? '' : raw);
  const out = [];
  s.split(/[\n,]/).forEach(part => {
    const t = part.trim();
    if (t && out.indexOf(t) < 0) out.push(t);
  });
  return out;
}

// The canonical text of a zone cell. Newline-joined, never comma-joined: comma is an
// ACCEPTED input, newline is the EMITTED one, and Excel round-trips newline-in-a-quoted-
// cell losslessly. Emitting commas would make `MID1, MID3` come back as one token the day
// somebody's lot name legitimately contains a comma.
function serializeMaterialList(tokens) {
  return parseMaterialList(tokens).join('\n');
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
// ⚠️ THIS REVERSES A RULE SETTLED EARLIER. `splitMaterialId` refuses an id with no
//    separator ("never guess"), and contracts/band_arithmetic pins that refusal. Under
//    this grammar a bare `MID1` is not unresolvable - it MEANS the whole lot. The
//    never-guess principle is untouched and still applies to every genuinely malformed
//    token (`ABC_`, `_01`, `_`, blank, and every BIN failure below), which is why those
//    all still refuse. Exactly one legacy case changes meaning; see
//    contracts/doe_band_rules/vectors.json → material_token_cases.
//
// ⚠️ UNCHANGED BY THE ZONE REWRITE, deliberately. The token grammar was settled with the
//    user and pinned; the layer model moving from bands to zones says nothing about how a
//    material is named. Every material_token_case below is carried over byte for byte.
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
    // Same integer reader as the layer heights. A second number parser here is how
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

// ── 구역 산술 ──────────────────────────────────────────────────────────────────

// The MID zone's extent, derived from STACK and the presence of the other two.
// Returns { from, to, size, known }. `known:false` means STACK is unreadable and NOTHING
// downstream may compute a layer count - callers must not treat size 0 as "no layers",
// because "0 layers" is a legitimate structure (E-row) and "unknown" is not.
function midZone(row) {
  const st = stackState(row);
  const has1h = parseMaterialList(row && row.mat_1h).length > 0;
  const hasTop = parseMaterialList(row && row.mat_top).length > 0;
  // A marker's extent is KNOWN and EMPTY — like the E-row's 0-layer MID, a real zero,
  // NOT the unknowable `known:false` of an unreadable height. Folding the two together
  // would either make V5 nag at a declared marker or let a typo'd height demand nothing.
  if (st.state === 'marker') return { from: null, to: null, size: 0, known: true };
  if (st.state !== 'ok') return { from: null, to: null, size: 0, known: false };
  const from = has1h ? 2 : 1;
  const to = hasTop ? st.value - 1 : st.value;
  return { from, to, size: Math.max(0, to - from + 1), known: true };
}

// The layers ONE zone covers, or null when it cannot be computed. Never an empty array
// for "unreadable" - an unreadable height that silently contributed zero layers is how a
// 16-layer stack becomes 15, which is the whole reason V5 exists.
function zoneLayers(row, zone) {
  const st = stackState(row);
  // Marker: [] for every zone, even one with content typed in — the extent is genuinely
  // empty (zero demand by construction), and the content is V6's contradiction to report,
  // not the geometry's to legitimize. Distinct from `null` below, which means UNKNOWABLE.
  if (st.state === 'marker') return [];
  if (st.state !== 'ok') return null;
  const present = parseMaterialList(row && row[zone]).length > 0;
  if (zone === 'mat_1h') return present ? [1] : [];
  if (zone === 'mat_top') return present ? [st.value] : [];
  const z = midZone(row);
  const out = [];
  for (let L = z.from; L <= z.to; L++) out.push(L);
  return out;
}

// Human label for one row+zone, used in every rule message. A message that says only
// "MID가 비어 있습니다" makes the user hunt for the row.
function zoneLabel(row, zone) {
  const v = String((row && row.value) !== undefined && row.value !== null ? row.value : '');
  return `값 '${v}'의 ${ZONE_LABEL[zone]}`;
}

// ── 차단 규칙 ─────────────────────────────────────────────────────────────────
//
// Returns { ok, blocks[], warns[] }; `ok` is false iff blocks exist. Each entry carries
// { rule, message, value?, zone? } so the panel can name the reason ON THE ROW instead of
// saying "저장 실패" somewhere else.
//
//   V5  STACK을 양의 정수로 읽을 수 없다        ← evaluated FIRST; nothing else is computable
//   V2  STACK 1인데 1H·TOP이 둘 다 있다         ← 두 자재가 같은 1층을 잡는다
//   V1  MID 구역이 비어 있지 않은데 MID가 없다   ← 조건부. 구역이 0층이면 발동하지 않는다
//   V4  자재 토큰을 읽을 수 없다
//   V3  로트 전체와 그 로트의 슬롯이 같은 BIN에 함께 지정됐다   ← 계획 전체의 성질
//   V6  STACK 0(상태 표시 값)인데 구역에 자재가 있다   ← marker rows answer to V6 ALONE.
//       A marker's materials are never looked up or demanded, so V4 on them would give a
//       second, contradictory instruction (fix the token vs remove the materials) — same
//       suppression pattern as V5-suppresses-V1. They are also absent from V3's pool scan:
//       a demandless token cannot double-count anything.
//
// plan = { values: [{ value, desc, color, stack, mat_1h[], mat_mid[], mat_top[] }] }
function validateZonePlan(plan) {
  const blocks = [];
  const warns = [];
  const rows = (plan && plan.values) || [];
  const add = (list, rule, message, extra) => list.push({ rule, message, ...(extra || {}) });

  rows.forEach(row => {
    const v = String((row && row.value) !== undefined && row.value !== null ? row.value : '');
    const st = stackState(row);
    const mats = {};
    ZONES.forEach(z => { mats[z] = parseMaterialList(row && row[z]); });

    // V6 — the marker contradiction, and the ONLY rule a marker row answers to. Zone
    // content on a 0-stack row means one of the two statements is wrong, and only the
    // user knows which — so it is reported, not silently dropped. The materials are named
    // in the message because the zone cells render disabled (해당 없음) on a marker row,
    // which would otherwise make the offending content invisible.
    if (st.state === 'marker') {
      const withContent = ZONES.filter(z => mats[z].length > 0);
      if (withContent.length > 0) {
        add(blocks, 'V6', `값 '${v}'은(는) STACK 0(상태 표시 값)인데 구역에 자재가 있습니다 — `
          + withContent.map(z => `${ZONE_LABEL[z]}: ${mats[z].join(', ')}`).join(' · ')
          + ` — 층이 없는 값은 자재를 가질 수 없습니다. STACK을 채우거나 자재를 지우십시오.`,
          { value: v, zone: withContent[0] });
      }
      return;   // V5/V2/V1/V4/W-DUP-MAT do not fire on a marker row
    }

    // V5 FIRST. With an unreadable height every zone extent is a guess, and a guessed
    // extent is precisely the "screen is fine, number is short" defect this rule exists
    // to prevent. blank and invalid are ONE case here on purpose - both mean "no height".
    if (st.state !== 'ok') {
      const shown = st.state === 'blank' ? '(비어 있음)' : JSON.stringify(row && row.stack);
      add(blocks, 'V5', `값 '${v}'의 STACK ${shown}을(를) 1 이상의 정수로 읽을 수 없습니다 — 층 구조를 계산할 수 없습니다.`,
        { value: v });
    } else if (st.value === 1 && mats.mat_1h.length > 0 && mats.mat_top.length > 0) {
      // V2. At STACK 1 there is exactly one layer and both zones claim it. Note this is
      // NOT reported as a MID problem: MID's zone is 0층 here and blaming MID would send
      // the user to the one cell that is innocent.
      add(blocks, 'V2', `값 '${v}'은(는) STACK 1인데 1H와 TOP이 모두 있습니다 — `
        + `'${mats.mat_1h[0]}'와(과) '${mats.mat_top[0]}'이(가) 같은 1층을 잡습니다.`, { value: v, zone: 'mat_1h' });
    }

    // V1 — conditional, and the condition is the whole point. `STACK=1` MID-only passes
    // (구역 1–1층, MID 있음); `STACK=2` with 1H+TOP and no MID passes (구역 0층).
    // Only computed when the height is readable: with V5 already reported, guessing an
    // extent here would produce a second, contradictory message about the same row.
    if (st.state === 'ok') {
      const z = midZone(row);
      if (z.size > 0 && mats.mat_mid.length === 0) {
        add(blocks, 'V1', `${zoneLabel(row, 'mat_mid')} 구역이 ${formatLayerRuns(zoneLayers(row, 'mat_mid'))}`
          + `(${z.size}층)인데 비어 있습니다 — 구역이 있으면 MID는 반드시 있어야 합니다.`,
          { value: v, zone: 'mat_mid' });
      }
    }

    // V4 — an unparseable token blocks. It cannot be looked up, so its 가용 could only
    // ever be reported as 0 - and 0 reads as "all consumed" when the truth is "we never
    // resolved it". Refuse rather than guess.
    ZONES.forEach(z => {
      mats[z].forEach(raw => {
        const t = parseMaterialToken(raw);
        if (!t.ok) {
          add(blocks, 'V4', `${zoneLabel(row, z)}의 자재 '${raw}'을(를) 읽을 수 없습니다 — ${t.reason}`,
            { value: v, zone: z });
        }
      });
      // A duplicate WITHIN one zone changes the denominator of `share` for no reason.
      // Across zones it is legitimate (the same lot at the bottom and in the middle).
      const seen = new Set();
      const dup = [];
      parseMaterialList(row && row[z]).forEach(m => { if (seen.has(m)) dup.push(m); seen.add(m); });
      const rawList = Array.isArray(row && row[z]) ? row[z] : String((row && row[z]) || '').split(/[\n,]/);
      const trimmed = rawList.map(x => String(x).trim()).filter(Boolean);
      const dupRaw = trimmed.filter((m, i) => trimmed.indexOf(m) !== i);
      if (dup.length > 0 || dupRaw.length > 0) {
        add(warns, 'W-DUP-MAT', `${zoneLabel(row, z)}에 같은 자재가 중복 지정됐습니다: `
          + `${[...new Set(dup.concat(dupRaw))].join(', ')}`, { value: v, zone: z });
      }
    });
  });

  // ── V3: a whole lot and one of its own slots, in the same BIN ───────────────
  // `MID1:2` covers every slot of MID1 at BIN 2; `MID1_03:2` covers slot 03 at BIN 2.
  // Together they count slot 03 twice, and inflated demand shows up as a shortage at the
  // worst moment. Same lot at a DIFFERENT bin is a different pool and is fine.
  //
  // This is a property of the WHOLE PLAN, not of a row pair - the two tokens are usually
  // on different values, which is why the message lands in table ② where both are visible
  // at once. Reporting it on one of the two rows would make it half a message.
  {
    // Keyed by JSON.stringify([lot, bin]), for the reason `materialPoolKey` records: there
    // is no character that cannot occur in a lot name, and an invisible separator is WORSE
    // than a legal one because tooling strips it. Join `MID1` + bin `12` and `MID11` + bin
    // `2` on a stripped separator and both give "MID112" - V3 would then pair two unrelated
    // pools, blocking a correct plan while missing the real double-count.
    const lotScoped = new Map();     // JSON [lot, bin] -> where it was named
    const slotScoped = new Map();
    rows.forEach(row => {
      // Marker rows are not in this scan: their tokens demand nothing, so pairing one
      // with a real row's slot would block a correct plan over wafers nobody asked for.
      // The content itself is already V6's report.
      if (stackState(row).state === 'marker') return;
      const v = String((row && row.value) !== undefined && row.value !== null ? row.value : '');
      ZONES.forEach(z => {
        parseMaterialList(row && row[z]).forEach(raw => {
          const t = parseMaterialToken(raw);
          if (!t.ok) return;           // V4 reports it; do not double-report here
          const key = JSON.stringify([t.lot, t.bin]);
          (t.scope === 'lot' ? lotScoped : slotScoped).set(key, { raw: t.raw, value: v, zone: z });
        });
      });
    });
    lotScoped.forEach((lotHit, key) => {
      const slotHit = slotScoped.get(key);
      if (!slotHit) return;
      add(blocks, 'V3', `자재 '${lotHit.raw}'(로트 전체 · 값 '${lotHit.value}')와 `
        + `'${slotHit.raw}'(그 로트의 슬롯 · 값 '${slotHit.value}')이 같은 BIN에 함께 지정됐습니다 — `
        + `그 슬롯이 두 번 계산됩니다.`, { value: slotHit.value, zone: slotHit.zone });
    });
  }

  return { ok: blocks.length === 0, blocks, warns };
}

// ── 소요 ──────────────────────────────────────────────────────────────────────
//
// 한 구역의 총 소요 = (그 값으로 칠한 셀 수) × (그 구역의 층 수)
// 자재당           = ceil(총 소요 / 그 구역의 자재 수)
//
// ⚠️ THE CEILING DOES NOT DISTRIBUTE, and that is why the sum happens before it:
//        ceil(3/2) + ceil(3/2) = 4     but     ceil(6/2) = 3
//    One zone is ONE demand on ONE material set. Any second place that computes this is a
//    defect by construction - see the `saveLegendToServer` ceil/round incident, where
//    saving used ceil and display used round and the DB held 34 while the screen said 33.
function zoneDemand(row, zone, painted) {
  const span = zoneLayers(row, zone);
  if (span === null) return { layers: 0, total: 0, share: 0 };
  const layers = span.length;
  const total = Number(painted || 0) * layers;
  const mats = parseMaterialList(row && row[zone]);
  const share = mats.length > 0 ? Math.ceil(total / mats.length) : 0;
  return { layers, total, share };
}

// ── ② 자재 롤업 — 파생 전용 ───────────────────────────────────────────────────
//
// Row identity is the POOL (lot, slot, bin), not the material name.
//   사용 = Σ over (값, 구역)  ceil(층수 × 그 값으로 칠한 셀 수 ÷ 그 구역의 자재 수)
//
// The per-material ceiling means the shares of one zone sum to MORE than that zone's
// total. That is deliberate and long-standing: rounding down or to nearest hides a
// shortfall, and a plan that quietly under-orders is worse than one that over-orders.
//
// ⚠️ `used` IS A SUFFICIENCY CHECK, NOT AN ALLOCATION. Wafers are consumed one at a time
//    in an order nobody records, so an even split answers exactly one question - "is there
//    enough across this pool" - and answers nothing about which wafer goes where.
function materialRollupRows(plan, paintedOf) {
  const rows = (plan && plan.values) || [];
  const byPool = new Map();
  rows.forEach(row => {
    // A marker row (STACK 0) is ABSENT from the rollup, not present-with-zero: a
    // "사용 0" row would read as "planned, costs nothing" and invite an availability
    // query for material nobody is demanding. Its painted count is a message, not a
    // multiplier, and its zone content (if any) is V6's contradiction — not inventory.
    if (stackState(row).state === 'marker') return;
    const v = String((row && row.value) !== undefined && row.value !== null ? row.value : '');
    const painted = Number((paintedOf && paintedOf(v)) || 0);
    ZONES.forEach(z => {
      const d = zoneDemand(row, z, painted);
      const mats = parseMaterialList(row && row[z]);
      mats.forEach(raw => {
        const tok = parseMaterialToken(raw);
        const key = materialPoolKey(tok);
        if (key === null) return;                 // V4 blocks the save; it is not a row here
        if (!byPool.has(key)) {
          byPool.set(key, { key, lot: tok.lot, slot: tok.slot, bin: tok.bin, scope: tok.scope, raw: tok.raw, used: 0, uses: [] });
        }
        const e = byPool.get(key);
        e.used += d.share;
        // The zone is kept on the use so the panel can say WHERE the demand came from
        // without recomputing it - one implementation of the number, one of its provenance.
        e.uses.push({ value: v, zone: z, layers: d.layers, qty: d.share });
      });
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

// ── 엑셀 계약 ─────────────────────────────────────────────────────────────────
//
// SIX LOGICAL COLUMNS, in this order. These header words are what the panel PRINTS and
// what the parser LOOKS FOR - one list, so column drift cannot happen between them.
const DOE_COLUMNS = [
  { id: 'value',   header: 'VALUE' },
  { id: 'stack',   header: 'STACK' },
  { id: 'desc',    header: 'DESC' },
  { id: 'mat_1h',  header: '1H' },
  { id: 'mat_mid', header: 'MID' },
  { id: 'mat_top', header: 'TOP' },
];

// 계약 밖이지만 **머리줄에서는 알아본다.** 화면에 열로 보이는 것들이라 사람은 머리줄을 통째로
// 긁는다 - 이 단어들을 모르는 척하면 그 머리줄이 머리줄로 인식되지 않고 **데이터 행으로**
// 들어가, 값 이름이 "COLOR"인 행이 생긴다.
//
//   COLOR — 앱이 소유한다. 엑셀의 셀 채우기는 `text/plain`으로 이동하지 않으므로 붙여넣어도
//           빈 칸이나 잡음으로 도착한다. 새 값에는 앱이 색을 배정하고, 기존 값은 자기 색을
//           그대로 갖는다 (사용자 지시 2026-07-28).
//   칠함  — 칠해진 셀 수. 파생값이라 어느 방향에도 속하지 않는다.
//   COUNT — 같은 파생값의 **내보내기 이름**. map_editor의 COPY HEADER MODE가 우측 보조표를
//           `VALUE | COUNT | STACK | DESC`로 싣는다(사용자 회사 양식). 이 단어를 모르면 그
//           머리줄이 머리줄로 인식되지 않아, 사용자가 자기 양식을 그대로 되붙일 때 값 이름이
//           "VALUE"이고 STACK이 "COUNT"인 행이 생긴다. 알아보되 **버린다** — 칠한 셀 수는
//           격자에서 세는 것이지 붙여넣기로 정하는 것이 아니다.
const IGNORED_HEADERS = ['COLOR', '칠함', '칠함*', 'COUNT'];

function columnIdByHeader(word) {
  const w = String(word === null || word === undefined ? '' : word).trim().toUpperCase();
  if (w === '') return null;
  if (IGNORED_HEADERS.some(h => h.toUpperCase() === w)) return 'IGNORE';
  const hit = DOE_COLUMNS.find(c => c.header === w);
  return hit ? hit.id : null;
}

// Is this record a header? Every non-empty cell must name a DISTINCT known column, and
// there must be at least two of them. The two-cell floor is what keeps a one-column paste
// of the literal text `MID` (a perfectly legal lot name) from being eaten as a heading.
function looksLikeHeader(record) {
  const cells = (record || []).map(c => String(c === null || c === undefined ? '' : c).trim());
  const named = cells.filter(c => c !== '');
  if (named.length < 2) return false;
  const ids = named.map(columnIdByHeader);
  if (ids.some(id => id === null)) return false;
  // `IGNORE` may repeat (COLOR and 칠함 are two of them); contract columns may not.
  const real = ids.filter(id => id !== 'IGNORE');
  return new Set(real).size === real.length;
}

// ── 머리줄 없는 붙여넣기의 선행 빈 열 ────────────────────────────────────────
//
// 엑셀에서 표를 만든 사람은 **색 열을 그대로 갖고 있을 가능성이 높다** — 글자 없이 칠해진
// 칸들. 그 블록은 `text/plain`으로 **첫 칸이 빈 일곱 필드**로 도착하고, 곧이곧대로 받으면
// 모든 열이 한 칸씩 밀려 VALUE가 STACK으로 들어간다.
//
// 머리줄이 있으면 이름 매칭이 이걸 통째로 해결한다(COLOR는 위에서 무시된다). 없을 때의
// 규칙은 **추측이 아니라 배울 수 있는 규칙**이어야 하므로, 네 조건을 전부 만족할 때만
// 첫 열을 버린다:
//
//   ① 머리줄이 없다
//   ② 시작 열이 VALUE다 (계약의 첫 열)
//   ③ 첫 필드가 **모든 행에서** 비어 있다 — 한 행의 성질이 아니라 **열의 성질**이다
//   ④ 버리지 않으면 블록이 계약보다 **넓다** (7 > 6)
//
// ④가 밀림을 막는다. 정확히 6칸인데 첫 칸이 비어 있으면 버리지 않는다 — 그때의 정직한
// 읽기는 "VALUE가 비었다"이고, 이름 없는 값은 존재할 수 없으므로 그 행은 화면에서 즉시
// 눈에 띈다. 어느 쪽이든 **조용히 밀리지는 않는다.**
function leadingBlankColumnDropped(body, startColId) {
  if (startColId !== DOE_COLUMNS[0].id) return false;
  if (!Array.isArray(body) || body.length === 0) return false;
  const room = DOE_COLUMNS.length;
  const widest = body.reduce((m, r) => Math.max(m, (r || []).length), 0);
  if (widest <= room) return false;
  return body.every(r => String(((r || [])[0]) ?? '').trim() === '');
}

/**
 * A pasted TSV grid -> per-row patches keyed by LOGICAL COLUMN ID.
 *
 * ㉠ HEADER PRESENT -> map by name. Any order, any subset. This is what kills the real
 *    accident: pasting `VALUE STACK 1H MID TOP` without a header puts MID into DESC and
 *    nothing on screen looks wrong.
 * ㉡ NO HEADER -> fill from `startCol` (the focused field's logical index) rightwards.
 *    NEVER "the cell to the right on screen" - a row renders as two lines and those two
 *    orders differ. The contract is the index, and the layout is free to change.
 * ㉢ NEVER REFUSED. A partial paste is accepted as a partial paste. Bouncing a 3-column
 *    block back with "7 columns required" sends the user to Excel to rebuild the table,
 *    and at that moment this screen has no reason to exist.
 *
 * Returns { rows: [{colId: text}], header, columns, wide } - `wide` counts cells that fell
 * off the right edge, so the caller can say how many were ignored instead of pretending
 * the paste was clean.
 */
function mapPastedGrid(grid, startColId) {
  const src = Array.isArray(grid) ? grid : [];
  const startIdx = Math.max(0, DOE_COLUMNS.findIndex(c => c.id === startColId));
  const header = src.length > 0 && looksLikeHeader(src[0]);
  let columns;
  let body;
  let droppedLeading = false;
  if (header) {
    columns = src[0].map(columnIdByHeader);
    body = src.slice(1);
  } else {
    body = src;
    droppedLeading = leadingBlankColumnDropped(body, startColId);
    if (droppedLeading) body = body.map(r => (r || []).slice(1));
    columns = [];
    for (let i = startIdx; i < DOE_COLUMNS.length; i++) columns.push(DOE_COLUMNS[i].id);
  }
  let wide = 0;
  const rows = body.map(record => {
    const patch = {};
    (record || []).forEach((cell, i) => {
      const colId = columns[i];
      if (colId === 'IGNORE') return;          // 계약 밖 열(COLOR·칠함) — 무시는 손실이 아니다
      if (!colId) { if (String(cell || '').trim() !== '') wide++; return; }
      patch[colId] = String(cell === null || cell === undefined ? '' : cell);
    });
    return patch;
  });
  return { rows, header, columns, wide, droppedLeading };
}

// One legend row -> one TSV record, RAW TOKENS ONLY.
//
// `MID1`, never the rendered `MID1_✱:1`; `_✱` is a drawing that says "every slot of this
// lot" and pasting a drawing back produces a lot literally named `MID1_✱`. Same for `≈`,
// 「미상」 and 「해당 없음」 - all of those are how the screen says something, not what the
// user typed. An inapplicable zone exports as an EMPTY cell, because that is exactly what
// it is: no material, for a layer that does not exist.
//
// COLOR and 칠함 are not here: `DOE_COLUMNS` is the whole contract in both directions, so
// a column that is not in it cannot be emitted OR read, and the two can never disagree.
function planRowToRecord(row) {
  return DOE_COLUMNS.map(c => {
    if (c.id === 'stack') {
      const st = stackState(row);
      // An unreadable STACK exports its RAW text, not a repaired number. The point of a
      // round trip is to hand back what is there so the user can fix it in Excel.
      // A marker is READABLE and exports its canonical '0'.
      return (st.state === 'ok' || st.state === 'marker') ? String(st.value)
        : String((row && row.stack) === null || (row && row.stack) === undefined ? '' : row.stack);
    }
    if (ZONES.indexOf(c.id) >= 0) return serializeMaterialList(row && row[c.id]);
    const v = row && row[c.id];
    return String(v === null || v === undefined ? '' : v);
  });
}

// The whole of ① as a grid, header first. The header always goes out: it is what makes the
// block re-pasteable in any column order, and it costs one line.
function planToGrid(rows) {
  return [DOE_COLUMNS.map(c => c.header)].concat((rows || []).map(planRowToRecord));
}

// ② as a grid. 「미상」 GOES OUT AS THE WORD. Exporting it as 0 puts a number Excel will
// happily sum into a column that means "we could not find out" - the single most expensive
// way to lose the distinction this whole screen defends.
const ROLLUP_COLUMNS = ['MAT', 'BIN', 'MAP', '가용', '사용', '잔여'];
const ROLLUP_UNKNOWN = '미상';
function rollupToGrid(rollupRows) {
  const num = s => (s && s.reliable === true && s.value !== null && s.value !== undefined)
    ? String(s.value) : ROLLUP_UNKNOWN;
  return [ROLLUP_COLUMNS.slice()].concat((rollupRows || []).map(r => [
    // The MAT cell is the raw token the user typed, so a copied ② can be pasted into ①.
    String(r.raw === null || r.raw === undefined ? '' : r.raw),
    String(r.bin),
    r.mapExists === true ? 'O' : (r.mapExists === false ? 'X' : ROLLUP_UNKNOWN),
    num(r.availability),
    String(r.used),
    num(r.remaining),
  ]));
}

// ── 폐기 모델 읽기 (bands -> zones) ───────────────────────────────────────────
//
// WHY THIS EXISTS AT ALL. `map_split_registry.bands` holds real plans written by the band
// model. If the zone reader simply ignored that column, opening one of those maps would
// show an EMPTY plan - and the legend save is a `replace_map` write, so the first
// keystroke afterwards would delete the plan that was on screen a moment ago as an empty
// set. Reading the old shape is not a courtesy; it is what keeps invariant ④ true.
//
// AND IT REFUSES RATHER THAN GUESSES. Not every band arrangement is expressible as three
// zones (four bands, a band that does not start at layer 1, an unreadable `to`). For those
// it returns `{ ok:false }`, and the caller must show the row as unreadable and BLOCK the
// save - collapsing a 4-band stack into 3 zones and then replace_map-ing the collapse over
// the server's truth is exactly the "screen is fine, value is wrong" defect.
//
// The mapping, stated once:
//   n = 1              -> MID only. One band covering the whole stack IS "everything
//                        between", and 1H/TOP are the exceptions carved out of it.
//   n > 1  1H  = band[0]   iff band[0] covers exactly layer 1
//          TOP = band[n-1] iff band[n-1] covers exactly layer STACK
//          MID = whatever is left, and there must be at most one of it
function bandsToZones(bands) {
  const src = Array.isArray(bands) ? bands : [];
  if (src.length === 0) return { ok: true, stack: '', mat_1h: [], mat_mid: [], mat_top: [] };
  const spans = [];
  for (let i = 0; i < src.length; i++) {
    const st = boundState(src[i] && src[i].to);
    // An unreadable `to` is refused, NOT skipped. `prevTo` skips it (that was the right
    // answer while the panel was still editing bands: show it, mark it, keep going). Here
    // skipping would silently shorten the stack, which is the one outcome a migration is
    // never allowed to produce.
    if (st.state !== 'ok') return { ok: false, reason: `${i + 1}번째 구간의 끝 층을 읽을 수 없습니다.` };
    const prev = prevTo(src, i);
    if (st.value <= prev) return { ok: false, reason: `${i + 1}번째 구간의 끝 층 ${st.value}이(가) 앞 구간(${prev})보다 크지 않습니다.` };
    spans.push({ from: prev + 1, to: st.value, materials: parseMaterialList(src[i] && src[i].materials) });
  }
  const stack = spans[spans.length - 1].to;
  if (spans.length === 1) {
    return { ok: true, stack, mat_1h: [], mat_mid: spans[0].materials, mat_top: [] };
  }
  const rest = spans.slice();
  let h1 = [];
  let top = [];
  if (rest[0].from === 1 && rest[0].to === 1) h1 = rest.shift().materials;
  if (rest.length > 0 && rest[rest.length - 1].from === stack && rest[rest.length - 1].to === stack) {
    top = rest.pop().materials;
  }
  if (rest.length > 1) {
    return { ok: false, reason: `구간 ${src.length}개는 1H·MID·TOP 세 구역으로 표현할 수 없습니다 — 중간 구간이 ${rest.length}개입니다.` };
  }
  return { ok: true, stack, mat_1h: h1, mat_mid: rest.length ? rest[0].materials : [], mat_top: top };
}

export {
  ZONES, ZONE_LABEL, DOE_COLUMNS, ROLLUP_COLUMNS, ROLLUP_UNKNOWN,
  boundState, stackState, midZone, zoneLayers, zoneLabel, formatLayerRuns,
  parseMaterialList, serializeMaterialList,
  parseMaterialToken, materialPoolKey,
  validateZonePlan, zoneDemand, materialRollupRows, remainingState,
  IGNORED_HEADERS, columnIdByHeader, looksLikeHeader, leadingBlankColumnDropped,
  mapPastedGrid, planRowToRecord, planToGrid, rollupToGrid,
  bandsToZones,
};
