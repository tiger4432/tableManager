"""「내 config가 먹었는가」 — 선언을 세 모집단으로 나눠 **이름으로** 답한다.

왜 있는가 (사용자 2026-07-30: *"enrich auto confirm 잘 적용되었는지 확인할수 있게 admin에
추가, 이거말고도 컨피그 잘 먹었는지 확인할 방법 전무"*)
    어드민의 config 라우트는 `POST /admin/reload-configs` 하나뿐이고, 캐시를 갱신하고
    워커에 이벤트를 뿌린 뒤 **무엇이 먹었는지 아무것도 반환하지 않는다.** 서버가 읽는
    config는 10개다. 즉 쓰기 전용 버튼 하나가 전부다.

    그 공백은 이미 실제 결함을 숨기고 있다. `auto_confirm: true`를 `candidate_for` 선언
    없이 켜면 컬렉터는 경고 한 줄(`enrichment_candidates:456`)을 남기고 조용히 비활성이
    되는데, **라이브가 정확히 그 상태다**(2026-07-30 실측: 어떤 뷰도 `candidate_for`를
    선언하지 않았다). 노브는 켜진 것처럼 읽히고 아무 일도 하지 않으며, 그 사실의 유일한
    목격자는 아무도 안 보는 데몬 로그다.

세 모집단 (총괄 확정 경계 계약)
    `effective`   — 효과가 있는 선언.
    `ineffective` — 선언은 있는데 효과가 없다. **반드시 명명된 사유를 동반한다.**
    `rejected`    — 파싱/검증에 실패해 아예 반영되지 않았다. 사유 동반.

    🔴 클라이언트는 「효과 없음」을 자기 규칙으로 판정하지 않는다. 서버가 만든
    `detail` 문자열을 그대로 렌더한다. 클라가 사유를 유도하기 시작하면 U6에서 6종을
    삭제한 하드코딩 사본 계급이 그대로 재발한다. 그래서 사람이 읽을 문장은 **전부
    서버가 만든다**(UI 문자열이므로 영어 — 소유자 2026-08-31 「UI 무조건 영어로」).

닫힌 어휘 — 새 단어를 만들지 않는다
    런타임 열화 어휘(`main.CHIP_TRACE_*`)를 그대로 재사용한다. 같은 구분이 config 로드
    시점으로 한 층 올라온 것뿐이라, 어휘가 갈라질 이유가 없다:

    | 단어                   | 런타임(chip-trace)에서의 뜻            | 여기서의 뜻 |
    |------------------------|----------------------------------------|-------------|
    | `not_declared`         | 매핑이 이 (type,target)을 선언하지 않음 | 효과에 필요한 선언이 없음 (노브 OFF, 또는 `candidate_for` 0건) |
    | `mapping_unavailable`  | 선언을 **읽지 못했다**                  | 선언이 파싱/검증에 실패해 반영되지 않음 |
    | `scope_unresolved`     | 0개 또는 2개 이상이 주장 — 고르지 않음  | 선언의 범위가 판단키를 고정하지 못함(부분 바인드) |
    | `not_reached`          | 실행되지 않은 다리에 매달린 다리        | 상위 스위치가 꺼져 이 선언까지 도달하지 않음 |

    이 4개가 전부다. `REASONS`가 정본이고 `contracts/config_resolve_report/vectors.json`이
    양쪽(pytest·node 하네스)을 같은 기댓값에 채점한다.

모집단이 답하지 못하는 것 — `settings`
    모집단은 **선언**에 대한 이야기다. "그래서 서버가 지금 쓰는 값이 뭔데"는 다른 질문이고,
    선언이 아예 없을 때(파일 부재 → 전부 기본값)에도 답이 있어야 한다. 그래서 `settings`는
    별도 목록으로 나가고 각 항목이 **값과 그 값이 온 자리**를 함께 말한다.

확장 (나머지 9개 config)
    도메인마다 `_RESOLVERS`에 등록기 하나. 봉투(`build_domain`)와 어휘는 공유하고,
    도메인 고유 사실은 `fields`에 담는다. enrichment가 첫 슬라이스이고, 어느 config가
    이 틀에 안 맞는지는 두 번째를 붙일 때 드러난다 — 미리 설계하지 않는다.
"""
import json
import logging
import os

# 🔴 [S-211 ①, 판정 355] 이 넷은 «함수 안»에 있었다. 고리를 숨기려고가 아니라 고리가 «있어서»
#    그랬고(로더 ↔ 보고서), 문장이 `virtual_join_refusal` 로 내려가 그 고리가 사라졌으므로
#    이제 모듈 수준에서 선언한다. 「보고가 워커를 읽는다」는 맞는 방향이라 그대로 둔다.
#    ⚠️ 이 모듈을 «모듈 수준»에서 읽는 제품 코드는 없다(실측: `main.py` 셋 다 함수 안). 그래서
#    이 import 들의 비용은 보고서를 «처음 부르는» 요청에 붙고, 기동 경로에는 붙지 않는다.
import chain_bindings
from chain import ingestion_worker as worker
import mapper_sdk
from chain import rule_shape
from chain.join_refusal import join_detail                     # noqa: F401

logger = logging.getLogger(__name__)


def _runnable_name(name):
    """「Can this name run」, asked where it is answered (판정 498 ①).

    Imported inside the call rather than at module scope: this module is read by the loader
    it reports on, and the seat pulls in the builtin table, so a module-level import would
    close a ring that has been deliberately kept open.
    """
    from chain import rule_run

    return rule_run.runnable(name)


def _names(seq, sep: str = ", ") -> str:
    """이름 목록을 **문장에 넣을 수 있는** 형태로.

    🔴 `detail`은 클라이언트가 그대로 렌더하는 **사람이 읽을 문장**이다(모듈 상단 계약).
    f-string에 리스트를 그냥 끼우면 `['slot']`이라는 Python repr이 운영자 화면까지
    간다 — 대괄호와 따옴표를 먼저 해독해야 문장을 읽을 수 있다.
    「가독성은 기능이다」(핵심가치)이므로 이건 사소한 미관 문제가 아니라 결함이다.
    """
    return sep.join(str(s) for s in (seq or []))


def _as_json(value) -> str:
    """운영자가 **편집한 그 파일의 문법(JSON)**으로 값을 되돌려 보여준다.

    같은 이유로 `!r`도 쓰지 않는다: Python repr은 `"true"`를 `'true'`로 적는데,
    운영자가 연 파일에 작은따옴표는 없다. 「당신이 쓴 값」을 되읽어 주는 문장에서
    철자가 다르면 자기 파일을 못 알아본다.
    """
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)

# --- 닫힌 어휘 (contracts/config_resolve_report/vectors.json이 정본을 공유한다) ---
REASON_NOT_DECLARED = "not_declared"
REASON_MAPPING_UNAVAILABLE = "mapping_unavailable"
REASON_SCOPE_UNRESOLVED = "scope_unresolved"
REASON_NOT_REACHED = "not_reached"
REASONS = (REASON_NOT_DECLARED, REASON_MAPPING_UNAVAILABLE,
           REASON_SCOPE_UNRESOLVED, REASON_NOT_REACHED)
#: What each reason is CALLED on a screen (lead 909ea2052 ②). The token stays the key; the screen
#: draws the name it is sent and keeps no copy of these words.
REASON_NAMES = {
    REASON_NOT_DECLARED: "Not declared",
    REASON_MAPPING_UNAVAILABLE: "Mapping unavailable",
    REASON_SCOPE_UNRESOLVED: "Scope unresolved",
    REASON_NOT_REACHED: "Not reached",
}

POPULATIONS = ("effective", "ineffective", "rejected")
#: What each population is CALLED on a screen, the way `REASON_NAMES` names the reasons
#: (lead bed890af2 ③). Lower case: it is read after a count - 「40 no effect」.
POPULATION_NAMES = {"effective": "fine", "ineffective": "no effect", "rejected": "rejected"}

SCOPE_FILE = "file"
SCOPE_SETTING = "setting"
SCOPE_RULE = "rule"
SCOPE_VIEW = "reference_view"
#: ⓑ 의 ineffective 항목은 «표»입니다 — 어떤 규칙도 trigger_table 로 가리키지
#: 않는 선언 표. 그것을 `rule` 로 내면 그 줄이 «거짓»입니다(「이 줄이 참인가」).
SCOPE_TABLE = "table"
#: ⓓ 의 effective 항목은 «노드 타입»입니다 — 좌석이 `collect` 로 고를 수 있는 이름.
#: 판정 316 이 `table` 을 더한 것과 «같은 사유»입니다: 그것을 `rule` 로 내면 그 줄이 거짓입니다.
SCOPE_NODE_TYPE = "node_type"
SCOPES = (SCOPE_FILE, SCOPE_SETTING, SCOPE_RULE, SCOPE_VIEW, SCOPE_TABLE,
          SCOPE_NODE_TYPE)

ORIGIN_FILE = "file"
ORIGIN_DEFAULT = "default"


