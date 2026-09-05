from pydantic import BaseModel, ConfigDict, field_validator
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import datetime as dt_pkg

# [성능 최적화] 타임존 객체 캐싱
LOCAL_TIMEZONE = dt_pkg.datetime.now(dt_pkg.timezone.utc).astimezone().tzinfo

class CellData(BaseModel):
    value: Any                          # 현재 표출되고 있는 최종 값
    is_overwrite: bool = False          # 사용자(human)에 의한 고정 여부 (== sources['user'] 존재 여부)
    sources: Dict[str, Any] = {}        # { "user": val, "parser_a": val, ... } 각 소스별 원천 데이터
    updated_by: Optional[str] = "system"
    priority_source: Optional[str] = None # 현재 value를 결정한 소스 명칭

class CellUpdate(BaseModel):
    row_id: str
    column_name: str
    value: Any
    source_name: str = "user" 
    updated_by: Optional[str] = "user"

class AuditLogResponse(BaseModel):
    id: int
    table_name: str
    row_id: str
    column_name: str
    old_value: Any
    new_value: Any
    source_name: str
    updated_by: str
    transaction_id: Optional[str] = None
    business_key: Optional[str] = None
    timestamp: datetime
    is_row_deleted: Optional[bool] = False

    @field_validator("timestamp", mode="after")
    @classmethod
    def convert_to_local(cls, v: datetime) -> datetime:
        if v:
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.astimezone(LOCAL_TIMEZONE)
        return v

    class Config:
        from_attributes = True

class AuditHistoryPage(BaseModel):
    """One page of a row's or a cell's audit history.

    An ENVELOPE, not a bare list, and that is the whole point of it. These two
    endpoints used to return every audit row a cell had ever accumulated, so the
    client had no way to distinguish "this is the complete history" from "this is
    as much of it as the server was willing to send" - and a capped list that
    looks complete is a wrong answer, not a slow one.

    `truncated` is the same word (and the same invariant) `value_suggest` uses
    for the same situation. See server/audit_history.py.

    `row_history_total` EXISTS BECAUSE AN EMPTY CELL PAGE IS NOT "NO HISTORY".
    Machine writes store ONE audit row per ROW, under the literal column name
    `ROW_UPDATE` (crud.py), so `column_name == col` never matches them. Measured
    on the isolated `assy_qa` copy 2026-08-11: 225,586 of 239,786 audit rows
    (94.08%) carry `ROW_UPDATE`, and 225,101 distinct rows have machine history
    and NOT ONE per-column entry - for every one of those, every cell tab is
    empty while the row tab is full. The records were never missing; they were
    missing ON ONE SCREEN, which is why nobody reported it.
    """
    logs: list[AuditLogResponse]
    #: True == there is older history past this page. Show the 더 보기 affordance.
    truncated: bool = False
    #: Feed back as `?cursor=`. Non-null exactly when `truncated` is true.
    next_cursor: Optional[str] = None
    #: Page size actually in force (config `default_limit`, or the caller's
    #: `limit` clamped to `max_limit`). Present so a client can tell "I asked for
    #: 5,000 and got 1,000" without knowing the server's config.
    limit: int
    #: len(logs), so no caller has to count to decide whether to render.
    returned: int = 0
    #: Audit entries on the ROW this cell belongs to - i.e. what the row tab
    #: would page through. Cell route only; `None` on the row route, where
    #: `returned`/`truncated` already describe the same population.
    #:
    #: 🔴 THE ONE FACT THAT DISTINGUISHES THE TWO EMPTY TABS. `returned == 0`
    #:    with `row_history_total == 0` means this row genuinely has no history.
    #:    `returned == 0` with `row_history_total > 0` means the records exist and
    #:    THIS SCREEN CANNOT SHOW THEM. Rendering both as "기록 없음" is the
    #:    silent wrong answer this envelope exists to prevent.
    #:
    #:    Deliberately NOT derived by parsing the machine summary string. That
    #:    string is a RENDERED SENTENCE (`f"{col}: {val}"` joined on ", ", NULL
    #:    written as the Korean word 비어있음) and one of its values is itself
    #:    JSON with its own commas and colons - a live `wafer_map_metadata` row
    #:    reads `grid_metadata: {"grid_cols": 2, "grid_rows": 2, ...}`, so
    #:    splitting on ", " invents a column named `"grid_rows"`. Presentation
    #:    parsed back into data is confidently wrong history.
    row_history_total: Optional[int] = None
    #: True == `row_history_total` is a FLOOR ("N개 이상"), not the exact count.
    #: The count is a capped probe (`audit_history.ROW_TOTAL_PROBE_CAP`) so that a
    #: pathologically deep row cannot turn a disclosure into an O(depth) scan.
    row_history_truncated: bool = False

