# 🚀 AssyManager 서버 성능 튜닝 가이드 (인덱스·트라이그램·work_mem)

> **Status:** 🟠 관점 문서 | **Last-verified:** 2026-08-04 | **Owner:** Ops | 상위 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)
>
> 🔴 **이 문서는 기동 절차의 정본이 아닙니다.** 정본은 [SYSTEM_OVERVIEW §7](../overview/SYSTEM_OVERVIEW.md)이고, 환경 구성은 [CONDA_SETUP_GUIDE](./CONDA_SETUP_GUIDE.md)·[NATIVE_POSTGRES_SETUP_GUIDE](./NATIVE_POSTGRES_SETUP_GUIDE.md)입니다. 여기 남은 것은 **대용량 조회를 빠르게 유지하는 관점**뿐입니다.
>
> ⚠️ **2026-08-04 정정 — 이 문서가 인쇄하던 명령 셋이 전부 이 저장소에 존재하지 않았습니다.** `pip install -r requirements.txt`(그런 파일이 없다 — 환경은 conda `environment.yml`), `python scripts/setup_db_performance.py`(실제 경로는 `server/scripts/`), `uvicorn main:app --port 8000`(이 시스템은 그렇게 뜨지 않고 포트도 다르다). 존재하지 않는 명령을 인쇄하는 가이드는 없느니만 못합니다 — 운영자가 도구가 고장 났다고 결론짓습니다. **셋 다 고쳤습니다.**

이 가이드는 대규모 데이터를 초고속으로 조회하는 관점(인덱스·트라이그램·`work_mem`)을 설명합니다.

## 1. 환경 구축 (Environment)

**conda 환경 `assy_manager` 하나입니다.** 정의는 저장소 루트의 `environment.yml`이고, 절차는 [CONDA_SETUP_GUIDE](./CONDA_SETUP_GUIDE.md)가 정본입니다.

```bash
conda env create -f environment.yml    # 최초 1회
conda activate assy_manager
```

🔴 **모든 파이썬 실행은 이 환경에서 합니다.** 시스템 파이썬으로 돌리면 `psycopg2` 부재 등으로 **거짓 실패**가 납니다 — 스크립트를 활성화 없이 부를 때는 `conda run -n assy_manager python <파일>`입니다.

## 2. 데이터베이스 성능 인덱스 (PostgreSQL)

```bash
conda run -n assy_manager python server/scripts/setup_db_performance.py
```

*`btree_gin`·`pg_trgm` 확장을 활성화하고 최신순/품번순/검색용 인덱스를 구성합니다.*

- 🔴 **`create_all`은 이미 존재하는 테이블에 인덱스를 추가하지 않습니다.** 그래서 인덱스 선언이 `server/database/models.py`와 이 스크립트 **두 곳**에 있는 것이고, 새 인덱스는 **둘 다** 고쳐야 실제로 생깁니다.
- 🔴 **`server/scripts/`는 한 방향 문입니다** — 런타임 코드가 그쪽을 import하면 **운영에서만** `ModuleNotFoundError`가 나고 스위트는 초록입니다. 새 로직은 `server/`에 두고 `scripts/`는 argparse만 갖습니다.

## 3. 서버 실행 (Running)

```bash
python run_decoupled_app.py
```

웹서버(:8080) + 워커 4종의 **5프로세스**가 한 번에 뜹니다. 절차·정지·헬스 판정은 [SYSTEM_OVERVIEW §7](../overview/SYSTEM_OVERVIEW.md)이 정본입니다.

## 4. 성능 모니터링 및 검증
서버 콘솔 로그를 통해 현재 쿼리 성능을 실시간으로 확인할 수 있습니다.

*   **정상 수치**: 
    *   `ID Scan`: 0.1s 미만 (인덱스 전용 스캔)
    *   `Entity Fetch`: 0.3s 미만 (2,500건 기준)
    *   `Total`: 0.5s 미만 (최적의 상태)

## 5. 성능 유지보수 팁 (Maintenance)
*   **검색어 최소 길이**: 풀텍스트 검색 시 가급적 **3글자 이상** 입력을 권장합니다 (Trigram 인덱스 최적 성능 지점).
*   **메모리 설정**: 대량의 검색 결과 정렬이 느려질 경우, `main.py` 내부의 `work_mem` 설정을 128MB 등으로 상향 조정할 수 있습니다.
*   **캐시 갱신**: 행 개수(`Count`)가 실제와 다르게 느껴질 경우, 60초가 지나면 자동으로 갱신됩니다.

---
**Note**: 본 서버는 2-Step Fetching 기술을 사용하여 ORM 오버헤드를 극단적으로 줄이도록 설계되었습니다.
