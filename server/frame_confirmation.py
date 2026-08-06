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

# [D3] 「빌린 기하 위에서 정렬됨」 토큰. 어휘의 정본은 `map_overlay.GEOMETRY_ASSUMED`이고
# 여기 이름을 붙이는 것은 임포트 사이클 없이 롤업 한 줄을 쓰기 위해서다 —
# `test_map_alignment_assumption.py`가 두 철자가 같은지 못 박는다(`bonding_plan`의
# BINDING_* 블록과 같은 규율).
_ASSUMED = "assumed"

# [D-2] 판정 상태가 **전달되지 않았다**는 사실의 이름.
#
# 🔴 왜 `unscored`가 아닌가: 그 낱말은 「채점이 없었다」는 **주장**이고, 이 자리에 오는 실행은
#    대부분 채점이 있었다. 실측 2026-08-06 — `/view`가 `winner: rot0_front`, `margin: 87`로
#    답한 단위의 확정 기록이 `ruling_state: unscored`로 남았다. 한 행이 서로를 부정하는 두
#    문장을 실은 것이고, 그 행을 읽는 층 ⑨는 아무도 보지 않은 것에 대한 진술을 읽는다.
# 🔴 그리고 이 낱말은 `map_alignment.STATE_*`의 구성원이 **아니다** — 일부러 아니다. 저쪽
#    어휘는 「채점이 무엇을 말했나」이고 이것은 「그 말이 여기까지 왔나」다. 다른 질문이라
#    같은 집합에 넣으면 소비자가 판정 하나로 읽는다.
STATE_NOT_TRANSPORTED = "state_not_transported"


def accepted_ruling_states() -> set:
    """기록할 수 있는 판정 상태 — **어휘의 정본은 `map_alignment` 하나다.**

    여기 철자를 적으면 그것이 두 번째 집합이 되고, 화면이 본 낱말과 기록된 낱말이 갈리는 날
    양쪽 다 멀쩡해 보인다(`_ASSUMED`·`bonding_plan`의 BINDING_* 블록과 같은 규율).
    `STATE_NOT_CONSIDERED`는 후보 하나의 상태이지 판정의 상태가 아니라 들어가지 않는다.
    """
    import map_alignment
    return {map_alignment.STATE_SCORED,
            map_alignment.STATE_NO_WINNER,
            map_alignment.STATE_NOT_SCORABLE}


def __getattr__(name):
    """`ACCEPTED_RULING_STATES`를 **쓸 때** 푼다 (PEP 562).

    `map_alignment`는 이 모듈을 지연 임포트하므로 최상단 임포트도 돌기는 하지만, 이 모듈의
    나머지 임포트가 전부 지연이라 여기만 최상단으로 올리면 임포트 무게가 조용히 바뀐다.
    상수를 여기 복사하는 대신 이 방법을 쓰는 이유는 위 `accepted_ruling_states` 주석과 같다.
    """
    if name == "ACCEPTED_RULING_STATES":
        return accepted_ruling_states()
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


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