def entry(scope: str, subject, detail: str, reason: str = None,
          warnings: list = None, fields: dict = None) -> dict:
    """모집단 항목 1건. `detail`이 클라이언트가 **그대로 렌더**할 문장이다."""
    if reason is not None and reason not in REASONS:
        # 어휘 밖 단어는 계약 위반이다. 조용히 통과시키면 클라가 못 읽는 사유가 흘러간다.
        raise ValueError(f"reason must be one of {REASONS}, got {reason!r}")
    bad = [w for w in (warnings or []) if w not in REASONS]
    if bad:
        raise ValueError(f"warnings must come from {REASONS}, got {bad!r}")
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {SCOPES}, got {scope!r}")
    return {
        "scope": scope,
        "subject": subject,
        "detail": detail,
        "reason": reason,
        "warnings": list(warnings or []),
        "fields": dict(fields or {}),
    }


def source(key: str, path: str, detail: str, exists: bool = None,
           degraded: bool = False) -> dict:
    """설정 파일 1개의 상태. **부재는 거부가 아니다** — `/graph/mapping-summary`와 같은 규율."""
    present = os.path.exists(path) if exists is None else bool(exists)
    return {
        "key": key,
        "path": path,
        "exists": present,
        "status": "degraded" if degraded else "ok",
        "detail": detail,
    }


def setting(key: str, value, origin: str, path: str, declared=None,
            detail: str = "") -> dict:
    """지금 **실효 중인** 값 1건과 그 값이 온 자리."""
    return {
        "key": key,
        "value": value,
        "origin": origin,          # "file" | "default"
        "path": path,
        "declared": declared,      # 파일에 적힌 원값(없으면 None)
        "detail": detail,
    }


def build_domain(domain: str, title: str, sources: list, settings: list,
                 effective: list, ineffective: list, rejected: list) -> dict:
    return {
        "domain": domain,
        "title": title,
        "sources": list(sources),
        "settings": list(settings),
        "effective": list(effective),
        "ineffective": list(ineffective),
        "rejected": list(rejected),
        "counts": {
            "effective": len(effective),
            "ineffective": len(ineffective),
            "rejected": len(rejected),
        },
    }


# ---------------------------------------------------------------------------
# enrichment — 첫 슬라이스
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# chain — 셋업 순서의 ② 걸음 (S-180 ⓑ)
# ---------------------------------------------------------------------------

DOMAIN_CHAIN = "chain"

#: ⑥ 걸음의 이름. ⚠️ 순서는 «여섯»이 다 서 있고(S-180 ⓒ), 그 걸음의
#: 등록기는 ⓓ 에서 옵니다 — 순서를 «반쯤» 적으면 그 사이에 문서와 코드가 다른 순서를
#: 들게 됩니다. 등록기가 없는 걸음은 보고에 «안 나타납니다».
DOMAIN_WALK = "walk"

#: 합성 규칙에 붙는 표. 🔴 운영자가 «안 적은» 줄이 목록에 이름 없이 섞이면
#: 「내가 안 썼는데 왜 있지」가 되고, 그 사람은 고칠 수 없는 것을 고치러 갑니다.
ORIGIN_DECLARED = "declared"


def _resolve_chain() -> dict:
    """② 파생 — 「무엇이 «무엇을 깨우는가»」.

    🔴 **판정은 `chain_bindings.rule_refusals` 가 합니다** (S-180 ⓑ-0). 그 함수는 로더와
    드라이런 화면이 «같이» 부르는 하나이고, 이 등록기가 셋째 호출자입니다. 문법을 여기서
    다시 쓰면 「내 규칙이 돌까」에 답하는 자리가 넷이 됩니다.

    🔴 **파일을 여는 것은 `read_rules_document` 하나입니다.** 로더는 살아남은 규칙만
    돌려주므로 「무엇을 버렸나」에 답할 수 없고, 그걸 알려고 파일을 다시 여는 순간 이 모듈이
    둘째 독자가 됩니다.

    ⚠️ **주어가 둘입니다.** effective/rejected 는 «규칙»이고 ineffective 는 «표»입니다 —
    이 걸음의 질문이 「무엇이 무엇을 깨우나」라서, 「아무도 안 깨우는 표」가 이 걸음의 «빈
    자리»입니다. 그 항목을 `rule` 스코프로 내면 그 줄이 거짓이므로 `SCOPE_TABLE` 로 냅니다.

    ⚠️ 합성 규칙은 «문법 채점 대상이 아닙니다** — 이 프로세스가 지은 것이라 작성 문법에
    대면 「우리 버그를 그들의 오타로」 보고하게 됩니다. effective 에 넣되 `origin` 으로
    이름을 답니다.
    """
    from database import crud

    effective, ineffective, rejected = [], [], []

    read = worker.read_rules_document()
    sources = [source(
        "rules", read["path"],
        "Declares what wakes what. A table not named here derives nothing - "
        "empty and wrong are told apart below.",
        exists=read["exists"], degraded=bool(read["error"]))]

    if read["error"]:
        rejected.append(entry(
            SCOPE_FILE, os.path.basename(read["path"]),
            "The chain rules file could not be read (%s). While it cannot be read, no table "
            "derives anything." % read["error"],
            reason=REASON_MAPPING_UNAVAILABLE))
        return build_domain(DOMAIN_CHAIN, DOMAIN_TITLES[DOMAIN_CHAIN], sources, [],
                            effective, ineffective, rejected)

    triggered = set()
    from database import crud as _catalogue
    for index, declared in enumerate(read["rules"] or ()):
        path = "rules[%d]" % index
        # 🪦 [판정 498 ①] `MAPPER_REGISTRY.get` STOOD HERE AND IT KNOWS ONE TABLE OF TWO.
        # A `builtin:` name was reported unresolvable while the loader ran it happily.
        # 🔴 [판정 619 ③] AND THE INPUT WAS RAW WHERE THE LOADER'S IS EXPANDED.
        # A unified declaration is not a runnable rule until `expand_declaration` stands it,
        # so this seat reported one as 「돌 수 없습니다」 - and the RETROACTIVE path is
        # gated on this report - while the loader ran the same file happily.
        # `ledger/admin.save_chain_rule_raw` already does the two steps (expand, then judge
        # each candidate); this seat did only the second, on the wrong input.
        name = str((declared or {}).get("name") or path) if isinstance(declared, dict) else path
        stood, expand_refusal, _notes = rule_shape.expand_declaration(
            declared, _catalogue.TABLE_CONFIG)
        if expand_refusal:
            rejected.append(entry(
                SCOPE_RULE, name,
                "`%s` cannot be expanded - %s" % (name, expand_refusal),
                reason=REASON_MAPPING_UNAVAILABLE,
                fields={"origin": ORIGIN_DECLARED}))
            continue
        for rule in stood:
            name = str((rule or {}).get("name") or path) if isinstance(rule, dict) else path
            issues = chain_bindings.rule_refusals(
                rule, path, mapper_resolvable=_runnable_name,
                mapper_params=mapper_sdk.MAPPER_PARAMS.get)
            if issues:
                first = issues[0]
                rejected.append(entry(
                    SCOPE_RULE, name,
                    "Rule `%s` cannot run - %s: %s%s"
                    % (name, first.path, first.message,
                       " (and %d more)" % (len(issues) - 1) if len(issues) > 1 else ""),
                    reason=REASON_MAPPING_UNAVAILABLE,
                    fields={"issues": [i.to_mapping() for i in issues],
                            "origin": ORIGIN_DECLARED}))
                continue

            trigger = str((rule or {}).get("trigger_table") or "")
            if trigger:
                triggered.add(trigger)
            warnings = chain_bindings.rule_warnings(rule, path)
            effective.append(entry(
                SCOPE_RULE, name,
                "`%s` runs on changes to `%s`." % (name, trigger),
                fields={"origin": ORIGIN_DECLARED, "trigger_table": trigger,
                        "warnings": [w.to_mapping() for w in warnings]}))

    # ⚰️ [2026-09-24, 소유자 「enrich.json 아예 삭제」] 제품이 «합성한» 규칙과 합성 반쪽의
    #    실패를 여기서 따로 그렸다. 평면 인리치 파일이 은퇴해 합성되는 규칙이 없다 — 인리치
    #    선언도 `chain_rules.json` 에 적혀 위의 «선언된» 규칙으로 선다.

    # ⚠️ 표 목록은 «카탈로그»에서 옵니다(① 걸음). 이 걸음이 자기 표 목록을 들면
    # 두 걸음이 「무슨 표가 있나」에 다르게 답하게 됩니다.
    for table in sorted(str(t) for t in (crud.load_table_config() or {})
                        if not str(t).startswith("__")):
        if table in triggered:
            continue
        # 🔴 [판정 454 ③] 「정상입니다」 IS A JUDGEMENT, AND A DEAD HALF TAKES AWAY THE
        # EVIDENCE FOR IT. With one half gone this seat cannot know which of these tables
        # a missing rule belonged to - the rules are not there to ask - so the honest
        # sentence says the judgement is incomplete instead of calling it normal. Leaving
        # 「정상」 here and putting a file-level rejection above it would be the shape 판정 453
        # just ruled on: a correction above does not repair the sentence below.
        ineffective.append(entry(
            SCOPE_TABLE, table,
            "Changes to `%s` wake nothing - no rule names this table as its `trigger_table`. "
            "For a table that needs no derivation this is normal." % table,
            reason=REASON_NOT_DECLARED))

    return build_domain(DOMAIN_CHAIN, DOMAIN_TITLES[DOMAIN_CHAIN], sources, [],
                        effective, ineffective, rejected)


