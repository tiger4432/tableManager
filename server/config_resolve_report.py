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
    서버가 만든다**(UI 문자열이므로 한국어).

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

logger = logging.getLogger(__name__)


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

POPULATIONS = ("effective", "ineffective", "rejected")

SCOPE_FILE = "file"
SCOPE_SETTING = "setting"
SCOPE_RULE = "rule"
SCOPE_VIEW = "reference_view"
SCOPES = (SCOPE_FILE, SCOPE_SETTING, SCOPE_RULE, SCOPE_VIEW)

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
        parts.append(f"후보 선언: {pairs}")
    else:
        parts.append("후보 선언 없음 (표시 전용)")
    if narrow:
        if declared:
            warnings.append(REASON_SCOPE_UNRESOLVED)
            tail = "같은 값이 서로 다른 {k}에 그대로 확정될 수 있습니다 — 켜기 전에 확인하세요."
        else:
            tail = ("여기에 candidate_for를 선언하면 같은 값이 서로 다른 {k}에 그대로 "
                    "확정됩니다 — 후보 원천으로 쓰지 마세요.")
        unbound_txt = _names(unbound, "/")
        scope_txt = f"{_names(binds, '/')} 키만으로" if binds else "아무 키도 없이"
        parts.append(
            f"⚠️ 이 뷰는 {scope_txt} 조회하므로 판단키 {unbound_txt}을(를) 구별하지 "
            f"못합니다. " + tail.format(k=unbound_txt))
    return {
        "label": label,
        "candidate_for": declared,
        "required_binds": binds,
        "scope_narrow": narrow,
        "warnings": warnings,
        "detail": " · ".join(parts),
    }


