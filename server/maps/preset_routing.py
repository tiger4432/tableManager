"""[F5] Load-time preset routing — WHICH physical spec a map opens with.

Today an operator either remembers which preset a map needs, or the map opens
with whatever was left in the panel from the previous map. Both cost clicks (the
V1 instrument catches them), and the second one is worse than a click: a wrong
physical spec changes `inside`, `inside` changes the set of cells that can be
saved, and the map is then refused by the comparison gate.

The answer is DECLARED, never guessed, and it is resolved in a FIXED ORDER —
the order is the contract:

    map key -> (lot token out of the key column)
                 |
                 +--(1)-- product-code lookup table -> product code -> preset
                 |            | no row (NORMAL — see below)
                 |            v
                 +--(2)-- ordered text-pattern rules, first match wins -> preset
                              | no match
                              v
                          (3)  NO ROUTING — the caller keeps today's behaviour

[Two facts this design is built around — confirmed by the user]

(1) The lookup table exists only in production; it is absent here. So the
    ABSENCE OF THE DECLARATION IS THE NORMAL CONFIGURATION and stage 1 is simply
    skipped. There is deliberately NO environment branch in this code: one code
    path, only the declaration differs. A branch would create a limb that runs
    only in production and therefore can never be verified here.

(2) That table is INCOMPLETE — not every lot is in it. So A LOOKUP MISS IS NOT
    AN ERROR. It never logs above debug and it never surfaces as a warning; it
    falls through to stage 2 silently. The outcome is still reported in the
    response (`lookup.status`) so an operator can verify a declaration without
    the code having to shout about the normal case.

[Never invent a preset] Stages 1 and 2 both failing is answered EXPLICITLY
(`no_match` / `not_declared`), never by picking something plausible. A wrong
preset is not a cosmetic defect: it changes `inside`, and that changes which
cells can be stored.

[Priority is absolute: stored metadata > routing > panel]
`wafer_map_metadata` is the SSOT for a map's frame ("the meta is the only basis
for alignment"). A map that already has a registered spec is answered
`meta_present` with NO preset, so routing structurally cannot overwrite it.
Routing exists for maps that have no meta yet — and their first Push registers
one, so the routing answer is a first-open default and nothing else.

[One canonicalisation — 7b] Every key that touches a stored value rides
`map_overlay.canonical_key_value` through `canonical_bind_value` /
`canonical_map_key`. There is no second normalisation in this module: a
`number`-declared column stores 1, the map identity reads `LOT_1`, and a parsed
token spelling it `LOT_01` must still find it. That defect was fixed once (7b);
re-normalising here would reintroduce it in a new place.

[Reused primitives, no new lookup machinery] The declared cross-table lookup
already exists in this system in three shapes — `map_overlay_config.table_bindings`,
Enrichment `reference_views`, and F3 `value_suggest`. This module follows the
Enrichment shape: a per-key declaration object, normalised and validated at load
with invalid pieces DROPPED (never silently repaired), read fresh per request
(the config is small — the same rule map-presets and enrichment already follow).

[Where the declaration lives] `map_overlay_config.json`, key `preset_routing`,
NOT `maps.json`. `maps.json` holds the preset BODIES but it is an API-managed
file — `POST/DELETE /api/map-presets` rewrites it whole — so hand-written
operational rules do not belong there. `map_overlay_config.json` is the
hand-declared map-behaviour config, it is never machine-written, and it already
holds the per-table cross-table declaration (`table_bindings`) this mirrors.
Rules name a preset by KEY or by its `name`, which is the reference form
`transfer_plan_config.target_map.preset` already uses across the same two files.

[Scale] One resolution per MAP LOAD: at most one metadata query and at most one
lookup query, both `LIMIT 1`, never a per-cell or per-request path. The lookup
filters a declared column, which is NOT indexed on a dynamic table (only
`business_key_val` / `updated_at` are) — the config guide states the index the
operator must create, and `_note_lookup_scan` states it once per process. The
indexed `business_key_val` mirror is deliberately NOT substituted here: it
stores `str(v).strip()`, a different normalisation from `canonical_key_value`,
and a disagreement between the two would manufacture a MISS — which this design
renders invisible on purpose.
"""
import logging
import re

logger = logging.getLogger(__name__)

import map_overlay