DOMAIN_ENRICHMENT = "enrichment"


def _view_report(rule: dict, view: dict) -> dict:
    """참조뷰 1건을 사람이 읽을 형태로. 함정을 **켜기 전에** 보이게 하는 자리다.

    함정(실 config로 실증됨): `core_wafer_attribution`의 뷰 `같은 lot 전체 슬롯`은 lot
    하나만으로 조회한다. 여기에 `candidate_for`를 선언하면 결과는 `ambiguous`가 아니라
    **`single`**이다 — `wafer_slot_history`가 그 lot에 대해 행 하나만 갖고 있기 때문이다.
    그리고 그 하나의 `wafer_id`가 23개 슬롯 전부에 쓰인다. 판단키는 (lot, slot)인데 뷰의
    범위는 lot이므로, 뷰는 판단키가 구별하는 것을 구별하지 못한다 — 런타임 어휘로
    `scope_unresolved`가 정확히 이 뜻이다(누가 주장하는지 고정되지 않음).

    「선언한 뒤에」가 아니라 「선언하기 전에」 보여야 하므로, 좁은 범위의 뷰는 **선언
    여부와 무관하게** 그 사실을 문장으로 말한다. 다만 `warnings`(규칙 수준으로 올라가는
    신호)에는 **선언된 뷰만** 넣는다 — 아무 일도 하지 않는 표시 전용 뷰가 규칙에 경고를
    달면 그 경고는 곧 무시당하고, 진짜로 위험할 때 아무도 안 본다.
    """
    label = view.get("label")
    declared = dict(view.get("candidate_for") or {})
    binds = list(view.get("required_binds") or [])
    decision_key = list(rule.get("decision_key") or [])
    narrow = set(binds) < set(decision_key)
    unbound = sorted(set(decision_key) - set(binds))
    warnings = []
    parts = []
    if declared:
        pairs = ", ".join(f"{t} ← {c}" for t, c in sorted(declared.items()))
        parts.append(f"Candidates declared: {pairs}")
    else:
        parts.append("No candidates declared (display only)")
    if narrow:
        if declared:
            warnings.append(REASON_SCOPE_UNRESOLVED)
            tail = "The same value can be confirmed into different {k} - check before switching it on."
        else:
            tail = ("Declaring candidate_for here would confirm the same value into "
                    "different {k} - do not use it as a candidate source.")
        unbound_txt = _names(unbound, "/")
        scope_txt = f"by {_names(binds, '/')} only" if binds else "with no key at all"
        parts.append(
            f"⚠️ This view looks up {scope_txt}, so it cannot tell the decision key "
            f"{unbound_txt} apart. " + tail.format(k=unbound_txt))
    return {
        "label": label,
        "candidate_for": declared,
        "required_binds": binds,
        "scope_narrow": narrow,
        "warnings": warnings,
        "detail": " · ".join(parts),
    }


def _rule_fields(rule: dict, views: list, knob_on: bool, raw_knob, max_keys: int) -> dict:
    from chain.enrichment import candidates as ec

    return {
        "auto_confirm": knob_on,
        "auto_confirm_declared": bool(rule.get("auto_confirm_declared")),
        "auto_confirm_raw": raw_knob,
        "source_table": rule.get("source_table"),
        "derived_table": rule.get("derived_table"),
        "decision_key": list(rule.get("decision_key") or []),
        "target_fields": list(rule.get("target_fields") or []),
        # 「어느 뷰가 어느 target_field의 후보를 나르는가」 — 비어 있으면 노브는 무력하다.
        "candidate_fields": {
            t: [v["label"] for v in ec.declaring_views(rule, t)]
            for t in (rule.get("target_fields") or [])
        },
        "max_keys_per_unit": max_keys,
        "reference_views": views,
    }


def _resolve_enrichment() -> dict:
    """enrichment 선언의 해석 보고서. **DB를 건드리지 않는다** (config만 읽는다).

    드라이런 숫자(「몇 건이 사람 없이 확정 가능한가」)는 큐 전체를 걷는 분석 질의라
    여기 있지 않다 — `GET /admin/enrichment/auto-confirm/dry-run`이 별도로 답한다.
    """
    from chain.enrichment import candidates as ec
    from database import crud

    # 🔴 [2026-09-24] 출처는 선언이 «사는» 파일이다. 이 칸이 평면 인리치 파일을 들던 동안,
    #    그 파일이 없는 박스에서 이 보고는 「enrichment 규칙이 하나도 없습니다」라고 말했다 —
    #    바로 아래 목록이 통합 문법의 규칙을 읽고 있는데도. 파일을 여는 것은 한 문이다.
    read = worker.read_rules_document()
    rules_path = read["path"]
    rejections = []
    # `/enrichment/rules`와 **같은 인자로** 로드한다 — 보고서와 라우트가 다른 답을 내면
    # 보고서가 답하려던 질문 자체가 무의미해진다(같은 신호원 규율).
# 🔴 [판정 636] 보고는 «선 선언 전부»를 셉니다. 통합 문법으로 적힌 것이 빠지면
    #    그 보고는 「선언이 없다」와 「내가 안 봤다」를 같은 모양으로 냅니다.
    from chain import enrich_declarations

    rules = enrich_declarations.declarations(
        known_tables=crud.TABLE_CONFIG, rejections=rejections)

    settings_path = ec.INGESTION_SETTINGS_PATH
    raw_settings = ec._load_ingestion_settings()
    settings_exists = os.path.exists(settings_path)

    effective, ineffective, rejected = [], [], []

    # --- 파일/검증 거부: 로더가 남긴 것을 닫힌 어휘로 사상 ---
    for r in rejections:
        rejected.append(entry(
            r["scope"] if r["scope"] in SCOPES else SCOPE_RULE,
            r.get("subject"),
            f"The declaration did not take effect - {r['detail']}",
            reason=REASON_MAPPING_UNAVAILABLE))

    # --- 전역 스위치 + 캡 ---
    switch_declared = ec.GLOBAL_KILL_SWITCH_KEY in raw_settings
    switch_raw = raw_settings.get(ec.GLOBAL_KILL_SWITCH_KEY)
    switch_valid = (not switch_declared) or isinstance(switch_raw, bool)
    switch_on = ec.global_auto_confirm_enabled(raw_settings)

    cap_declared = ec.MAX_KEYS_SETTINGS_KEY in raw_settings
    cap_raw = raw_settings.get(ec.MAX_KEYS_SETTINGS_KEY)
    cap_valid = (not cap_declared) or (
        isinstance(cap_raw, int) and not isinstance(cap_raw, bool) and cap_raw > 0)
    cap_value = ec.max_keys_per_unit(raw_settings)

    if not settings_exists:
        origin_note = "the default, as there is no file"
    elif not switch_declared:
        origin_note = "the default, as the file does not declare it"
    else:
        origin_note = "as the file declares"

    settings = [
        setting(ec.GLOBAL_KILL_SWITCH_KEY, switch_on,
                ORIGIN_FILE if (switch_declared and switch_valid) else ORIGIN_DEFAULT,
                settings_path,
                declared=switch_raw if switch_declared else None,
                detail=(f"Global switch = {'ON' if switch_on else 'OFF'} - "
                        f"{origin_note}. While OFF nothing is auto-confirmed, whatever "
                        f"each rule's knob says.")),
        setting(ec.MAX_KEYS_SETTINGS_KEY, cap_value,
                ORIGIN_FILE if (cap_declared and cap_valid) else ORIGIN_DEFAULT,
                settings_path,
                declared=cap_raw if cap_declared else None,
                detail=(f"Decision-key probe cap per unit of work = {cap_value}. Keys past it "
                        f"are not confirmed and stay on the worklist (nothing is lost).")),
    ]
    if switch_declared and not switch_valid:
        rejected.append(entry(
            SCOPE_SETTING, ec.GLOBAL_KILL_SWITCH_KEY,
            f"'{ec.GLOBAL_KILL_SWITCH_KEY}' value {_as_json(switch_raw)} is not a JSON boolean "
            f"and was ignored - it runs as the default, true (does not block).",
            reason=REASON_MAPPING_UNAVAILABLE))
    if cap_declared and not cap_valid:
        rejected.append(entry(
            SCOPE_SETTING, ec.MAX_KEYS_SETTINGS_KEY,
            f"'{ec.MAX_KEYS_SETTINGS_KEY}' value {_as_json(cap_raw)} is not a positive integer "
            f"and was ignored - it runs as the default, {ec.DEFAULT_MAX_KEYS_PER_UNIT}.",
            reason=REASON_MAPPING_UNAVAILABLE))

    # --- 규칙별 ---
    for rule in rules:
        name = rule["name"]
        raw_knob = rule.get("auto_confirm", False)
        knob_valid = isinstance(raw_knob, bool)
        knob_declared = bool(rule.get("auto_confirm_declared"))
        knob_on = ec.rule_auto_confirm_enabled(rule, raw_settings)
        views = [_view_report(rule, v) for v in (rule.get("reference_views") or [])]
        warnings = sorted({w for v in views for w in v["warnings"]})
        fields = _rule_fields(rule, views, knob_on, raw_knob, cap_value)
        declaring = [t for t, labels in fields["candidate_fields"].items() if labels]

        if knob_declared and not knob_valid:
            rejected.append(entry(
                SCOPE_RULE, name,
                f"'{ec.RULE_KNOB}' value {_as_json(raw_knob)} is not a JSON boolean "
                f"and was ignored - this rule runs as the default, OFF.",
                reason=REASON_MAPPING_UNAVAILABLE, fields=fields))
            continue
        if not knob_declared or raw_knob is False:
            ineffective.append(entry(
                SCOPE_RULE, name,
                (f"'{ec.RULE_KNOB}' is not declared - no auto-confirm (default OFF)."
                 if not knob_declared else
                 f"'{ec.RULE_KNOB}': false - no auto-confirm."),
                reason=REASON_NOT_DECLARED, warnings=warnings, fields=fields))
            continue
        if not switch_on:
            ineffective.append(entry(
                SCOPE_RULE, name,
                f"'{ec.RULE_KNOB}': true, but the global switch "
                f"'{ec.GLOBAL_KILL_SWITCH_KEY}' is false, so this declaration is not reached.",
                reason=REASON_NOT_REACHED, warnings=warnings, fields=fields))
            continue
        if not declaring:
            ineffective.append(entry(
                SCOPE_RULE, name,
                f"'{ec.RULE_KNOB}': true, but no reference view declares 'candidate_for', "
                f"so it has no effect. Auto-confirm does not guess candidate columns - "
                f"declare which result column of which view carries the candidates for "
                f"{_names(rule.get('target_fields'))}.",
                reason=REASON_NOT_DECLARED, warnings=warnings, fields=fields))
            continue

        detail = (f"Auto-confirm ON - {_names(sorted(declaring))} resolved through "
                  f"{sum(len(v) for v in fields['candidate_fields'].values())} view declarations. "
                  f"It writes only when there is exactly one candidate, and never touches a "
                  f"cell that already has a value or a history.")
        if warnings:
            detail += " ⚠️ See the view warnings below."
        effective.append(entry(SCOPE_RULE, name, detail,
                               warnings=warnings, fields=fields))

    rules_exists = read["exists"]
    file_rejected = any(r["scope"] == SCOPE_FILE for r in rejections)
    sources = [
        source("rules", rules_path,
               ("No declaration file - there are no enrichment rules."
                if not rules_exists else
                ("The declaration file could not be read - no rule takes effect."
                 if file_rejected else
                 f"{len(rules)} rules read.")),
               exists=rules_exists, degraded=file_rejected),
        source("settings", settings_path,
               ("No file - every setting below is the server default."
                if not settings_exists else "File read."),
               exists=settings_exists),
    ]
    return build_domain(DOMAIN_ENRICHMENT, DOMAIN_TITLES[DOMAIN_ENRICHMENT],
                        sources, settings, effective, ineffective, rejected)