class AuditLogGroupResponse(BaseModel):
    transaction_id: Optional[str] = None
    total_count: int = 0
    summary_columns: list[str] = []
    logs: list[AuditLogResponse]

class AuditLogGroupPage(BaseModel):
    """One page of the recent-transactions projection behind `/audit_logs/recent`.

    THE SAME ENVELOPE AS `AuditHistoryPage`, AND DELIBERATELY NOT THE SAME LIST
    NAME. That route returns audit rows and calls them `logs`; this one returns
    TRANSACTION GROUPS, each of which carries a `logs` field of its own. Spelling
    both lists `logs` would put two different populations behind one word and
    make the shape read `body.logs[0].logs`, so the list here is `groups` - what
    it actually holds.

    `truncated` and `next_cursor` are the words `audit_history.fetch_page`
    returns, with the same meaning: "there is more history below the last group"
    and "where to resume". They also still travel as `X-Audit-Truncated` /
    `X-Audit-Next-Cursor` response headers, because a caller that already reads
    those keeps working; see the route.
    """
    groups: list[AuditLogGroupResponse]
    #: True == the bounded scan gave up before reaching `limit_groups`.
    truncated: bool = False
    #: Feed back as `?cursor=`.
    #:
    #: ⚠️ THE PAIRING IS WEAKER HERE THAN ON `AuditHistoryPage`, ON PURPOSE. There,
    #: `next_cursor` is non-null exactly when `truncated` is true. Here `truncated`
    #: can be true with a NULL cursor, and that third state is a real answer, not an
    #: oversight: when a live merge grows the projection past `limit_groups` it drops
    #: the tail, so the recorded resume position now sits behind the new end of the
    #: list and naming it would hand back groups the caller already has
    #: (`audit_cache.add_logs_batch`). "There is more, and the position is gone" is
    #: the honest answer; a client that wants the rest reloads from the top.
    next_cursor: Optional[str] = None
    #: The caller's `limit_groups` as it was applied. Unlike `AuditHistoryPage.limit`
    #: this is NOT clamped - what bounds the cost here is the scan ceiling
    #: (`audit_cache.RECENT_DEFAULTS["recent_max_scan_rows"]`), not the group cap,
    #: so asking for more groups buys a shorter walk per group, never a longer walk.
    limit_groups: int
    #: len(groups), so no caller has to count to decide whether to render.
    returned: int = 0

class CellUpdateBatch(BaseModel):
    updates: list[CellUpdate]

class BatchCellPriorityRequest(BaseModel):
    updates: list[Dict[str, Any]]
    source_name: Optional[str] = None
    updated_by: Optional[str] = "user"

class BatchCellSourceDeleteRequest(BaseModel):
    cells: list[Dict[str, Any]]
    source_name: str

class CellUpsert(BaseModel):
    business_key_val: Any
    updates: Dict[str, Any]
    source_name: str = "user"
    updated_by: Optional[str] = "user"

class CellUpsertBatch(BaseModel):
    items: list[CellUpsert]

class GeneralUpdateItem(BaseModel):
    row_id: Optional[str] = None           # PK 기반 업데이트 시 사용
    business_key_val: Optional[Any] = None # 비즈니스 키 기반 업서트 시 사용
    updates: Dict[str, Any]                # { "column_name": value }
    source_name: str = "user"
    updated_by: Optional[str] = "system"

