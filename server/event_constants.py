"""프로세스 간 내부 이벤트(HTTP POST /internal/events/*) 공용 상수.

워처(parsers/directory_watcher.py)와 체인 워커(chain_ingestion_worker.py) 등
발신 측 데몬들이 공유한다. 값 변경 시 두 발신 경로와 수신부(main.py)의
구버전 호환 절단(500)을 함께 검토할 것.
"""

# [C-5] 인제션/체인 완료 통지에 동봉하는 감사 로그(created_logs) 상한.
# 웹서버(main.py /internal/events/*)와 audit_cache는 어차피 트랜잭션당 500건만 유지하므로,
# 발신 측이 전량(수만~수십만 dict, 직렬화 시 수십 MB JSON)을 메모리 누적·HTTP POST하는 것은
# 순수 낭비이자 웹서버 이벤트 루프 동결(대형 json.loads / pydantic 검증의 GIL 점유) 요인이다.
# 이벤트 필드 형태(created_logs: list)는 그대로 유지하고 항목 수만 제한하며(경계 계약 불변),
# 실제 총 로그 건수는 total_log_count 필드로 별도 전달한다(순수 추가 필드).
MAX_NOTIFY_CREATED_LOGS = 500