# ⚰️ [판정 652 3걸음] THE `virtual_join` SLICE STOOD HERE — its domain constant, its
# refusal-code map, and `_resolve_virtual_join`. It reported on `virtual_join_rules.json`,
# which is gone. 🔴 그 슬라이스가 답하던 물음은 «안 죽었습니다»: 「이 조인이 승인됐나 =
# 조인 키를 덮는 UNIQUE 인덱스가 실재하나」는 `GET /admin/chain/join/verify` 가 답하고,
# 거기는 세션이 있어 「모양은 유효한데 확인은 못 한다」는 반쪽 답을 낼 필요가 없습니다 —
# 이 보고서의 「DB 질의 0건」 계약이 바로 그 반쪽을 강제하던 것이었습니다.
# ⚠️ `join_detail` 은 «삽니다»(`chain.join_refusal`). 조인 거절의 한국어 문장은
#    그 조립기 하나가 짓고, 새 라우트가 그것을 씁니다.



# ---------------------------------------------------------------------------
# notation normalization (표기 정규화)
# ---------------------------------------------------------------------------

DOMAIN_NOTATION = "notation"

_NOTATION_CODE_TO_REASON = {
    "zero_pad_unimplemented": REASON_NOT_REACHED,
    "unknown_rule": REASON_MAPPING_UNAVAILABLE,
    "undeclared": REASON_NOT_DECLARED,
    "not_text": REASON_MAPPING_UNAVAILABLE,
    "shape": REASON_MAPPING_UNAVAILABLE,
}

# 코드별 한국어 앞머리. 로더가 만든 영문 사유를 그대로 붙이지 않고, 운영자가 무엇을
# 고쳐야 하는지 먼저 말한다(virtual join의 `_VJ_CODE_LEAD`와 같은 자세).
#
# 🔴 `would_rewrite_raw`와 `key_column`이 이 표에서 사라진 것은 완화가 아니라 **주어의
# 소멸**이다. 둘 다 「파생 컬럼에 대한 쓰기」를 막던 문구인데, 2026-08-04 사용자 확정으로
# 파생 컬럼 자체가 없어졌다 ― 이제 정규화는 쓰기가 아니라 **조회 시점에 비교의 양쪽을
# 접는 일**이라 덮어쓸 원본도, 옮길 신원도 없다. 다시 어딘가에 접힌 값을 저장하게 되면
# 두 거부는 함께 돌아와야 한다(근거는 `notation_norm` 모듈 상단에 남겨 두었다).
_NOTATION_CODE_LEAD = {
    "zero_pad_unimplemented":
        "Refused: the rule is not implemented - refused by name rather than ignored, so "
        "nothing reads as switched on while doing nothing",
    "unknown_rule": "Ignored: unknown rule name",
    "undeclared": "Not applied: the table or column is not declared in table_config.json",
    "not_text":
        "Refused: not a text column - numbers have no notation (and a column declared "
        "'number' already parses '01' and '1' into one value)",
    "shape": "Not applied: the declaration's shape is wrong",
}


def notation_preview_detail(preview: dict) -> str:
    """폴드 미리보기 1건을 운영자가 읽을 한국어 한 문단으로.

    🔴 문장을 만드는 곳은 여기 하나다 ― 라우트(`/admin/config/notation/preview`)가 이
    함수를 부르므로, 같은 사실이 두 화면에서 다른 문장으로 나올 자리가 없다
    (`join_detail`과 같은 규율).

    앞에 오는 것은 **병합군**이다. 「무엇이 무엇으로 접히는가」가 아니라 「내 규칙이
    서로 다른 두 값을 합쳐 버리지 않았는가」가 운영자가 실제로 물어야 하는 질문이고,
    사라진 파생 컬럼이 눈으로 하던 확인이 바로 그것이었다.
    """
    if preview.get("error"):
        return (f"The preview of {preview['table']}.{preview['column']} could not be built "
                f"- {preview['error']}")
    if not preview.get("declared"):
        return (f"{preview['table']}.{preview['column']} has no normalisation declared "
                f"- comparisons use the raw values.")
    merges = preview.get("merge_groups") or []
    head = (f"{preview['table']}.{preview['column']}: "
            f"{preview.get('distinct_raw', 0)} raw spellings fold into "
            f"{preview.get('distinct_folded', 0)}.")
    if not merges:
        body = ("No group was merged - the rules merge nothing in this column (if the "
                "other side of a join is messy, the effect shows there).")
    else:
        worst = merges[0]
        variants = " | ".join(str(v["raw"]) for v in worst["variants"][:5])
        body = (f"{len(merges)} groups merge different raw spellings into one value. "
                f"The largest is '{worst['folded']}', gathering {worst['raw_count']} spellings "
                f"({variants}). Read the list and check that they really are the same - "
                f"if one is not, fix the rule in notation_rules.json (stored values stay "
                f"raw, so there is nothing to undo).")
    tail = ""
    if preview.get("truncated"):
        tail = (f" (Note) More spellings than the limit ({preview.get('group_limit')}) - "
                f"only some are shown.")
    return f"{head} {body}{tail}"