def _load_metas_and_basis(db, contributors: list, reference: dict = None) -> tuple:
    """`({(source_table, map_id): meta}, basis_meta)` — DB 사실 두 종류를 **한 번에** 읽는다.

    두 소비자가 있고(기여자별 기하 근거 판정, 확정 메타 쓰기) 둘이 같은 행을 읽으므로 질의를
    두 벌 두지 않는다. 질의는 **테이블마다 한 번**이다(맵 하나씩 읽으면 단위의 맵 수만큼
    왕복이 된다). `_load_metas`가 IN 절을 자기 상한으로 청킹하므로 여기서 다시 자르지 않는다.

    바닥 읽기 실패는 `None`으로 접는다 — 바닥을 못 읽었다고 확정 기록이 통째로 죽으면 안 된다.
    """
    import map_alignment
    import map_overlay

    by_table = {}
    for c in contributors or []:
        t = c.get("source_table")
        if t:
            by_table.setdefault(str(t), set()).add(str(c.get("map_id") or ""))
    metas = {}
    for table, ids in by_table.items():
        metas.update({(table, m): meta
                      for m, meta in map_alignment._load_metas(db, table, sorted(ids)).items()})
    # [D6] 바닥의 메타도 읽는다 — 빌림에 축이 둘이 되면서 「무엇 위에 섰나」를 소스 메타만으로
    # 유도할 수 없다. phys를 **선언한** 맵이 격자만 빌렸을 수 있고, 그 사실은 소스 메타가
    # 아니라 소스와 바닥의 **차이**에만 있다.
    basis_meta = None
    ref = reference or {}
    if ref.get("table") and ref.get("map_id"):
        try:
            basis_meta = map_overlay.load_map_meta(db, str(ref["table"]), str(ref["map_id"]))
        except Exception:
            basis_meta = None
    return metas, basis_meta


def _geometry_bases(metas: dict, contributors: list, basis_meta: dict = None) -> dict:
    """기여자마다 **무엇 위에서 정렬됐는가** → `{(source_table, map_id): 토큰}`.

    🔴 **요청이 실어 오는 값이 아니라 여기서 유도한다.** 클라가 보내면 그것이 같은 사실의
       두 번째 철자가 되고, 낡은 클라 하나가 이 사실을 통째로 흘린다 — 그런데 이 사실은
       정확히 「나중에 가정이 거짓이면 어느 결정이 그 위에 있었나」에 답하려고 남기는 것이라
       흘리면 기록의 존재 이유가 사라진다.

    🔴 **재채점이 아니다.** 이미 DB에 있는 두 사실만 읽는다: 그 맵의 메타가 기하를 선언하고
       있는가, 그리고 이 기여자가 제외됐는가. 판정 규칙 자체는 `map_alignment` 하나에 있다.
    """
    import map_alignment

    out = {}
    for c in contributors or []:
        key = (str(c.get("source_table") or ""), str(c.get("map_id") or ""))
        out[key] = map_alignment.geometry_basis_of(metas.get(key),
                                                   c.get("excluded_reason"),
                                                   basis_meta)
    return out


# ═══ [D7] 확정은 `wafer_map_metadata`까지 간다 (제품 소유자 2026-08-06) ═══════════════════
#
# 종전에 사슬은 `frame_confirmation`에서 끊겼다. 제품 소유자가 그것을 목적 사슬의 종점까지
# 잇게 했다: **확정된 좌표계**를 에디터와 계획이 읽을 수 있는 자리에 두는 것.
# 뒤집힌 불변식과 그 근거는 `map_overlay`의 [D7] 블록에 있고 여기서 다시 쓰지 않는다.
#
# 🔴 **머리 한 행과 메타 행은 같은 트랜잭션이다 — 규율이 아니라 구조로.** `apply_batch_updates`는
#    무조건 커밋하고 이 세션은 확정 머리·소스 행이 아직 안 커밋된 채 들어 있는 그 세션이므로,
#    메타 쓰기가 커밋하는 순간 셋이 **한 커밋**으로 나간다. 메타 쓰기가 터지면 머리도 커밋되지
#    않는다(라우트가 롤백한다). 그래서 `commit=False`로 부르면서 메타를 쓰라는 요청은 그
#    구조를 깨는 요청이고 — 커밋 시점이 호출자에게 넘어가는데 메타 쓰기는 자기가 커밋한다 —
#    **조용히 둘로 갈리는 대신 거절한다.**
#
# 🔴 **`user` 서열로 쓴다.** 이것은 사람의 결정이고(`confirmed_by`가 그 사람이다), 그리고
#    그보다 낮은 서열로 쓰면 `custom_script`가 써 둔 `grid_metadata` 셀이 그대로 이겨서
#    **아무것도 안 바뀐 채 200이 나간다** — `e6fcc92`가 방금 고친 실패의 정확히 같은 형태다.
META_SOURCE_NAME = "user"


