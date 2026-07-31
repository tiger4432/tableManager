"""Virtual join 선언 로더/검증기 ― **UNIQUE 인덱스가 없으면 거부한다.**

[무엇인가] Virtual join은 두 테이블을 **저장하지 않고 조회 시점에** 잇는다.
`/api/maps/overlay`가 좌표로 하는 일을 행(row) 모양으로 하는 것이고, 잇는 기준은
좌표가 아니라 선언된 조인 키다. 이 파일은 그 **선언**만 다룬다 ― 조인 실행은 여기 없다.

[왜 가드가 먼저인가 ― 실측 2026-07-31, 운영 DB read-only]
    core_defect_map ⋈ eds_fail_map (lot,slot,x,y)   103,040 →     103,040   x1
    core_defect_map ⋈ eds_fail_map (lot,slot)       103,040 → 132,715,520   x1288
    bonding_log     ⋈ wafer_process (lot,slot)       14,436 →   2,552,624   x177

**오른쪽 테이블이 조인 키로 유일하지 않으면 왼쪽 행 하나가 맞는 행 수만큼 불어난다.**
두 선언은 컬럼 두 개 차이인데 결과는 10만 행과 1억 3천만 행이다. 문법도 맞고 컬럼도
존재하므로, 선언을 읽는 시점에 거부하지 않으면 거부할 자리가 없다.

[유일성의 근거는 하나다 ― UNIQUE 인덱스 (사용자 확정 2026-07-31)]
    「인덱스 없으면 거절해」 · 「유니크 INDEX 걸면 그냥 DB 영속 아닌가」

    그 지적이 설계를 바꿨다. UNIQUE 인덱스는 **이미 영속**이다 ― config가 아니라
    데이터베이스에 살고, 이후의 어떤 쓰기도 그 성질을 깰 수 없다. `pg_index`를 읽는 것은
    정책 노브가 아니라 **살아 있는 사실의 조회**다. 그래서 등급도, 스냅샷도, 예산도 없다:
    조인 키를 덮는 UNIQUE 인덱스가 있으면 통과, 없으면 거부. 그것이 전부다.

    거부는 운영자에게 **할 일을 준다** ― `required_index_ddl`이 만들어야 할 인덱스의
    DDL 문장을 그대로 돌려준다. 「UNIQUE 인덱스가 없다」만 말하고 어느 컬럼인지 말하지
    않는 거부는 운영자가 행동할 수 없는 거부다.

[왜 중복 프로브를 두지 않는가 ― 만들기 전에 이미 있는지 본다]
직전 판(2026-07-31 오전)에는 `GROUP BY … HAVING count(*)>1` 프로브가 있었다. 예산
(`statement_timeout`)과 `incomplete` 상태가 딸려 있었는데, 그것들은 **전수 스캔을 게이트로
쓰기 위한** 장치였다(실측 859행/ms → 1,000만 행 약 11.6초). 게이트가 UNIQUE 인덱스로
바뀌면서 그 장치는 소비자가 없어졌고, **아무도 보지 않는 안전장치는 없느니만 못하다** ―
다음 읽는 사람이 무언가 검사되고 있다고 가정하기 때문이다.

중복 진단 자체를 잃는 것도 아니다. 운영자가 거부를 받고 인덱스를 만들려 하면
**PostgreSQL이 같은 진단을 더 정확하게, 행동하는 바로 그 순간에** 내놓는다:

    ERROR:  could not create unique index "uq_vjoin_..."
    DETAIL:  Key (lot, slot)=(LOT-A, 01) is duplicated.

이쪽이 중복된 키 값까지 지목하고, 스냅샷이 아니라 그 순간의 진실이며, 우리 판정과
데이터베이스가 어긋날 여지가 없다. 같은 연산이 이미 있는데 열등한 사본을 두지 않는다.

[세 가지 인덱스를 명시적으로 배제한다 ― 판정이 이것 위에 서 있다]
  `indisvalid = false`   취소된 CREATE INDEX CONCURRENTLY의 잔해. 플래너는 영원히 쓰지
                         않고 제약도 강제되지 않는다. `to_regclass`로는 잘 풀린다.
  `indpred IS NOT NULL`  부분 인덱스. 술어 안에서만 유일하므로 전체 유일성이 아니다.
  `indexprs IS NOT NULL` 표현식 인덱스. 컬럼이 아니라 식에 대한 유일성이다.
셋 다 「UNIQUE 인덱스가 있다」로 읽히지만 유일성을 보장하지 않는다.

[왼쪽의 중복은 팬아웃이 아니다 ― 그것이 이 기능의 목적이다]
검사는 **오른쪽에만** 적용된다. 사용자 시나리오 `dt_log → core_wafer_map
(core_lot, core_slot)`는 왼쪽이 키당 128행이고 오른쪽이 키당 1행이라 768행 → 768행(x1.00)
이다. 왼쪽이 같은 키를 여러 번 갖는 것은 정상이며 ― 로그 여러 줄이 같은 웨이퍼를 가리키는
것이 곧 조인의 용도다 ― 이 가드가 그것을 잡으면 기능 자체를 잡는 것이다.

[미상(未詳)의 정의 ― 경계 계약]
조인 결과에서 `미상`은 **두 경우를 모두 덮는다**:
  ① 오른쪽에 맞는 행이 아예 없다(no right row).
  ② 맞는 행은 있는데 그 값이 비어 있다(matched but NULL/빈 문자열).
LEFT 조인만으로는 ②가 보이지 않는다. 실측(2026-07-31)이 그 이유다 ―
`bonding_log → core_wafer_map.wafer_id`는 14,436행 **전부**가 오른쪽 행을 찾지만
3,792행(26.27%)의 `wafer_id`가 비어 있고, `core_defect_map → core_wafer_map.wafer_id`는
103,040행 전부가 행을 찾지만 88,872행(86.25%)이 비어 있다. ②를 `미상`에서 빼면
분석가는 「값이 있다」고 읽는다. INNER 조인은 ①을 조용히 지우므로 금지다.

[이름 충돌의 정의 ― 경계 계약, 사용자 확정 2026-07-31]
expose 컬럼 이름이 **왼쪽에 이미 있어도 된다**(운영 `dt_log`가 lot/slot 대신 `wafer_id`를
직접 실어 오는 행을 섞어 두기 때문이다). 합치는 규칙은 하나다 ― **부재일 때만 채운다**:
    왼쪽 값 있음  → 왼쪽 값을 **그대로 둔다**(조인 값은 버린다)
    왼쪽 값 비었음 → 조인 값을 쓴다
    둘 다 없음    → `unresolved_label`
"비었음"의 정의는 `crud.clean_str_value(v) == ""`로, 시스템의 나머지와 **같은 것을 뜻해야
한다**(꼬리 공백이 여기서는 값이고 저기서는 공백이면 안 된다). 이 연산은
`enrichment_candidates`의 absent-only 관문과 **구조적으로 같다** ― 같은 어휘를 쓴다.

여기서 `2026-07-31 이전의 shadow 거부`가 사라졌다. 그 거부의 근거("어느 쪽 값을 보고
있는지 알 수 없는 표")는 absent-only 하나로는 해소되지 않는다 ― 합쳐진 컬럼은 셀마다
출처가 달라지기 때문이다. 그래서 실행기가 **셀 단위 provenance**(`sources`에
`virtual_join`)를 함께 싣는 것이 이 완화의 조건이며, 그것 없이 이 검사만 빼면 원래의
걱정이 그대로 돌아온다. 정규화된 선언은 `collide`(왼쪽에도 있는 것) / `virtual_only`
(조인만이 만들어 내는 것)로 그 둘을 갈라 실어 보낸다.

[이 파일이 보장하는 것]
`load_verified_rules`가 돌려준 선언은 **오른쪽이 조인 키로 유일함이 데이터베이스에 의해
강제된다.** 스냅샷이 아니라 제약이므로 이후의 쓰기가 깰 수 없다. 세션 없이 부르는
`load_virtual_join_rules`는 **모양만** 검증하며 아무것도 승인하지 않는다.
"""
import hashlib
import json
import logging
import os
import re

