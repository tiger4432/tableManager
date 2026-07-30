"""Virtual join 선언 로더/검증기 ― **팬아웃하는 선언을 로드 시점에 거부한다.**

[무엇인가] Virtual join은 두 테이블을 **저장하지 않고 조회 시점에** 잇는다.
`/api/maps/overlay`가 좌표로 하는 일을 행(row) 모양으로 하는 것이고, 잇는 기준은
좌표가 아니라 선언된 조인 키다. 이 파일은 그 **선언**만 다룬다 ― 조인 실행은 여기 없다.

[왜 가드가 먼저인가 ― 실측 2026-07-31, 운영 DB read-only]
    core_defect_map ⋈ eds_fail_map (lot,slot,x,y)   103,040 →     103,040   x1
    core_defect_map ⋈ eds_fail_map (lot,slot)       103,040 → 132,715,520   x1288
    bonding_log     ⋈ wafer_process (lot,slot)       14,436 →   2,552,624   x177

**맵 정체성(lot/slot)으로 이으면 맵의 셀 수만큼 곱해지고, 칩 정체성(lot/slot/x/y)으로
이으면 곱해지지 않는다.** 두 선언은 글자 하나 차이인데 결과는 103,040행과 1억 3천만 행이다.
이 차이는 실행해 보기 전에는 아무 데도 나타나지 않으므로 ― 문법도 맞고 컬럼도 존재한다 ―
**선언을 읽는 시점에 거부하지 않으면 거부할 자리가 없다.**

[유일성의 근거는 두 겹이고, 한 겹은 공짜가 아니다]

  ① 정적 구조 검사 (항상 · DB 접근 0회 · 이 파일의 `_validate_join`)
     오른쪽 테이블이 `table_config`에 선언한 키(`composite_key_source`, 없으면
     `business_key`)가 **조인 키의 부분집합**이어야 한다. 부분집합이 아니면 그 테이블은
     조인 키만으로 행 하나를 지목하지 못한다 ― 위 x1288/x177이 정확히 이 경우다.
     **필요조건이지 충분조건이 아니다.**

  ② 라이브 유일성 검증 (`db` 세션이 주어졌을 때만 · `verify_uniqueness`)
     ①만으로는 부족하다는 것이 실측으로 증명됐다. `bonding_map`은 선언 키
     `(base,x,y)`로 ①을 **통과**하지만 실제로는 중복 그룹 2,312개(최대 10행/키)를
     갖고 있다 ― ①만 믿으면 1,759,574행 테이블에 10배 팬아웃을 허가한다.

[왜 「선언한 키니까 유일하다」를 믿지 않는가 ― 실측이 반증했다]
`business_key_val`에는 **UNIQUE 제약이 없다**(평범한 btree 2개뿐). dedup 업서트는 규약일
뿐 DB가 강제하지 않으며, 운영 DB에서 실제로 깨져 있다:

    bonding_log      log_id            중복 그룹 117개 / 234행 (전부 non-null)
    bonding_map      base+x+y          중복 그룹 2,312개 / 4,645행 (non-null 2,082개)
    inventory_master part_no           중복 그룹 164개 / 427행
    wafer_process    proc_id           중복 그룹 43개 / 86행

그래서 선언은 **필요조건**으로만 쓰고 유일성의 증거로는 쓰지 않는다.

[증거 등급 ― 무엇을 보장하는지 이름으로 구분한다]
  `unique_index`  DB의 UNIQUE 인덱스가 조인 키를 덮는다. **영구 보장** ― 이후의 어떤
                  쓰기도 이 성질을 깰 수 없다. 유일하게 「나중에 터지지 않는다」고
                  말할 수 있는 등급이다.
  `probe_clean`   프로브가 완주했고 중복이 없었다. **그 시점의 스냅샷일 뿐이다** ―
                  이후에 들어온 행이 중복을 만들 수 있다.
  `unverified`    정적 검사만 통과했다. 라이브 증거가 없다.

[비용 실측 ― 왜 프로브에 예산이 붙는가]
중복을 **찾는** 방향은 싸다(첫 중복에서 멈춘다): 1.0ms / 2.5ms / 351ms.
중복이 **없음을 증명하는** 방향은 전수 스캔이다: 103,040행 = 약 120ms(859행/ms).
같은 속도로 1,000만 행이면 **약 11.6초**이고 정렬이 디스크로 넘친다(337k행에서 이미
temp write 881블록 관측). 그래서 프로브는 `statement_timeout` 예산 안에서만 돌고,
예산이 다하면 「깨끗하다」가 아니라 **「증명하지 못했다」**로 답한다.

[이 파일이 보장하는 것과 못 하는 것 ― 부분을 부분이라고 말한다]
  보장한다  ― ①을 통과하지 못하는 선언은 **절대** 유효 규칙 목록에 들어가지 않는다.
              이것은 데이터가 아니라 **선언의 모양**에 대한 성질이라 시간이 지나도 변하지 않는다.
  보장 못 한다 ― `probe_clean`/`unverified` 등급은 미래를 말하지 않는다. 나중에 들어온
              행이 중복을 만들면 그 선언은 팬아웃한다. **영구 보장은 `unique_index` 뿐이며,
              그 인덱스를 만드는 것은 운영자의 DDL이고 이 파일의 권한 밖이다.**

[미상(未詳)의 정의 ― 경계 계약]
조인 결과에서 `미상`은 **두 경우를 모두 덮는다**:
  ① 오른쪽에 맞는 행이 아예 없다(no right row).
  ② 맞는 행은 있는데 그 값이 비어 있다(matched but NULL/빈 문자열).
LEFT 조인만으로는 ②가 보이지 않는다. 실측(2026-07-31)이 그 이유다 ―
`bonding_log → core_wafer_map.wafer_id`는 14,436행 **전부**가 오른쪽 행을 찾지만
3,792행(26.27%)의 `wafer_id`가 비어 있고, `core_defect_map → core_wafer_map.wafer_id`는
103,040행 전부가 행을 찾지만 88,872행(86.25%)이 비어 있다. ②를 `미상`에서 빼면
분석가는 「값이 있다」고 읽는다. INNER 조인은 ①을 조용히 지우므로 금지다.
"""
import json
import logging
import os
import re