def _resolve_notation() -> dict:
    """표기 정규화 선언의 해석 보고서. **DB를 건드리지 않는다**(config만 읽는다).

    이 도메인의 `effective`는 「이 컬럼의 표기가 정규화된 것으로 선언됐다」는 뜻이다.
    저장되는 것은 없다 ― 소비자가 **조회 시점에 비교의 양쪽을** 접는다. 그래서 이 보고서가
    답하지 못하는 절반이 두 개 있고, 둘 다 세션이 필요해 각자 라우트가 있다:
      · 「내 규칙이 무엇을 합치는가」 → `/admin/config/notation/preview` (병합군)
      · 「이 조인이 승인됐는가」     → `/admin/chain/join/verify` (함수 인덱스)
    """
    import notation_norm as nn
    from database import crud

    rules_path = nn.NOTATION_RULES_PATH
    rejections = []
    by_table = nn.load_notation_rules(known_tables=crud.TABLE_CONFIG,
                                      rejections=rejections)

    effective, ineffective, rejected = [], [], []

    for r in rejections:
        code = r.get("code", "shape")
        lead = _NOTATION_CODE_LEAD.get(code, "Not applied")
        rejected.append(entry(
            SCOPE_FILE if r["scope"] == nn.SCOPE_FILE else SCOPE_RULE,
            r.get("subject"),
            f"{lead} ― {r['detail']}",
            reason=_NOTATION_CODE_TO_REASON.get(code, REASON_MAPPING_UNAVAILABLE)))

    for table, specs in sorted(by_table.items()):
        for column, spec in sorted(specs.items()):
            on = nn.enabled_rule_names(spec["rules"])
            if on:
                effect = (f"When this column is a join key, both sides of the comparison "
                          f"use the folded value - even if the other column declares "
                          f"nothing (folding one side only would silently lose matches "
                          f"that already held). Nothing is stored: raw values stay raw, "
                          f"and a rule change applies from the next lookup.")
            else:
                effect = ("No rule is switched on, so nothing folds "
                          "- the declaration is valid but comparisons stay raw.")
            effective.append(entry(
                SCOPE_RULE, f"{table}.{column}",
                f"{table}.{column} is declared with normalised notation. "
                f"Rules on: {_names(on) if on else 'none'}. {effect} "
                f"What merges into what is answered as merge groups by "
                f"GET /admin/config/notation/preview?table={table}&column={column} "
                f"- look there first after switching a rule on.",
                fields={"table": table, "column": column,
                        "rules": dict(spec["rules"])}))

    rules_exists = os.path.exists(rules_path)
    file_rejected = any(r["scope"] == nn.SCOPE_FILE for r in rejections)
    n_decls = sum(len(v) for v in by_table.values())
    sources = [
        source("rules", rules_path,
               ("No declaration file - no column has its notation normalised."
                if not rules_exists else
                ("The declaration file could not be read - no column is normalised."
                 if file_rejected else
                 f"{n_decls} declarations are valid.")),
               exists=rules_exists, degraded=file_rejected),
    ]
    settings = [
        setting("implemented_rules", list(nn.IMPLEMENTED_RULES), ORIGIN_DEFAULT,
                rules_path, declared=None,
                detail=("The rules that can actually apply. separator folds runs of '.', "
                        "'_', '-' and spaces into one '-' (to drive '_', the character that "
                        "joins map keys, out of values). case upper-cases ASCII a-z only - "
                        "PostgreSQL's upper() and Python's upper() disagree outside ASCII "
                        "(measured: 'straße'), so it is narrowed to where both engines "
                        "agree. zero_pad is not on the list - declaring it true is refused.")),
        setting("separator_target", nn.SEPARATOR_TARGET, ORIGIN_DEFAULT,
                rules_path, declared=None,
                detail=("The one form separators fold into. Why it is not '_' is the point "
                        "of this feature - '_' joins composite map keys, so a value holding "
                        "'_' splits the key it belongs to.")),
        setting("stores_anything", False, ORIGIN_DEFAULT, rules_path,
                declared=None,
                detail=("This feature stores nothing - no derived column, no write hook, "
                        "no re-derivation script. Consumers fold both sides at lookup time, "
                        "so changing a rule leaves nothing to undo or fill in.")),
        setting("map_keys_unchanged", True, ORIGIN_DEFAULT, rules_path,
                declared=None,
                detail=("Splitting and joining map keys is not affected by this declaration. "
                        "wafer_map_metadata is registered under the raw identity, so the "
                        "moment a map key read normalised values, existing map_ids would part "
                        "from their meta rows. That is a data migration, not a setting.")),
    ]
    return build_domain(DOMAIN_NOTATION, DOMAIN_TITLES[DOMAIN_NOTATION],
                        sources, settings, effective, ineffective, rejected)


DOMAIN_BINDING = "binding"

_BINDING_KEY_MEANING = {
    "x": "The map's horizontal coordinate column",
    "y": "The map's vertical coordinate column",
    "val": "The cell value column (what the legend and scoring read)",
    "index": "The sequence column - never derived (there is no naming convention)",
    "key_columns": "The identity columns that name one map",
}


def _resolve_binding() -> dict:
    """맵 좌표/정체성 바인딩이 **키마다** 무엇으로 결정됐는가. DB를 건드리지 않는다.

    WHY THIS DOMAIN EXISTS. 바인딩은 두 파일이 같은 사실을 말할 수 있는 자리이고,
    2026-08-10까지 그 둘이 어긋났을 때 아무도 알 수 없었다 — 선언이 유도를 이기는데
    「무엇이 이겼나」를 묻는 자리가 없었기 때문이다. 이제 우선순위는 키마다
    `선언 > table_config 유도 > 이름을 대고 거절` 하나이고, 이 도메인이 그 결과를 키
    단위로 돌려준다. 「됩니다」가 아니라 **어느 철자가 이겼는지**가 답이다.
    """
    import map_overlay
    from database import crud
    from paths import config_path

    cfg = map_overlay.load_overlay_config()
    declared_tables = set((cfg.get("table_bindings") or {}).keys())
    declared_tables = {t for t in declared_tables if not t.startswith("__")}
    tables = sorted(set(crud.TABLE_CONFIG or {}) | declared_tables)

    overlay_path = config_path("map_overlay_config.json")
    table_path = config_path("table_config.json")
    sources = [
        source("map_overlay_config", overlay_path,
               "Where exceptions to the coordinate binding are declared. A key not here "
               "is inherited from table_config - never filled from a naming convention."),
        source("table_config", table_path,
               "The base of the binding. map_key_columns is the canonical identity, and "
               "the x/y/value columns are derived here too."),
    ]

    candidates = map_overlay.resolve_value_column_candidates(cfg)

    effective, ineffective, rejected = [], [], []
    for table in tables:
        if table.startswith("__"):
            continue
        binding, prov, _guessed = map_overlay.resolve_binding_parts(cfg, table)
        refused = [k for k, p in prov.items() if p["origin"] == map_overlay.ORIGIN_REFUSED]
        # What the derivation WOULD have said, so a declaration can be told apart
        # from a restatement of it. Until 2026-08-14 this domain only offered the
        # operator a hypothetical ("if table_config says the same, you may delete
        # it") — which is the one thing the operator cannot evaluate from the
        # screen, and it is why a duplicated `key_columns` survived long enough to
        # drift (R-2026-08-14-A F3).
        derived, _dguessed = map_overlay.derive_binding_parts(table, candidates)
        block = ((cfg.get("table_bindings") or {}).get(table)) or {}
        stated_reason = block.get("__reason") if isinstance(block, dict) else None
        # 맵으로 해석되지 않고 선언도 없는 테이블은 이 도메인의 관심사가 아니다 —
        # 전부 실으면 「맵이 아니다」가 95줄의 소음이 되어 진짜 거절을 덮는다.
        if binding is None and not refused and table not in declared_tables:
            continue

        for key in map_overlay.BINDING_KEYS:
            p = prov.get(key) or {}
            origin, value = p.get("origin"), p.get("value")
            meaning = _BINDING_KEY_MEANING.get(key, key)
            subject = f"{table}.{key}"
            if origin == map_overlay.ORIGIN_REFUSED:
                rejected.append(entry(
                    SCOPE_SETTING, subject,
                    f"`{table}` declares {key} as {_as_json(value)}, a column table_config "
                    f"does not have - so this table's whole binding is refused. Delete it, "
                    f"do not fix it: a declaration beats derivation, so a wrong spelling "
                    f"does not come back by editing, and a deleted key is inherited from "
                    f"table_config. ({meaning})",
                    reason=REASON_MAPPING_UNAVAILABLE,
                    fields={"table": table, "key": key, "declared": value}))
            elif origin == map_overlay.ORIGIN_DECLARED:
                would_be = derived.get(key)
                restates = would_be == value
                fields = {"table": table, "key": key, "value": value,
                          "origin": origin, "derived_would_be": would_be,
                          "restates_derivation": restates}
                if restates:
                    # "delete it", not "you may delete it": the condition was
                    # checked here. The values are equal, so deleting the
                    # declaration cannot change one character on the screen.
                    detail = (f"`{table}` declares {key} as {_as_json(value)}, the same "
                              f"value table_config derives - this declaration changes "
                              f"nothing. Delete it: two copies of one truth part one day, "
                              f"and a duplicate hides whether the derivation still runs. "
                              f"({meaning})")
                else:
                    detail = (f"`{table}` {key} is {_as_json(value)}, declared by "
                              f"map_overlay_config (a declaration beats derivation). "
                              f"table_config " +
                              (f"derives {_as_json(would_be)}"
                               if would_be is not None else "cannot derive this key") +
                              f". {meaning}.")
                    # An override without a stated reason is not a declaration, it
                    # is drift (R-2026-08-14-A F3). Scoped to the IDENTITY key on
                    # purpose: in this repo overriding x/y/val is the normal state
                    # (every fixture table namespaces its coordinate columns) and
                    # `__derived_note` already states that reason collectively, so
                    # demanding a per-table reason there would be noise, and a
                    # requirement that fires on everything gets ignored.
                    if key == "key_columns":
                        # `override_reason`, not `reason`: the envelope's own `reason`
                        # is the closed runtime vocabulary and must not be shadowed
                        # by free prose inside `fields`.
                        fields["reason_declared"] = bool(stated_reason)
                        if stated_reason:
                            fields["override_reason"] = stated_reason
                        else:
                            detail += (" ⚠️ This block has no `__reason` - an identity "
                                       "declared differently from table_config must say "
                                       "what is known that makes it different. An "
                                       "override with no reason is drift, not a declaration.")
                effective.append(entry(SCOPE_SETTING, subject, detail, fields=fields))
            elif origin == map_overlay.ORIGIN_INHERITED:
                effective.append(entry(
                    SCOPE_SETTING, subject,
                    f"`{table}` {key} is {_as_json(value)}, inherited from table_config "
                    f"- map_overlay_config declares nothing. {meaning}. "
                    f"Change table_config and this value follows.",
                    fields={"table": table, "key": key, "value": value,
                            "origin": origin}))
            else:
                ineffective.append(entry(
                    SCOPE_SETTING, subject,
                    f"Nobody states `{table}` {key} - it is not declared and table_config "
                    f"does not derive it. {meaning}. "
                    f"It is not filled from a naming convention: a missing column sent as "
                    f"declared would match 0 on that axis, and the screen would read that "
                    f"as no match.",
                    reason=REASON_NOT_DECLARED,
                    fields={"table": table, "key": key}))

        if binding is None and not refused:
            rejected.append(entry(
                SCOPE_RULE, table,
                f"`{table}` does not resolve as a map - x/y/val/key_columns must all be "
                f"stated and some are not. Refused rather than answered in part (guessed "
                f"coordinates make 0 matches look normal).",
                reason=REASON_MAPPING_UNAVAILABLE, fields={"table": table}))

    return build_domain(DOMAIN_BINDING, DOMAIN_TITLES[DOMAIN_BINDING],
                        sources, [], effective, ineffective, rejected)