logger = logging.getLogger("VirtualJoinConfig")

from paths import CONFIG_DIR  # single override point (ASSY_DATA_ROOT)

VIRTUAL_JOIN_RULES_PATH = os.path.join(CONFIG_DIR, "virtual_join_rules.json")

# 식별자 형태 강제. 이름은 table_config에서 오지만 인덱스 DDL 문장에 보간되므로
# 검증이 조립보다 먼저 온다(enrichment_config._CANDIDATE_COLUMN_RE와 같은 자세).
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# --- 거부 코드 (내부 어휘 ― config_resolve_report가 닫힌 사유로 사상한다) ---
CODE_NO_UNIQUE_INDEX = "no_unique_index"     # 유일성을 강제하는 인덱스가 없다
CODE_FANOUT_DECLARED = "fanout_declared"     # 집계 형태는 아직 구현이 없다
CODE_SHAPE = "shape"                         # 평범한 문법/존재 오류

# 인덱스 이름 규약. PostgreSQL 식별자 상한은 63바이트라 넘치면 해시로 접는다
# (`value_suggest.suggest_index_name`과 같은 규율·같은 상한).
INDEX_PREFIX = "uq_vjoin_"
_MAX_IDENTIFIER = 63

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
    보고서가 「인덱스가 없어 거부」와 「컬럼 오타라 거부」에 **다른 한국어 문장**을 붙이는
    데만 쓴다. 어휘로의 사상은 여전히 보고서 계층의 책임이다.

    `facts`는 **문장이 아니라 사실**이다(테이블명·컬럼 목록·DDL). 로더의 `detail`은 영어
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