logger = logging.getLogger("VirtualJoinConfig")

from paths import CONFIG_DIR  # single override point (ASSY_DATA_ROOT)

VIRTUAL_JOIN_RULES_PATH = os.path.join(CONFIG_DIR, "virtual_join_rules.json")

# 식별자 형태 강제. 테이블/컬럼 이름은 table_config에서 오지만, 프로브 경로가 이름을
# 다루므로 검증이 실행보다 먼저 온다(enrichment_config._CANDIDATE_COLUMN_RE와 같은 자세).
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# --- 유일성 증거 등급 (내부 어휘 ― 닫힌 사유 어휘와 별개다) ---
EVIDENCE_UNIQUE_INDEX = "unique_index"
EVIDENCE_PROBE_CLEAN = "probe_clean"
EVIDENCE_UNVERIFIED = "unverified"
EVIDENCE_GRADES = (EVIDENCE_UNIQUE_INDEX, EVIDENCE_PROBE_CLEAN, EVIDENCE_UNVERIFIED)

# --- 거부 코드 (내부 어휘 ― config_resolve_report가 닫힌 사유로 사상한다) ---
CODE_KEY_NOT_COVERED = "key_not_covered"        # ① 정적 검사 실패 = 팬아웃 선언
CODE_DUPLICATE_FOUND = "duplicate_found"        # ② 프로브가 중복을 찾았다
CODE_PROBE_INCOMPLETE = "probe_incomplete"      # ② 예산 소진 ― 증명 못 함
CODE_FANOUT_DECLARED = "fanout_declared"        # 집계 형태는 아직 없다
CODE_SHAPE = "shape"                            # 평범한 문법/존재 오류

# 프로브 예산. 기본값 근거: 실측 859행/ms이므로 2,000ms는 약 170만 행까지 완주한다
# (bonding_map 1,759,574행이 그 경계에 있다). 넘는 테이블은 예산을 올리는 대신
# UNIQUE 인덱스를 만드는 편이 옳다 ― 그것만이 영구 보장이기 때문이다.
DEFAULT_PROBE_BUDGET_MS = 2000
MAX_PROBE_BUDGET_MS = 30000

# 조인 결과에서 해소되지 않은 값이 취하는 표시. 「값이 빔」까지 포함한다(모듈 상단 계약).
DEFAULT_UNRESOLVED_LABEL = "미상"

# 한 선언이 노출할 수 있는 오른쪽 컬럼 수 상한. 조인 하나가 왼쪽 테이블의 폭을
# 통째로 두 배로 만들지 않게 하는 것이 목적이다.
MAX_EXPOSE_COLUMNS = 32