# ---------------------------------------------------------------------------
# ledger — 소스 선언과 어휘 확장 (판정 R-2026-08-15-M)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# catalog — 셋업 순서의 ① 걸음 (S-180 ⓐ)
# ---------------------------------------------------------------------------

DOMAIN_CATALOG = "catalog"

#: 이 도메인이 읽는 파일. 값은 «로더의» 상수이고 여기서 경로를 조립하지 않습니다.
CATALOG_SOURCE_KEY = "tables"


def _resolve_catalog() -> dict:
    """① 표 — 「무엇이 «있는가»」. 셋업 여섯 걸음의 첫 걸음입니다.

    🔴 **판정은 카탈로그 «어댑터»가 합니다.** 표 하나씩 `setup_bundle._adapt_physical_catalog`
    에 먹이면 그 함수가 «이미 하는» 세 가지 답이 그대로 세 모집단이 됩니다 —
    관계를 «내면» effective, `invalid_catalog` 로 «던지면» rejected, 아무것도 «안 내면»
    ineffective. 조건을 여기서 다시 쓰면 카탈로그가 「먹었나」에 답하는 자리가 둘이 되고,
    갈라지는 날 둘 다 그럴듯합니다. 이 파일에 거절 조건은 «한 줄도» 없습니다.

    ⚠️ 「컬럼이 없어 건너뛴 표」가 왜 결함이 «아니라» ineffective 인가: 어댑터는 그런 표를
    조용히 지나갑니다(`continue`). 선언은 «있는데» 읽는 쪽이 쓸 수 없는 상태이고, 그것이
    `not_declared` 의 뜻 그대로입니다 — 「효과에 필요한 선언이 없음」. 새 사유 낱말을
    만들지 않았습니다.

    ⚠️ 그리고 `open(`/`json.load` 가 이 함수에 «없습니다». 파일을 여는 것은 로더의 일이고,
    그 드리프트 단언이 계약 시험에 있습니다.
    """
    from database import crud
    from ledger import setup_bundle
    import validation

    effective, ineffective, rejected = [], [], []

    document, load_error = {}, None
    try:
        document = crud.load_table_config_or_raise()
    except Exception as exc:
        load_error = "%s: %s" % (exc.__class__.__name__, exc)

    sources = [source(
        CATALOG_SOURCE_KEY, crud.CONFIG_PATH,
        "The table declarations. While this file cannot be read, every later step loses the tables it reads.",
        degraded=bool(load_error))]

    if load_error:
        rejected.append(entry(
            SCOPE_FILE, os.path.basename(crud.CONFIG_PATH),
            "The table declaration file could not be read (%s). Without tables, derivation, "
            "confirmation, joins, the ledger and the walk have nothing to point at." % load_error,
            reason=REASON_MAPPING_UNAVAILABLE))
        return build_domain(DOMAIN_CATALOG, DOMAIN_TITLES[DOMAIN_CATALOG], sources, [],
                            effective, ineffective, rejected)

    for name, declared in sorted((document or {}).items(), key=lambda kv: str(kv[0])):
        if str(name).startswith("__"):
            continue
        try:
            adapted = setup_bundle._adapt_physical_catalog({name: declared})
        except validation.DeclarationValidationError as exc:
            # 🔴 사유는 «거절문 그대로»입니다. 여기서 다시 쓰면 거절문의 둘째 철자가 됩니다.
            rejected.append(entry(
                SCOPE_RULE, name,
                "`%s` failed catalogue validation - %s: %s"
                % (name, exc.path, exc.message),
                reason=REASON_MAPPING_UNAVAILABLE,
                fields=exc.to_mapping()))
            continue

        relation = adapted.get(name)
        if relation is None:
            ineffective.append(entry(
                SCOPE_RULE, name,
                "`%s` is declared but its `column_types` is empty, so the catalogue does not "
                "read it. Write its columns and the later steps can use this table." % name,
                reason=REASON_NOT_DECLARED))
            continue

        effective.append(entry(
            SCOPE_RULE, name,
            "`%s` stands in the catalogue with %d columns." % (name, len(relation.get("columns") or {})),
            fields={"columns": sorted(relation.get("columns") or {}),
                    "composite_key": list(relation.get("composite_key") or [])}))

    return build_domain(DOMAIN_CATALOG, DOMAIN_TITLES[DOMAIN_CATALOG], sources, [],
                        effective, ineffective, rejected)


DOMAIN_LEDGER = "ledger"

#: One English title per domain (lead 909ea2052 ②) — three domains are built in two places each,
#: and a literal per call site is how two builds of one domain come to say two names.
DOMAIN_TITLES = {
    DOMAIN_CHAIN: "Derived (chain rules)",
    DOMAIN_ENRICHMENT: "Enrichment auto-confirm",
    DOMAIN_NOTATION: "Notation normalisation",
    DOMAIN_BINDING: "Map coordinate and identity binding",
    DOMAIN_CATALOG: "Table catalogue",
    DOMAIN_LEDGER: "Ledger declaration (sources and vocabulary)",
    DOMAIN_WALK: "Walk seats",
}


