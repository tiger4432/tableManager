"""좌표계 확정 기록 — 맵 정렬 스펙 §0.2 층 ⑧ (사슬에서 **쓰는 유일한 층**).

[이 모듈이 하는 일과 안 하는 일]
하는 일은 하나다: 사람이 내린 「이 설비·제품의 좌표계는 이것이다」를 **한 번의 쓰기로**
남긴다. 계산하지 않는다 — 후보 채점·판정은 `map_alignment`(층 ⑤⑥⑦)의 일이고 이 모듈은
그 결과를 받아 적는다. 재파생도 하지 않는다 — 어느 줄을 다시 만들지는 이미
`frame_trigger_scope`+`SCOPE_ROW_CAP`, `chain_replay` R1/R2, `plan_retraction` 셋이 풀어
놓았고 넷째 철자를 만들지 않는다. 여기가 대는 것은 **그 셋이 범위로 쓸 수 있는 식별자**다.

[enrichment 경로와의 관계 — 대체가 아니다]
확정의 몸짓은 `eqp_product_frame_attribution` 규칙이 이미 갖고 있다(판단 단위가 정확히
`(dt_eqp, product)`, 사람 확인 경로, auto_confirm 스윕과 dry-run, reference_views의 후보
제시, cell_overwrites가 나르는 누가·언제). 그 경로를 이 모듈이 다시 만들지 않는다.
담을 수 없는 셋만 여기서 담는다: **소스 목록**, **소스별 정렬**, **판**.
자세한 근거는 `database/models.py`의 `FrameConfirmation` 주석에 있다.

[퇴화형과의 관계]
지금 운영 중인 것은 `bonding_plan.CANONICAL_FRAME_ROLES`가 **설정 순서로 첫 역할**을 골라
기준 프레임을 삼는 것이다. 그것은 N항 합의 결정을 config 순서에 맡긴 것이고 기록도 판도
소스 목록도 없다. 이 모듈은 그 자리를 대신할 기록을 만든다 — 다만 `bonding_plan`을
여기에 **연결하는 것은 층 ⑨의 작업**이라 이 모듈에는 없다.
"""
import logging
import uuid

from sqlalchemy import func, select

logger = logging.getLogger(__name__)

# 기여자가 없는 확정은 확정이 아니다. 「무엇을 합쳤나」가 비면 이 기록의 존재 이유가 없다.
MIN_CONTRIBUTORS = 1

# 미등재 소스가 crud.get_source_priority에서 받는 값. 여기 숫자를 다시 적지 않으려고
# 이름만 붙여 둔다 — 서열의 정본은 crud 하나다.
UNRANKED = 99

# 확정 한 판이 소비 층(⑨)에 주는 **보증의 세기**. 새 어휘가 아니다 — 두 값 모두 프로젝트가
# 이미 쓰는 정직한 강등 어휘이고, `not_declared`는 `config_resolve_report.REASON_NOT_DECLARED`
# 와 같은 단어다(철자는 여기 적되 `test_plan_frame_basis.py`가 정본과 같은지 못 박는다 —
# `bonding_plan`의 BINDING_* 블록과 같은 규율).
WARRANT_CONFIRMED = "confirmed"
WARRANT_NOT_DECLARED = "not_declared"


class ConfirmationRefused(Exception):
    """확정을 거절한다. 사유 문장은 서버가 만든다(`map_alignment`와 같은 규율)."""


def weakest_contributor(contributors: list, table_name: str = None) -> tuple:
    """기여자들 중 **가장 약한** 것 → (source_name, priority).

    스펙 §0.2 ⑨: 합쳐진 셀은 가장 약한 기여자를 따라간다. 넷 중 셋이 확정이어도 그 셀은
    미확정이다.

    ⚠️ 여기서 새 규칙을 만들지 않는다. `graph_materializer`가 셀 레이어 진실을 고를 때 쓰는
    식과 **같은 식**이다 (`max(candidates, key=lambda s: (_source_priority(s, t), s))`).
    그쪽 `_source_priority`도 결국 `crud.get_source_priority`로 위임하므로, 이 함수와
    그 함수는 같은 서열표를 본다. 동률일 때 이름으로 가르는 두 번째 키까지 같은 이유는
    같은 입력이 실행마다 다른 답을 내면 안 되기 때문이다.
    """
    from database import crud

    names = [c.get("source_name") or "unknown" for c in contributors]
    if not names:
        raise ConfirmationRefused("기여 소스가 없어 확정할 수 없습니다")
    weakest = max(names, key=lambda s: (crud.get_source_priority(s, table_name), s))
    return weakest, crud.get_source_priority(weakest, table_name)