# --- answer statuses -------------------------------------------------------
STATUS_OK = "ok"                      # a preset was resolved
STATUS_NOT_DECLARED = "not_declared"  # no routing declared for this table
STATUS_NO_MATCH = "no_match"          # declared, but neither stage answered
STATUS_META_PRESENT = "meta_present"  # the map already has a stored spec — it wins
STATUS_UNRESOLVABLE = "unresolvable"  # the map key cannot be decomposed
STATUS_PRESET_MISSING = "preset_missing"  # a rule matched, its preset does not exist

# --- which stage answered --------------------------------------------------
STAGE_PRODUCT_LOOKUP = "product_lookup"
STAGE_PATTERN = "pattern"

# --- stage 1 outcome (reported, not logged) --------------------------------
LOOKUP_NOT_DECLARED = "not_declared"
LOOKUP_HIT = "hit"
LOOKUP_MISS = "miss"                  # NORMAL — the table is incomplete by design
LOOKUP_UNMAPPED = "unmapped"          # code found, no preset declared for it
LOOKUP_TABLE_ABSENT = "table_absent"  # NORMAL outside production
LOOKUP_COLUMN_ABSENT = "column_absent"
LOOKUP_NO_KEY = "no_key"              # the lot token is empty
LOOKUP_ERROR = "error"                # the query itself failed — this DOES warn

MATCH_KINDS = ("equals", "prefix", "suffix", "contains", "regex")

MAX_RULES = 200          # ordered evaluation is per map load; a runaway list is a typo
MAX_PATTERN_LEN = 200    # operator-authored regex: bound the input, not the engine

# One-time notices, keyed by (table, column). Per process, same discipline as
# `map_meta_registrar._known_present` — an operational hint must not become
# per-map-load log noise.
_SCAN_NOTED = set()


# ---------------------------------------------------------------------------
# Declaration normalisation (Enrichment shape: validate at load, DROP the bad
# pieces with a stated reason — never repair silently)
# ---------------------------------------------------------------------------

