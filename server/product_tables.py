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

Nothing else should hard-code these declarations. Adding a fifth product table
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
        "__comment": "[제품 소유 저장소 — 이름·컬럼을 바꾸지 마라] 맵 값(legend)의 정본 레지스트리. 값마다 split_desc(실험 split 조건의 자연어 기록)와 color를 붙이며, 맵 에디터의 legend가 이 테이블로 서버 영속화된다(localStorage는 오프라인 캐시로 강등). bk = ref_table|map_key|value 이고 구분자는 반드시 '|' 다 — map_key 자체가 '_' 조인 문자열이고 테이블명에도 '_'가 흔해 '_'로는 키가 모호해진다(client2/src/map_editor.js의 SPLIT_KEY_SEP와 일치해야 함). 전사 계획(M2)의 DOE는 값 단위 속성을 여기서 조인해 읽으므로 map_doe에 중복 저장하지 않는다. | map_key_columns = (ref_table, map_key): a legend is saved as a whole set for one map, so removing a value has to fall out of the write. Without this declaration `replace_map` has no scope to delete by and the client is forced to compute the difference itself - which is how deleted DOE values used to come back on the next load.",
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
            "eventtime": "string"
        },
        "display_columns": [
            "split_key",
            "ref_table",
            "map_key",
            "value",
            "split_desc",
            "color",
            "eventtime"
        ],
        "map_key_columns": [
            "ref_table",
            "map_key"
        ]
    },
    "map_doe": {
        "__comment": "[제품 소유 저장소 — 이름·컬럼을 바꾸지 마라] 전사 계획(M2)의 DOE 정의. 행 단위는 (값, STACK 구간)이라 bk = ref_table|map_key|doe_value|band_seq 다. band_seq(정수 서수)가 정체를 지고 stack_band(자유 텍스트 라벨)는 비키 컬럼이다 — 라벨을 키에 넣으면 라벨 수정이 곧 re-key가 되어 하위 자재 행이 고아가 된다. transfer_plan_config.json의 plan_store.doe 바인딩이 이 테이블을 가리킨다. updated_by·eventtime은 클라이언트가 저장 시 함께 쓰는 감사 컬럼이며(client2/src/transfer_plan.js), 특히 eventtime은 다시 읽혀 계획 헤더의 '서버 <시각>' 칩이 된다 — 선언에서 빼면 서버가 조용히 버려(crud.py의 column_types 게이트) 칩이 사라진다. | map_key_columns = (ref_table, map_key): that pair IS the plan's identity - there is no plan_id - so it is the scope a `replace_map` write deletes by. A DOE save sends the plan's complete set; deletion is then part of the write instead of a separate client-side difference step. Removing this declaration silently turns `replace_map` into crud.py's column-guessing fallback, which matches almost nothing and deletes nothing.",
        "business_key": "doe_key",
        "composite_key_source": [
            "ref_table",
            "map_key",
            "doe_value",
            "band_seq"
        ],
        "composite_key_separator": "|",
        "column_types": {
            "doe_key": "string",
            "ref_table": "string",
            "map_key": "string",
            "doe_value": "string",
            "band_seq": "number",
            "stack_band": "string",
            "qty_total": "number",
            "knobs": "string",
            "note": "string",
            "updated_by": "string",
            "eventtime": "string"
        },
        "display_columns": [
            "doe_key",
            "ref_table",
            "map_key",
            "doe_value",
            "band_seq",
            "stack_band",
            "qty_total",
            "knobs",
            "note",
            "updated_by",
            "eventtime"
        ],
        "map_key_columns": [
            "ref_table",
            "map_key"
        ]
    },
    "map_doe_source": {
        "__comment": "[제품 소유 저장소 — 이름·컬럼을 바꾸지 마라] DOE 구간에 투입되는 자재(소스 웨이퍼) 묶음. 한 구간에 여러 매가 붙으므로(pool) bk에 소스 차원이 더해진다: ref_table|map_key|doe_value|band_seq|source_lot|source_slot. 매별 소요는 구간 총량(map_doe.qty_total)의 균등 배분이며 qty가 명시되면 그것이 우선한다. transfer_plan_config.json의 plan_store.doe_source 바인딩이 이 테이블을 가리킨다. updated_by·eventtime은 map_doe와 동일하게 클라이언트가 저장 시 함께 쓰는 감사 컬럼이다 — 선언에서 빼면 조용히 버려진다. | map_key_columns = (ref_table, map_key): same scope as map_doe. The material pool of a plan is saved as one complete set, so dropping the last material of a band has to be expressible as a write.",
        "business_key": "source_key",
        "composite_key_source": [
            "ref_table",
            "map_key",
            "doe_value",
            "band_seq",
            "source_lot",
            "source_slot"
        ],
        "composite_key_separator": "|",
        "column_types": {
            "source_key": "string",
            "ref_table": "string",
            "map_key": "string",
            "doe_value": "string",
            "band_seq": "number",
            "source_lot": "string",
            "source_slot": "string",
            "qty": "number",
            "note": "string",
            "updated_by": "string",
            "eventtime": "string"
        },
        "display_columns": [
            "source_key",
            "ref_table",
            "map_key",
            "doe_value",
            "band_seq",
            "source_lot",
            "source_slot",
            "qty",
            "note",
            "updated_by",
            "eventtime"
        ],
        "map_key_columns": [
            "ref_table",
            "map_key"
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
