"""[P2] 파일 인제션 체크포인트 테이블 생성 (멱등).

`file_ingestion_checkpoints`는 오프셋 재개와 해시 dedup의 원장이다. 부팅 경로
(웹서버 `create_all` / 워처 `ensure_ingestion_checkpoint_table`)가 자동으로 만들지만,
**프로세스 재기동 없이** 먼저 준비하고 싶을 때 이 스크립트를 쓴다.

실행:
    conda run -n assy_manager python server/scripts/setup_ingestion_checkpoint.py

information_schema 게이트 + checkfirst이므로 여러 번 실행해도 안전하다.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.database import engine  # noqa: E402
from database import models  # noqa: E402


def main():
    created = models.ensure_ingestion_checkpoint_table(engine)
    if created:
        print(f"[OK] Created: {created}")
    else:
        print("[OK] Table 'file_ingestion_checkpoints' already exists — nothing to do.")

    from sqlalchemy import inspect
    inspector = inspect(engine)
    cols = [c["name"] for c in inspector.get_columns("file_ingestion_checkpoints")]
    idx = [i["name"] for i in inspector.get_indexes("file_ingestion_checkpoints")]
    print(f"     columns: {cols}")
    print(f"     indexes: {idx}")


if __name__ == "__main__":
    main()