def _record(rejections, scope: str, subject, detail: str, code: str = CODE_SHAPE,
            facts: dict = None):
    """무효 선언 1건을 수집기에 남긴다 ― `enrichment_config._record`와 같은 형태.

    `code`와 `facts`가 늘어난 것이 유일한 차이다. enrichment는 로더가 **명명된 사유를
    싣지 않는다**는 규율을 갖는데, 그것은 `config_resolve_report`의 **닫힌 어휘**를 로더가
    만들지 못하게 하려는 것이다. `code`는 그 어휘가 아니라 이 파일의 내부 분류이고,
    보고서가 「팬아웃이라 거부」와 「컬럼 오타라 거부」에 **다른 한국어 문장**을 붙이는
    데만 쓴다. 어휘로의 사상은 여전히 보고서 계층의 책임이다.

    `facts`는 **문장이 아니라 사실**이다(테이블명·컬럼 목록). 로더의 `detail`은 영어
    로그 문구인데, 그것을 한국어 문장 뒤에 그대로 이어 붙이면 운영자가 읽는 최종 문장이
    반쯤 영어가 된다(INV-F9-8이 금지하는 「완성되지 않은 문장」의 한 형태다). 사실만
    넘기면 보고서가 온전한 한국어 문장을 짓는다.
    """
    if rejections is None:
        return
    rejections.append({"scope": scope, "subject": subject, "detail": detail,
                       "code": code, "facts": dict(facts or {})})


def _is_str_list(value) -> bool:
    return isinstance(value, list) and len(value) > 0 and all(
        isinstance(v, str) and v.strip() for v in value)


def declared_key_columns(table_cfg: dict) -> list:
    """테이블이 `table_config`에 선언한 행 정체성 컬럼들.

    `composite_key_source`가 정본이고, 없으면 `business_key` 단독이다. 둘 다 없으면
    빈 목록 ― 그 테이블은 **어떤 조인 키로도** 행 하나를 지목한다고 주장할 수 없다.
    """
    if not isinstance(table_cfg, dict):
        return []
    comp = table_cfg.get("composite_key_source")
    if isinstance(comp, list) and comp and all(isinstance(c, str) for c in comp):
        return list(comp)
    bk = table_cfg.get("business_key")
    return [bk] if isinstance(bk, str) and bk.strip() else []


def key_is_covered(declared_key: list, right_join_cols: list) -> bool:
    """오른쪽 테이블의 선언 키가 조인 키에 **덮이는가**(부분집합인가).

    덮이면: 조인 키가 선언 키의 모든 성분을 고정하므로, 선언 키가 행을 결정한다는
    dedup 업서트 규약 아래에서 오른쪽은 조인 키당 최대 1행이다.
    덮이지 않으면: 조인 키가 고정하지 못하는 성분이 남아 그 성분의 값 수만큼 곱해진다
    ― `eds_fail_map`의 `(x,y)`가 남으면 셀 수(1,288)만큼 곱해진 것이 실측이다.

    선언 키가 비어 있으면 **덮이지 않은 것으로 본다**(주장할 근거가 없다).
    """
    if not declared_key:
        return False
    return set(declared_key) <= set(right_join_cols)


