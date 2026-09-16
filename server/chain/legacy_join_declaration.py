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
셋 다 「UNIQUE 인덱스가 있다」로 읽히지만 (컬럼에 대한) 유일성을 보장하지 않는다.

⚠️ **2026-08-04 — 세 번째 배제는 조건부가 됐다.** 조인 키에 표기 정규화가 선언되면
(`notation_norm`) 비교가 **접힌 식**으로 이루어지므로, 그때는 컬럼 유일성이 아니라 **식
유일성이 정확히 필요한 것**이다. 방향이 뒤집힌다: 접히는 키에서는 `indexprs IS NOT NULL`
인덱스만 후보가 되고 평범한 인덱스는 배제된다. 이유가 성능이 아니라 **정확성**임에 주의 ―
원본으로 서로 다른 두 행('CL-1', 'CL_1')이 접히면 한 값이므로, 컬럼에 UNIQUE가 있어도
접힌 키로는 중복이고 그 중복이 곧 팬아웃이다. `indpred`와 `indisvalid` 배제는 그대로다.

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

from verified_join_contract import (
    VerifiedJoinDescriptor,
    _bind_physical_verifier_issuer,
)

_VERIFIED_JOIN_ISSUER = _bind_physical_verifier_issuer()

logger = logging.getLogger("VirtualJoinConfig")

from paths import CONFIG_DIR  # single override point (ASSY_DATA_ROOT)

VIRTUAL_JOIN_RULES_PATH = os.path.join(CONFIG_DIR, "virtual_join_rules.json")

# 식별자 형태 강제. 이름은 table_config에서 오지만 인덱스 DDL 문장에 보간되므로
# 검증이 조립보다 먼저 온다(enrichment_config._CANDIDATE_COLUMN_RE와 같은 자세).
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 🔴 [S-283 · 판정 440·442] THE INDEX SEAT LIVES IN `chain.join_key_index` NOW, and these
# names are imported back rather than re-spelled. The definition is single, so the one
# guarantee that matters here holds by construction: the index expression and the query
# expression come from ONE function, and PostgreSQL uses an expression index only when the
# two match. A second spelling would not raise - it would read ten million rows and leave
# every test green.
#
# ⚰️ IT USED TO SAY 「THIS IMPORT IS THE ALIAS STEP 4 DELETES」. Step 4 is this commit, and
# what it deleted was the PACKAGE, not this import: both seats live in `chain` now, so this
# is an ordinary import between neighbours rather than a bridge holding a dismantled package
# together. The names are still taken from one definition, which is the part that mattered.
from chain.join_key_index import (                                  # noqa: F401
    INDEX_PREFIX, _MAX_IDENTIFIER, _folds_list, required_index_name, column_is_text,
    index_key_expression, required_index_ddl, _dialect_of, _INDEX_EXPR_CASTS,
    _REDUNDANT_PARENS_RE, _casefold_outside_literals, normalize_index_expression,
    _index_key_expressions, unique_index_covering)

# --- 거부 코드 (내부 어휘 ― config_resolve_report가 닫힌 사유로 사상한다) ---
# 🪦 [S-211 ①, 판정 355] 코드 다섯과 그 «한국어 문장»이 `virtual_join_refusal` 로 내려갔다.
#    이 모듈이 그것을 읽는 것은 «아래로» 가는 방향이라 고리를 만들지 않는다. 종전에는 이
#    파일이 문장을 지으려고 «보고서»(`config_resolve_report`)를 함수 안에서 import 했고,
#    보고서는 이 파일을 import 했다 — 함수 안에 둬서 «보이지 않던» 고리다.
from chain.join_refusal import (CODE_FANOUT_DECLARED, CODE_NO_LEFT_INDEX,
                               CODE_NO_REWRITE_CAP, CODE_NO_UNIQUE_INDEX,
                               CODE_READ_TIME_RETIRED, CODE_SHAPE,
                               virtual_join_detail)
# 🔴 [판정 481 ③] SHARED WITH THE LEDGER BUNDLE VALIDATOR, which is stdlib-only and
# cannot import `chain.*` - so the sentence is authored one level down (판정 300).
from validation import READ_TIME_RETIRED_DETAIL