# ---------------------------------------------------------------------------
# 운영자가 만들어야 하는 인덱스
# ---------------------------------------------------------------------------

def required_index_name(table: str, columns: list) -> str:
    """조인 키를 덮는 UNIQUE 인덱스의 권장 이름(63바이트 이내)."""
    base = "%s%s_%s" % (INDEX_PREFIX, table, "_".join(columns))
    if len(base.encode("utf-8")) <= _MAX_IDENTIFIER:
        return base
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    keep = _MAX_IDENTIFIER - len(INDEX_PREFIX) - len(digest) - 1
    return "%s%s_%s" % (INDEX_PREFIX, ("%s_%s" % (table, "_".join(columns)))[:keep], digest)


def required_index_ddl(table: str, columns: list) -> str:
    """운영자가 그대로 실행할 수 있는 DDL 한 줄.

    `CONCURRENTLY`인 이유: 운영 테이블에 쓰기를 잠그지 않기 위해서다. 대가는 이 문장이
    트랜잭션 블록 안에서 돌 수 없다는 것이고(psql에서 손으로 실행하는 형태라 문제가 아니다),
    **취소되면 INVALID 인덱스가 남는다**는 것이다 ― 그래서 `unique_index_covering`이
    `indisvalid`를 검사한다. 취소했으면 지우고 다시 만들어야 판정이 인정한다.
    """
    return 'CREATE UNIQUE INDEX CONCURRENTLY %s ON "%s" (%s);' % (
        required_index_name(table, columns), table,
        ", ".join('"%s"' % c for c in columns))


# ---------------------------------------------------------------------------
# 선언 검증 (모양만 ― DB 접근 0회)
# ---------------------------------------------------------------------------