def _validate_join(name: str, raw: dict, known_tables: dict, rejections: list = None) -> tuple:
    """선언 1건을 검증·정규화한다.

    반환: `(normalized|None, 실패사유|None, code|None, facts|None)`.
    `facts`는 보고서가 온전한 한국어 문장을 짓는 데 쓰는 **구조화된 사실**이고,
    지금은 팬아웃 거부(`CODE_KEY_NOT_COVERED`)만 채운다 ― 운영자가 가장 자주 만나는
    거부이고, 「무엇이 고정되지 않았는가」를 문장이 지목해야 고칠 수 있기 때문이다.
    """
    if not isinstance(raw, dict):
        return None, "join declaration must be an object", CODE_SHAPE, None
    if raw.get("enabled", True) is False:
        return None, None, None, None  # 비활성 ― 오류 아님, 조용히 제외

    left_table = raw.get("left_table")
    right_table = raw.get("right_table")
    if not isinstance(left_table, str) or not left_table.strip():
        return None, "'left_table' is required", CODE_SHAPE, None
    if not isinstance(right_table, str) or not right_table.strip():
        return None, "'right_table' is required", CODE_SHAPE, None
    left_table, right_table = left_table.strip(), right_table.strip()

    # 집계 형태는 **아직 구현되지 않았다.** 여기서 조용히 허용하면 유일성 검사를 끄는
    # 스위치만 있고 그 스위치가 향하는 안전한 경로는 없는 상태가 된다 ― 처음 거부를
    # 만난 운영자가 그것을 켜고 1억 3천만 행 조인을 얻는다. 그래서 이름 있는 거부다.
    cardinality = raw.get("join_cardinality", "one")
    if cardinality != "one":
        return None, (
            f"'join_cardinality': {json.dumps(cardinality, ensure_ascii=False)} is not "
            f"supported yet; only 'one' (row join with a unique right side) exists. "
            f"The aggregate form has no implementation to be safe in."
        ), CODE_FANOUT_DECLARED, None

    raw_key = raw.get("join_key")
    if not isinstance(raw_key, list) or not raw_key:
        return None, ("'join_key' must be a non-empty list of "
                      "{left: column, right: column} pairs"), CODE_SHAPE, None
    join_key = []
    seen_right = set()
    for i, pair in enumerate(raw_key):
        if not isinstance(pair, dict):
            return None, f"join_key[{i}] must be an object {{left, right}}", CODE_SHAPE, None
        lc, rc = pair.get("left"), pair.get("right")
        for label, col in (("left", lc), ("right", rc)):
            if not isinstance(col, str) or not _IDENT_RE.match(col.strip()):
                return None, (f"join_key[{i}].{label} must be a plain column identifier "
                              f"([A-Za-z_][A-Za-z0-9_]*)"), CODE_SHAPE, None
        lc, rc = lc.strip(), rc.strip()
        if rc in seen_right:
            # 같은 오른쪽 컬럼을 두 번 묶으면 조인 키가 넓어 보이지만 실제로 고정하는
            # 성분은 하나다 ― 덮임 판정이 거짓으로 통과한다.
            return None, (f"join_key binds right column '{rc}' more than once; "
                          f"the duplicate does not narrow the key"), CODE_SHAPE, None
        seen_right.add(rc)
        join_key.append({"left": lc, "right": rc})

    expose = raw.get("expose")
    if not _is_str_list(expose):
        return None, "'expose' must be a non-empty list of right-table column names", CODE_SHAPE, None
    expose = [c.strip() for c in expose]
    if len(expose) > MAX_EXPOSE_COLUMNS:
        return None, (f"'expose' declares {len(expose)} columns; the cap is "
                      f"{MAX_EXPOSE_COLUMNS}"), CODE_SHAPE, None
    if len(set(expose)) != len(expose):
        return None, "'expose' contains duplicate column names", CODE_SHAPE, None
    for c in expose:
        if not _IDENT_RE.match(c):
            return None, (f"expose column '{c}' is not a plain column identifier "
                          f"([A-Za-z_][A-Za-z0-9_]*)"), CODE_SHAPE, None

    label = raw.get("unresolved_label", DEFAULT_UNRESOLVED_LABEL)
    if not isinstance(label, str) or not label.strip():
        return None, "'unresolved_label' must be a non-empty string", CODE_SHAPE, None
    label = label.strip()

    right_join_cols = [p["right"] for p in join_key]
    declared_key = []

    # --- 테이블/컬럼 존재 검증 + ① 정적 유일성 (table_config가 주어진 경우에만) ---
    if known_tables is not None:
        left_cfg = known_tables.get(left_table)
        right_cfg = known_tables.get(right_table)
        if left_cfg is None:
            return None, (f"left_table '{left_table}' is not registered in "
                          f"table_config.json"), CODE_SHAPE, None
        if right_cfg is None:
            return None, (f"right_table '{right_table}' is not registered in "
                          f"table_config.json"), CODE_SHAPE, None
        left_cols = set((left_cfg.get("column_types") or {}).keys())
        right_cols = set((right_cfg.get("column_types") or {}).keys())

        missing = [p["left"] for p in join_key if p["left"] not in left_cols]
        if missing:
            return None, (f"join_key left column(s) missing in '{left_table}': "
                          f"{', '.join(missing)}"), CODE_SHAPE, None
        missing = [p["right"] for p in join_key if p["right"] not in right_cols]
        if missing:
            return None, (f"join_key right column(s) missing in '{right_table}': "
                          f"{', '.join(missing)}"), CODE_SHAPE, None
        missing = [c for c in expose if c not in right_cols]
        if missing:
            return None, (f"expose column(s) missing in '{right_table}': "
                          f"{', '.join(missing)}"), CODE_SHAPE, None
        # 왼쪽에 같은 이름이 이미 있으면 조인 컬럼이 그것을 가린다 ― 어느 쪽 값을 보고
        # 있는지 알 수 없는 표가 만들어진다.
        shadowed = [c for c in expose if c in left_cols]
        if shadowed:
            return None, (f"expose column(s) {', '.join(shadowed)} already exist on "
                          f"'{left_table}'; the joined value would shadow the left one"), CODE_SHAPE, None

        # ① 정적 유일성 ― 이 파일의 존재 이유
        declared_key = declared_key_columns(right_cfg)
        if not key_is_covered(declared_key, right_join_cols):
            if declared_key:
                uncovered = sorted(set(declared_key) - set(right_join_cols))
                reason = (f"right table '{right_table}' identifies a row by "
                          f"{' + '.join(declared_key)}, and the join key does not fix "
                          f"{', '.join(uncovered)}")
            else:
                reason = (f"right table '{right_table}' declares neither "
                          f"'composite_key_source' nor 'business_key', so no join key can "
                          f"be shown to select one row")
            return None, (
                f"join key does not select a single row on the right side: {reason}. "
                f"A row join needs the right side to be unique on the join key; "
                f"otherwise every left row is multiplied by the number of matching "
                f"right rows."
            ), CODE_KEY_NOT_COVERED, {
                "right_table": right_table,
                "declared_key": list(declared_key),
                "uncovered": sorted(set(declared_key) - set(right_join_cols)),
                "join_key": list(right_join_cols),
            }

    normalized = {
        "name": name,
        "left_table": left_table,
        "right_table": right_table,
        "join_key": join_key,
        "left_columns": [p["left"] for p in join_key],
        "right_columns": right_join_cols,
        "expose": expose,
        "unresolved_label": label,
        "join_cardinality": "one",
        # ①을 통과했다는 사실. ②의 결과는 `verify_uniqueness`가 따로 채운다 ―
        # 정적 통과를 유일성의 증거로 읽지 못하게 필드를 나눠 둔다.
        "declared_key": declared_key,
        "uniqueness_evidence": EVIDENCE_UNVERIFIED,
    }
    return normalized, None, None, None