def _write_confirmed_meta(db, contributors: list, metas: dict, basis_meta: dict,
                          reference: dict, frame: str, mark: dict,
                          ruling: dict = None) -> list:
    """확정된 좌표계를 `wafer_map_metadata`에 남긴다 → 쓴 `(target_table, map_id)` 목록.

    맵마다 한 행이고, **제외된 기여자는 쓰지 않는다** — 제외된 소스는 어디에도 정렬되지
    않았고 확정된 좌표계를 갖지 않는다(`geometry_basis_of`와 같은 규율).
    무엇을 쓰고 무엇을 안 쓰는지는 `map_alignment.confirmed_meta_for`가 정한다 — 여기서
    두 번째 규칙을 만들지 않는다.
    """
    import json

    import map_alignment
    import map_meta_registrar
    from database import crud, models, schemas

    if models.DYNAMIC_TABLES.get(map_meta_registrar.META_TABLE) is None:
        # 메타 테이블이 선언돼 있지 않은 사이트에서 확정 자체가 실패하면 안 된다. 기록은
        # 남고 사슬만 여기서 끝난다 — 그 사실은 로그가 말한다.
        logger.warning("[frame_confirm] '%s' is not a declared table — the confirmed "
                       "coordinate system was not stored", map_meta_registrar.META_TABLE)
        return []

    ref = reference or {}
    basis = {"table": ref.get("table"), "map_id": ref.get("map_id")}
    items, written = [], []
    for c in contributors or []:
        if c.get("excluded_reason"):
            continue
        table = str(c.get("source_table") or "")
        map_id = str(c.get("map_id") or "")
        if not table:
            continue
        # 프레임은 **그 기여자가 적용한 것**이다. 한 판에 여러 소스가 서로 다른 프레임으로
        # 정렬될 수 있고, 그때 판의 대표 프레임을 전부에 쓰면 나머지 맵의 기록이 거짓이 된다.
        applied = c.get("applied_frame") or frame
        # 🔴 배치는 소스 행이 쓰는 것과 **같은 함수**에서 온다(§_placement_of). 여기서 다시
        #    규칙을 쓰면 기록된 시프트와 저장된 원점이 서로 다른 배치를 가리킬 수 있고,
        #    그 둘이 갈리면 화면과 기록이 서로를 부정한다.
        meta = map_alignment.confirmed_meta_for(
            metas.get((table, map_id)), basis_meta, basis, applied, mark,
            _placement_of(c, ruling))
        if meta is None:
            continue
        items.append(schemas.GeneralUpdateItem(
            business_key_val=map_meta_registrar.meta_business_key(table, map_id),
            updates={"target_table": table, "map_id": map_id,
                     "grid_metadata": json.dumps(meta)},
            source_name=META_SOURCE_NAME,
            updated_by=(mark or {}).get("confirmed_by") or "unknown",
        ))
        written.append((table, map_id))
    if not items:
        return []
    batch = schemas.GeneralUpdateBatch(
        updates=items,
        transaction_id=(mark or {}).get("confirmation_uid") or None,
        silent=True)
    crud.apply_batch_updates(db, map_meta_registrar.META_TABLE, batch)
    return written