# 인덱스 이름 규약. PostgreSQL 식별자 상한은 63바이트라 넘치면 해시로 접는다
# (`value_suggest.suggest_index_name`과 같은 규율·같은 상한).

# 조인 결과에서 해소되지 않은 값이 취하는 표시. 「값이 빔」까지 포함한다(모듈 상단 계약).
DEFAULT_UNRESOLVED_LABEL = "미상"

# 한 선언이 노출할 수 있는 오른쪽 컬럼 수 상한. 조인 하나가 왼쪽 테이블의 폭을
# 통째로 두 배로 만들지 않게 하는 것이 목적이다.
MAX_EXPOSE_COLUMNS = 32



#: 🔴 A STANDING REFUSAL IS NOT NEWS (2026-09-14 outage). The verified-rules cache expires
#: every RULES_CACHE_TTL seconds and every read that misses it re-runs this loader, so a
#: join missing its unique index logged the SAME rejection every few seconds, forever, on
#: the READ path - with no chain rule involved. That is what "I disabled every chain and
#: the errors keep coming" was. The refusal still reaches the operator through the config
#: report and `/admin/config/virtual-join/verify`, which are the places you go to ask;
#: the log says it when it CHANGES.
_REPORTED_REJECTIONS = {}


def _say_once(key, logger_, message, *args):
    """Log `message` only when this key's state is new or different."""
    stamp = message % args if args else message
    if _REPORTED_REJECTIONS.get(key) == stamp:
        return False
    if len(_REPORTED_REJECTIONS) >= 1000:
        _REPORTED_REJECTIONS.clear()
    _REPORTED_REJECTIONS[key] = stamp
    logger_.warning("%s (repeats are silenced until this changes)", stamp)
    return True

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









def rewrite_row_count(connection, rule, key_values) -> int:
    """참조 행 «하나»가 바뀔 때 다시 쓸 대상 행 수 — 쓰기 «전»에 센다 (S-189 ⓐ, 판정 302).

    🔴 세는 것이 «먼저»인 이유는 이 제품의 핵심 제약이 변경 비용이기 때문이다. 소급 등록부가
    이미 같은 자세를 갖고 있고(`retroactive` 의 사전 세기), 그 씨앗을 그대로 쓴다.

    🔴 접기는 «조인과 같은 철자»다. `index_key_expression` 은 인덱스 DDL 과 실행기가 이미
    지나는 함수이고, 세는 질의가 다르게 접으면 「세었을 때 3 행, 썼을 때 5 행」이 된다 —
    그리고 그 차이는 상한을 조용히 넘긴다.
    """
    from sqlalchemy import text

    left_columns = [p["left"] for p in rule["join_key"]]
    folds = _folds_list(rule["right_columns"], rule.get("right_folds"))
    where = " AND ".join(
        "%s = :k%d" % (index_key_expression(col, fold, rule["left_table"]), i)
        for i, (col, fold) in enumerate(zip(left_columns, folds)))
    # 🔴 THE VALUE IS FOLDED TOO, AND MEASURING CAUGHT THIS. The expression folds the
    # COLUMN (`coalesce(col,'')`), so binding a raw `None` compares `'' = NULL` -> NULL and
    # the count came back ZERO for a key this box has 70,800 rows of. Folding one side only
    # is the exact defect S-181 was about, and `fold_key_value` is its one spelling
    # (판정 285: 키를 견주는 자리에서 NULL = NULL).
    from database.crud import fold_key_value

    # ⚠️ TWO FOLDS, TWO DOMAINS, AND THE MAPPING IS SPELLED OUT HERE BECAUSE MEASURING
    # CAUGHT IT. `fold_key_value` is the authority on blankness and answers `None` for an
    # absent key part; `index_key_expression` folds the COLUMN to `coalesce(col, '')` and so
    # answers `''`. Binding the first into the second compares `'' = NULL` -> NULL, and the
    # count came back ZERO for the key this box has 70,800 rows of. Neither fold is wrong —
    # they are halves of a pair written for an INDEX, where both sides pass through the same
    # SQL. Crossing the boundary is what needs saying.
    def _bound(col, value):
        folded = fold_key_value(rule["left_table"], col, value)
        return "" if folded is None else folded

    params = {("k%d" % i): _bound(col, value)
              for i, (col, value) in enumerate(zip(left_columns, key_values))}
    sql = 'SELECT count(*) FROM "%s" WHERE %s' % (rule["left_table"], where)
    return int(connection.execute(text(sql), params).scalar() or 0)


