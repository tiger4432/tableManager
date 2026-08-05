"""좌표계 확정 기록(스펙 §0.2 층 ⑧)의 물리 스키마 — **추가 전용 · 멱등**.

    conda run -n assy_manager python server/migrations/add_frame_confirmation.py

[안전 규약]
- DROP도 ALTER TYPE도 없다. 기존 데이터에 손대는 문장이 한 줄도 없다.
- 기존 테이블에는 `create_all`이 컬럼도 인덱스도 추가하지 않는다. 운영 DB로 가는 길은
  이 스크립트뿐이다(`cell_sources`의 형제 인덱스가 같은 이유로
  `scripts/setup_db_performance.py`에 중복 선언돼 있다).
- `cell_sources`는 큰 표다. 그래서 두 가지를 지킨다:
  · 컬럼 추가는 **NULL 허용 · 기본값 없음**이라 PostgreSQL에서 카탈로그만 고친다(표 재작성 없음).
  · 인덱스는 `CONCURRENTLY`로 만든다. 일반 CREATE INDEX는 쓰기를 막고, 지금 이 DB에는
    인제션·체인·그래프 워커가 붙어 있다. CONCURRENTLY는 트랜잭션 안에서 못 도니
    autocommit으로 따로 돌린다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from database.database import engine  # noqa: E402

DDL_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS frame_confirmation (
        id                BIGSERIAL PRIMARY KEY,
        confirmation_uid  TEXT        NOT NULL,
        dt_eqp            TEXT        NOT NULL,
        product           TEXT        NOT NULL,
        version           INTEGER     NOT NULL,
        core_frame        TEXT,
        dt_frame          TEXT,
        reference_table   TEXT,
        reference_map_id  TEXT,
        ruling_state      TEXT        NOT NULL,
        ruling_reason     TEXT,
        winner_frame      TEXT,
        margin            INTEGER,
        discriminating    INTEGER,
        weakest_source    TEXT        NOT NULL,
        weakest_priority  INTEGER     NOT NULL,
        confirmed_by      TEXT        NOT NULL,
        confirmed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        superseded_by     TEXT,
        supersedes_uid    TEXT,
        rule_name         TEXT,
        unit_key          TEXT,
        decision_key      JSONB,
        enrichment_row_id TEXT
    )
    """,
    # 위 CREATE는 IF NOT EXISTS라 이미 만들어진 DB에는 손대지 않는다. 그래서 나중에 생긴
    # 컬럼은 ADD COLUMN으로 따로 붙인다 - 전부 NULL 허용·기본값 없음이라 카탈로그만 고친다.
    "ALTER TABLE frame_confirmation ADD COLUMN IF NOT EXISTS supersedes_uid TEXT",
    "ALTER TABLE frame_confirmation ADD COLUMN IF NOT EXISTS rule_name TEXT",
    "ALTER TABLE frame_confirmation ADD COLUMN IF NOT EXISTS unit_key TEXT",
    "ALTER TABLE frame_confirmation ADD COLUMN IF NOT EXISTS decision_key JSONB",
    # [D3] 이 판이 「같은 웨이퍼」 가정 위에 서 있는가(스펙 §9ⓐ). NULL = 이 어휘가 생기기
    # 전에 남은 판이고, 「가정 아님」이 아니라 「모름」이다 — 기본값을 두면 옛 행들이 한
    # 번도 물어진 적 없는 질문에 「아니오」라고 답하게 된다.
    "ALTER TABLE frame_confirmation ADD COLUMN IF NOT EXISTS geometry_assumed BOOLEAN",
    # [D-1] 확정의 **주체**: 어느 테이블의 어느 좌표 삼중항을 어느 프레임으로 정렬했나.
    # 클라(`client2/src/map2/api.js`)는 이 넷을 이미 보내고 있었고 라우트가 읽지 않았다.
    "ALTER TABLE frame_confirmation ADD COLUMN IF NOT EXISTS confirmed_frame TEXT",
    "ALTER TABLE frame_confirmation ADD COLUMN IF NOT EXISTS map_table TEXT",
    "ALTER TABLE frame_confirmation ADD COLUMN IF NOT EXISTS x_col TEXT",
    "ALTER TABLE frame_confirmation ADD COLUMN IF NOT EXISTS y_col TEXT",
    "ALTER TABLE frame_confirmation ADD COLUMN IF NOT EXISTS value_col TEXT",
    # [D-1] 규칙이 선언한 target_field 그대로의 확정값. `decision_key JSONB`와 같은 이유·모양
    # 이다 — 컬럼 두 개는 첫 규칙 하나의 답만 담고 나머지 규칙의 답은 NULL로 들어갔다.
    "ALTER TABLE frame_confirmation ADD COLUMN IF NOT EXISTS frames JSONB",
    "ALTER TABLE frame_confirmation_source "
    "ADD COLUMN IF NOT EXISTS geometry_basis TEXT",
    # 첫 선언의 흔적 컬럼은 **지우지 않고 NULL을 허용**하는 것으로 물러난다(추가 전용 규율).
    # 다른 decision_key를 가진 규칙에서는 둘 다 NULL이 된다.
    "ALTER TABLE frame_confirmation ALTER COLUMN dt_eqp DROP NOT NULL",
    "ALTER TABLE frame_confirmation ALTER COLUMN product DROP NOT NULL",
    """
    CREATE TABLE IF NOT EXISTS frame_confirmation_source (
        id                BIGSERIAL PRIMARY KEY,
        confirmation_uid  TEXT    NOT NULL,
        role              TEXT    NOT NULL,
        source_table      TEXT    NOT NULL,
        map_id            TEXT    NOT NULL DEFAULT '',
        source_name       TEXT    NOT NULL,
        source_priority   INTEGER NOT NULL,
        applied_frame     TEXT,
        shift_dx          INTEGER,
        shift_dy          INTEGER,
        agreement         INTEGER,
        discriminating    INTEGER,
        excluded_reason   TEXT
    )
    """,
    # 판 번호 경합을 애플리케이션 락이 아니라 여기서 막는다.
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_frame_conf_uid "
    "ON frame_confirmation (confirmation_uid)",
    # 판 번호의 유일성을 실제로 강제하는 것은 이것이다(단위의 정본이 규칙 선언이므로).
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_frame_conf_rule_unit_ver "
    "ON frame_confirmation (rule_name, unit_key, version)",
    # 「이 단위의 현행 판」 — 지난 판이 쌓여도 이 인덱스는 안 자란다.
    "CREATE INDEX IF NOT EXISTS idx_frame_conf_rule_live "
    "ON frame_confirmation (rule_name, unit_key) WHERE superseded_by IS NULL",
    # [D3] 「어느 결정이 가정 위에 서 있나」. 부분 인덱스라 가정 없는 판은 안 들어간다.
    # models.py에도 같은 선언이 있다.
    "CREATE INDEX IF NOT EXISTS idx_frame_conf_assumed "
    "ON frame_confirmation (rule_name, unit_key) WHERE geometry_assumed",
    # 첫 선언의 흔적 색인. 다른 규칙에서는 두 컬럼이 NULL이고 UNIQUE는 NULL을 서로 다르게
    # 보므로 아무것도 막지 않는다 - 지우지 않는 것은 추가 전용 규율 때문이다.
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_frame_conf_unit_ver "
    "ON frame_confirmation (dt_eqp, product, version)",
    "CREATE INDEX IF NOT EXISTS idx_frame_conf_live "
    "ON frame_confirmation (dt_eqp, product) WHERE superseded_by IS NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_frame_conf_src_unique "
    "ON frame_confirmation_source (confirmation_uid, role, source_table, map_id)",
    "CREATE INDEX IF NOT EXISTS idx_frame_conf_src_lookup "
    "ON frame_confirmation_source (confirmation_uid)",
    # 층 ⑨(계획)의 조회 방향 — 「이 맵이 어느 확정의 기여자였나」. 위 UNIQUE는 선두가
    # confirmation_uid라 이 질문에 쓰이지 못한다. models.py에도 같은 선언이 있다.
    "CREATE INDEX IF NOT EXISTS idx_frame_conf_src_map "
    "ON frame_confirmation_source (source_table, map_id)",
]