def _norm_str(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalize_lookup(table: str, raw):
    """`product_lookup` -> {table, key_column, value_column} or None.

    None means "stage 1 is off", which is the NORMAL state outside production.
    An incomplete declaration is an operator error and says so once, at load.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        logger.warning("[PresetRouting:%s] 'product_lookup' must be an object; ignored", table)
        return None
    if raw.get("enabled", True) is False:
        return None
    lookup_table = _norm_str(raw.get("table"))
    key_column = _norm_str(raw.get("key_column"))
    value_column = _norm_str(raw.get("value_column"))
    missing = [name for name, val in (("table", lookup_table),
                                      ("key_column", key_column),
                                      ("value_column", value_column)) if not val]
    if missing:
        logger.warning("[PresetRouting:%s] 'product_lookup' dropped: missing %s",
                       table, missing)
        return None
    return {"table": lookup_table, "key_column": key_column,
            "value_column": value_column}


def _normalize_rules(table: str, raw_rules) -> list:
    """Ordered pattern rules. ORDER IS PRESERVED — first match wins downstream.

    `match` is required: there is no default kind. A defaulted matcher is a
    guess about what the operator meant, and this module does not guess.
    """
    rules = []
    if raw_rules is None:
        return rules
    if not isinstance(raw_rules, list):
        logger.warning("[PresetRouting:%s] 'rules' must be a list; ignored", table)
        return rules
    if len(raw_rules) > MAX_RULES:
        logger.warning("[PresetRouting:%s] %d rules declared; only the first %d "
                       "are evaluated", table, len(raw_rules), MAX_RULES)
    for i, raw in enumerate(raw_rules[:MAX_RULES]):
        if not isinstance(raw, dict):
            logger.warning("[PresetRouting:%s] rule #%d dropped: must be an object", table, i)
            continue
        if raw.get("enabled", True) is False:
            continue
        name = _norm_str(raw.get("name")) or f"#{i}"
        kind = _norm_str(raw.get("match"))
        value, preset = _norm_str(raw.get("value")), _norm_str(raw.get("preset"))
        if kind not in MATCH_KINDS:
            logger.warning("[PresetRouting:%s] rule '%s' dropped: 'match' must be one "
                           "of %s (got %r)", table, name, list(MATCH_KINDS),
                           raw.get("match"))
            continue
        if not value:
            # Names the offending value rather than just "required": a numeric
            # `"value": 7` is the easy mistake here, and the lot token it is
            # compared against is always a string.
            logger.warning("[PresetRouting:%s] rule '%s' dropped: 'value' must be a "
                           "non-empty string (got %r)", table, name, raw.get("value"))
            continue
        if len(value) > MAX_PATTERN_LEN:
            logger.warning("[PresetRouting:%s] rule '%s' dropped: 'value' exceeds %d chars",
                           table, name, MAX_PATTERN_LEN)
            continue
        if not preset:
            logger.warning("[PresetRouting:%s] rule '%s' dropped: 'preset' must be a "
                           "maps.json preset key or name (got %r)", table, name,
                           raw.get("preset"))
            continue
        if kind == "regex":
            try:
                re.compile(value)
            except re.error as e:
                logger.warning("[PresetRouting:%s] rule '%s' dropped: invalid regex %r (%s)",
                               table, name, value, e)
                continue
        rules.append({"name": name, "match": kind, "value": value, "preset": preset})
    return rules


def resolve_routing_config(cfg: dict, table: str):
    """Normalized routing declaration for `table`, or None when there is none.

    None is the answer for: no `preset_routing` block, no entry for this table,
    `enabled: false`, and a declaration that normalises to nothing usable. All
    four mean the same thing to the caller — no routing — so they collapse here
    instead of leaking four shapes into the resolver.
    """
    routing = (cfg or {}).get("preset_routing")
    if not isinstance(routing, dict):
        return None
    raw = routing.get(table)
    if not isinstance(raw, dict):
        return None
    if raw.get("enabled", True) is False:
        return None

    lookup = _normalize_lookup(table, raw.get("product_lookup"))

    product_presets = {}
    raw_presets = raw.get("product_presets")
    if isinstance(raw_presets, dict):
        for code, preset in raw_presets.items():
            code_s, preset_s = _norm_str(code), _norm_str(preset)
            if code_s and preset_s:
                product_presets[code_s] = preset_s
    elif raw_presets is not None:
        logger.warning("[PresetRouting:%s] 'product_presets' must be an object "
                       "{product_code: preset}; ignored", table)

    rules = _normalize_rules(table, raw.get("rules"))

    if lookup is None and not product_presets and not rules:
        return None

    return {
        "table": table,
        "lot_key_part": _norm_str(raw.get("lot_key_part")),
        "product_lookup": lookup,
        "product_presets": product_presets,
        "rules": rules,
    }


# ---------------------------------------------------------------------------
# Preset reference resolution (key first, then `name`)
# ---------------------------------------------------------------------------

def resolve_preset(presets: dict, ref: str):
    """`ref` -> (preset_key, preset body) or (None, None).

    A reference matches a preset KEY first and its `name` second. Both spellings
    exist in the wild: `maps.json` keys are opaque (`custom_1784890104442`)
    while `transfer_plan_config.target_map.preset` already references presets by
    `name`. Ties on `name` take the first declared — dict order is JSON order.
    """
    if not isinstance(presets, dict) or not isinstance(ref, str):
        return None, None
    ref = ref.strip()
    if not ref:
        return None, None
    body = presets.get(ref)
    if isinstance(body, dict):
        return ref, body
    for key, body in presets.items():
        if isinstance(body, dict) and str(body.get("name", "")).strip() == ref:
            return key, body
    return None, None


# ---------------------------------------------------------------------------
# Answer construction — the ONE place a preset can be attached to a response
# ---------------------------------------------------------------------------

def _lookup_state(declared=False, status=LOOKUP_NOT_DECLARED, product_code=None):
    return {"declared": bool(declared), "status": status, "product_code": product_code}


def _answer(table, map_key, canonical_key, status, detail,
            preset_key=None, preset=None, matched_by=None, lookup=None):
    return {
        "table": table,
        "map_key": map_key,
        "canonical_map_key": canonical_key,
        "status": status,
        "preset_key": preset_key,
        "preset": preset,
        "matched_by": matched_by,
        "lookup": lookup if lookup is not None else _lookup_state(),
        "detail": detail,
    }


def _matched(stage, rule, lot, product_code=None):
    return {"stage": stage, "rule": rule, "lot": lot, "product_code": product_code}


def _resolve_answer(table, map_key, canonical_key, presets, preset_ref,
                    matched_by, lookup):
    """Attach the preset named by a winning rule — or refuse, naming the ghost.

    A dangling reference does NOT fall through to the next rule. Falling through
    would answer with a preset nobody's rule selected, and the typo that caused
    it would stay invisible forever.
    """
    preset_key, preset = resolve_preset(presets, preset_ref)
    if preset_key is None:
        return _answer(
            table, map_key, canonical_key, STATUS_PRESET_MISSING,
            f"규칙 '{matched_by['rule']}'이 지정한 프리셋 '{preset_ref}'이 maps.json에 "
            f"없다 — 라우팅하지 않는다(틀린 프리셋은 inside를 바꾼다)",
            matched_by=matched_by, lookup=lookup)
    return _answer(
        table, map_key, canonical_key, STATUS_OK,
        f"규칙 '{matched_by['rule']}'({matched_by['stage']})이 프리셋 "
        f"'{preset_key}'으로 라우팅했다",
        preset_key=preset_key, preset=preset, matched_by=matched_by, lookup=lookup)


# ---------------------------------------------------------------------------
# Stage 1 — declared product-code lookup
# ---------------------------------------------------------------------------

def _note_lookup_scan(table: str, column: str):
    """State the index requirement ONCE per (table, column) per process.

    A dynamic table indexes `business_key_val` and `updated_at` only
    (`models.init_dynamic_models`), so an equality filter on a declared lookup
    column is a sequential scan. Informational, not a warning: the routing is
    still correct, and it fires on USE rather than on a miss (INV-R-2).
    """
    key = (table, column)
    if key in _SCAN_NOTED:
        return
    _SCAN_NOTED.add(key)
    logger.info("[PresetRouting] product lookup filters %s.%s, which dynamic tables "
                "do not index — create an index on it for large lookup tables "
                "(docs/guide/config/map_overlay_config.md)", table, column)


def _lookup_product_code(db, lookup: dict, lot_raw):
    """(product code | None, outcome). ONE query, `LIMIT 1`.

    A miss, a missing table and a missing column all return None quietly: in
    this environment the table does not exist at all, and in production it is
    incomplete. The caller falls through to stage 2 in every case and the
    outcome travels in the response instead of the log.
    """
    from database import models

    lookup_table = lookup["table"]
    model = models.DYNAMIC_TABLES.get(lookup_table)
    if model is None:
        logger.debug("[PresetRouting] lookup table '%s' is not registered — stage 1 skipped",
                     lookup_table)
        return None, LOOKUP_TABLE_ABSENT

    key_col = getattr(model, lookup["key_column"], None)
    val_col = getattr(model, lookup["value_column"], None)
    if key_col is None or val_col is None:
        logger.debug("[PresetRouting] lookup '%s' has no %s/%s column — stage 1 skipped",
                     lookup_table, lookup["key_column"], lookup["value_column"])
        return None, LOOKUP_COLUMN_ABSENT

    # [INV-R-4] The bind rides 7b canonicalisation with the LOOKUP table's
    # declared type — the same discipline `build_key_filters` applies to cell
    # filters. The raw token is canonicalised here (not the map table's already
    # canonical form) because the two tables may declare the column differently.
    bound = map_overlay.canonical_bind_value(lookup_table, lookup["key_column"], lot_raw)
    if bound is None or bound == "":
        return None, LOOKUP_NO_KEY

    _note_lookup_scan(lookup_table, lookup["key_column"])
    try:
        row = db.query(val_col).filter(key_col == bound).limit(1).first()
    except Exception as e:
        # A failing QUERY is not a miss — this one is a real fault and says so.
        logger.warning("[PresetRouting] product lookup failed (%s.%s == %r): %s",
                       lookup_table, lookup["key_column"], bound, e)
        return None, LOOKUP_ERROR

    if not row or row[0] is None:
        logger.debug("[PresetRouting] no product row for %s.%s == %r (normal — the "
                     "lookup table is incomplete)", lookup_table, lookup["key_column"], bound)
        return None, LOOKUP_MISS

    code = map_overlay.canonical_bind_value(lookup_table, lookup["value_column"], row[0])
    if code is None or code == "":
        return None, LOOKUP_MISS
    return code, LOOKUP_HIT


# ---------------------------------------------------------------------------
# Stage 2 — ordered text patterns
# ---------------------------------------------------------------------------

def _rule_matches(rule: dict, text) -> bool:
    """Case-SENSITIVE match of one rule against the lot token."""
    if text is None:
        return False
    kind, value = rule["match"], rule["value"]
    if kind == "equals":
        return text == value
    if kind == "prefix":
        return text.startswith(value)
    if kind == "suffix":
        return text.endswith(value)
    if kind == "contains":
        return value in text
    if kind == "regex":
        try:
            return re.search(value, text) is not None
        except re.error:
            return False
    return False


def _lot_token(binding: dict, routing: dict, map_key: str):
    """(key column, RAW token) for the part of the map key that carries the lot.

    Decomposition is `map_overlay.map_key_parts` — the single split rule the
    cell filters and the identity string already share. Default is the FIRST
    key column, which is the lot for both shapes in the field (`[lot, slot]`
    and a single-column key).
    """
    parts = map_overlay.map_key_parts(binding, map_key)
    if not parts:
        return None, None
    wanted = routing.get("lot_key_part")
    if not wanted:
        return parts[0]
    for column, raw in parts:
        if column == wanted:
            return column, raw
    return None, None


# ---------------------------------------------------------------------------
# The resolver
# ---------------------------------------------------------------------------

def resolve_preset_routing(db, cfg: dict, table: str, map_key: str,
                           presets: dict = None) -> dict:
    """Which preset should `table`/`map_key` open with?

    Returns (every key always present):
      {table, map_key, canonical_map_key, status, preset_key, preset,
       matched_by, lookup, detail}

    `preset_key`/`preset` are non-null ONLY for `status == "ok"`. Every other
    status means "do not route" and the caller keeps its current behaviour —
    there is no partial answer and no plausible guess.

    `matched_by` = {stage, rule, lot, product_code} names the rule that decided
    and why, so the client can show it. `lookup` = {declared, status,
    product_code} reports stage 1 without logging the normal miss.
    """
    presets = presets if isinstance(presets, dict) else {}

    # Undeclared is the normal state: answer before touching the database.
    routing = resolve_routing_config(cfg, table)
    if routing is None:
        return _answer(table, map_key, None, STATUS_NOT_DECLARED,
                       f"'{table}'에 프리셋 라우팅 선언이 없다 — 기존 동작 그대로 연다")

    binding = map_overlay.resolve_binding(cfg, table)
    if binding is None:
        return _answer(table, map_key, None, STATUS_UNRESOLVABLE,
                       f"'{table}'의 맵 좌표 바인딩을 유도할 수 없어 맵 키를 분해할 수 없다 "
                       f"— table_config에 x/y 컬럼과 map_key_columns가 있어야 하며, "
                       f"컬럼명이 관례와 다르면 map_overlay_config.table_bindings에 선언한다")

    # [7b] The stored identity, not the spelling we were handed.
    canonical_key = map_overlay.canonical_map_key(table, binding, map_key)

    # [Absolute priority] A registered spec is the SSOT for this map's frame.
    # Routing must not be able to overwrite it, so it is refused here rather
    # than left to the caller's discipline.
    if map_overlay.load_map_meta(db, table, canonical_key) is not None:
        return _answer(table, map_key, canonical_key, STATUS_META_PRESENT,
                       f"'{table}/{canonical_key}'는 wafer_map_metadata에 규격이 이미 "
                       f"등록돼 있다 — 저장된 규격이 라우팅보다 우선이며 덮지 않는다")

    lot_column, lot_raw = _lot_token(binding, routing, map_key)
    if lot_column is None:
        return _answer(table, map_key, canonical_key, STATUS_UNRESOLVABLE,
                       f"맵 키 '{map_key}'에서 lot 조각을 찾을 수 없다 — 선언한 "
                       f"lot_key_part='{routing.get('lot_key_part')}'가 이 테이블의 "
                       f"키 컬럼이 아니다")
    lot = map_overlay.canonical_bind_value(table, lot_column, lot_raw)

    lookup_cfg = routing["product_lookup"]
    lookup = _lookup_state(declared=lookup_cfg is not None)

    # --- (1) product-code lookup -------------------------------------------
    if lookup_cfg is not None:
        code, outcome = _lookup_product_code(db, lookup_cfg, lot_raw)
        lookup = _lookup_state(declared=True, status=outcome, product_code=code)
        if code is not None:
            preset_ref = routing["product_presets"].get(code)
            if preset_ref is None:
                # The table answered but nobody declared a preset for that code.
                # Normal while the mapping is being filled in — fall to (2).
                lookup["status"] = LOOKUP_UNMAPPED
            else:
                return _resolve_answer(
                    table, map_key, canonical_key, presets, preset_ref,
                    _matched(STAGE_PRODUCT_LOOKUP, f"product_presets['{code}']",
                             lot, product_code=code),
                    lookup)

    # --- (2) ordered patterns, first match wins ----------------------------
    for rule in routing["rules"]:
        if _rule_matches(rule, lot):
            return _resolve_answer(
                table, map_key, canonical_key, presets, rule["preset"],
                _matched(STAGE_PATTERN, rule["name"], lot,
                         product_code=lookup.get("product_code")),
                lookup)

    # --- (3) no routing ----------------------------------------------------
    return _answer(table, map_key, canonical_key, STATUS_NO_MATCH,
                   f"lot '{lot}'에 대한 라우팅 선언이 없다 — 기존 동작 그대로 연다",
                   lookup=lookup)