def rewrite_refusal(rule, counted):
    """상한을 넘었을 때의 «거절문», 아니면 None.

    ⛔ 넘으면 «거절»이지 «잘라 쓰기»가 아니다(판정 302). 상한까지만 쓰고 마는 것은 대상 표를
    「일부는 새 값, 일부는 옛 값」으로 남기는 것이고, 그 상태는 어느 행이 어느 쪽인지 말해
    주지 않는다 — 화면에서 «조용히 틀린 답»이 된다.
    """
    cap = rule.get("max_rewrite_rows")
    if not rule.get("materialize") or not cap or counted <= cap:
        return None
    return ("this change rewrites %d rows of '%s' and the rule's declared ceiling is %d. "
            "Refused whole rather than written to the ceiling: a half-written join layer "
            "leaves the table part new and part old with nothing saying which. Raise "
            "'max_rewrite_rows' if %d is a cost you accept."
            % (counted, rule["left_table"], cap, counted))


def required_left_index_name(table: str, columns: list) -> str:
    """실체화가 요구하는 «왼쪽» 색인의 이름 (S-189 ⓐ).

    🔴 여기에는 UNIQUE 가 «없습니다», 그리고 그것이 이 함수가 오른쪽 것과 따로 있는 이유
    전부입니다. 오른쪽 키는 유일해야 하고(그것이 승인 조건입니다), 왼쪽 키는 «유일하지 않은
    것이 정상»입니다 — 이 박스에서 `dt_log` 의 한 `dt_job` 이 «70,800 행»입니다. 그 수가 곧
    팬아웃이고, 그래서 오른쪽 DDL 을 왼쪽에 쓰면 «만들 수 없는 색인»을 시키는 것이 됩니다.
    """
    return "ix_mjoin_%s__%s" % (table, "_".join(columns))