def compose_unit_key(rule: dict, decision_key: dict) -> str:
    """결정키 값들 → 단위 문자열. **새 조립 규칙이 아니다.**

    그 규칙 파생 테이블의 `business_key_val`을 만드는 것과 같은 방식(선언된
    `composite_key_separator`로 `decision_key` 순서대로 join)이라, 이 문자열로
    `eqp_frame_attribution` 행을 그대로 찾을 수 있다. 구분자를 여기 적어 두면 그것이 두 번째
    철자가 되므로 테이블 선언에서 읽는다.
    """
    from database import crud

    cols = list(rule.get("decision_key") or [])
    if not cols:
        raise ConfirmationRefused("규칙 '%s'에 decision_key 선언이 없습니다"
                                  % rule.get("name"))
    missing = [c for c in cols if crud.clean_str_value(decision_key.get(c)) == ""]
    if missing:
        raise ConfirmationRefused(
            "결정 단위가 덜 채워졌습니다 - 확정은 단위 전체에 대해서만 성립합니다. "
            "빠진 결정키: %s" % ", ".join(missing))
    derived = rule.get("derived_table")
    sep = (crud.TABLE_CONFIG.get(derived) or {}).get("composite_key_separator", "_")
    return sep.join(crud.clean_str_value(decision_key.get(c)) for c in cols)


def live_confirmation(db, rule_name: str, unit_key: str):
    """이 단위의 현행 판. 없으면 None. **읽기만 한다.**"""
    from database import models
    return (db.query(models.FrameConfirmation)
              .filter(models.FrameConfirmation.rule_name == rule_name,
                      models.FrameConfirmation.unit_key == unit_key,
                      models.FrameConfirmation.superseded_by.is_(None))
              .order_by(models.FrameConfirmation.version.desc())
              .first())


def live_confirmation_for_maps(db, maps):
    """이 맵들 중 하나라도 **합의에 실제로 올라간** 현행 판. 없으면 None. **읽기만 한다.**

    층 ⑨(계획)가 「이 계획의 좌표계는 확정돼 있나」를 묻는 길이다. 단위를 (설비, 제품)으로
    되짚지 않는 이유는 두 개다. ① 계획은 그 두 값을 모른다 — 계획의 신원은 (lot, slot)이다.
    ② 되짚으려면 계획이 `dt_log`의 컬럼명을 알아야 하는데, 그것은 「결정 단위에 컬럼명을 적지
    마라」와 정면으로 어긋난다. 대신 확정이 **스스로 적어 둔 사실**로 묻는다: 이 맵이 그
    합의의 기여자였는가. 추론이 아니라 기록이므로 틀릴 자리가 없다.

    ⚠️ `excluded_reason`이 붙은 행은 답이 되지 않는다. 제외된 소스는 어디에도 정렬되지
    않았고, 그 판의 기준 프레임을 자기 근거라고 주장할 수 없다. 기록에는 남는다(없었던
    것인지 거절된 것인지 구별해야 하므로) — 이 질문에만 「아니오」다.

    maps: [(source_table, map_id)]. 계획이 선언한 맵 소스 수만큼이므로 상수 개다.
    """
    from sqlalchemy import and_, or_

    from database import models

    pairs = [(str(t), str(m or "")) for (t, m) in (maps or []) if t]
    if not pairs:
        return None
    branches = [and_(models.FrameConfirmationSource.source_table == t,
                     models.FrameConfirmationSource.map_id == m) for (t, m) in pairs]
    return (db.query(models.FrameConfirmation)
              .join(models.FrameConfirmationSource,
                    models.FrameConfirmationSource.confirmation_uid
                    == models.FrameConfirmation.confirmation_uid)
              .filter(models.FrameConfirmation.superseded_by.is_(None),
                      models.FrameConfirmationSource.excluded_reason.is_(None),
                      or_(*branches))
              # 같은 맵이 여러 단위의 합의에 올라갈 수 있다. 최신 판을 고르고 동률은 uid로
              # 가른다 — 같은 입력이 실행마다 다른 답을 내면 그것은 기준이 아니다.
              .order_by(models.FrameConfirmation.version.desc(),
                        models.FrameConfirmation.confirmation_uid)
              .first())