def validate_virtual_join_rules(raw_config, known_tables: dict = None,
                                rejections: list = None) -> list:
    """선언 dict 전체를 검증한다. 무효 선언은 **목록에서 제외**된다."""
    rules = []
    if not isinstance(raw_config, dict):
        logger.error("virtual_join_rules.json must be an object {name: declaration}")
        _record(rejections, "file", None,
                "virtual_join_rules.json must be an object {name: declaration} ― "
                "NO virtual join is in effect")
        return rules
    for name, raw in raw_config.items():
        if not isinstance(name, str) or not name.strip() or name.startswith("_"):
            continue  # `__comment` 류는 선언이 아니다
        normalized, err, code, facts = _validate_join(name, raw, known_tables,
                                                      rejections=rejections)
        if err is not None:
            logger.warning("[VirtualJoin:%s] declaration rejected: %s", name, err)
            _record(rejections, "rule", name, err, code=code, facts=facts)
            continue
        if normalized is not None:
            rules.append(normalized)
    return rules


def load_virtual_join_rules(path: str = None, known_tables: dict = None,
                            rejections: list = None) -> list:
    """virtual_join_rules.json을 읽어 **①을 통과한** 선언만 반환한다(파일 없음 → 빈 목록).

    **DB를 건드리지 않는다.** ②(라이브 유일성)는 `verify_uniqueness`가 세션을 받아
    따로 수행한다 ― `config_resolve_report`가 이 로더를 호출하는데, 그 보고서는
    「DB 질의 0건」이 계약이라(`test_the_report_issues_no_database_queries`) 로더가
    세션을 잡으면 그 계약이 깨진다.

    파일 **부재**는 거부가 아니다(선언이 없을 뿐) ― 수집기에 남기지 않는다.
    """
    rules_path = path or VIRTUAL_JOIN_RULES_PATH
    if not os.path.exists(rules_path):
        return []
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            raw_config = json.load(f)
    except Exception as e:
        logger.error("Failed to load virtual join rules from %s: %s", rules_path, e)
        _record(rejections, "file", None,
                f"virtual_join_rules.json could not be read ({e.__class__.__name__}) ― "
                f"NO virtual join is in effect")
        return []
    return validate_virtual_join_rules(raw_config, known_tables=known_tables,
                                       rejections=rejections)


