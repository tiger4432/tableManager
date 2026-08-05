"""Auto-registration of `wafer_map_metadata` rows for ingestion-created maps (M3).

[Why this module exists]
`wafer_map_metadata` is the single source of truth for map alignment
(map_overlay docstring: meta absence is not an error but a REGISTRATION GAP that
surfaces as screen-frame "화면기준" chips). The manual map editor registers a meta
row on every push, but the two ingestion writers (file watcher pipeline and
chain ingestion worker) never did — e.g. `bonding_map` accumulated ~390k
distinct map keys against 9 meta rows. This module closes that gap at the
ingestion write path.

[Contract]
- Trigger: a batch upserted into a table that DECLARES `map_key_columns` in
  table_config AND resolves a coordinate binding via `map_overlay.resolve_binding`
  (declared > derived — same rule as every other map consumer). Tables with
  `map_key_columns` but no coordinate binding (e.g. `map_split_registry`, a
  registry, not a map) are skipped naturally.
- Absent-only: an existing meta row is NEVER touched. User/editor-registered
  meta is authoritative; this module only fills holes. (Layer-priority note:
  rows created here carry source `auto_map_meta`, which resolves to the lowest
  priority (99) in `compute_priority_value`, so a later user edit always wins.)
- Honest minimum: the synthetic meta mirrors the editor's 표준(standard) choice
  for metadata-less maps — rectangular bbox grid of the batch's x/y extent,
  rotation 0, side front, and the MASK-NEUTRAL physical vocabulary
  (chip 1x1 / offset 0 / edge margin 3 / wafer dia circumscribing the grid's
  half-diagonal; the mask predicate has no off switch, so "no mask" must be
  expressed in its own vocabulary — see map_editor.js [fix C]). We do NOT guess
  real wafer geometry (no circle) — M4 direction is map-based validity.
  One deliberate divergence from the editor's standard choice: `grid_start_x/y`
  is the batch's min x/y (not 0), because the editor shifts loaded coordinates
  only under the interactive 'standard' choice; ingested rows keep their raw
  coordinates, so the frame must start where the data starts.
- Knob: `auto_register_map_meta` in ingestion_settings.json (default ON).
  Read once per work unit (file / chain tx group) — hot from the next unit,
  consistent within one unit (the D1 snapshot discipline).
- Scale (10M-row rule): one existence check per DISTINCT map key per batch on
  the indexed `business_key_val` column (chunked IN lists), never per row;
  plus a process-lifetime known-present cache so re-ingesting the same map
  costs zero extra queries. Bbox accumulation is O(rows) integer compares.
- Recursion guard: `wafer_map_metadata` itself is refused explicitly (and it
  declares no `map_key_columns` anyway), so meta creation can never trigger
  self-registration. Meta rows are written through `crud.apply_batch_updates`
  (the normal write path), so outbox events flow and the chain worker's
  undelivered-broadcast sweep delivers the client refresh.

[Usage]
    collector = MapMetaCollector(table_name, table_info_snapshot)
    for chunk in ...:
        collector.collect(row_dicts)     # plain {column: value} dicts
    created = collector.flush(db)        # after the upsert loop; commits itself
"""
import json
import logging
import math
import os
import threading
import uuid

logger = logging.getLogger(__name__)

try:
    import paths
except ImportError:  # imported without server/ on sys.path (same guard as crud.py)
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import paths

META_TABLE = "wafer_map_metadata"
SOURCE_NAME = "auto_map_meta"
SETTINGS_KEY = "auto_register_map_meta"
DEFAULT_ENABLED = True
INGESTION_SETTINGS_PATH = paths.config_path("ingestion_settings.json")

# Chunk size for both the existence-check IN list and the creation batches
# (the shared 1000-row chunking discipline).
CHUNK_SIZE = 1000

# Process-lifetime cache of (target_table, map_id) pairs verified present (or
# just created). Bounded: on overflow it is simply cleared — the worst case is
# one redundant indexed existence check, never a wrong answer. Note the cache
# only asserts "present at some point this run": if an operator hard-deletes a
# meta row mid-run, re-registration happens after the next process restart.
_KNOWN_CACHE_MAX = 200_000
_known_present = set()
_known_lock = threading.Lock()

_warned_once = set()


def reset_known_cache():
    """Test/ops hook — forget every known-present key."""
    with _known_lock:
        _known_present.clear()