# 파생 셀의 확정 도장. NULL = 확정된 좌표계에서 파생된 것이 아님(기존 행 전부의 상태).
DDL_STAMP_COLUMN = (
    "ALTER TABLE cell_sources ADD COLUMN IF NOT EXISTS confirmation_uid TEXT"
)

DDL_STAMP_INDEX = (
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sources_confirmation "
    "ON cell_sources (confirmation_uid, table_name, row_id) "
    "WHERE confirmation_uid IS NOT NULL"
)


def main():
    print("[migrate] frame confirmation record (spec MAP_ALIGNMENT layer 8)")

    with engine.begin() as conn:
        for stmt in DDL_TABLES:
            conn.execute(text(stmt))
        print("[migrate] tables and indices: ok")
        conn.execute(text(DDL_STAMP_COLUMN))
        print("[migrate] cell_sources.confirmation_uid: ok (catalog-only, no rewrite)")

    # CONCURRENTLY는 트랜잭션 밖에서만 돈다.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(DDL_STAMP_INDEX))
        print("[migrate] idx_sources_confirmation: ok (concurrent, writers not blocked)")

    with engine.connect() as conn:
        for t in ("frame_confirmation", "frame_confirmation_source"):
            n = conn.execute(text("SELECT count(*) FROM " + t)).scalar()
            print("[verify] %s exists, rows=%s" % (t, n))
        ok = conn.execute(text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name='cell_sources' AND column_name='confirmation_uid'")).scalar()
        print("[verify] cell_sources.confirmation_uid present:", bool(ok))
        idx = conn.execute(text(
            "SELECT indexdef FROM pg_indexes WHERE indexname='idx_sources_confirmation'"
        )).scalar()
        print("[verify] idx_sources_confirmation:", idx)


if __name__ == "__main__":
    main()