def resolve_ruling_state(ruling: dict, state=None) -> str:
    """이 판정의 상태 → 기록할 낱말. **채점하지 않는다.**

    🔴 [D-2] `/view`는 상태를 **응답 최상위** `state`에 싣고 `ruling` 안에는 넣지 않는다
       (`map_alignment.build_alignment_view`). 그래서 「`ruling`을 그대로 넘겨라」는 지시를
       그대로 따른 요청은 상태를 통째로 흘렸고, 이 자리가 어휘에 없는 낱말로 기본값을 먹었다.
       고칠 곳은 기본값이 아니라 **전달**이라, 상태는 이제 `state`로 따로 받는다.

    세 갈래이고 그 이상은 만들지 않는다:
      ① 전달됐다 → 어휘 검사만 하고 **그대로** 적는다.
      ② 안 왔는데 판정이 승자를 지명했다 → `scored`. **유도가 아니라 전사(轉寫)다** —
         `build_alignment_view`가 화면의 상태를 정하는 첫 분기가 정확히 `if
         ruling.get("winner")`이고, 여기서 같은 입력에 같은 식을 쓰므로 두 답이 갈릴 수 없다.
      ③ 안 왔고 승자도 없다 → **모른다고 말한다.** 판정만으로는 `no_winner`(채점은 됐는데
         못 갈랐다)와 `not_scorable`(채점 자체가 성립 안 함)이 갈리지 않는다. 실제로
         `no_candidate_scored` 하나가 양쪽 갈래에서 다 나온다. 여기서 표를 만들어 찍으면
         그것이 두 번째 판정 구현이고, 둘이 갈리는 날 화면은 멀쩡한 채 기록만 틀린다.

    🔴 그리고 **자기 판정과 어긋나는 상태는 거절한다.** 승자를 지명한 판정은 정의상 채점된
       판정이다. 「채점 안 됨 + 승자는 rot0_front」는 한 행 안의 모순이고, 그것이 이 결함이
       기본값으로 만들어 내던 바로 그 행이다 — 명시로 도착한다고 참이 되지 않는다.
    """
    import map_alignment

    r = ruling or {}
    winner = r.get("winner")
    given = (state or r.get("state") or "").strip()
    if given:
        if given not in accepted_ruling_states():
            raise ConfirmationRefused(
                "판정 상태 '%s'는 선언된 어휘가 아닙니다. 허용: %s"
                % (given, ", ".join(sorted(accepted_ruling_states()))))
        if winner and given != map_alignment.STATE_SCORED:
            raise ConfirmationRefused(
                "판정이 승자 '%s'를 지명했는데 상태가 '%s'입니다 - 한 기록이 서로를 "
                "부정하는 두 문장을 실을 수 없습니다" % (winner, given))
        return given
    if winner:
        return map_alignment.STATE_SCORED
    return STATE_NOT_TRANSPORTED


def _reject_unreadable_frame(where: str, value):
    """이 낱말이 **프레임인가.** 아니면 거절. 읽히면 그대로 통과시킨다(정규화하지 않는다).

    🔴 [D9, 보드 #23 감사 2026-08-06] **어휘 검사가 한쪽에만 있었다.** 메타 행을 쓰는 쪽은
       `parse_frame`을 통과해야 하는데(`map_alignment.confirmed_meta_for`) 확정 기록 쪽은
       아무 문자열이나 받았다. 실측: `frame="rot45_front"`인 요청이 200으로 끝났고,
       `frame_confirmation.confirmed_frame`에 `rot45_front`가 남았으며 메타 행은 **아예 만들어
       지지 않았다.** 한 요청이 기록 하나에는 답을 남기고 다른 하나에는 안 남기는데 응답은
       성공이다 — 두 기록이 갈리는 가장 조용한 형태다.

    🔴 **어휘의 정본은 `map_alignment` 하나다**(`accepted_ruling_states`와 같은 규율).
       여기서 45를 거절하는 표를 만들면 그것이 두 번째 철자이고, 후보 공간이 언젠가 바뀌면
       둘이 갈린다.

    ⚠️ **`frames`(규칙의 `target_fields`) 값에는 걸지 않는다 — 그것은 프레임이 아니다.**
       `dt_job_lot_slot_attribution`의 대상은 `dt_lot_confirmed`/`dt_slot_confirmed`이고 거기
       들어가는 값은 lot·slot이다. 프레임 검사를 거기까지 넓히면 프레임이 아닌 정답을 거절한다.
    ⚠️ `ruling["winner"]`에도 걸지 않는다. 저것은 **채점기가 무엇을 말했나**의 전사이지
       확정의 주체가 아니고, 메타 행이 읽는 값도 아니라 갈릴 자리가 없다.
    """
    import map_alignment

    from database import crud

    val = crud.clean_str_value(value)
    if val == "":
        return None
    if map_alignment.parse_frame(val) is None:
        raise ConfirmationRefused(
            "%s '%s'은 프레임이 아닙니다 - 회전은 0/90/180/270, 면은 front/back이며 "
            "철자는 'rot<각도>_<면>'입니다" % (where, val))
    return val