def _validate_join(name: str, raw: dict, known_tables: dict, rejections: list = None) -> tuple:
    """선언 1건의 **모양**을 검증·정규화한다.

    반환: `(normalized|None, 실패사유|None, code|None, facts|None)`.
    유일성은 여기서 판정하지 않는다 ― 그것은 `pg_index`가 아는 사실이고 세션이 필요하다.
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
    for label, t in (("left_table", left_table), ("right_table", right_table)):
        if not _IDENT_RE.match(t):
            return None, (f"'{label}' must be a plain table identifier "
                          f"([A-Za-z_][A-Za-z0-9_]*)"), CODE_SHAPE, None

    # 집계 형태는 **아직 구현되지 않았다.** 여기서 조용히 허용하면 유일성 요구를 끄는
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
            # 성분은 하나다. 인덱스 이름·DDL도 그 중복을 그대로 실어 나른다.
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

    # 왼쪽에도 같은 이름이 있는 expose 컬럼. `known_tables` 없이 부르면 **알 수 없다**
    # ― 그때는 빈 목록이 아니라 `None`이라 실행기가 "충돌 없음"으로 오독할 수 없다.
    # (실행기의 유일한 입구인 `load_verified_rules`는 항상 table_config를 받는다.)
    collide = None

    # --- 테이블/컬럼 존재 검증 (table_config가 주어진 경우에만) ---
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
        # 이름 충돌은 **정상이며 기대되는 경우**다(사용자 확정 2026-07-31). 운영
        # `dt_log`는 lot/slot 대신 `wafer_id`를 직접 실어 오는 행이 섞여 있어서, 조인이
        # 채우려는 바로 그 컬럼이 왼쪽에 이미 있다.
        #
        # 이 자리에는 「왼쪽에 같은 이름이 있으면 거부」가 있었다. 근거는 "어느 쪽 값을
        # 보고 있는지 알 수 없는 표가 만들어진다"였고 그 걱정 자체는 옳았다 ― 다만
        # 거부가 그 답이 아니다. 답은 두 개이고 **둘 다 갖춘 뒤에** 이 검사를 뺐다:
        #   ① **부재일 때만 채운다**(absent-only). 왼쪽 값이 있으면 손대지 않으므로
        #      기존 값이 조인 값으로 바뀌는 일이 없다. `enrichment_candidates`의
        #      absent-only 관문과 **구조적으로 같은 연산**이라 같은 어휘를 쓴다.
        #   ② **셀마다 출처를 싣는다.** 합쳐진 컬럼의 각 셀이 `sources`에
        #      `virtual_join`을 달고 오므로 "어느 쪽 값인가"를 셀 단위로 읽을 수 있다.
        #      기존 셀 소스 표시가 그대로 보여 준다(새 UI 없음).
        # 그래서 `collide`는 오류가 아니라 **실행기가 알아야 하는 사실**로 내려간다.
        collide = [c for c in expose if c in left_cols]

    normalized = {
        "name": name,
        "left_table": left_table,
        "right_table": right_table,
        "join_key": join_key,
        "left_columns": [p["left"] for p in join_key],
        "right_columns": right_join_cols,
        "expose": expose,
        # expose 중 왼쪽에도 같은 이름이 있는 것들(absent-only로 합쳐질 컬럼) /
        # 왼쪽에 없어 조인만이 만들어 내는 것들. 실행기가 이 둘을 다르게 다루고,
        # **쓰기 거부는 `virtual_only`에만 건다** ― `collide` 쪽은 실재하는 저장
        # 컬럼이라 편집이 정상이고, 그 편집이 곧 absent-only 규칙의 "왼쪽 값 있음"이다.
        "collide": collide,
        "virtual_only": None if collide is None else [c for c in expose if c not in collide],
        "unresolved_label": label,
        "join_cardinality": "one",
        # 운영자가 만들어야 하는 인덱스. 선언만으로 계산되므로 세션 없이도 말할 수 있고,
        # 그래서 DB를 못 보는 해석 보고서도 「무엇을 만들면 되는지」를 말할 수 있다.
        "required_index": required_index_name(right_table, right_join_cols),
        "required_index_ddl": required_index_ddl(right_table, right_join_cols),
    }
    return normalized, None, None, None


def validate_virtual_join_rules(raw_config, known_tables: dict = None,
                                rejections: list = None) -> list:
    """선언 dict 전체의 **모양**을 검증한다. 무효 선언은 목록에서 제외된다."""
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
    """virtual_join_rules.json을 읽어 **모양이 유효한** 선언을 반환(파일 없음 → 빈 목록).

    🔴 **이 함수가 돌려준 선언은 승인된 것이 아니다.** 유일성은 `pg_index`가 아는
    사실이라 세션이 필요하고, 승인 경로는 `load_verified_rules` 하나뿐이다. 이 함수가
    따로 있는 이유는 `config_resolve_report`가 「DB 질의 0건」 계약을 갖기 때문이다
    (`test_the_report_issues_no_database_queries`).

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
# 유일성 ― 카탈로그 조회 하나가 전부다
# ---------------------------------------------------------------------------

def _dialect_of(db) -> str:
    try:
        return db.get_bind().dialect.name
    except Exception:
        return ""