def _resolve_ledger() -> dict:
    """원장의 선언 — 소스와 어휘가 «한 파일»(`ledger_config.json`)에 있습니다.

    🔴 **두 번째 판정기를 만들지 않는다**(지시서 §1). admin의 저장 3단째가 묻는
    「먹었는가」는 이 도메인 하나로 답한다. 새 조립기를 세우면 같은 사실이 두 화면에서 다른
    문장으로 나오고, 그 순간 「사람이 읽을 문장은 서버가 만든다」는 계약이 깨진다.

    두 파일을 한 도메인에 넣는 이유: 운영자가 하는 일이 하나이기 때문이다 — 「테이블을
    원장에 이었다」. 소스는 섰는데 그 소스가 쓰려는 낱말이 안 실렸으면, 그건 두 도메인의
    문제가 아니라 한 여정의 실패다.
    """
    from ledger import config as ledger_config

    sources_path = ledger_config.config_path()
    effective, ineffective, rejected = [], [], []

    # ---- 소스 선언
    document, load_error = {}, None
    read_path = sources_path
    sample_path = ledger_config.sample_path(read_path)
    if not os.path.exists(read_path) and os.path.exists(sample_path):
        read_path = sample_path
    try:
        with open(read_path, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except FileNotFoundError:
        document = {}
    except Exception as e:
        load_error = f"{e.__class__.__name__}: {e}"

    if load_error:
        rejected.append(entry(
            SCOPE_FILE, os.path.basename(sources_path),
            f"The source declaration file could not be read ({load_error}). While it "
            f"cannot be read, no table is translated into the ledger.",
            reason=REASON_MAPPING_UNAVAILABLE))
    else:
        declared_sources = (document.get("sources") or {})
        for name, declaration in sorted(declared_sources.items()):
            if str(name).startswith("__"):
                continue
            kind = (declaration or {}).get("kind", ledger_config.SOURCE_KIND_LINEAGE)
            try:
                ledger_config.validate({"sources": {name: declaration}},
                                       origin=read_path)
            except Exception as e:
                rejected.append(entry(
                    SCOPE_RULE, name,
                    f"Source `{name}` failed validation - {e}",
                    reason=REASON_MAPPING_UNAVAILABLE,
                    fields={"source": name, "kind": kind}))
                continue
            version = ledger_config.translator_version(
                {"version": document.get("version", 1),
                 "sources": {name: declaration}}, name)
            effective.append(entry(
                SCOPE_RULE, name,
                f"`{name}` translates in the {kind} grammar. It stamps the provenance "
                f"{version} on every atom, so each claim can be traced to the rule that "
                f"made it.",
                fields={"source": name, "kind": kind, "translator_ver": version,
                        "subject_types": list(declaration.get("subject_types") or [])}))

    # ---- 어휘 — 선언이 «유일한» 출처
    # 🔴 이 자리는 낱말을 «두 출처»로 갈라 보고했습니다 — 코드가 싣는 것과 선언이 늘린 것.
    #    그 갈래도 그것을 만들던 확장 파일도 없어졌습니다. 선언 하나가 낱말을 정하므로
    #    보고도 하나입니다: 「선언이 무엇을 싣고, 그중 무엇이 아직 발화되지 않나」.
    declared_vocabulary = (document.get("vocabulary") or {})
    if not declared_vocabulary:
        ineffective.append(entry(
            SCOPE_FILE, os.path.basename(sources_path),
            "The declaration has no vocabulary - no predicate can be stated and every atom "
            "is refused. Not 'not grown yet': the gate has no predicate to let through.",
            reason=REASON_NOT_DECLARED))
    else:
        emitters = _ledger_emitted_predicates(document)
        for key in sorted(declared_vocabulary):
            name = str(key).split("@", 1)[0]
            effective.append(entry(
                SCOPE_RULE, name,
                f"`{name}` is declared. The gate checks atoms against its signature, "
                f"and the walk's `follow` accepts it.",
                fields={"predicate": name, "origin": "declaration"}))
        # 「낱말은 실렸는데 아무도 발화하지 않는다」 — 선언은 섰지만 여정이 안 끝난 상태.
        # 조용히 두면 운영자는 술어를 등재해 놓고 원자가 안 생기는 이유를 어디서도 못 읽는다.
        silent = sorted({str(k).split("@", 1)[0] for k in declared_vocabulary} - emitters)
        if silent:
            ineffective.append(entry(
                SCOPE_RULE, ", ".join(silent),
                f"No translator states the declared predicates {', '.join(silent)} - "
                f"they are in the vocabulary and the gate accepts them, but no source "
                f"declaration makes atoms with them, so the ledger has none yet.",
                reason=REASON_NOT_DECLARED,
                fields={"predicates": silent}))


    settings = [
        setting("vocabulary.declared_words", len(document.get("vocabulary") or {}),
                ORIGIN_FILE if document.get("vocabulary") else ORIGIN_DEFAULT,
                sources_path,
                detail="Predicates in the declaration - the gate and the walk accept only these."),
        setting("batch.molecules_per_transaction",
                int((document.get("batch") or {}).get("molecules_per_transaction", 200)),
                ORIGIN_FILE if (document.get("batch") or {}).get(
                    "molecules_per_transaction") else ORIGIN_DEFAULT,
                sources_path,
                detail="Molecules per transaction. A molecule is never split."),
    ]
    sources = [
        source("ledger_config", sources_path,
               "Source -> ledger translation declarations (column mapping, time column, subject types, watermark).",
               degraded=bool(load_error)),
    ]
    return build_domain(DOMAIN_LEDGER, DOMAIN_TITLES[DOMAIN_LEDGER],
                        sources, settings, effective, ineffective, rejected)


def _ledger_emitted_predicates(document: dict) -> set:
    """선언된 소스들이 «발화할 수 있는» 술어 집합.

    번역기가 어느 낱말을 내는지는 코드의 사실이므로 여기서 유도한다 — 선언 파일에 「이
    소스는 X를 낸다」는 칸이 없기 때문이다. 그 칸이 생기는 날(derivation 종류, R-M ⑤)
    이 함수는 선언을 읽는 쪽으로 바뀐다.
    """
    from ledger import config as ledger_config

    out = {"register"}
    for name, declaration in (document.get("sources") or {}).items():
        if str(name).startswith("__") or not isinstance(declaration, dict):
            continue
        kind = declaration.get("kind", ledger_config.SOURCE_KIND_LINEAGE)
        if kind == ledger_config.SOURCE_KIND_DECLARED:
            # 🔴 이 문법만은 **선언이 직접 말한다** — 다른 셋은 번역기 코드가 낱말을
            # 소유하므로 여기서 유도해야 하지만, 선언형은 `emit`이 곧 그 목록이다.
            # 그래서「등재는 했는데 아무도 발화하지 않는다」가 이 문법으로 소스를 하나
            # 선언하는 순간 «자동으로» 해소된다.
            out.update(str(rule.get("predicate") or "").strip()
                       for rule in (declaration.get("emit") or [])
                       if isinstance(rule, dict) and rule.get("predicate"))
        elif kind == ledger_config.SOURCE_KIND_OBSERVATION:
            out.add(ledger_config.OBSERVATION_PREDICATE)
        elif kind == ledger_config.SOURCE_KIND_TRANSFER:
            out.add(ledger_config.TRANSFER_PREDICATE)
        else:
            for rule in (declaration.get("vocabulary") or {}).values():
                if not isinstance(rule, dict):
                    continue
                if rule.get("lineage") == "parent_child":
                    out.add("derived_from")
                if rule.get("slot_pairing", "none") != "none":
                    out.add("slot_map")
                if rule.get("emit_has_wafer"):
                    out.add("has_wafer")
    return out


# 도메인 등록기. 나머지 config는 여기에 한 줄씩 붙는다.
# 🔴 새 도메인은 **뒤에** 붙인다 — contracts/config_resolve_report의 하네스가
#    `resolve_report()["domains"][0]`로 enrichment를 집는다.
# ---------------------------------------------------------------------------
# walk — 셋업 순서의 ⑥ 걸음 (S-180 ⓓ)
# ---------------------------------------------------------------------------

def _resolve_walk() -> dict:
    """⑥ 걷기 좌석 — 「무엇을 «묻는가»」.

    🔴 **이 걸음에는 자기 파일이 «없습니다».** 좌석이 고르는 이름은 ⑤ 원장 선언의 엔터티이고,
    그래서 「셋업됐나」의 술어는 «걷기 라우트가 이미 쓰는 그 집합»입니다 —
    `ledger_trace_router._collectable_types()`. 그 함수는 `node_type_not_declared` 로 거절할 때
    「declared」로 내미는 «바로 그» 목록을 만듭니다. 여기서 엔터티를 다시 세면 한 선언이
    한 화면에서는 고를 수 있고 다른 화면에서는 거절되는 상태가 생깁니다(그 함수가 자기 주석에
    적어 둔 바로 그 결함입니다).

    ⚠️ **거절이 «없습니다».** 걷기의 거절(`node_type_not_declared`)은 «요청 하나»에 대한
    답이지 셋업의 상태가 아닙니다 — 아무도 안 물었으면 거절할 것도 없습니다. 그래서 이
    걸음의 모집단은 둘뿐이고, 「선언을 못 읽음」만 파일 범위의 rejected 입니다.

    ⚠️ **좌석 자체는 «세지 않습니다».** `client2/src/map2/seating.js` 는 화면 상태이고,
    서버가 그것을 셀 수 있다고 말하는 순간 이 보고가 «모르는 것을 아는 척»합니다.
    """
    effective, ineffective, rejected = [], [], []

    collectable, failure = set(), None
    try:
        from ledger.trace_router import _collectable_types

        collectable = _collectable_types()
    except Exception as exc:
        # HTTPException 은 detail 에 사유를 싣습니다 — 그 문장을 그대로 나릅니다.
        detail = getattr(exc, "detail", None)
        failure = (detail or {}).get("message") if isinstance(detail, dict) else None
        failure = failure or ("%s: %s" % (exc.__class__.__name__, exc))

    sources = [source(
        "entities", "ledger_config.json (entities)",
        "The names a walk seat can pick are the ledger declaration's entities. This step "
        "has no file of its own and stands as far as the Ledger step does.",
        exists=failure is None, degraded=bool(failure))]

    if failure:
        rejected.append(entry(
            SCOPE_FILE, "entities",
            "The declaration could not be read, so the walk cannot say what it can pick - %s" % failure,
            reason=REASON_MAPPING_UNAVAILABLE))
        return build_domain(DOMAIN_WALK, DOMAIN_TITLES[DOMAIN_WALK], sources, [],
                            effective, ineffective, rejected)

    for name in sorted(collectable):
        effective.append(entry(
            SCOPE_NODE_TYPE, name,
            "`%s` can be picked as a seat's `collect`." % name))

    if not effective:
        ineffective.append(entry(
            SCOPE_FILE, "entities",
            "No entity is declared - a seat has no name to pick, so the walk cannot ask "
            "anything. Declare entities in the Ledger step and this fills in.",
            reason=REASON_NOT_DECLARED))

    return build_domain(DOMAIN_WALK, DOMAIN_TITLES[DOMAIN_WALK], sources, [],
                        effective, ineffective, rejected)


_RESOLVERS = {
    # ⓐ 셀업 순서의 첫 걸음. 이 dict 의 순서는 이제 대표를 고르지 않습니다(S-180 ⓐ-0).
    DOMAIN_CATALOG: _resolve_catalog,
    DOMAIN_CHAIN: _resolve_chain,
    DOMAIN_ENRICHMENT: _resolve_enrichment,
    DOMAIN_NOTATION: _resolve_notation,
    DOMAIN_BINDING: _resolve_binding,
    DOMAIN_LEDGER: _resolve_ledger,
    DOMAIN_WALK: _resolve_walk,
}


#: 셋업 «순서» — 이 리스트가 «정본»이고 `docs/guide/SETUP_ORDER.md` 는 그 설명입니다
#: (S-180 ⓒ). 소유자 2026-09-11 「체계적인 셋업이 안 됨」.
#:
#: 🔴 순서가 «코드»에 있어야 하는 이유는 그 문서가 자기 §「지금 없는 것」에 적어 둔 그대로입니다 —
#: 「사람이 이 장을 열어야만 «무엇이 먼저인가»를 알 수 있고, 그것이 결함이다」. 문서만 아는 순서는
#: 화면이 답할 수 없고, 화면이 답하지 못하면 운영자는 «어디가 비었는지»를 파일 여섯 개를 열어
#: 알아내야 합니다.
#:
#: ⚠️ 걸음이 «없는» 도메인이 있습니다(`notation`·`binding`). 그것은 이 순서가 덜 적힌 것이
#: 아니라 그 도메인이 여섯 걸음의 «밖»이라는 뜻이고, 응답에서 `step: null` 로 «보입니다» —
#: 숨기면 화면이 가진 도메인과 이 순서가 다른 세계가 됩니다.
#: 🔴 `after` 는 «문서의 «앞» 줄 그대로»이고, 그것은 «선형이 아닙니다» (판정 317).
#: 처음 이 리스트를 «줄 세워» 적었더니(각 걸음이 앞 걸음에 의존) 이 박스에서 원장이
#: `blocked_by: 4` 로 나왔고, 저는 그것을 「기능이 도는 증거」로 읽었습니다. 반대였습니다 —
#: 원장의 앞은 ④ 가 «아니라» ① 이고, 가상 조인이 «없는» 설치(정당합니다)에서 원장이
#: «영원히 차단»으로 그려집니다. 「이 줄이 참인가」에서 거짓이고, 어느 설치에서나 그렇습니다.
#:
#: ⚠️ ④ 의 앞은 «걸음이 아닙니다** — 오른쪽 표의 UNIQUE 인덱스라는 «DB 상태»이고, 없으면
#: 그 걸음이 «자기» 모집단에서 `no_unique_index` 로 거절합니다. 걸음으로 적으면 없는 의존이
#: 생깁니다.
#:
#: ⚠️ 그리고 여기 있는 것은 «정적 앞»뿐입니다. 문서는 조건부 의존도 적습니다(③·⑤ 가
#: 「파생 표를 쓴다면」 ②③ 에 기댑니다) — 그것은 «소스마다» 달라 이 리스트가 답할 수 없고,
#: 계산하려면 선언을 읽어야 합니다. 별건입니다. 여기서 «추측»하지 않습니다.
SETUP_STEPS = (
    {"step": 1, "name": "Tables", "domain": DOMAIN_CATALOG, "after": None},
    {"step": 2, "name": "Derive", "domain": DOMAIN_CHAIN, "after": 1},
    {"step": 3, "name": "Confirm", "domain": DOMAIN_ENRICHMENT, "after": 1},
    # ⚰️ [판정 652 3걸음] 「4 · 가상 조인」이 여기 있었습니다. 그 문법이 은퇴해 걸음이
    #    아니라 «없는 것»이 됐고, 뒤 둘을 «다시 번호 매깁니다» — 구멍 난 번호는 운영자가
    #    없는 걸음을 찾게 만듭니다. `after` 는 이 리스트가 정본이라 같이 옮겼습니다.
    {"step": 4, "name": "Ledger", "domain": DOMAIN_LEDGER, "after": 1},
    {"step": 5, "name": "Walk seats", "domain": DOMAIN_WALK, "after": 4},
)

#: domain -> 그 걸음. 순서를 «두 번» 적지 않으려고 위에서 만듭니다.
_STEP_OF = {item["domain"]: item for item in SETUP_STEPS}


def _step_is_standing(domain: dict) -> bool:
    """이 걸음이 «서 있는가» — 뒤 걸음이 기댈 수 있는 상태인가 (판정 318).

    🔴 서 있다 = 효과가 «하나 이상» 있고, «파일 범위» 거절이 «없다».

    🔴 그리고 «부분 거절»은 뒤를 막지 않습니다. 처음에 이것을 「거절이 하나라도 있으면 차단」
    으로 적었더니 이 박스에서 걷기가 `blocked_by: 5` 로 나왔는데 그 걷기의 effective 는 «9»
    였습니다 — 「막혔다」와 「이 걸음이 돌고 있다」가 «한 화면에 동시에 참»입니다. 「이 줄이
    참인가」에서 거짓이고, ⓒ-b 에서 고친 거짓 차단과 «같은 부류»입니다.

    ⚠️ 규칙·표·노드 범위의 거절은 그 걸음의 «자기 모집단»에 그대로 보입니다 — 사라지는 것이
    아니라, 뒤 걸음을 막는 근거가 «아닐» 뿐입니다. 운영자가 그것을 읽을 자리는 그 걸음입니다.
    ⚠️ 파일 범위 거절만 다릅니다: 선언을 «못 읽으면» 그 걸음이 무엇을 주는지 «아무도 모르고»,
    뒤 걸음이 기댈 근거가 남지 않습니다.
    """
    counts = domain.get("counts") or {}
    if not counts.get("effective"):
        return False
    return not any((item or {}).get("scope") == SCOPE_FILE
                   for item in domain.get("rejected") or ())


def _annotate_steps(out: list) -> list:
    """각 도메인 봉투에 `step` 과 `blocked_by` 를 «더합니다». 기존 칸은 손대지 않습니다.

    ⚠️ `blocked_by` 는 «이 보고 안»의 앞 걸음만 봅니다. 도메인을 골라서 부르면
    (`resolve_report(["ledger"])`) 앞 걸음이 이 보고에 «없고», 그때는 «모른다»는 뜻으로
    `None` 입니다 — 없는 것을 「안 막혔다」로 읽게 두지 않으려고 `blocked` 를 따로 두지
    않았습니다: 막혔는지는 «전체 보고»가 답하는 질문입니다.
    """
    by_name = {d.get("domain"): d for d in out}
    for domain in out:
        item = _STEP_OF.get(domain.get("domain"))
        domain["step"] = item["step"] if item else None
        domain["blocked_by"] = None
        if not item or item["after"] is None:
            continue
        previous = next((s for s in SETUP_STEPS if s["step"] == item["after"]), None)
        standing = by_name.get(previous["domain"]) if previous else None
        if standing is not None and not _step_is_standing(standing):
            domain["blocked_by"] = previous["step"]
    return out


def resolve_report(domains: list = None) -> dict:
    """등록된 도메인의 해석 보고서. 한 도메인의 실패가 나머지를 삼키지 않는다."""
    names = list(domains) if domains else list(_RESOLVERS)
    out = []
    for name in names:
        resolver = _RESOLVERS.get(name)
        if resolver is None:
            continue
        try:
            out.append(resolver())
        except Exception as e:
            logger.exception("[ConfigResolve] domain '%s' failed", name)
            out.append(build_domain(
                name, name, [], [], [], [],
                [entry(SCOPE_FILE, None,
                       f"This domain's settings could not be resolved ({e.__class__.__name__}).",
                       reason=REASON_MAPPING_UNAVAILABLE)]))
    return {
        "domains": _annotate_steps(out),
        # 클라이언트가 라벨/필터를 **하드코딩하지 않도록** 어휘를 함께 싣는다.
        "vocabulary": {"reasons": list(REASONS), "reason_names": dict(REASON_NAMES),
                       "populations": list(POPULATIONS),
                       "population_names": dict(POPULATION_NAMES),
                       "scopes": list(SCOPES),
                       # 🔴 순서도 «어휘»입니다 — 화면이 걸음 이름을 자기가 적으면 이 리스트와
                       # 갈라지고, 갈라진 쪽은 오류를 안 냅니다.
                       "setup_steps": [dict(item) for item in SETUP_STEPS]},
    }