def warrant_of(header) -> str:
    """확정 한 판이 계획에 주는 보증의 세기 → `WARRANT_CONFIRMED` 또는 `WARRANT_NOT_DECLARED`.

    스펙 §0.2 ⑨: 합쳐진 것은 **가장 약한 기여자**를 따라간다. 최약 기여자가 서열에 등재되지
    않은 소스면(= `crud.get_source_priority`의 미등재값 `UNRANKED`) 넷 중 셋이 확정이어도 이
    판은 확정을 보증하지 못한다. **여기서 새 규칙을 만들지 않는다** — 최약 기여자와 그
    서열은 `record_confirmation`이 쓰기 시점에 이미 굳혀 둔 값이고, 이 함수는 그 값을 읽어
    문턱 하나를 적용할 뿐이다.
    """
    if header is None:
        return WARRANT_NOT_DECLARED
    return (WARRANT_NOT_DECLARED
            if int(header.weakest_priority or 0) >= UNRANKED
            else WARRANT_CONFIRMED)


def record_confirmation(db, rule: dict, decision_key: dict, contributors: list,
                        confirmed_by: str, frames: dict = None,
                        ruling: dict = None, reference: dict = None,
                        enrichment_row_id: str = None, commit: bool = True):
    """확정 한 판을 남긴다. **이 모듈에서 쓰는 함수는 이것 하나다.**

    `rule`: 인리치먼트 규칙 선언(`enrichment_config.load_enrichment_rules`가 낸 것).
        단위(`decision_key`)와 확정 대상 필드(`target_fields`)의 정본이 이것이라
        여기에 컬럼명을 하드코딩하지 않는다.
    `decision_key`: {컬럼: 값}. 선언된 결정키를 **전부** 채워야 한다 — 반만 채운 단위의
        확정은 자기가 무엇을 확정했는지 모른다.
    `frames`: {target_field: 프레임 문자열}. 키는 규칙의 `target_fields` 안에 있어야 한다.
    `contributors`: 소스 하나에 dict 하나.
        {"role", "source_table", "map_id", "source_name",
         "applied_frame", "shift_dx", "shift_dy",
         "agreement", "discriminating", "excluded_reason"}
        제외된 소스도 넣는다 — 빠뜨리면 없었던 것인지 거절된 것인지 나중에 구별되지 않는다.

    `ruling`·`reference`: `map_alignment`가 낸 것을 그대로 넘긴다. **여기서 채점하지 않는다** —
        쓰기 경로가 다시 채점하면 조작자가 보고 결정한 것과 기록된 것이 갈릴 수 있고,
        기록해야 하는 것은 조작자가 본 쪽이다.

    머리 한 행 + 소스 N행 + 지난 판 봉인이 **한 트랜잭션**이다. 소스 목록이 반쯤 들어간
    확정은 소스 목록이 있다고 주장하면서 틀린 목록을 주므로, 없느니만 못하다.
    """
    from database import models

    rule_name = rule.get("name")
    unit_key = compose_unit_key(rule, decision_key or {})

    if len(contributors or []) < MIN_CONTRIBUTORS:
        raise ConfirmationRefused(
            "합의에 올린 소스가 없습니다 - 어느 소스들을 합쳤는지가 이 기록의 내용입니다")

    frames = dict(frames or {})
    allowed = set(rule.get("target_fields") or [])
    unknown = sorted(k for k in frames if k not in allowed)
    if unknown:
        raise ConfirmationRefused(
            "규칙 '%s'이 선언하지 않은 확정 대상입니다: %s" % (rule_name, ", ".join(unknown)))

    ruling = ruling or {}
    reference = reference or {}

    weakest, weakest_pri = weakest_contributor(contributors)
    uid = "fc_" + uuid.uuid4().hex

    # 판 번호. 경합은 idx_frame_conf_rule_unit_ver UNIQUE가 잡는다 — 애플리케이션 락을 두면
    # 그 락이 또 하나의 진실이 된다.
    prev_max = db.execute(
        select(func.max(models.FrameConfirmation.version))
        .where(models.FrameConfirmation.rule_name == rule_name,
               models.FrameConfirmation.unit_key == unit_key)
    ).scalar()
    version = int(prev_max or 0) + 1

    header = models.FrameConfirmation(
        confirmation_uid=uid,
        rule_name=rule_name, unit_key=unit_key, decision_key=dict(decision_key or {}),
        # 첫 선언의 흔적 컬럼 — 그 규칙일 때만 채운다(모델 주석 참조).
        dt_eqp=(decision_key or {}).get("dt_eqp"),
        product=(decision_key or {}).get("product"),
        version=version,
        core_frame=frames.get("core_frame"), dt_frame=frames.get("dt_frame"),
        reference_table=reference.get("table"),
        reference_map_id=reference.get("map_id"),
        ruling_state=ruling.get("state") or "unscored",
        ruling_reason=ruling.get("reason_code"),
        winner_frame=ruling.get("winner"),
        margin=_as_int(ruling.get("margin")),
        discriminating=_as_int(ruling.get("discriminating")),
        weakest_source=weakest, weakest_priority=weakest_pri,
        confirmed_by=confirmed_by or "unknown",
        enrichment_row_id=enrichment_row_id,
    )
    db.add(header)

    for c in contributors:
        name = c.get("source_name") or "unknown"
        db.add(models.FrameConfirmationSource(
            confirmation_uid=uid,
            role=c.get("role") or "unknown",
            source_table=c.get("source_table") or "unknown",
            map_id=c.get("map_id") or "",
            source_name=name,
            source_priority=_priority_of(name),
            applied_frame=c.get("applied_frame"),
            shift_dx=_as_int(c.get("shift_dx")),
            shift_dy=_as_int(c.get("shift_dy")),
            agreement=_as_int(c.get("agreement")),
            discriminating=_as_int(c.get("discriminating")),
            excluded_reason=c.get("excluded_reason"),
        ))

    # 지난 판 봉인. 지우지 않고 가리키기만 한다 — 그 아래에서 파생된 셀이 아직 살아 있고,
    # 무엇을 다시 만들지는 이 표가 정하지 않는다.
    prev = live_confirmation(db, rule_name, unit_key)
    if prev is not None:
        prev.superseded_by = uid
        header.supersedes_uid = prev.confirmation_uid

    if commit:
        db.commit()
        db.refresh(header)
    else:
        db.flush()

    logger.info("[frame_confirm] %s v%d %s/%s weakest=%s(%d) sources=%d",
                uid, version, rule_name, unit_key, weakest, weakest_pri, len(contributors))
    return header


