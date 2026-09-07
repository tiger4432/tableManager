import os
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import paths                                                     # noqa: E402
from database.database import DEFAULT_PG_URL                     # noqa: E402

# 🔴 [C-20 ㉠] 값도 «순서»도 여기서 짓지 않는다. 이 파일은 기본 URL 을 자기가 적고
#    `env > 기본값` 만 따랐는데, 정본의 순서는 «세 단계»다:
#        env DATABASE_URL  >  <config dir>/database.json  >  DEFAULT_PG_URL
#    즉 사본은 «값»만 같고 «해석»이 달랐다 — 설정 파일로 DB 를 옮긴 설치에서 이 스크립트는
#    조용히 «다른 DB» 를 고쳤을 것이다. 그것이 두 철자의 값이다.
DATABASE_URL, _SOURCE = paths.resolve_database_url(DEFAULT_PG_URL)

def migrate():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        print("[Migration] Adding transaction_id column to audit_logs...")
        try:
            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN transaction_id VARCHAR;"))
            conn.execute(text("CREATE INDEX idx_audit_logs_tx_id ON audit_logs (transaction_id);"))
            conn.commit()
            print("[Migration] Success!")
        except Exception as e:
            print(f"[Migration] Error or already exists: {e}")

if __name__ == "__main__":
    migrate()