# ---------------------------------------------------------------------------
# ② 라이브 유일성 검증 ― 세션이 있을 때만
# ---------------------------------------------------------------------------

def _dialect_of(db) -> str:
    try:
        return db.get_bind().dialect.name
    except Exception:
        return ""


def unique_index_covering(db, table: str, columns: list):
    """조인 키를 덮는 **UNIQUE 인덱스**의 이름. 없으면 None.

    부분집합이면 충분하다: `(a)`에 UNIQUE가 있으면 `(a,b)`로도 당연히 유일하다.

    세 가지를 명시적으로 배제한다 ― 셋 다 「UNIQUE 인덱스가 있다」로 읽히지만
    유일성을 보장하지 않는다:
      `indisvalid=false`  취소된 CREATE INDEX CONCURRENTLY의 잔해. 플래너는 영원히
                          쓰지 않고 제약도 강제되지 않는다.
      `indpred IS NOT NULL` 부분 인덱스. 술어 안에서만 유일하므로 전체 유일성이 아니다.
      `indexprs IS NOT NULL` 표현식 인덱스. 컬럼이 아니라 식에 대한 유일성이다.

    PostgreSQL이 아니면 **None을 돌려준다**(모른다). 이것은 안전한 방향의 무지다 ―
    영구 보장 등급을 못 받으면 프로브가 대신 판정하고, 프로브도 못 하면 거부다.
    """
    from sqlalchemy import text
    if not columns:
        return None
    if _dialect_of(db) != "postgresql":
        return None
    rows = db.execute(text("""
        SELECT i.relname AS idx, array_agg(a.attname::text) AS cols
        FROM pg_index x
        JOIN pg_class c ON c.oid = x.indrelid
        JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(x.indkey)
        WHERE c.relname = :t AND n.nspname = 'public'
          AND x.indisunique AND x.indisvalid
          AND x.indpred IS NULL AND x.indexprs IS NULL
        GROUP BY i.relname
    """), {"t": table}).fetchall()
    target = set(columns)
    for idx, cols in rows:
        if set(cols) <= target:
            return idx
    return None


def probe_duplicate(db, table: str, columns: list, budget_ms: int = None) -> dict:
    """오른쪽 테이블이 조인 키로 유일한가. 반환:
    `{"status": "clean"|"duplicate"|"incomplete", "sample": tuple|None}`

    질문을 **존재 질문**으로 던진다(`GROUP BY … HAVING count(*)>1 LIMIT 1`). 중복이
    있으면 첫 중복에서 멈추므로 싸다(실측 1.0~351ms). 없으면 전수 스캔이라 비싸다
    (실측 859행/ms → 1,000만 행 약 11.6초) ― 그래서 예산이 붙고, 예산이 다하면
    `incomplete`다. **`incomplete`는 `clean`이 아니다**: 증명하지 못한 것을 통과시키면
    이 가드가 존재하는 이유가 사라진다.

    SAVEPOINT 안에서 돈다. PostgreSQL에서 실패한 문장은 트랜잭션 전체를 abort시키고
    이후 모든 질의가 죽는데, `COMMIT`이 정상 반환하면서 서버는 ROLLBACK으로 바꾼다 ―
    타임아웃을 그냥 catch하면 세션이 이미 죽은 채로 호출자에게 돌아간다
    (`enrichment_config._isolated_execute`가 같은 이유로 SAVEPOINT를 쓴다).
    """
    from sqlalchemy import func, text
    from database import models

    budget = DEFAULT_PROBE_BUDGET_MS if budget_ms is None else int(budget_ms)
    budget = max(1, min(budget, MAX_PROBE_BUDGET_MS))

    model = models.DYNAMIC_TABLES.get(table)
    if model is None:
        return {"status": "incomplete", "sample": None,
                "detail": f"table model '{table}' is not initialized"}
    try:
        cols = [getattr(model, c) for c in columns]
    except AttributeError as e:
        return {"status": "incomplete", "sample": None, "detail": str(e)}

    nested = db.begin_nested()
    try:
        # 예산은 PostgreSQL에서만 강제된다. sqlite에는 문장 타임아웃이 없고, 이 경로를
        # 타는 sqlite는 테스트 픽스처뿐이라 예산이 의미를 갖는 크기가 아니다.
        # `budget`은 이 파일이 만든 정수라 SQL 텍스트에 넣어도 호출자 문자열이 아니다.
        if _dialect_of(db) == "postgresql":
            db.execute(text(f"SET LOCAL statement_timeout = {budget}"))
        row = (db.query(*cols)
                 .group_by(*cols)
                 .having(func.count() > 1)
                 .limit(1)
                 .first())
        nested.commit()
        if row is None:
            return {"status": "clean", "sample": None}
        return {"status": "duplicate", "sample": tuple(row)}
    except Exception as e:
        try:
            nested.rollback()
        except Exception:
            pass
        # 예산 소진도, 그 밖의 실패도 「증명하지 못했다」로 같다 ― 다른 이름을 주면
        # 둘 중 하나가 통과로 읽힐 자리가 생긴다.
        logger.warning("[VirtualJoin] uniqueness probe on %s(%s) did not complete: %s",
                       table, ", ".join(columns), e.__class__.__name__)
        return {"status": "incomplete", "sample": None,
                "detail": f"{e.__class__.__name__}"}


