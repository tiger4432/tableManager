# 🚀 AssyManager 서버 스타팅 가이드 (High-Performance Engine)

이 가이드는 1,000만 건 이상의 대규모 데이터를 초고속(0.1초대)으로 처리하는 AssyManager 서버의 설치 및 운영 방법을 설명합니다.

## 1. 환경 구축 (Environment)
*   **Python 버전**: 3.10 이상 권장
*   **패키지 설치**:
    ```bash
    pip install -r requirements.txt
    ```

## 2. 데이터베이스 초기 설정 (PostgreSQL)
서버를 실행하기 전, 데이터베이스 성능 최적화 인덱스를 반드시 생성해야 합니다.

1.  **인덱스 및 확장 프로그램 일괄 생성**:
    ```bash
    python scripts/setup_db_performance.py
    ```
    *이 스크립트는 `btree_gin`, `pg_trgm` 확장을 활성화하고, 최신순/품번순/검색용 고성능 인덱스를 자동으로 구성합니다.*

## 3. 서버 실행 (Running)
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

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
