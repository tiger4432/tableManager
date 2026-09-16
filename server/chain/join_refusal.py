# -*- coding: utf-8 -*-
"""virtual join 거부의 «코드»와 «운영자가 읽는 문장» — 한 자리.

🔴 이 모듈이 «가벼운» 이유가 전부입니다 (S-211 ①, 판정 355). 여기엔 stdlib 말고 아무것도
   import 되지 않고, 앞으로도 그래야 합니다. 로더(`virtual_join_config`)와 보고서
   (`config_resolve_report`)가 «둘 다» 이것을 읽고, 둘 중 어느 쪽도 상대를 읽지 않습니다.

🔴 무엇을 고쳤나: 로더가 거부 문장을 지으려고 «보고서 모듈»을 함수 안에서 import 하고 있었고
   (`virtual_join_config.verification_report`), 보고서는 로더를 import 했습니다. 고리입니다.
   그 고리는 «함수 안 import» 로 숨겨져 있어 오늘 아무 일도 안 났지만, 숨긴 것이지 없앤 것이
   아닙니다 — 실측: 여덟 짜리 SCC 의 엣지 중 import 시점은 «셋»뿐이고 나머지 «22 문장»이 전부
   함수 안이었습니다.

🔴 방향은 이렇게 정해집니다: **로더가 필요한 것은 «문장»이지 «보고서»가 아닙니다.** 그래서
   문장을 «둘 다보다 아래»로 내렸습니다. 보고서가 로더를 읽는 것은 «맞는 방향»이라 그대로입니다.

⚠️ 「서버가 문장의 정본」이 이 모듈이 지키는 계약입니다 — 보고서와
   `GET /admin/config/virtual-join/verify` 가 «같은 거부»에 다른 문장을 내면 그 계약이 깨집니다.
   그래서 한국어를 짓는 자리는 여기 «하나»입니다.
"""

# --- 거부 코드 (내부 어휘 ― `config_resolve_report` 가 닫힌 사유로 사상한다) ---
#: 🔴 코드가 «문장과 같은 모듈»에 사는 이유: 코드를 하나 더하면 그것이 내는 문장도 같이
#: 정해져야 합니다. 두 파일에 나눠 두면 코드만 늘고 문장은 기본값으로 조용히 떨어집니다.
CODE_NO_UNIQUE_INDEX = "no_unique_index"     # 유일성을 강제하는 인덱스가 없다
CODE_FANOUT_DECLARED = "fanout_declared"     # 집계 형태는 아직 구현이 없다
CODE_SHAPE = "shape"                         # 평범한 문법/존재 오류
# S-189 ⓐ (판정 302). 실체화는 «쓰기»라서 비용이 선언에 적혀야 한다.
CODE_NO_REWRITE_CAP = "no_rewrite_cap"       # materialize 인데 상한을 안 적었다
CODE_NO_LEFT_INDEX = "no_left_index"         # 역방향(참조→대상) 색인이 없다
# S-283 (판정 446·452 ①). 읽는 시점에 계산하는 조인은 «은퇴했다». 남은 것은 쓰기 조인뿐이다.
CODE_READ_TIME_RETIRED = "read_time_retired"  # materialize 가 false 다

# 코드별 한국어 앞머리. 로더가 만든 영문 사유를 그대로 붙이지 않고, 운영자가 무엇을
# 고쳐야 하는지 먼저 말한다(INV-F9-8 ― `detail`은 그가 읽는 최종 문장이다).
CODE_LEAD = {
    CODE_NO_UNIQUE_INDEX:
        "오른쪽 테이블이 조인 키로 유일하다는 보장이 없어 선언을 거부했습니다",
    CODE_FANOUT_DECLARED:
        "아직 구현되지 않은 조인 형태라 선언을 거부했습니다",
    CODE_SHAPE:
        "선언이 반영되지 않았습니다",
    CODE_READ_TIME_RETIRED:
        "읽는 시점에 계산하는 조인은 더 이상 없어서 이 선언을 이름 대어 거부했습니다",
}

#: ⚠️ [판정 481 ③] THE ENGLISH DETAIL FOR `read_time_retired` IS NOT HERE, and that is not an
#: oversight. Two validators must now say it - this side's loader and the LEDGER BUNDLE
#: validator - and the bundle validator is held to stdlib-only imports, so the shared
#: sentence lives in `validation.READ_TIME_RETIRED_DETAIL` (판정 300 settled that same
#: shape). Importing it HERE would break the property this module's own header states in
#: its first line: nothing but stdlib is imported, and that is what keeps the loader and
#: the report from closing a cycle around this module.
#:
#: What this module owns is unchanged: the CODE above and its Korean lead below. The
#: English detail was always the loader's `loader_detail` argument, never authored here.


def _names(seq, sep: str = ", ") -> str:
    """이름 목록을 **문장에 넣을 수 있는** 형태로.

    🔴 f-string 에 리스트를 그냥 끼우면 `['slot']` 이라는 Python repr 이 운영자 화면까지
    갑니다 — 대괄호와 따옴표를 먼저 해독해야 문장을 읽을 수 있습니다.
    ⚠️ `config_resolve_report._names` 가 같은 규칙을 같은 한 줄로 들고 있습니다. 그쪽은
    이 모듈과 «무관한» 열넷 군데에서 쓰이므로 여기로 끌어오면 보고서가 virtual join 모듈을
    일반 헬퍼 때문에 읽게 됩니다 — 그것이 더 나쁜 방향이라 한 줄을 남겼습니다.
    """
    return sep.join(str(s) for s in (seq or []))


def virtual_join_detail(code: str, facts: dict = None, loader_detail: str = "") -> str:
    """virtual join 거부 1건의 **운영자가 읽는 최종 문장**. 서버가 짓는다.

    보고서와 `GET /admin/config/virtual-join/verify` 가 **같은 함수**를 쓴다. 갈라 두면
    같은 거부가 두 화면에서 다른 문장으로 나오고, 그 순간 「서버가 문장의 정본」이라는
    계약이 깨진다. `no_unique_index` 는 세션이 있어야 나오는 코드라 보고서 경로에서는
    발화하지 않는다 ― 그래서 이 함수가 라우트에서도 불려야 그 분기가 살아 있다.
    """
    facts = facts or {}
    lead = CODE_LEAD.get(code, CODE_LEAD[CODE_SHAPE])
    # 유일성 거부는 구조화된 사실이 오므로 **온전한 한국어 문장**을 짓는다. 로더의
    # `detail`은 영어 로그 문구라, 그것을 이어 붙이면 운영자가 읽는 최종 문장이
    # 반쯤 영어가 된다(INV-F9-8). 사실이 없는 거부만 영어 사유를 그대로 나른다.
    if code == CODE_NO_UNIQUE_INDEX and facts.get("required_index_ddl"):
        return (f"{lead}. {facts['right_table']} 테이블의 "
                f"{_names(facts.get('join_key'), ', ')}을(를) 덮는 UNIQUE 인덱스가 "
                f"없습니다. 다음을 실행해 만드세요: {facts['required_index_ddl']} "
                f"만드는 중 중복 오류가 나면 그 값이 실제로 둘 이상 있다는 뜻이므로 "
                f"데이터를 먼저 정리해야 합니다.")
    return f"{lead} ― {loader_detail}"
