"""Product-owned table declarations — **the** single definition.

Ownership line (see docs/guide/CONFIG_GUIDE.md 5.8-ter):

* **product-owned**  assyManager's own storage. The product decides the table
  name and the columns; a site has no reason to change either. Declared here.
* **site-owned**     the customer's factory data. Table and column names differ
  per deployment. Never declared here, never touched by the installer.

Why a Python module and not a second JSON file: ``server/config/**`` is
gitignored (only ``*.sample`` is tracked), so a canonical JSON there would not
ship. This module is code, tracked, and imported by exactly two consumers:

1. ``server/scripts/install_product_tables.py``  — installs these entries into a
   site's live ``table_config.json``.
2. ``server/config/table_config.json.sample``    — the tracked template. Its
   product section is *generated* by the same installer
   (``install_product_tables.py --sample --apply``) and
   ``server/tests/test_install_product_tables.py`` asserts the two agree, so the
   sample can never silently drift away from this module.

Nothing else should hard-code these declarations. Adding another product table
means editing this dict and re-running the installer against the sample.

Import convention follows ``paths.py`` / ``event_constants.py``: ``server/`` is
on ``sys.path`` in every entry point, so ``import product_tables`` resolves.
"""

# Entry keys that carry documentation only. ``database/models.py``
# ``init_dynamic_models`` reads ``column_types`` / ``business_key`` /
# ``composite_key_*`` and ignores everything else, so these keys cannot change
# runtime behaviour. The installer therefore treats a difference in them as a
# note, not as drift — otherwise every existing site would be flagged the moment
# a comment is reworded.
ANNOTATION_KEYS = ("__comment",)