def _resolve_frames(rule: dict, frames: dict, frame: str) -> dict:
    """확정된 프레임들 → `{target_field: 프레임}`. **키는 규칙 선언에서 온다.**

    🔴 [D-1] 저장이 `core_frame`/`dt_frame` 두 컬럼이던 시절, 그 두 이름을 선언하지 않은
       규칙의 답은 통째로 NULL로 들어갔고 라우트는 200을 냈다(실측 2026-08-06:
       `dt_job_lot_slot_attribution`). 확정 기록에서 **비어도 되는 마지막 필드**가 「무엇을
       확정했나」다 — 비면 이 기록의 존재 이유가 사라지고, 그런데도 완료로 보인다.

    🔴 **빈 채로 성공하지 않는다.** `frames`도 비고 `frame`도 없으면 거절한다. 화면은
       `frames`를 일부러 비워 보내고 답을 `frame`에 담으므로(2026-08-05 판정), 둘 중
       하나라도 있으면 그것이 답이다.
    """
    from database import crud

    out = {}
    allowed = set(rule.get("target_fields") or [])
    unknown = sorted(k for k in (frames or {}) if k not in allowed)
    if unknown:
        raise ConfirmationRefused(
            "규칙 '%s'이 선언하지 않은 확정 대상입니다: %s"
            % (rule.get("name"), ", ".join(unknown)))
    for k, v in (frames or {}).items():
        val = crud.clean_str_value(v)
        if val == "":
            # 필드 이름만 대고 답을 비우는 것은 같은 구멍에 열쇠만 꽂은 것이다.
            raise ConfirmationRefused(
                "확정 대상 '%s'의 프레임이 비었습니다 - 이름만으로는 무엇을 확정했는지 "
                "말하지 못합니다" % k)
        out[k] = val
    if not out and crud.clean_str_value(frame) == "":
        raise ConfirmationRefused(
            "확정된 프레임이 없습니다 - 무엇을 확정했는지가 이 기록의 내용입니다")
    return out