class EffortReport(BaseModel):
    """[V1 계기] 이 트랜잭션 한 건을 완료하는 데 사람이 쓴 **원시 상호작용 카운트**.

    ⚠️ **이 객체가 없는 것과 0인 것은 다르다.** 워커·인제션·체인은 같은 엔드포인트를
    쓰지만 키보드 앞에 사람이 없다 — 그런 요청은 이 필드를 **보내지 않아야** 하고,
    서버는 "미계측"으로 취급해 기록 자체를 남기지 않는다. 0으로 채우면 "공수 0의 완벽한
    교정"으로 집계에 섞여 평균을 조용히 희석시킨다.

    카운트는 **정수**여야 한다. Validation lives in `main._validate_effort`, which never
    clamps and never casts (making a wrong value look plausible is the worst thing that
    can happen to an instrument). EVERY field here is typed `Any` and defaults to None or
    0 **so that pydantic can never reject the request**: a 422 raised while parsing this
    optional blob would take the user's correction down with it. A malformed blob is
    discarded, reported in `effort_error` on the response, and logged - the write always
    goes through (fix round F4, 2026-07-29).

    `nav`는 컨텍스트를 **잃는** 전이, `nav_preserved`는 **유지하는** 전이의 수다.
    면제된 전이를 세지 않고 버리면 그 면제가 저장된 숫자에 굳어 되돌릴 수 없다 —
    소급 산출이 불가능한 계기에서는 그것이 곧 영구히 틀린 기준선이다. 둘 다 원시
    카운트로 보관하고 배점(`nav_preserved` 기본 0)으로 해석한다.
    `nav_preserved`도 **선택**이다 — 아직 이 필드를 보내지 않는 클라는 오류가 아니다.

    ⚠️ **모르는 키는 무시하지 않는다** (총괄 지시 2026-07-29, map-pm 실측).
    pydantic 기본값은 미선언 키를 **조용히 버리는 것**이라, 클라가 `nav_preserved: 5`를
    보내도 에러 없이 사라졌다 — 다른 값은 정상이라 아무것도 고장 나 보이지 않는다.
    **조용히 버려진 값은 애초에 보내지 않은 값과 구별되지 않는다**는 것이 이 프로젝트가
    반복해서 대가를 치른 결함 형태다(유령 수량·절단된 push의 성공 보고·무동작 replace의
    200). 이 계기는 **소급 재계산이 불가능**하므로 몇 달 뒤에 발견하면 기준선이 이미 없다.
    클라와 서버가 같은 저장소에서 함께 배포되므로(독립 배포 스큐 없음) 불일치는 곧 실수이고,
    실수는 시끄러워야 한다. 그래서 `extra="allow"`로 받아 두고 `main._validate_effort`가
    **문제의 키 이름과 함께** 그 사유를 응답(`effort_error`)과 서버 로그에 남긴다.
    But loud is not the same as blocking: the unknown key discards the MEASUREMENT, not
    the correction. `session_id` is likewise `Any` and optional here - an absent one is a
    broken counter, reported the same way, and it must never become a 422 that refuses
    the operator's edit.
    """
    model_config = ConfigDict(extra="allow")

    session_id: Any = None
    key: Any = 0
    mouse: Any = 0
    nav: Any = 0
    nav_preserved: Any = 0


class GeneralUpdateBatch(BaseModel):
    # An unknown TOP-LEVEL key is the same defect as an unknown key inside `effort`, at
    # the opposite end: `{"efort": {...}}` used to return 200 with the whole measurement
    # silently never happening. Accepted here (`extra="allow"`) so the correction still
    # lands, then named in `effort_error` + the log by the endpoint (fix round F7).
    model_config = ConfigDict(extra="allow")

    updates: list[GeneralUpdateItem]
    transaction_id: Optional[str] = None # [Phase 75] 외부에서 주입하는 트랜잭션 ID 지원
    silent: bool = False                 # [Phase 76] True일 경우 WebSocket 브로드캐스트 생략
    replace_map: bool = False            # True일 경우 동일 맵의 기존 레코드를 클린 삭제 후 재기록
    # [U6] Explicit replace_map purge scope: {column: value}. When present it is used
    # verbatim for the purge DELETE (validated against the table's map-key contract);
    # when absent the scope is derived from updates[0] as before. An explicit scope
    # with an empty `updates` list is the intentional erase-all of that scope.
    scope: Optional[Dict[str, Any]] = None
    # [V1 계기] 사람이 이 tx를 완료하는 데 쓴 상호작용 카운트. **선택 필드** —
    # 없으면 "미계측"이며 0이 아니다(EffortReport 주석 참조). 자동 경로(워처·체인 워커·
    # 스크립트)는 crud를 직접 호출하므로 애초에 이 필드를 통과하지 않는다.
    #
    # Declared `Any`, not `Optional[EffortReport]`, on purpose: a non-object blob
    # (`"effort": 5`) would otherwise be rejected by pydantic BEFORE the endpoint runs,
    # and the operator's correction would die with the broken counter. The shape above is
    # still the contract - `main._validate_effort` parses it there, where a bad blob can
    # be discarded and reported without touching the write (fix round F4).
    effort: Optional[Any] = None

class RowDeleteBatch(BaseModel):
    row_ids: list[str]
    user_name: str = "system"

class DataRowBase(BaseModel):
    row_id: str
    table_name: str
    data: Dict[str, CellData]

class DataRowCreate(DataRowBase):
    pass