def verify_uniqueness(db, rule: dict, budget_ms: int = None) -> dict:
    """선언 1건의 ② 라이브 유일성. 반환은 `rule`에 병합할 수 있는 dict.

    `{"uniqueness_evidence": ..., "uniqueness_detail": ..., "refused": bool,
      "code": ...|None}`

    등급 판정 순서가 곧 증거의 세기 순서다: UNIQUE 인덱스(영구) → 프로브 완주(스냅샷)
    → 증명 실패(거부). **거부는 두 가지뿐이고 둘 다 통과가 아니다** ― 중복을 찾았거나,
    중복이 없음을 예산 안에 증명하지 못했거나.
    """
    table = rule["right_table"]
    columns = rule["right_columns"]

    idx = unique_index_covering(db, table, columns)
    if idx:
        return {"uniqueness_evidence": EVIDENCE_UNIQUE_INDEX,
                "uniqueness_detail": idx, "refused": False, "code": None}

    probe = probe_duplicate(db, table, columns, budget_ms=budget_ms)
    if probe["status"] == "clean":
        return {"uniqueness_evidence": EVIDENCE_PROBE_CLEAN,
                "uniqueness_detail": None, "refused": False, "code": None}
    if probe["status"] == "duplicate":
        return {"uniqueness_evidence": EVIDENCE_UNVERIFIED,
                "uniqueness_detail": probe.get("sample"),
                "refused": True, "code": CODE_DUPLICATE_FOUND}
    return {"uniqueness_evidence": EVIDENCE_UNVERIFIED,
            "uniqueness_detail": probe.get("detail"),
            "refused": True, "code": CODE_PROBE_INCOMPLETE}


def load_verified_rules(db, path: str = None, known_tables: dict = None,
                        budget_ms: int = None, rejections: list = None) -> list:
    """①+② 둘 다 통과한 선언만. **조인을 실행하는 코드가 써야 하는 진입점이다.**

    `load_virtual_join_rules`(①만)를 직접 소비하면 `bonding_map` 같은 테이블이
    통과한다 ― 선언 키 `(base,x,y)`로 ①은 통과하지만 실제 중복 그룹이 2,312개다.
    """
    rules = load_virtual_join_rules(path=path, known_tables=known_tables,
                                    rejections=rejections)
    verified = []
    for rule in rules:
        result = verify_uniqueness(db, rule, budget_ms=budget_ms)
        if result["refused"]:
            detail = (f"right table '{rule['right_table']}' is not unique on the join "
                      f"key ({', '.join(rule['right_columns'])})")
            if result["code"] == CODE_PROBE_INCOMPLETE:
                detail = (f"uniqueness of '{rule['right_table']}' on the join key "
                          f"({', '.join(rule['right_columns'])}) could not be proven "
                          f"within the probe budget")
            logger.warning("[VirtualJoin:%s] rejected by live check: %s",
                           rule["name"], detail)
            _record(rejections, "rule", rule["name"], detail, code=result["code"])
            continue
        rule = dict(rule)
        rule["uniqueness_evidence"] = result["uniqueness_evidence"]
        rule["uniqueness_detail"] = result["uniqueness_detail"]
        verified.append(rule)
    return verified