def required_left_index_ddl(table: str, columns: list) -> str:
    """운영자가 그대로 실행할 수 있는 왼쪽 색인 DDL 한 줄.

    ⚠️ 오른쪽 색인은 «읽기 시점 조인»이 쓰고, 이것은 «참조 행이 바뀔 때 대상 행을 찾는»
    질의가 씁니다. 실측(S-189 설계): 오른쪽은 `required_index_ddl` 이 «요구»하지만 왼쪽은
    오늘 «아무것도 요구하지 않습니다» — 이 박스에 우연히 있을 뿐이고, 우연은 계약이 아닙니다.

    `CONCURRENTLY` 이유는 오른쪽과 같습니다(운영 표에 쓰기를 잠그지 않기).
    """
    return 'CREATE INDEX CONCURRENTLY %s ON "%s" (%s);' % (
        required_left_index_name(table, columns), table,
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

    # ------------------------------------------------------------------ S-189 ⓐ
    # 🔴 실체화는 «쓰기»이고, 이 제품의 핵심 제약은 «변경 비용»이다. 참조 행 하나가 바뀌면
    # 그 키를 가진 대상 행이 «전부» 다시 써진다 — 이 박스 실측으로 `dt_log` 최대 «70,800 행»,
    # 소유자 IO 규격(≤1.3 s/1k)으로 환산하면 한 번의 편집이 ≈92 s 다.
    #
    # ⛔ 그래서 상한에 «기본값이 없다»(판정 302). 제품이 숫자를 고르면 그 숫자는 «아무도 안 본
    # 숫자»가 되고, 92 초가 조용히 도는 것을 제품이 «허락»한 것이 된다. `occurred_at_basis` 와
    # 같은 자세다 — 선언 가능한 것은 선언하게 하고, 없으면 이름 대어 거절한다.
    # ------------------------------------------------------------------ S-283
    # 🔴 `materialize: false` 는 «읽는 시점»에 조인해서 값을 만들어 내보내던 선언이고,
    # 그 기제는 은퇴했다(판정 461). 조용히 떨어뜨리지 «않는다» — 조용히 떨어지면 운영자
    # 화면에서 「선언은 있는데 컬럼이 없다」가 되고, 그것이 「없다」와 같은 모양이다.
    # 이름을 대어 거부하고, 다음 행동을 같이 적는다.
    materialize = raw.get("materialize", False)
    if materialize is False:
        # 🔴 [판정 481 ③] THE SENTENCE IS IMPORTED, NOT WRITTEN HERE. The ledger bundle
        # validator refuses the same declaration and must say the same thing; two copies
        # drift into two repairs (판정 474).
        return None, READ_TIME_RETIRED_DETAIL, CODE_READ_TIME_RETIRED, None

    if materialize is not True:
        return None, ("'materialize' must be true or false, not "
                      + json.dumps(materialize, ensure_ascii=False)), CODE_SHAPE, None
    cap = raw.get("max_rewrite_rows")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0:
        return None, (
            "'materialize' is on and 'max_rewrite_rows' is not declared. A change to "
            "ONE referenced row rewrites every target row carrying that join key, and "
            "this product says what a change costs before making it - so the ceiling "
            "is yours to write, not the product's to guess. Count it first: "
            "SELECT max(k) FROM (SELECT count(*) k FROM <left_table> GROUP BY "
            "<join key>) s"), CODE_NO_REWRITE_CAP, None

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

    # --- 표기 정규화: 이 비교를 접어야 하는가 (양쪽 다, 아니면 아무 쪽도) ---
    # 🔴 한쪽만 접는 코드 경로는 존재하지 않는다. `join_pair_rules`가 「어느 한쪽이라도
    # 선언됐으면 양쪽」을 결정하고, 그 결과 하나가 ON 절·인덱스 DDL·게이트에 **똑같이**
    # 실린다. 실측(2026-08-04)이 그 이유다 ― `dt_log.core_lot`은 병합군 15개,
    # `core_wafer_map.core_lot`은 0개라, 깨끗한 쪽에 선언할 이유가 있는 운영자는 없다.
    # 그런데 한쪽만 접은 조인은 도움이 안 되는 정도가 아니라 **이미 맞고 있던 매치를
    # 조용히 잃는다**.
    try:
        import notation_norm
        for pair in join_key:
            pair["fold"] = notation_norm.join_pair_rules(
                left_table, pair["left"], right_table, pair["right"])
    except Exception as e:
        # 선언을 읽지 못하면 **접지 않는다** ― 이 기능이 없던 때의 동작이고, 안전한
        # 방향이다(접지 않은 비교는 덜 합쳐질 뿐, 없던 매치를 만들지 않는다).
        logger.error("[VirtualJoin:%s] notation declarations unreadable, NO join "
                     "key is folded: %s", name, e)
        for pair in join_key:
            pair["fold"] = None

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
    right_folds = [p["fold"] for p in join_key]

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
        # 조인 키별 접기 규칙(없으면 None). 실행기·게이트·DDL이 **같은 목록**을 읽으므로
        # 「질의는 접는데 인덱스는 안 접힌」 상태가 성립할 자리가 없다.
        "right_folds": right_folds,
        "folded": any(f for f in right_folds),
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
        # S-189 ⓐ. `materialize` False 면 나머지는 오늘과 «바이트 동일»이다.
        "materialize": materialize is True,
        "max_rewrite_rows": raw.get("max_rewrite_rows") if materialize is True else None,
        # 🔴 왼쪽 색인은 «참조 변화 → 대상 행 찾기»가 쓴다. 오른쪽 것과 목적이 반대라
        # UNIQUE 가 아니고, 그래서 이름도 DDL 도 따로다.
        "required_left_index": (
            required_left_index_name(left_table, [p["left"] for p in join_key])
            if materialize is True else None),
        "required_index": required_index_name(right_table, right_join_cols,
                                              right_folds),
        "required_index_ddl": required_index_ddl(right_table, right_join_cols,
                                                 right_folds),
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
            _say_once(("shape", name), logger, "[VirtualJoin:%s] declaration rejected: %s", name, err)
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
    raw_config = {}
    if os.path.exists(rules_path):
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                raw_config = json.load(f)
        except Exception as e:
            logger.error("Failed to load virtual join rules from %s: %s", rules_path, e)
            _record(rejections, "file", None,
                    f"virtual_join_rules.json could not be read ({e.__class__.__name__}) ― "
                    f"NO virtual join is in effect")
            return []
    rules = validate_virtual_join_rules(raw_config, known_tables=known_tables,
                                        rejections=rejections)
    # 🔴 [S-251] AND THE UNIFIED FILE DECLARES THESE TOO. `into: {read: true}` was in the
    # grammar with nobody reading it - `rule_shape` translated a virtual join INTO that
    # shape, and nothing ever translated one back out, so a read-time join could live only
    # in `virtual_join_rules.json`. They join the SAME list here, so they get the same
    # validation, the same namespace, the same uniqueness gate (S-235) and the same
    # retraction (S-248) - one join, one set of answers, wherever it was written.
    #
    # ⚠️ THE FILE'S ABSENCE IS NOT THE END OF THE QUESTION ANY MORE. This used to return
    # `[]` the moment `virtual_join_rules.json` was missing; a deployment that declared its
    # joins only in the unified file would have had none of them.
    #
    # ⛔ AND A PARTIAL LIST IS STILL NOT RETRACTED FROM. A caller passing `path` is reading
    # a subset on purpose, so it does not get the unified half either - the two halves of
    # 「what is declared」 stay together.
    if path is None:
        rules.extend(_read_time_joins_from_unified(
            {rule["name"] for rule in rules}, known_tables, rejections))
    return rules


def _read_time_joins_from_unified(taken: set, known_tables, rejections) -> list:
    """`into: {read: true}` declarations in `chain_rules.json`, as virtual join rules.

    ⚠️ THE SAME VALIDATOR, ON PURPOSE. These go through `_validate_join` exactly as a
    declaration in the old file does - a second validator would be a second answer to
    「is this join runnable」, and the whole point of the unified grammar is that where you
    wrote it does not change what it means.
    """
    try:
        from chain import ingestion_worker, rule_shape
    except Exception:                                              # noqa: BLE001
        return []

    out = []
    for raw in ingestion_worker.read_rules_document()["rules"] or ():
        if not isinstance(raw, dict) or not isinstance(raw.get("derive"), dict):
            continue
        internal = rule_shape.from_declaration(raw)
        if (internal.get("derive") or {}).get("kind") != "join":
            continue
        if not (internal.get("into") or {}).get("read"):
            continue
        name = str(internal.get("name") or "")
        if rule_shape.is_switched_off(internal):
            # ⛔ OFF IS OFF (판정 399 ③′). Not validated, not counted, not complained about.
            continue
        # 🔴 [S-282 · 판정 440] RETIRED, AND THE COLLECTOR SAYS SO IN THE LOADER'S WORDS.
        # The owner declared that production writes its join columns into the table
        # (`into.table`), so this capability is being retired rather than kept alive for
        # nobody. The refusal is `rule_shape.READ_TIME_RETIRED` and not a second spelling:
        # `expand_declaration` meets the same declaration, and if only IT refused, the
        # loader would report a rule this collector still RAN.
        #
        # ⚠️ NOTHING IS DELETED HERE. The validator, the adapter and the engine all still
        # stand; what stops is ADOPTING a unified `into.read` declaration as a live join.
        _say_once(("read_time_retired", name), logger,
                  "[VirtualJoin:%s] %s", name, rule_shape.READ_TIME_RETIRED)
        _record(rejections, "rule", name, rule_shape.READ_TIME_RETIRED, code=CODE_SHAPE)
    # ⚰️ EVERYTHING BELOW THIS LOOP WAS LEFT UNREACHABLE BY STEP 1 AND IS GONE: the
    # both-files name collision, `_validate_join` and the adoption. They sat after an
    # unconditional `continue`, so `git grep` showed a name-collision refusal this file could
    # no longer produce - a reader counting doorways would have counted one that was shut.
    return out


# ---------------------------------------------------------------------------
# 유일성 ― 카탈로그 조회 하나가 전부다
# ---------------------------------------------------------------------------



# PostgreSQL이 인덱스 식을 되돌려 줄 때 붙이는 잡음. 판정은 이것들을 지운 뒤에 한다.










def verify_uniqueness(db, rule: dict) -> dict:
    """선언 1건의 유일성 판정. 반환:
    `{"unique_index": 이름|None, "refused": bool, "code": ...|None}`

    통과 조건은 하나다 ― 조인 키를 덮는 유효한 UNIQUE 인덱스의 존재. 조인 키가 접히면
    그 인덱스는 **접힌 식**에 대한 것이라야 한다(`unique_index_covering` 참조).
    """
    # `folds` is passed ONLY when something actually folds. A declaration with no
    # normalized join key must reach `unique_index_covering` with the exact call shape it
    # had before this feature existed - several suites stand a 3-argument double in for
    # it, and widening the call unconditionally would break them all while changing no
    # behaviour. A folded declaration DOES widen it, and a double that cannot answer the
    # folded question should fail loudly rather than answer the unfolded one.
    folds = rule.get("right_folds") or []
    kwargs = {"folds": folds} if any(folds) else {}
    idx = unique_index_covering(db, rule["right_table"], rule["right_columns"], **kwargs)
    if idx:
        return {"unique_index": idx, "refused": False, "code": None}
    return {"unique_index": None, "refused": True, "code": CODE_NO_UNIQUE_INDEX}



class _NarrowKey(Exception):
    """선언만으로 «설 수 없음»이 확정된 경우. 값을 나르지 않는다 — 문장은 이미 말해졌다."""

def load_verified_rules(db, path: str = None, known_tables: dict = None,
                        rejections: list = None) -> list:
    """모양 + 유일성 **둘 다** 통과한 선언만. **조인을 실행하는 코드의 유일한 진입점.**

    `load_virtual_join_rules`(모양만)를 직접 소비하면 유일성이 검사되지 않은 선언이
    그대로 실행된다 ― 그 차이가 1억 3천만 행이다.

    반환 항목은 UI executor와 Ledger setup compiler가 함께 소비하는 immutable
    `VerifiedJoinDescriptor`다. catalog 선언 dict 자체에는 verified 등급을 부여하지 않는다.
    """
    rules = load_virtual_join_rules(path=path, known_tables=known_tables,
                                    rejections=rejections)
    verified = []
    for rule in rules:
        # 🔴 ONE DECLARATION, ONE VERDICT (2026-09-15). This call was outside any try, so
        # one declaration whose catalog query raised took every other table's join down
        # with it - 「모든 선언 무조건 다 돌면서 다 막아버렸네」. A rule that cannot be
        # verified is refused BY NAME and the loop goes on; the session is rolled back so
        # the next rule's query is not answered by an aborted transaction.
        try:
            result = verify_uniqueness(db, rule)
        except Exception as verify_error:
            try:
                db.rollback()
            except Exception:
                pass
            _say_once(("verify", rule["name"]), logger,
                      "[VirtualJoin:%s] uniqueness could not be verified (this rule only): %s",
                      rule["name"], str(verify_error).strip().splitlines()[0] if str(verify_error).strip() else verify_error)
            _record(rejections, "rule", rule["name"],
                    "uniqueness could not be verified: %s" % verify_error, code=CODE_SHAPE)
            continue
        if result["refused"]:
            # 🔴 포기하기 «전»에 제품이 한 번 세워 본다 (S-235, 소유자 2026-09-14).
            #    종전에는 여기서 운영자에게 DDL 을 내밀었고, 그 결과 운영자가 «조인을 전부
            #    끄는» 것으로 끝났다. 인덱스가 그냥 없거나 «INVALID 잔해»가 이름을 붙잡고
            #    있을 뿐이면 - 중복은 하나도 없이 - 세우면 그대로 살아난다.
            #    ⚠️ 프로세스당 규칙당 한 번뿐이다: 이 자리는 5초 TTL 캐시가 다시 부른다.
            try:
                from chain import unique_key
                # 🔴 「행 하나는 사실 하나」의 선언만으로 잡히는 위반부터 (소유자 2026-09-15).
                #    조인 키가 그 표의 «신원보다 좁으면» 유일 인덱스는 영원히 설 수 없다 —
                #    데이터를 한 행도 안 읽고 안다. 이때 만들어 보는 것은 시간 낭비이고,
                #    중복 목록을 내미는 것은 «틀린 곳»을 가리키는 것이다: 고칠 것은
                #    데이터가 아니라 이 선언의 키다. 2026-09-14 에 그 한 줄이 없어서
                #    운영자가 조인을 전부 껐다.
                identity = unique_key.narrower_than_identity(
                    rule["right_table"], rule["right_columns"], known_tables)
                if identity:
                    _say_once(("narrow", rule["name"]), logger,
                              "[VirtualJoin:%s] 조인 키 (%s) 가 %s 의 «신원»(%s)보다 "
                              "좁습니다 - 유일 인덱스는 설 수 없고 접기로도 못 고칩니다. "
                              "이 조인의 키를 신원까지 넓히십시오",
                              rule["name"], ", ".join(rule["right_columns"]),
                              rule["right_table"], ", ".join(identity))
                    raise _NarrowKey()
                built = unique_key.ensure_once(
                    db, rule["name"], rule["right_table"], rule["right_columns"],
                    rule.get("right_folds"))
                if built.get("created"):
                    result = verify_uniqueness(db, rule)
            except _NarrowKey:
                pass  # 문장은 위에서 이미 말했다. 만들어 보지 않는다
            except Exception as ensure_error:
                logger.warning("[VirtualJoin:%s] 유일 인덱스 자동 설치 실패: %s",
                               rule["name"], ensure_error)
        if result["refused"]:
            _say_once(("unique", rule["name"]), logger,
                      "[VirtualJoin:%s] rejected: no unique index covers %s(%s)",
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
        verified.append(_VERIFIED_JOIN_ISSUER.issue(rule))

    # 🔴 [S-248] AN INDEX LIVES EXACTLY AS LONG AS THE JOIN THAT REQUIRES IT. The product
    # builds `uq_vjoin_*`; when the join that asked for it is refused, migrated or switched
    # off, nothing took it back - and the write gate cannot see it, because that gate knows
    # the keys of VERIFIED rules only. So the index bit from outside the gate: 23505 on every
    # insert of a colliding row, and the group failed permanently on every retry.
    #
    # ⚠️ ONLY FOR THE DEFAULT DECLARATION FILE. A caller passing `path` is reading a PARTIAL
    # list (a test, a report), and 「required」 computed from a partial list would retract
    # indexes real joins still need.
    #
    # ⛔ AND IT CAN NEVER BREAK LOADING. Whatever happens in there, the rules this function
    # was asked for come back.
    if path is None:
        try:
            from chain import builtins as chain_builtins
            from chain import unique_key

            # 🔴 [S-240] BOTH PRODUCERS OR NEITHER. A unified join declares its unique key
            # too, and its index carries the same `uq_vjoin_` prefix - so a required set
            # computed from the read-time declarations alone is the very PARTIAL list this
            # function already refuses to retract from when a caller passes `path`. Half a
            # required set does not retract a little less; it retracts the wrong thing.
            required = {r["unique_index"] for r in verified if r.get("unique_index")}
            required |= chain_builtins.declared_unique_index_names(
                known_tables=known_tables)
            unique_key.retract_unrequired_once(db, required)
        except Exception as retract_error:                             # noqa: BLE001
            logger.warning("[VirtualJoin] 제품 인덱스 회수를 건너뜁니다"
                           "(로딩은 계속): %s", retract_error)
    return verified


def verification_report(db, path: str = None, known_tables: dict = None) -> dict:
    """선언별 「승인됐는가 · 아니면 무엇을 만들어야 하는가」. 라우트가 쓰는 형태.

    카탈로그 조회 하나라 요청 경로에 앉아도 된다(행을 세지 않으므로 비용이 테이블
    크기와 무관하다 ― 프로브를 라우트에 앉힐 수 없었던 이유가 정확히 그것이었다).

    쓰는 이가 읽을 **한국어 문장**은 `virtual_join_refusal.virtual_join_detail` 이 짓는다
    ― 보고서와 이 라우트가 같은 거부에 다른 문장을 내면 「서버가 문장의 정본」이라는
    계약이 깨진다. 로더가 한국어를 «짓지» 않는 것도 같은 규율이다(사상은 보고서 계층).
    🪦 그 함수는 `config_resolve_report` 에 있었고, 이 자리가 그것을 함수 안에서 import 해
       고리를 만들었다 (S-211 ①, 판정 355).
    """
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
            # 접기는 **비교의 성질**이라 선언마다 다르고, 어느 쪽 컬럼이 선언됐는지와
            # 상관없이 양쪽에 걸린다. 그 사실을 여기서 말하지 않으면 운영자는 왜 이
            # 조인만 다른 인덱스를 요구하는지 알 방법이 없다.
            "folded_join_key": [
                {"left": p["left"], "right": p["right"],
                 "rules": sorted(k for k, v in (p.get("fold") or {}).items() if v)}
                for p in rule["join_key"] if p.get("fold")],
            "expose": list(rule["expose"]),
            "accepted": not result["refused"],
            "unique_index": result["unique_index"],
            "required_index": rule["required_index"],
            "required_index_ddl": None if result["unique_index"] else rule["required_index_ddl"],
            "detail": (None if not result["refused"] else
                       virtual_join_detail(CODE_NO_UNIQUE_INDEX, facts)),
        })
    return {
        "declarations": out,
        "accepted": sum(1 for d in out if d["accepted"]),
        "refused": sum(1 for d in out if not d["accepted"]),
        "invalid": [{"subject": r.get("subject"),
                     "detail": virtual_join_detail(
                         r.get("code", CODE_SHAPE), r.get("facts"), r["detail"])}
                    for r in rejections],
    }