def as_payload(db, header) -> dict:
    """확정 한 판을 응답 모양으로. 화면이 「방금 무엇을 했는지」를 다시 조회하지 않고 보게 한다."""
    from database import models

    rows = (db.query(models.FrameConfirmationSource)
              .filter_by(confirmation_uid=header.confirmation_uid)
              .order_by(models.FrameConfirmationSource.source_priority,
                        models.FrameConfirmationSource.role).all())
    return {
        "confirmation_uid": header.confirmation_uid,
        "version": header.version,
        "unit": {"rule": header.rule_name, "unit_key": header.unit_key,
                 "decision_key": header.decision_key or {}},
        "frames": {"core_frame": header.core_frame, "dt_frame": header.dt_frame},
        "reference": {"table": header.reference_table, "map_id": header.reference_map_id},
        "ruling": {"state": header.ruling_state, "reason_code": header.ruling_reason,
                   "winner": header.winner_frame, "margin": header.margin,
                   "discriminating": header.discriminating},
        # 합쳐진 기록은 최약 기여자를 따라간다(스펙 §0.2 ⑨). 화면이 이 값을 다시 유도하지
        # 않도록 계산 결과를 실어 보낸다.
        "weakest": {"source_name": header.weakest_source,
                    "priority": header.weakest_priority},
        "confirmed_by": header.confirmed_by,
        "confirmed_at": (header.confirmed_at.isoformat() if header.confirmed_at else None),
        "supersedes": header.supersedes_uid,
        "sources": [{"role": r.role, "source_table": r.source_table, "map_id": r.map_id,
                     "source_name": r.source_name, "source_priority": r.source_priority,
                     "applied_frame": r.applied_frame,
                     "shift": (None if r.shift_dx is None and r.shift_dy is None
                               else {"dx": r.shift_dx, "dy": r.shift_dy}),
                     "agreement": r.agreement, "discriminating": r.discriminating,
                     "excluded_reason": r.excluded_reason} for r in rows],
    }


def derived_cell_scope(db, confirmation_uid: str):
    """이 확정 아래에서 파생된 셀 — **질의만 돌려준다. 아무것도 지우지 않는다.**

    스펙 §0.3의 「넷째 철자를 만들지 말 것」이 여기 걸린다. 회수는 이미
    `chain_replay.withdraw_source`가 하고, 이 함수는 그것이 범위로 쓸 대상을 셀 단위로
    가리킬 뿐이다(스펙 §0.3 4: 행 컬럼이 아니라 `cell_sources` 단위여야 한다).
    """
    from database import models
    return (db.query(models.CellSource)
              .filter(models.CellSource.confirmation_uid == confirmation_uid))


def _priority_of(source_name: str, table_name: str = None) -> int:
    from database import crud
    return crud.get_source_priority(source_name, table_name)


def _as_int(v):
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