def record_confirmation(db, rule: dict, decision_key: dict, contributors: list,
                        confirmed_by: str, frames: dict = None,
                        ruling: dict = None, reference: dict = None,
                        enrichment_row_id: str = None, commit: bool = True,
                        frame: str = None, map_table: str = None,
                        columns: dict = None, state: str = None):
    """확정 한 판을 남긴다. **이 모듈에서 쓰는 함수는 이것 하나다.**

    `rule`: 인리치먼트 규칙 선언(`enrichment_config.load_enrichment_rules`가 낸 것).
        단위(`decision_key`)와 확정 대상 필드(`target_fields`)의 정본이 이것이라
        여기에 컬럼명을 하드코딩하지 않는다.
    `decision_key`: {컬럼: 값}. 선언된 결정키를 **전부** 채워야 한다 — 반만 채운 단위의
        확정은 자기가 무엇을 확정했는지 모른다.
    `frames`: {target_field: 프레임 문자열}. 키는 규칙의 `target_fields` 안에 있어야 한다.
        저장도 **이 모양 그대로**다(`decision_key`와 같은 이유·같은 형태) — 컬럼 두 개로는
        첫 규칙의 답만 담기고 나머지 규칙의 답은 조용히 사라진다.
    `frame`·`map_table`·`columns`: **확정의 주체** — 어느 테이블의 어느 좌표 삼중항을 어느
        프레임으로 정렬했나(제품 소유자 판정 2026-08-05: 「`CORE FRAME`은 이름이고 단위는
        `CORE_X`/`CORE_Y`/`C_BN`」). 화면이 보내는 것이 이것이고, `frames`는 비어서 온다.
        `columns`는 `{"x","y","val"}`이며 `val`은 없을 수 있다(점유 전용 실행).
        🔴 `frames`와 `frame` 둘 다 비면 **거절한다.** 아무것도 기록하지 않은 확정은 거절된
        확정보다 나쁘다 — 완료로 보이기 때문이다.
    `state`: `/view` 응답의 **최상위** `state`. 판정 dict 안에 없는 이유는 거기 없기
        때문이다(§`resolve_ruling_state`). 화면의 전사 규칙은 「`ruling`을 복사하고 `state`를
        복사한다」 두 줄이다.
    `contributors`: 소스 하나에 dict 하나.
        {"role", "source_table", "map_id", "source_name",
         "applied_frame", "agreement", "discriminating", "excluded_reason"}
        제외된 소스도 넣는다 — 빠뜨리면 없었던 것인지 거절된 것인지 나중에 구별되지 않는다.
        🔴 `shift_dx`/`shift_dy`는 **더 이상 읽지 않는다**(2026-08-06). 배치는 채점기가
        만든 서버의 사실이라 화면이 알 수 없고, 화면은 실제로 상수 0을 보내고 있었다.
        정본은 `ruling.shift`이고 아래 `_placement_of`가 거기서 가져온다.

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

    frames = _resolve_frames(rule, frames, frame)
    # [D9] 기록 A가 기록 B가 거절하는 프레임을 담지 못하게 한다 — 두 기록이 갈리는 자리
    # 하나를 **입구에서** 닫는다(§_reject_unreadable_frame). 제외된 소스는 어디에도
    # 정렬되지 않았으므로 프레임이 없어도 되고, 그때 값은 비어 있다.
    _reject_unreadable_frame("확정된 프레임", frame)
    for c in contributors or []:
        _reject_unreadable_frame(
            "소스 '%s'의 적용 프레임" % (c.get("map_id") or c.get("role") or "?"),
            c.get("applied_frame"))

    ruling = ruling or {}
    reference = reference or {}
    ruling_state = resolve_ruling_state(ruling, state)
    cols = dict(columns or {})

    weakest, weakest_pri = weakest_contributor(contributors)
    # [D3] 무엇 위에서 정렬됐는가 — 기여자마다. 머리의 `geometry_assumed`는 이 값들의
    # 롤업이지 두 번째 규칙이 아니다(`weakest_source`와 같은 계급).
    # [D7] 같은 읽기가 확정 메타 쓰기의 입력이기도 하다 — 질의를 두 벌 두지 않는다.
    metas, basis_meta = _load_metas_and_basis(db, contributors, reference)
    bases = _geometry_bases(metas, contributors, basis_meta)
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
        # 확정된 값의 정본 — 규칙이 선언한 이름 그대로.
        frames=dict(frames),
        # 첫 선언의 흔적 컬럼. `dt_eqp`/`product`와 같은 계급이고 그 규칙일 때만 채워진다.
        core_frame=frames.get("core_frame"), dt_frame=frames.get("dt_frame"),
        # 확정의 주체 — 어느 좌표를 정렬했나.
        confirmed_frame=frame or None, map_table=map_table or None,
        x_col=cols.get("x") or None, y_col=cols.get("y") or None,
        value_col=cols.get("val") or None,
        # 🔴 기준은 **판정이 선 그 기준**이다 — 여기서 다시 찾지 않는다. 쓰기 시점에 다시
        #    조회하면 그것이 같은 사실의 두 번째 유도이고, 채점과 쓰기 사이에 바닥이 바뀐
        #    바로 그 순간(이 컬럼이 존재하는 이유가 되는 순간)에 갈린다 — 기록은 조작자가
        #    보고 결정한 바닥이 아니라 지금의 바닥을 가리키게 된다. `shift`와 같은 규율.
        reference_table=reference.get("table"),
        reference_map_id=reference.get("map_id"),
        ruling_state=ruling_state,
        ruling_reason=ruling.get("reason_code"),
        winner_frame=ruling.get("winner"),
        margin=_as_int(ruling.get("margin")),
        discriminating=_as_int(ruling.get("discriminating")),
        weakest_source=weakest, weakest_priority=weakest_pri,
        geometry_assumed=any(v == _ASSUMED for v in bases.values()),
        confirmed_by=confirmed_by or "unknown",
        enrichment_row_id=enrichment_row_id,
    )
    db.add(header)

    # 🔴 [2026-08-06] **배치는 요청 본문에서 읽지 않는다.** 제품 소유자가 본 것이 이것이다:
    #    「되긴 하는데 화면에 다른 shift가 뜨는 듯, 계산에 사용된 거 말고」.
    #
    #    화면은 `shift_dx: 0, shift_dy: 0`을 **상수로** 보내 왔고(`client2/src/map2/main.js`),
    #    이 함수는 그것을 그대로 적었으며, 조회(§`live_confirmation` 응답의 `sources[].shift`)가
    #    그것을 되돌려 줬다. 그래서 앵커가 (4,5)로 놓은 판이 기록과 화면에서 (0,0)으로 보였다.
    #    두 필드가 같은 사실을 나르면 갈리고, 갈린 쪽이 화면에 뜬다.
    #
    #    배치는 **채점기가 만든 서버의 사실**이고 화면이 알 수 없는 값이다. 그러므로 정본은
    #    `ruling.shift`(= `candidates[이긴 행].shift`, §map_alignment)이고 이 자리는 그것을
    #    **가리킨다**. 여기서 다시 채점하는 것이 아니다 — 위 docstring의 「쓰기 경로가 다시
    #    채점하지 않는다」는 그대로 지켜진다. 조작자가 본 판정을 그대로 옮겨 적을 뿐이다.
    #
    #    🔴 **이긴 프레임에 선 기여자만** 이 값을 받는다. 조작자가 다른 프레임으로 덮어썼다면
    #    그 프레임에서 채점된 배치는 존재하지 않으므로 **null이지 0이 아니다** — 0은 「원점에
    #    놓았다」는 주장이고, 그것이 방금 고친 거짓말이다.
    for c in contributors:
        name = c.get("source_name") or "unknown"
        _p = _placement_of(c, ruling)
        c_dx = None if _p is None else _p["dx"]
        c_dy = None if _p is None else _p["dy"]
        db.add(models.FrameConfirmationSource(
            confirmation_uid=uid,
            geometry_basis=bases.get((str(c.get("source_table") or ""),
                                      str(c.get("map_id") or ""))),
            role=c.get("role") or "unknown",
            source_table=c.get("source_table") or "unknown",
            map_id=c.get("map_id") or "",
            source_name=name,
            source_priority=_priority_of(name),
            applied_frame=c.get("applied_frame"),
            shift_dx=c_dx,
            shift_dy=c_dy,
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

    # [D7] 확정된 좌표계를 `wafer_map_metadata`까지 나른다 — **같은 트랜잭션에서**.
    # `confirmed_at`은 서버 기본값이라 flush 뒤에 읽는다. 표지가 나르는 것이 출처만이
    # 아니라 **확정의 신원**인 이유는 §_write_confirmed_meta 위 블록에 있다.
    if frame:
        if not commit:
            # 조용히 둘로 갈리는 대신 거절한다(§_write_confirmed_meta).
            import map_meta_registrar
            raise ValueError(
                "record_confirmation(commit=False) cannot also write %s: the metadata "
                "write commits on its own, so the caller's deferred commit and this write "
                "would be two transactions claiming to be one"
                % map_meta_registrar.META_TABLE)
        db.flush()
        mark = {"table": (reference or {}).get("table"),
                "map_id": (reference or {}).get("map_id"),
                "confirmation_uid": uid,
                "confirmed_by": header.confirmed_by,
                "confirmed_at": (header.confirmed_at.isoformat()
                                 if header.confirmed_at else None)}
        wrote = _write_confirmed_meta(db, contributors, metas, basis_meta,
                                      reference, frame, mark, ruling)
        if wrote:
            logger.info("[frame_confirm] %s stored the confirmed coordinate system for %d "
                        "map(s): %s", uid, len(wrote),
                        ", ".join("%s/%s" % p for p in wrote[:5]))

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
        # 규칙이 선언한 이름 그대로. 종전에는 두 이름을 **항상** 실어서, 그 이름을 선언하지
        # 않은 규칙의 응답이 「core_frame: null, dt_frame: null」로 나갔다 — 화면이 방금 한
        # 일을 물었는데 남의 규칙의 빈칸을 돌려받은 것이다.
        "frames": dict(header.frames or {}),
        # 확정의 주체. 「무엇을 확정했나」에 답하는 것이 결국 이 넷이다.
        "confirmed": {"frame": header.confirmed_frame,
                      "map_table": header.map_table,
                      "columns": {"x": header.x_col, "y": header.y_col,
                                  "val": header.value_col}},
        "reference": {"table": header.reference_table, "map_id": header.reference_map_id},
        "ruling": {"state": header.ruling_state, "reason_code": header.ruling_reason,
                   "winner": header.winner_frame, "margin": header.margin,
                   "discriminating": header.discriminating,
                   # [D3] 가정 위에서 나온 판정은 **다른 사실**이다. 판정 dict 안에 두는
                   # 이유는 `/view`의 `ruling`이 같은 자리에 같은 낱말을 싣기 때문이다 —
                   # 화면이 조회와 확정을 같은 코드로 그린다.
                   "geometry_assumed": header.geometry_assumed},
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
                     "excluded_reason": r.excluded_reason,
                     # 이 소스가 **무엇 위에서** 정렬됐는가. 제외된 소스는 정렬되지 않았고
                     # 그 사실은 `excluded_reason`이 이미 말한다.
                     "geometry_basis": r.geometry_basis} for r in rows],
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


def _placement_of(contributor: dict, ruling: dict):
    """이 기여자의 **채점된 배치** `{"dx","dy"}`. 없으면 None이고 None은 (0,0)이 아니다.

    🔴 **철자는 이것 하나다.** 소스 행(`shift_dx/dy`)과 확정 메타의 원점
       (`map_alignment.start_for_placement`)이 같은 배치를 써야 하고, 두 곳이 각자 규칙을
       가지면 갈린다 — 오늘 이 코드베이스가 두 번 값을 치른 모양이다.

    배치는 **채점기가 만든 서버의 사실**이다. 요청 본문의 `shift_dx/dy`는 읽지 않는다
    (화면은 상수 0을 보내 왔다). 정본은 `ruling.shift`(= 이긴 후보 행의 `shift`)다.

    🔴 **이긴 프레임에 선 기여자만** 배치를 갖는다. 조작자가 다른 프레임으로 덮어썼다면
       그 프레임에서 채점된 배치는 존재하지 않는다 — null이지 0이 아니다. 0은 「원점에
       놓았다」는 주장이고 그것이 방금 고친 거짓말이다.
    """
    r = ruling or {}
    sh = r.get("shift") or {}
    if not sh or not r.get("winner"):
        return None
    if (contributor or {}).get("applied_frame") != r.get("winner"):
        return None
    dx, dy = _as_int(sh.get("dx")), _as_int(sh.get("dy"))
    if dx is None or dy is None:
        return None
    return {"dx": dx, "dy": dy}




def _as_int(v):
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