def _load_ingestion_settings() -> dict:
    """Minimal reader for ingestion_settings.json.

    Deliberately a (tiny) local copy of directory_watcher.load_ingestion_settings:
    importing directory_watcher from the chain worker would drag in watchdog and
    the legacy import shim for a 10-line file read.
    """
    try:
        if os.path.exists(INGESTION_SETTINGS_PATH):
            with open(INGESTION_SETTINGS_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                return loaded
    except Exception as e:
        logger.warning("Could not load ingestion settings (%s): %s", INGESTION_SETTINGS_PATH, e)
    return {}


def auto_register_enabled() -> bool:
    """`auto_register_map_meta` knob (default ON). Non-boolean values warn once
    and fall back to the default — same validation posture as the watcher's
    `_bool_setting`."""
    val = _load_ingestion_settings().get(SETTINGS_KEY, DEFAULT_ENABLED)
    if isinstance(val, bool):
        return val
    warn_key = (SETTINGS_KEY, repr(val))
    if warn_key not in _warned_once:
        _warned_once.add(warn_key)
        logger.warning(
            "Ignoring non-boolean '%s' value %r in ingestion_settings.json — "
            "expected JSON boolean true/false. Falling back to default %s.",
            SETTINGS_KEY, val, DEFAULT_ENABLED,
        )
    return DEFAULT_ENABLED


def compose_map_id(key_columns, row: dict, table_name: str = None):
    """Canonical map_id composition: map_key_columns values joined with '_'.

    [7b DONE 2026-07-29] Routed through the shared canonicalization
    (`map_overlay.canonical_bind_value` — declared column type governs):
    registration and lookup must compose the SAME identity, or a raw pre-cast
    '01' in a number-declared key column registers 'LOT_01' while the stored
    cell casts to 1 and every consumer looks up 'LOT_1'. With no table_name
    (or no declaration) the behavior is the previous `clean_str_value` pin:
    trim + integral-float folding. Divergence from the editor kept deliberate:
    the editor drops EMPTY key parts and joins the rest; here a missing/empty
    part disqualifies the row (returns None) — ingestion must not guess a
    partial identity it would then register meta for.
    """
    import map_overlay
    parts = []
    for col in key_columns:
        p = map_overlay.canonical_bind_value(table_name, col, row.get(col))
        if p is None or p == "":
            return None
        parts.append(p)
    return "_".join(parts)


def meta_business_key(target_table: str, map_id: str) -> str:
    """The `wafer_map_metadata` business key for one map — THE spelling.

    `wafer_map_metadata` declares `composite_key_source = [target_table, map_id]`, so this
    mirrors crud's composite assembly and reads the separator from the declaration rather
    than repeating it. Extracted 2026-08-06 because a second writer appeared
    (`frame_confirmation` records a confirmed coordinate system) and two spellings of an
    identity is how one writer creates the row the other cannot find.
    """
    from database import crud
    sep = (crud.TABLE_CONFIG.get(META_TABLE) or {}).get("composite_key_separator", "_")
    return "%s%s%s" % (crud.clean_str_value(target_table), sep,
                       crud.clean_str_value(map_id))


def _to_grid_int(v):
    """Parse a cell coordinate to an integral grid index; None if not integral."""
    if v is None:
        return None
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    i = int(f)
    return i if f == i else None


def synthesize_grid_meta(min_x: int, min_y: int, max_x: int, max_y: int) -> dict:
    """The mask-neutral synthetic frame (editor 표준 choice vocabulary).

    Field-for-field mirror of map_editor.js [fix C]: chip 1x1 / offset 0 /
    margin 3 and a wafer diameter whose effective radius circumscribes the
    grid's half-diagonal, so every cell corner is strictly inside the mask
    ellipse and the whole map stays pushable. `auto_registered: true` marks
    provenance (additive field — every consumer reads known keys only).
    """
    cols = max_x - min_x + 1
    rows = max_y - min_y + 1
    half_diag = math.sqrt(cols * cols + rows * rows) / 2.0
    return {
        "grid_cols": cols,
        "grid_rows": rows,
        "grid_start_x": min_x,
        "grid_start_y": min_y,
        "grid_y_invert": False,
        "rotation": 0,
        "side": "front",
        "phys_wafer_dia": max(300, math.ceil(2 * (half_diag + 4))),
        "phys_chip_x": 1,
        "phys_chip_y": 1,
        "phys_offset_x": 0,
        "phys_offset_y": 0,
        "phys_edge_margin": 3,
        "auto_registered": True,
    }


class MapMetaCollector:
    """Per-work-unit collector: cheap bbox accumulation per distinct map key,
    then one batched absent-only registration in flush().

    Inert (active=False, collect/flush no-ops) unless every gate passes at
    construction time — the knob, the recursion guard, `map_key_columns`, and a
    resolvable coordinate binding. Construction is the work-unit boundary, so
    the knob snapshot is consistent across the whole file / tx group.
    """

    def __init__(self, table_name: str, table_info: dict = None):
        self.table_name = table_name
        self.active = False
        self.key_columns = []
        self.x_col = "x"
        self.y_col = "y"
        # map_id -> [min_x, min_y, max_x, max_y]
        self.bboxes = {}

        # Recursion guard: never register meta about the meta table itself
        # (belt) — it also declares no map_key_columns (suspenders).
        if table_name == META_TABLE:
            return
        if not auto_register_enabled():
            return

        from database import crud
        cfg = table_info if isinstance(table_info, dict) and table_info else (crud.TABLE_CONFIG or {}).get(table_name)
        if not isinstance(cfg, dict):
            return
        key_cols = cfg.get("map_key_columns")
        if isinstance(key_cols, str):
            key_cols = [key_cols]
        if not (isinstance(key_cols, list) and key_cols and all(isinstance(c, str) and c for c in key_cols)):
            return

        # Coordinate binding: declared (map_overlay_config) > derived (table_config)
        # — the one shared rule every map consumer uses. None means "this table
        # cannot be interpreted as a map" (e.g. map_split_registry): skip.
        try:
            import map_overlay
            binding = map_overlay.resolve_binding(map_overlay.load_overlay_config(), table_name)
        except Exception as e:
            logger.warning("[MapMetaAuto] binding resolution failed for '%s': %s", table_name, e)
            return
        if not binding:
            return

        self.key_columns = list(key_cols)
        self.x_col = binding.get("x", "x")
        self.y_col = binding.get("y", "y")
        self.active = True

    def collect(self, rows):
        """Accumulate bbox per distinct map key from plain {column: value} dicts.

        Rows with an incomplete map key or a non-integral coordinate contribute
        nothing (the upsert path handles/ skips them by its own rules — meta
        must not invent an identity or a bound the data does not carry)."""
        if not self.active:
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            map_id = compose_map_id(self.key_columns, row, self.table_name)
            if map_id is None:
                continue
            x = _to_grid_int(row.get(self.x_col))
            y = _to_grid_int(row.get(self.y_col))
            if x is None or y is None:
                continue
            bbox = self.bboxes.get(map_id)
            if bbox is None:
                self.bboxes[map_id] = [x, y, x, y]
            else:
                if x < bbox[0]:
                    bbox[0] = x
                if y < bbox[1]:
                    bbox[1] = y
                if x > bbox[2]:
                    bbox[2] = x
                if y > bbox[3]:
                    bbox[3] = y

    def pending(self) -> bool:
        return self.active and bool(self.bboxes)

    def flush(self, db) -> int:
        """Create missing meta rows for every collected key. Returns #created.

        One indexed existence check per distinct key per work unit (chunked
        `business_key_val IN (...)`), absent-only creation through
        `crud.apply_batch_updates` (commits internally; outbox events flow).
        """
        if not self.pending():
            return 0
        from database import crud, models, schemas

        model = models.DYNAMIC_TABLES.get(META_TABLE)
        if model is None:
            _warn_key = ("no_meta_model",)
            if _warn_key not in _warned_once:
                _warned_once.add(_warn_key)
                logger.warning(
                    "[MapMetaAuto] '%s' model not initialized — auto-registration skipped. "
                    "Declare it in table_config.json.", META_TABLE)
            return 0

        # 1) Drop keys already verified this run (process-lifetime cache).
        with _known_lock:
            candidates = [mid for mid in self.bboxes if (self.table_name, mid) not in _known_present]
        if not candidates:
            return 0

        # 2) Batched existence check on the indexed business_key_val column.
        #    bk composition is `meta_business_key` — one spelling, shared with the
        #    confirmation writer.
        bk_of = {mid: meta_business_key(self.table_name, mid) for mid in candidates}
        existing = set()
        bk_list = list(bk_of.values())
        for i in range(0, len(bk_list), CHUNK_SIZE):
            chunk = bk_list[i:i + CHUNK_SIZE]
            for (found_bk,) in db.query(model.business_key_val).filter(
                    model.business_key_val.in_(chunk)).all():
                existing.add(found_bk)

        missing = [mid for mid in candidates if bk_of[mid] not in existing]
        present = [mid for mid in candidates if bk_of[mid] in existing]
        self._remember(present)
        if not missing:
            return 0

        # 3) Absent-only creation through the normal write path.
        created = 0
        tx_id = f"auto_map_meta_{uuid.uuid4()}"
        for i in range(0, len(missing), CHUNK_SIZE):
            chunk = missing[i:i + CHUNK_SIZE]
            items = []
            for mid in chunk:
                min_x, min_y, max_x, max_y = self.bboxes[mid]
                items.append(schemas.GeneralUpdateItem(
                    business_key_val=bk_of[mid],
                    updates={
                        "target_table": self.table_name,
                        "map_id": mid,
                        "grid_metadata": json.dumps(synthesize_grid_meta(min_x, min_y, max_x, max_y)),
                    },
                    source_name=SOURCE_NAME,
                    updated_by="system",
                ))
            batch = schemas.GeneralUpdateBatch(updates=items, transaction_id=tx_id, silent=True)
            crud.apply_batch_updates(db, META_TABLE, batch)
            created += len(items)
            self._remember(chunk)

        logger.info(
            "[MapMetaAuto] registered %d missing %s row(s) for '%s' (keys: %s%s)",
            created, META_TABLE, self.table_name,
            ", ".join(missing[:5]), " …" if len(missing) > 5 else "")
        return created

    def _remember(self, map_ids):
        with _known_lock:
            if len(_known_present) + len(map_ids) > _KNOWN_CACHE_MAX:
                _known_present.clear()
            for mid in map_ids:
                _known_present.add((self.table_name, mid))