# ---------------------------------------------------------------------------
# S-189 ⓒ — a materialised join IS a chain rule
# ---------------------------------------------------------------------------
#: The kind a synthesised join rule names. 🔴 ONE TABLE OF `builtin:` KINDS DISPATCHES THESE
#: (판정 305), the same posture the mapper registry takes: a name, a callable, and an unknown
#: name refused rather than resolved.
JOIN_MAPPER = "builtin:join"
JOIN_PREFIX = "virtual_join:"


def synthesized_join_rule_name(rule_name: str) -> str:
    """The chain-rule name a join declaration claims. One speller, so the collision check
    and the synthesis cannot disagree about what a join rule is called."""
    return JOIN_PREFIX + rule_name


def synthesized_join_chain_rules(path: str = None, known_tables: dict = None) -> list:
    """Every `materialize: true` join declaration, as a chain rule.

    🔴 ONLY THE MATERIALISING ONES. A read-time rule writes nothing, so giving it a chain
    rule would put a rule on the loader that can never do anything — and this box's two
    production rules are read-time today. They must come out of here byte-identically absent.

    🔴 `follow_up: True`, FOR THE REASON S-151 MEASURED. One reference row can reach 70,800
    target rows here (≈92 s at the owner's IO spec), and 「요청/커밋 경로 인라인 금지,
    뒤따르는 일은 페이싱된 별도 작업」 is the standing rule. The cell says so in the
    declaration rather than only in the code.

    ⚠️ `params` IS THE WHOLE NORMALIZED RULE, exactly as the enrichment half does it — a
    hand-listed subset is a list that goes stale silently, and the cell it drops is invisible
    until somebody asks why a declaration stopped working.
    """
    rules = []
    for rule in load_virtual_join_rules(path=path, known_tables=known_tables):
        if not rule.get("materialize"):
            continue
        rules.append({
            "name": synthesized_join_rule_name(rule["name"]),
            # The TARGET table is what a join writes, and it is also what wakes this rule
            # when one of its own rows moves (trigger ⓐ). The reference side reaches it
            # through the follow-up lap, which is why this is not a second trigger cell.
            "trigger_table": rule["left_table"],
            "target_table": rule["left_table"],
            "mapper": JOIN_MAPPER,
            "follow_up": True,
            "enabled": True,
            "params": dict(rule),
            "origin": "synthesized:" + rule["name"],
        })
    return rules


# 🪦 `join_name_collisions` (S-179 ①, 판정 292) sat here beside `synthesized_join_chain_rules`.
#    S-234 ① (판정 409) made the three rule files ONE namespace, judged once at the loader's
#    set-aware seat (`chain.ingestion_worker.load_chain_rules`) — a checker per file was the
#    evidence of a namespace per file.