def _rule_fields(rule: dict, views: list, knob_on: bool, raw_knob, max_keys: int) -> dict:
    import enrichment_candidates as ec

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
    import enrichment_candidates as ec
    import enrichment_config
    from database import crud

    rules_path = enrichment_config.ENRICHMENT_RULES_PATH
    rejections = []
    # `/enrichment/rules`와 **같은 인자로** 로드한다 — 보고서와 라우트가 다른 답을 내면
    # 보고서가 답하려던 질문 자체가 무의미해진다(같은 신호원 규율).
    rules = enrichment_config.load_enrichment_rules(
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
            f"선언이 반영되지 않았습니다 — {r['detail']}",
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
        origin_note = "파일이 없어 기본값입니다"
    elif not switch_declared:
        origin_note = "파일에 선언이 없어 기본값입니다"
    else:
        origin_note = "파일 선언값입니다"

    settings = [
        setting(ec.GLOBAL_KILL_SWITCH_KEY, switch_on,
                ORIGIN_FILE if (switch_declared and switch_valid) else ORIGIN_DEFAULT,
                settings_path,
                declared=switch_raw if switch_declared else None,
                detail=(f"전역 스위치 = {'ON' if switch_on else 'OFF'} — "
                        f"{origin_note}. OFF면 규칙별 노브와 무관하게 아무 것도 자동 "
                        f"확정하지 않습니다.")),
        setting(ec.MAX_KEYS_SETTINGS_KEY, cap_value,
                ORIGIN_FILE if (cap_declared and cap_valid) else ORIGIN_DEFAULT,
                settings_path,
                declared=cap_raw if cap_declared else None,
                detail=(f"작업 단위당 판단키 프로브 상한 = {cap_value}건. 넘는 키는 "
                        f"확정되지 않고 워크리스트에 그대로 남습니다(유실 아님).")),
    ]
    if switch_declared and not switch_valid:
        rejected.append(entry(
            SCOPE_SETTING, ec.GLOBAL_KILL_SWITCH_KEY,
            f"'{ec.GLOBAL_KILL_SWITCH_KEY}' 값 {_as_json(switch_raw)}은(는) JSON boolean이 "
            f"아니라 무시되었습니다 — 기본값 true(차단하지 않음)로 동작합니다.",
            reason=REASON_MAPPING_UNAVAILABLE))
    if cap_declared and not cap_valid:
        rejected.append(entry(
            SCOPE_SETTING, ec.MAX_KEYS_SETTINGS_KEY,
            f"'{ec.MAX_KEYS_SETTINGS_KEY}' 값 {_as_json(cap_raw)}은(는) 양의 정수가 아니라 "
            f"무시되었습니다 — 기본값 {ec.DEFAULT_MAX_KEYS_PER_UNIT}로 동작합니다.",
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
                f"'{ec.RULE_KNOB}' 값 {_as_json(raw_knob)}은(는) JSON boolean이 아니라 "
                f"무시되었습니다 — 이 규칙은 기본값 OFF로 동작합니다.",
                reason=REASON_MAPPING_UNAVAILABLE, fields=fields))
            continue
        if not knob_declared or raw_knob is False:
            ineffective.append(entry(
                SCOPE_RULE, name,
                (f"'{ec.RULE_KNOB}' 선언이 없습니다 — 자동 확정을 하지 않습니다(기본값 OFF)."
                 if not knob_declared else
                 f"'{ec.RULE_KNOB}': false — 자동 확정을 하지 않습니다."),
                reason=REASON_NOT_DECLARED, warnings=warnings, fields=fields))
            continue
        if not switch_on:
            ineffective.append(entry(
                SCOPE_RULE, name,
                f"'{ec.RULE_KNOB}': true 이지만 전역 스위치 "
                f"'{ec.GLOBAL_KILL_SWITCH_KEY}'가 false라 이 선언까지 도달하지 않습니다.",
                reason=REASON_NOT_REACHED, warnings=warnings, fields=fields))
            continue
        if not declaring:
            ineffective.append(entry(
                SCOPE_RULE, name,
                f"'{ec.RULE_KNOB}': true 이지만 어떤 참조뷰도 'candidate_for'를 선언하지 "
                f"않아 아무 효과가 없습니다. 자동 확정은 후보 컬럼을 추측하지 않습니다 — "
                f"어느 뷰의 어느 결과 컬럼이 {_names(rule.get('target_fields'))}의 후보를 "
                f"나르는지 선언해야 동작합니다.",
                reason=REASON_NOT_DECLARED, warnings=warnings, fields=fields))
            continue

        detail = (f"자동 확정 ON — {_names(sorted(declaring))} 필드를 "
                  f"{sum(len(v) for v in fields['candidate_fields'].values())}개 뷰 선언으로 "
                  f"해석합니다. 후보가 정확히 1개일 때만 쓰고, 이미 값/이력이 있는 셀은 "
                  f"건드리지 않습니다.")
        if warnings:
            detail += " ⚠️ 아래 뷰 경고를 확인하세요."
        effective.append(entry(SCOPE_RULE, name, detail,
                               warnings=warnings, fields=fields))

    rules_exists = os.path.exists(rules_path)
    file_rejected = any(r["scope"] == SCOPE_FILE for r in rejections)
    sources = [
        source("rules", rules_path,
               ("선언 파일이 없습니다 — enrichment 규칙이 하나도 없습니다."
                if not rules_exists else
                ("선언 파일을 읽지 못했습니다 — 어떤 규칙도 반영되지 않았습니다."
                 if file_rejected else
                 f"규칙 {len(rules)}건을 읽었습니다.")),
               exists=rules_exists, degraded=file_rejected),
        source("settings", settings_path,
               ("파일이 없습니다 — 아래 설정은 전부 서버 기본값입니다."
                if not settings_exists else "파일을 읽었습니다."),
               exists=settings_exists),
    ]
    return build_domain(DOMAIN_ENRICHMENT, "Enrichment 자동 확정",
                        sources, settings, effective, ineffective, rejected)


# ---------------------------------------------------------------------------
# virtual_join — 두 번째 슬라이스
# ---------------------------------------------------------------------------

DOMAIN_VIRTUAL_JOIN = "virtual_join"

# 로더의 내부 거부 코드 -> 닫힌 사유 어휘.
#
# `no_unique_index`가 `scope_unresolved`인 것은 편의가 아니라 그 단어의 뜻 그대로다:
# 런타임 어휘에서 이 단어는 「0개 또는 2개 이상이 주장 ― 고르지 않음」이고,
# 조인 키가 오른쪽 행 하나를 지목한다는 것이 보장되지 않은 상태가 정확히 그것이다.
# 나머지(문법 오류·미구현 형태)는 「선언이 파싱/검증에 실패해 반영되지 않음」이라
# `mapping_unavailable`이다. **새 단어를 만들지 않는다** ― 어휘 추가는 계약 변경이다.
_VJ_CODE_TO_REASON = {
    "no_unique_index": REASON_SCOPE_UNRESOLVED,
    "fanout_declared": REASON_MAPPING_UNAVAILABLE,
    "shape": REASON_MAPPING_UNAVAILABLE,
}

# 코드별 한국어 앞머리. 로더가 만든 영문 사유를 그대로 붙이지 않고, 운영자가 무엇을
# 고쳐야 하는지 먼저 말한다(INV-F9-8 ― `detail`은 그가 읽는 최종 문장이다).
_VJ_CODE_LEAD = {
    "no_unique_index":
        "오른쪽 테이블이 조인 키로 유일하다는 보장이 없어 선언을 거부했습니다",
    "fanout_declared":
        "아직 구현되지 않은 조인 형태라 선언을 거부했습니다",
    "shape":
        "선언이 반영되지 않았습니다",
}


def virtual_join_detail(code: str, facts: dict = None, loader_detail: str = "") -> str:
    """virtual join 거부 1건의 **운영자가 읽는 최종 문장**. 서버가 짓는다.

    보고서와 `GET /admin/config/virtual-join/verify`가 **같은 함수**를 쓴다. 갈라 두면
    같은 거부가 두 화면에서 다른 문장으로 나오고, 그 순간 「서버가 문장의 정본」이라는
    계약이 깨진다. `no_unique_index`는 세션이 있어야 나오는 코드라 보고서 경로에서는
    발화하지 않는다 ― 그래서 이 함수가 라우트에서도 불려야 그 분기가 살아 있다.
    """
    facts = facts or {}
    lead = _VJ_CODE_LEAD.get(code, _VJ_CODE_LEAD["shape"])
    # 유일성 거부는 구조화된 사실이 오므로 **온전한 한국어 문장**을 짓는다. 로더의
    # `detail`은 영어 로그 문구라, 그것을 이어 붙이면 운영자가 읽는 최종 문장이
    # 반쯤 영어가 된다(INV-F9-8). 사실이 없는 거부만 영어 사유를 그대로 나른다.
    if code == "no_unique_index" and facts.get("required_index_ddl"):
        return (f"{lead}. {facts['right_table']} 테이블의 "
                f"{_names(facts.get('join_key'), ', ')}을(를) 덮는 UNIQUE 인덱스가 "
                f"없습니다. 다음을 실행해 만드세요: {facts['required_index_ddl']} "
                f"만드는 중 중복 오류가 나면 그 값이 실제로 둘 이상 있다는 뜻이므로 "
                f"데이터를 먼저 정리해야 합니다.")
    return f"{lead} ― {loader_detail}"


def _resolve_virtual_join() -> dict:
    """virtual join 선언의 해석 보고서. **DB를 건드리지 않는다**(config만 읽는다).

    그래서 이 보고서가 답하는 것은 **모양이 유효한가**까지다. 승인은 조인 키를 덮는
    UNIQUE 인덱스의 존재에 달려 있고 그것은 `pg_index`가 아는 사실이라 세션이 필요한데,
    이 라우트는 「DB 질의 0건」이 계약이다(`test_the_report_issues_no_database_queries`).
    그래서 어떤 선언도 여기서 `effective`가 되지 않는다.

    다만 **무엇을 만들어야 하는지는 세션 없이도 말할 수 있다** ― 필요한 인덱스는 선언
    자체(오른쪽 테이블 + 조인 키)로 계산되기 때문이다. 「UNIQUE 인덱스가 없다」만 말하고
    어느 컬럼인지 말하지 않는 거부는 운영자가 행동할 수 없는 거부다.
    실제 존재 여부는 `GET /admin/config/virtual-join/verify`가 답한다.
    """
    import virtual_join_config as vjc
    from database import crud

    rules_path = vjc.VIRTUAL_JOIN_RULES_PATH
    rejections = []
    rules = vjc.load_virtual_join_rules(
        known_tables=crud.TABLE_CONFIG, rejections=rejections)

    effective, ineffective, rejected = [], [], []

    for r in rejections:
        code = r.get("code", "shape")
        rejected.append(entry(
            r["scope"] if r["scope"] in SCOPES else SCOPE_RULE,
            r.get("subject"),
            virtual_join_detail(code, r.get("facts"), r["detail"]),
            reason=_VJ_CODE_TO_REASON.get(code, REASON_MAPPING_UNAVAILABLE)))

    for rule in rules:
        fields = {
            "left_table": rule["left_table"],
            "right_table": rule["right_table"],
            "join_key": [f"{p['left']} = {p['right']}" for p in rule["join_key"]],
            "expose": list(rule["expose"]),
            "unresolved_label": rule["unresolved_label"],
            "required_index": rule["required_index"],
            "required_index_ddl": rule["required_index_ddl"],
        }
        ineffective.append(entry(
            SCOPE_RULE, rule["name"],
            f"선언의 모양은 유효합니다. 다만 승인되려면 {rule['right_table']} 테이블의 "
            f"{_names(rule['right_columns'], ', ')}을(를) 덮는 UNIQUE 인덱스가 있어야 "
            f"하는데, 이 화면은 설정 파일만 읽으므로 그 존재 여부를 알지 못합니다. "
            f"확인은 GET /admin/config/virtual-join/verify 로 하세요. 없다면 다음을 "
            f"실행해 만드십시오: {rule['required_index_ddl']} "
            f"그리고 조인을 실행하는 코드가 아직 없어, 승인되더라도 지금은 이 선언이 "
            f"어디에서도 사용되지 않습니다.",
            reason=REASON_NOT_REACHED, fields=fields))

    rules_exists = os.path.exists(rules_path)
    file_rejected = any(r["scope"] == SCOPE_FILE for r in rejections)
    sources = [
        source("rules", rules_path,
               ("선언 파일이 없습니다 ― virtual join 선언이 하나도 없습니다."
                if not rules_exists else
                ("선언 파일을 읽지 못했습니다 ― 어떤 선언도 반영되지 않았습니다."
                 if file_rejected else
                 f"선언 {len(rules)}건이 모양 검사를 통과했습니다.")),
               exists=rules_exists, degraded=file_rejected),
    ]
    settings = [
        setting("uniqueness_gate", "unique_index", ORIGIN_DEFAULT,
                rules_path, declared=None,
                detail=("승인 조건은 하나입니다 ― 조인 키를 덮는 유효한 UNIQUE 인덱스. "
                        "인덱스는 config가 아니라 데이터베이스에 살기 때문에 이후의 어떤 "
                        "쓰기도 그 성질을 깨지 못합니다. 취소된 CREATE INDEX "
                        "CONCURRENTLY가 남긴 무효 인덱스, 부분 인덱스, 표현식 인덱스는 "
                        "유일성을 강제하지 않으므로 인정하지 않습니다.")),
        setting("unresolved_label", vjc.DEFAULT_UNRESOLVED_LABEL, ORIGIN_DEFAULT,
                rules_path, declared=None,
                detail=(f"해소되지 않은 값의 표시 = {vjc.DEFAULT_UNRESOLVED_LABEL}. "
                        f"오른쪽에 맞는 행이 없는 경우와, 행은 있는데 값이 비어 있는 "
                        f"경우를 모두 덮습니다. 둘째를 빼면 분석가는 값이 있다고 "
                        f"읽습니다.")),
    ]
    return build_domain(DOMAIN_VIRTUAL_JOIN, "Virtual Join 선언",
                        sources, settings, effective, ineffective, rejected)


# ---------------------------------------------------------------------------
# notation normalization (표기 정규화)
# ---------------------------------------------------------------------------

DOMAIN_NOTATION = "notation"

_NOTATION_CODE_TO_REASON = {
    "zero_pad_unimplemented": REASON_NOT_REACHED,
    "unknown_rule": REASON_MAPPING_UNAVAILABLE,
    "undeclared": REASON_NOT_DECLARED,
    "would_rewrite_raw": REASON_MAPPING_UNAVAILABLE,
    "key_column": REASON_MAPPING_UNAVAILABLE,
    "shape": REASON_MAPPING_UNAVAILABLE,
}

# 코드별 한국어 앞머리. 로더가 만든 영문 사유를 그대로 붙이지 않고, 운영자가 무엇을
# 고쳐야 하는지 먼저 말한다(virtual join의 `_VJ_CODE_LEAD`와 같은 자세).
_NOTATION_CODE_LEAD = {
    "zero_pad_unimplemented":
        "구현되지 않은 규칙이라 거부했습니다 ― 켜져 있는 것처럼 읽히고 아무 일도 하지 "
        "않는 상태를 만들지 않기 위해, 조용히 무시하지 않고 이름을 붙여 거부합니다",
    "unknown_rule": "알 수 없는 규칙 이름이라 무시했습니다",
    "undeclared": "table_config.json에 선언되지 않은 테이블/컬럼이라 반영하지 않았습니다",
    "would_rewrite_raw":
        "원본 컬럼을 덮어쓰는 선언이라 거부했습니다 ― 이 기능은 원본을 절대 고치지 "
        "않습니다(잘못된 규칙은 규칙을 고쳐 다시 파생하는 것으로 복구하며, 그 복구는 "
        "원본이 그대로 남아 있어야 가능합니다)",
    "key_column":
        "파생 컬럼이 이 테이블의 업무 키에 속해 있어 거부했습니다 ― 파생값이 행의 "
        "정체성을 옮길 수는 없습니다",
    "shape": "선언의 모양이 올바르지 않아 반영하지 않았습니다",
}


def _resolve_notation() -> dict:
    """표기 정규화 선언의 해석 보고서. **DB를 건드리지 않는다**(config만 읽는다).

    이 도메인은 virtual join과 달리 유효 선언이 곧 `effective`다 ― 파생은 쓰기 경로에서
    실제로 실행되어 값을 남긴다. 다만 **아무도 그 값을 읽지 않는다**(1단계)는 사실은
    선언마다 문장으로 따라붙는다. 「먹었다」와 「쓰이고 있다」는 다른 질문이고, 둘을
    붙여 두지 않으면 다음 사람이 맵 키가 이미 정규화된 값으로 조회된다고 읽는다.
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
        lead = _NOTATION_CODE_LEAD.get(code, "선언을 반영하지 않았습니다")
        rejected.append(entry(
            SCOPE_FILE if r["scope"] == nn.SCOPE_FILE else SCOPE_RULE,
            r.get("subject"),
            f"{lead} ― {r['detail']}",
            reason=_NOTATION_CODE_TO_REASON.get(code, REASON_MAPPING_UNAVAILABLE)))

    for table, specs in sorted(by_table.items()):
        for raw_col, spec in sorted(specs.items()):
            on = [n for n in nn.KNOWN_RULES if spec["rules"].get(n)]
            effective.append(entry(
                SCOPE_RULE, f"{table}.{raw_col}",
                f"{table}.{raw_col}의 정규화 표기가 {spec['derived']}에 기록됩니다. "
                f"적용 중인 규칙: {_names(on) if on else '없음(값이 그대로 복사됩니다)'}. "
                f"원본 컬럼 {raw_col}은(는) 절대 수정되지 않으므로, 규칙이 잘못 합쳐진 "
                f"것을 발견하면 이 파일을 고치고 "
                f"server/scripts/rederive_notation_norm.py --apply 로 다시 파생하면 "
                f"됩니다. 다만 지금은 이 값을 읽는 코드가 아직 없습니다(1단계) ― 맵 키 "
                f"분해·필터·조인은 여전히 원본 값을 씁니다.",
                fields={"table": table, "raw_column": raw_col,
                        "derived_column": spec["derived"],
                        "rules": dict(spec["rules"])}))

    rules_exists = os.path.exists(rules_path)
    file_rejected = any(r["scope"] == nn.SCOPE_FILE for r in rejections)
    n_decls = sum(len(v) for v in by_table.values())
    sources = [
        source("rules", rules_path,
               ("선언 파일이 없습니다 ― 표기 정규화가 적용되는 컬럼이 하나도 없습니다."
                if not rules_exists else
                ("선언 파일을 읽지 못했습니다 ― 어떤 컬럼도 정규화되지 않습니다."
                 if file_rejected else
                 f"선언 {n_decls}건이 유효합니다.")),
               exists=rules_exists, degraded=file_rejected),
    ]
    settings = [
        setting("implemented_rules", list(nn.IMPLEMENTED_RULES), ORIGIN_DEFAULT,
                rules_path, declared=None,
                detail=("실제로 적용할 수 있는 규칙입니다. separator는 '.', '_', '-', "
                        "공백의 연속을 '-' 하나로 접습니다(맵 키를 잇는 문자인 '_'를 "
                        "값에서 몰아내는 것이 목적입니다). case는 대문자로 접습니다. "
                        "zero_pad는 목록에 없습니다 ― true로 선언하면 거부됩니다.")),
        setting("separator_target", nn.SEPARATOR_TARGET, ORIGIN_DEFAULT,
                rules_path, declared=None,
                detail=("구분자가 접히는 단일 형태입니다. '_'가 아닌 이유가 이 기능의 "
                        "핵심입니다 ― '_'는 복합 맵 키를 잇는 문자라, '_'를 품은 값은 "
                        "자기가 속한 키를 조각냅니다.")),
        setting("rewrites_raw_column", False, ORIGIN_DEFAULT, rules_path,
                declared=None,
                detail=("원본 컬럼은 어떤 경우에도 수정되지 않습니다. 파생 컬럼에 직접 "
                        "쓰려는 시도도 거부됩니다(원본에서 계산되는 값이므로). 그래서 "
                        "규칙이 틀렸다는 것을 나중에 알아도 되돌릴 것이 없습니다.")),
    ]
    return build_domain(DOMAIN_NOTATION, "표기 정규화 선언",
                        sources, settings, effective, ineffective, rejected)


# 도메인 등록기. 나머지 config는 여기에 한 줄씩 붙는다.
_RESOLVERS = {
    DOMAIN_ENRICHMENT: _resolve_enrichment,
    DOMAIN_VIRTUAL_JOIN: _resolve_virtual_join,
    DOMAIN_NOTATION: _resolve_notation,
}


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
                       f"이 도메인의 설정을 해석하지 못했습니다 ({e.__class__.__name__}).",
                       reason=REASON_MAPPING_UNAVAILABLE)]))
    return {
        "domains": out,
        # 클라이언트가 라벨/필터를 **하드코딩하지 않도록** 어휘를 함께 싣는다.
        "vocabulary": {"reasons": list(REASONS), "populations": list(POPULATIONS),
                       "scopes": list(SCOPES)},
    }