def unique_index_covering(db, table: str, columns: list):
    """조인 키를 덮는 **UNIQUE 인덱스**의 이름. 없으면 None.

    부분집합이면 충분하다: `(a)`에 UNIQUE가 있으면 `(a,b)`로도 당연히 유일하다.

    행을 세지 않는다 ― `pg_index`만 읽는다. 그래서 1,000만 행 테이블에서도 비용이
    테이블 크기와 무관하고, 답이 스냅샷이 아니라 **제약의 존재**다.

    배제 셋(`indisvalid`/`indpred`/`indexprs`)의 이유는 모듈 상단에 있다.

    PostgreSQL이 아니면 **None을 돌려준다**(모른다). 안전한 방향의 무지다 ― 모르면 거부다.
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


def verify_uniqueness(db, rule: dict) -> dict:
    """선언 1건의 유일성 판정. 반환:
    `{"unique_index": 이름|None, "refused": bool, "code": ...|None}`

    통과 조건은 하나다 ― 조인 키를 덮는 유효한 UNIQUE 인덱스의 존재.
    """
    idx = unique_index_covering(db, rule["right_table"], rule["right_columns"])
    if idx:
        return {"unique_index": idx, "refused": False, "code": None}
    return {"unique_index": None, "refused": True, "code": CODE_NO_UNIQUE_INDEX}


def load_verified_rules(db, path: str = None, known_tables: dict = None,
                        rejections: list = None) -> list:
    """모양 + 유일성 **둘 다** 통과한 선언만. **조인을 실행하는 코드의 유일한 진입점.**

    `load_virtual_join_rules`(모양만)를 직접 소비하면 유일성이 검사되지 않은 선언이
    그대로 실행된다 ― 그 차이가 1억 3천만 행이다.
    """
    rules = load_virtual_join_rules(path=path, known_tables=known_tables,
                                    rejections=rejections)
    verified = []
    for rule in rules:
        result = verify_uniqueness(db, rule)
        if result["refused"]:
            logger.warning("[VirtualJoin:%s] rejected: no unique index covers %s(%s)",
                           rule["name"], rule["right_table"],
                           ", ".join(rule["right_columns"]))
            _record(rejections, "rule", rule["name"],
                    f"no valid UNIQUE index covers "
                    f"{rule['right_table']}({', '.join(rule['right_columns'])})",
                    code=CODE_NO_UNIQUE_INDEX,
                    facts={"right_table": rule["right_table"],
                           "join_key": list(rule["right_columns"]),
                           "required_index": rule["required_index"],
                           "required_index_ddl": rule["required_index_ddl"]})
            continue
        rule = dict(rule)
        rule["unique_index"] = result["unique_index"]
        verified.append(rule)
    return verified


def verification_report(db, path: str = None, known_tables: dict = None) -> dict:
    """선언별 「승인됐는가 · 아니면 무엇을 만들어야 하는가」. 라우트가 쓰는 형태.

    카탈로그 조회 하나라 요청 경로에 앉아도 된다(행을 세지 않으므로 비용이 테이블
    크기와 무관하다 ― 프로브를 라우트에 앉힐 수 없었던 이유가 정확히 그것이었다).

    쓰는 이가 읽을 **한국어 문장**은 `config_resolve_report.virtual_join_detail`이 짓는다
    ― 보고서와 이 라우트가 같은 거부에 다른 문장을 내면 「서버가 문장의 정본」이라는
    계약이 깨진다. 로더가 한국어를 짓지 않는 것도 같은 규율이다(사상은 보고서 계층).
    """
    import config_resolve_report as crr

    rejections = []
    rules = load_virtual_join_rules(path=path, known_tables=known_tables,
                                    rejections=rejections)
    out = []
    for rule in rules:
        result = verify_uniqueness(db, rule)
        facts = {"right_table": rule["right_table"],
                 "join_key": list(rule["right_columns"]),
                 "required_index": rule["required_index"],
                 "required_index_ddl": rule["required_index_ddl"]}
        out.append({
            "name": rule["name"],
            "left_table": rule["left_table"],
            "right_table": rule["right_table"],
            "join_key": [f"{p['left']} = {p['right']}" for p in rule["join_key"]],
            "expose": list(rule["expose"]),
            "accepted": not result["refused"],
            "unique_index": result["unique_index"],
            "required_index": rule["required_index"],
            "required_index_ddl": None if result["unique_index"] else rule["required_index_ddl"],
            "detail": (None if not result["refused"] else
                       crr.virtual_join_detail(CODE_NO_UNIQUE_INDEX, facts)),
        })
    return {
        "declarations": out,
        "accepted": sum(1 for d in out if d["accepted"]),
        "refused": sum(1 for d in out if not d["accepted"]),
        "invalid": [{"subject": r.get("subject"),
                     "detail": crr.virtual_join_detail(
                         r.get("code", CODE_SHAPE), r.get("facts"), r["detail"])}
                    for r in rejections],
    }