class DataRowResponse(DataRowBase):
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_validator("created_at", "updated_at", mode="after")
    @classmethod
    def convert_to_local(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v:
            if v.tzinfo is None:
                v = v.replace(tzinfo=timezone.utc)
            return v.astimezone(LOCAL_TIMEZONE)
        return v

    class Config:
        from_attributes = True

class PaginatedDataResponse(BaseModel):
    table_name: str
    total: int
    skip: int
    limit: int
    data: list[DataRowResponse]

class TargetedRowIdRequest(BaseModel):
    offsets: list[int]
    q: Optional[str] = None
    cols: Optional[str] = None  # [Phase 73.6] 검색 대상 컬럼 제한 (comma separated)
    order_by: str = "row_id"
    order_desc: bool = False

class RowIndexDiscoveryRequest(BaseModel):
    q: Optional[str] = None
    cols: Optional[str] = None
    order_by: str = "row_id"
    order_desc: bool = False

# --- Dashboard Schemas ---
class TableStat(BaseModel):
    table_name: str
    row_count: int
    last_updated: Optional[str] = None
    status: str = "Active" # Active / Idle

class UncountedTable(BaseModel):
    """A table the dashboard could not count, WITH the reason.

    🔴 IT IS NOT A ROW OF ZERO. A table whose count failed and a table that is genuinely
    empty are different facts and an operator acts differently on them, so the failed one
    is not put in `table_stats` at all - it is named here. Dropping it silently would read
    as "that table does not exist", which is the same misreading with a different shape.
    """

    table_name: str
    reason: str


class RecorrectionStat(BaseModel):
    """재교정률 — 사람이 같은 셀을 두 번 이상 고친 비율 (SYSTEM_OVERVIEW §1 핵심가치 #1의 계기).

    `rate_pct`는 표본이 없거나(measured_cells=0) 집계가 시간 초과되면 None이다.
    소비자는 **반드시 measured_cells(분모)와 함께** 표시할 것 — 분모 없는 비율은 읽을 수 없다.
    """
    window_days: int
    measured_cells: int          # 창 안에서 사람이 쓴 서로 다른 셀 수 (= 분모)
    recorrected_cells: int       # 그중 서로 다른 트랜잭션으로 2회 이상 쓰인 셀 수 (= 분자)
    rate_pct: Optional[float] = None
    unavailable_reason: Optional[str] = None  # 집계 실패/시간초과 시 사유 (정상 시 None)


class EffortStat(BaseModel):
    """[V1 계기] 완료까지의 상호작용 점수 — SYSTEM_OVERVIEW §1 핵심가치 #1의 **정본** 계기.

    한 교정 tx의 점수 = key×w_key + mouse×w_mouse + nav×w_nav (낮을수록 좋음).
    집계 단위는 **세션별 평균을 낸 뒤 세션 간 평균**(사용자 지정) — 한 사람이 대량 작업한
    세션이 전체 평균을 지배하지 않도록.

    `avg_score`는 표본이 없거나 집계가 실패/시간 초과하면 None이다. 0으로 위장하지 않는다.

    ⚠️ `measured_ratio`(계측된 tx / 전체 사람 tx)를 **반드시 함께** 표시할 것. 계측은
    클라이언트가 보내 줄 때만 이뤄지므로 커버리지가 1.0이 아니며, 분모 없는 평균은 실제로
    측정되지 않은 범위까지 대표하는 것처럼 읽힌다.
    """
    window_days: int
    avg_score: Optional[float] = None   # 세션 평균들의 평균 (표본 0 또는 집계 실패 시 None)
    tx_count: int = 0                   # 창 안에서 계측된 교정 tx 수
    session_count: int = 0              # 그 tx들이 속한 서로 다른 세션 수
    weights: Dict[str, float] = {}      # 이 값을 산출할 때 적용된 배점 (재해석 근거)
    measured_ratio: Optional[float] = None  # 계측 tx / 전체 사람 tx (커버리지 — 집계 실패 시 None)
    unavailable_reason: Optional[str] = None  # 집계 실패/시간초과 시 사유 (정상 시 None)


class DashboardSummaryResponse(BaseModel):
    # 🔴 `total_tables`, `total_rows` and `table_stats` were REMOVED 2026-09-05. One loop
    # produced all three and it was 67% of this route's wall (74 of 80 statements), while
    # nothing read any of them - zero references in client2/src, zero in the shipped
    # bundle, and on the server only this definition and the assignment. Owner ruled the
    # three go together, since `total_rows` was the sum of the same counts.
    today_updates: int
    system_health: str = "Excellent"
    # 신규 필드는 Optional — 구 클라이언트 호환(응답 확장은 하위호환이지만 명시적으로 둔다).
    recorrection: Optional[RecorrectionStat] = None
    effort: Optional[EffortStat] = None
    # 못 센 표. 빈 목록이 정상이고, 비어 있지 않으면 `total_rows`가 그만큼 «모자란» 수다.
    uncounted_tables: list[UncountedTable] = []