# Order here is the order new entries are appended to a config file.
PRODUCT_TABLES = {
    "wafer_map_metadata": {
        "__comment": "[제품 소유 저장소 — 이름·컬럼을 바꾸지 마라] 맵 격자 규격(grid_metadata)의 정본. 맵을 담는 모든 테이블(defect·EDS·DT·bonding·core)이 여기에 등록돼야 정렬이 성립한다 — 미등록은 정상 상태가 아니라 누락이며, 화면에는 '화면기준' 칩으로 표면화된다. bk = target_table_map_id.",
        "business_key": "map_pk",
        "composite_key_source": [
            "target_table",
            "map_id"
        ],
        "composite_key_separator": "_",
        "column_types": {
            "map_pk": "string",
            "target_table": "string",
            "map_id": "string",
            "grid_metadata": "string"
        },
        "display_columns": [
            "map_pk",
            "target_table",
            "map_id",
            "grid_metadata"
        ]
    },
    "map_split_registry": {
        "__comment": "[제품 소유 저장소 — 이름·컬럼을 바꾸지 마라] 맵 값(legend)의 정본 레지스트리이자 **DOE 그 자체**. 값 하나 = 행 하나 = DOE 조건 하나다. bk = ref_table|map_key|value 이고 구분자는 반드시 '|' 다 — map_key 자체가 '_' 조인 문자열이고 테이블명에도 '_'가 흔해 '_'로는 키가 모호해진다(client2/src/map_editor.js의 SPLIT_KEY_SEP와 일치해야 함). | `split_desc` and `knobs` stay FLAT columns on purpose - they are what the ontology/LLM consumes, and nesting them would put the ontology's input inside a JSON blob. | ZONE MODEL (2026-07-27, supersedes bands): the layer structure of a value is THREE FIXED ZONES implied by one number. `stack` = that value's total layer count; `mat_1h` = layer 1; `mat_top` = layer `stack`; `mat_mid` = everything between. An empty `mat_1h` means MID starts at layer 1; an empty `mat_top` means MID runs to `stack`. There is no FROM, no TO, no band row and no value-set scope - the zones tile `1..stack` BY CONSTRUCTION, which is why overlap and gap checks disappeared rather than moved. `mat_mid` is MANDATORY: an empty MID with a real `stack` leaves layers uncovered. | `stack` IS DECLARED `string`, NOT `number`, AND THAT IS LOAD-BEARING. It was `number` for one commit and the physical column came out `double precision`; `crud.cast_value_by_type` then RAISED on `'0x10'`/`'nope'` (so a plan carrying one unreadable height could not be saved at all) and silently repaired `'7.5'` to `7.5` (so the next read truncated it to 7 - the 'screen is fine, number is short' defect this whole zone model exists to close). An unreadable STACK has to SURVIVE the round trip: V5 blocks on it, the panel shows the user their own text, and `planRowToRecord` exports the raw string back to Excel. A numeric column cannot hold any of that. The single integer reader (`transfer_plan._int_state` / `bandToState`) is what decides readability - never the column type. | THE THREE mat_* COLUMNS ARE JSON ARRAYS of raw tokens (`[\"MID1:1\", \"MID3:1\"]`), not a separator-joined string. A lot name may legally contain `:`, `_`, and there is no character that is safely outside it - the `materialPoolKey` comment in doe_bands.js records what happened the last time a separator was assumed (two unrelated pools merged into one row and their quantities were summed). The token text IS the identity; `lot[_slot][:BIN]` parsing is a later, DECLARED step and must never move the stored string. | NOTHING DERIVED IS STORED. In particular the per-material figure is a SUFFICIENCY CHECK, NOT AN ALLOCATION - wafers are consumed one at a time in an order nobody records, so an even split answers only \"is there enough across this pool\" (positive remainder = feasible). Never store it and never name it as \"this wafer contributes exactly N\". | `bands` IS RETIRED (2026-07-27) but STILL DECLARED, deliberately: `transfer_plan.REGISTRY_ROLES` requires the `bands` role, so removing this column alone turns GET /api/transfer-plan/validate into a 404 for every site. The column comes out in the SAME change that rewrites that reader for the zone model - not before. Do not add a new writer. | NO `updated_by` COLUMN, deliberately: crud.py lists updated_by in its `system_cols` and skips it in the column loop, so a declared updated_by can never be written through the generic table API - it would sit NULL forever and invite a join that returns nothing. map_doe/map_doe_source proved it: every row's updated_by is NULL. The 'who' is already carried per cell by cell_sources/cell_overwrites.updated_by. | map_key_columns = (ref_table, map_key): a legend is saved as a whole set for one map, so removing a value has to fall out of the write. Without this declaration `replace_map` has no scope to delete by, returns 200 and deletes NOTHING - which is how deleted DOE values used to come back on the next load.",
        "business_key": "split_key",
        "composite_key_source": [
            "ref_table",
            "map_key",
            "value"
        ],
        "composite_key_separator": "|",
        "column_types": {
            "split_key": "string",
            "ref_table": "string",
            "map_key": "string",
            "value": "string",
            "split_desc": "string",
            "color": "string",
            "knobs": "string",
            "stack": "string",
            "mat_1h": "string",
            "mat_mid": "string",
            "mat_top": "string",
            "bands": "string",
            "eventtime": "string"
        },
        "display_columns": [
            "split_key",
            "ref_table",
            "map_key",
            "value",
            "split_desc",
            "color",
            "knobs",
            "stack",
            "mat_1h",
            "mat_mid",
            "mat_top",
            "bands",
            "eventtime"
        ],
        "map_key_columns": [
            "ref_table",
            "map_key"
        ]
    },
    # [RETIRED 2026-08-13] `map_doe` and `map_doe_source` were declared here until
    # today. They lost their last writer at M2.6 (2026-07-27) when the DOE became the
    # `map_split_registry` row itself, and the declarations were kept only so an
    # operator could still read the rows while hand-migrating. The product owner
    # approved the physical DROP on 2026-08-13, so the declarations go with it:
    # leaving them here would make `install_product_tables.py` re-add them to a live
    # `table_config.json`, and the config watcher would then CREATE the tables again
    # — the drop would silently undo itself on the next deploy run.
    # Migrations: server/migrations/drop_map_doe_tables.sql (+ _reverse.sql, which
    # carries the full column list if anything ever has to come back).
    "valid_die_ref": {
        "__comment": "[제품 소유 저장소 — 이름·컬럼을 바꾸지 마라] THE storage table of valid-die maps. Promoted to product-owned 2026-08-04 by user ruling: \"유효 다이 맵을 저장하는 테이블은 valid_die_ref라는 테이블로 항상 고정\" — the map editor's table picker was removed in the same change, so the client now saves and loads the valid-die area from this table and no other. It was already declared at the founding site; being product-owned is what makes it exist at EVERY site and what stops it being deleted as if it were somebody's fixture table. | A row is one CELL of one valid-die map: bk = product_type_x_y, and map_key_columns = (product, type) is the pair that identifies the map, so a map key reads `PRODUCT_TYPE`. | Its consumer is `grid_metadata.valid_die_ref` in wafer_map_metadata, which names a map in THIS table; the reference resolution walks the same primitives as an overlay (spec -> binding -> frame -> projection) and REFUSES rather than falling back to the wafer circle when it cannot resolve. That is why an entry here is not enough on its own: a valid-die map must ALSO be registered in wafer_map_metadata or nothing can reference it. | `val` is the painted value per cell; the mask is 'which cells exist', so what a value says does not change the mask. Do not add a second 'is this die valid' column - the presence of the row IS the answer, and a second one would let the two disagree with nothing on screen saying which won.",
        "business_key": "cell_key",
        "composite_key_source": [
            "product",
            "type",
            "x",
            "y"
        ],
        "composite_key_separator": "_",
        "column_types": {
            "cell_key": "string",
            "product": "string",
            "type": "string",
            "x": "number",
            "y": "number",
            "val": "string"
        },
        "display_columns": [
            "cell_key",
            "product",
            "type",
            "x",
            "y",
            "val"
        ],
        "map_key_columns": [
            "product",
            "type"
        ]
    },
}

PRODUCT_TABLE_NAMES = tuple(PRODUCT_TABLES.keys())


def effective_declaration(entry):
    """The behaviour-bearing part of a table entry (annotations stripped).

    Comparisons between a config entry and the product definition run on this,
    so rewording a ``__comment`` never registers as drift.
    """
    if not isinstance(entry, dict):
        return entry
    return {k: v for k, v in entry.items() if k not in ANNOTATION_KEYS}
