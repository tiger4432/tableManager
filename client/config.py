import os
import sys
import getpass
import json

# ── 네트워크 환경 설정 ──
# 루프백 주소(127.0.0.1) 통신 시 프록시 간섭을 원천 차단하여 통신 안정성 확보
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

# ── 서버 접속 설정 (기본값) ──
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000

# ── 사용자 정보 (추적용 기본값) ──
try:
    CURRENT_USER = getpass.getuser()
except Exception:
    CURRENT_USER = "unknown_user"

# ── 설정 파일 경로 ──
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "client_settings.json")

def load_settings():
    """로컬 JSON 파일에서 설정을 로드하여 전역 변수에 반영합니다."""
    global SERVER_HOST, SERVER_PORT, CURRENT_USER, API_BASE_URL, WS_BASE_URL
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                SERVER_HOST = data.get("server_host", SERVER_HOST)
                SERVER_PORT = data.get("server_port", SERVER_PORT)
                CURRENT_USER = data.get("current_user", CURRENT_USER)
                print(f"[Config] Settings loaded from {SETTINGS_FILE}")
        except Exception as e:
            print(f"[Config] Failed to load settings: {e}")
    
    # 베이스 주소 재계산
    API_BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
    WS_BASE_URL = f"ws://{SERVER_HOST}:{SERVER_PORT}/ws"

def save_settings(host, port, user):
    """설정을 JSON 파일에 저장하고 현재 세션에 반영합니다."""
    global SERVER_HOST, SERVER_PORT, CURRENT_USER
    SERVER_HOST = host
    SERVER_PORT = int(port)
    CURRENT_USER = user
    
    data = {
        "server_host": SERVER_HOST,
        "server_port": SERVER_PORT,
        "current_user": CURRENT_USER
    }
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"[Config] Settings saved to {SETTINGS_FILE}")
        load_settings() # URL 재계산 호출
    except Exception as e:
        print(f"[Config] Failed to save settings: {e}")

# 초기 로드 실행
load_settings()

# ── 엔드포인트 빌더 (유지보수 포인트 일원화) ──

def get_tables_list_url() -> str:
    """가용한 테이블 목록 조회 엔드포인트"""
    return f"{API_BASE_URL}/tables"

def get_table_data_url(table_name: str) -> str:
    """특정 테이블의 데이터 페이징 조회 엔드포인트"""
    return f"{API_BASE_URL}/tables/{table_name}/data"

def get_table_schema_url(table_name: str) -> str:
    """특정 테이블의 비즈니스 키 및 컬럼 스키마 조회 엔드포인트"""
    return f"{API_BASE_URL}/tables/{table_name}/schema"

def get_row_upsert_url(table_name: str) -> str:
    """비즈니스 키 기반 행 추가/수정 엔드포인트"""
    return f"{API_BASE_URL}/tables/{table_name}/upsert"

def get_row_create_url(table_name: str) -> str:
    """빈 행 생성 엔드포인트"""
    return f"{API_BASE_URL}/tables/{table_name}/rows"

def get_row_delete_url(table_name: str, row_id: str) -> str:
    """특정 행 삭제 엔드포인트"""
    return f"{API_BASE_URL}/tables/{table_name}/rows/{row_id}"

def get_cell_update_url(table_name: str) -> str:
    """단일 셀 값 업데이트 엔드포인트"""
    return f"{API_BASE_URL}/tables/{table_name}/cells"

def get_batch_cell_update_url(table_name: str) -> str:
    """다중 셀 배치 업데이트 엔드포인트"""
    return f"{API_BASE_URL}/tables/{table_name}/cells/batch"

def get_table_export_url(table_name: str) -> str:
    """CSV 익스포트 스트리밍 엔드포인트"""
    return f"{API_BASE_URL}/tables/{table_name}/export"

def get_table_upload_url(table_name: str) -> str:
    """파일 업로드 엔드포인트 (인제션 트리거용)"""
    return f"{API_BASE_URL}/tables/{table_name}/upload"

def get_single_row_url(table_name: str, row_id: str) -> str:
    """특정 행 단건 조회 엔드포인트 (WS 부상 시 사용)"""
    return f"{API_BASE_URL}/tables/{table_name}/{row_id}"

def get_unified_update_url(table_name: str) -> str:
    """[통합] PK/BK 기반 단건 및 배치 업데이트 엔드포인트"""
    return f"{API_BASE_URL}/tables/{table_name}/data/updates"

def get_batch_delete_url(table_name: str) -> str:
    """[통합] 다중 행 일괄 삭제 엔드포인트"""
    return f"{API_BASE_URL}/tables/{table_name}/rows/batch_delete"

def get_target_row_ids_url(table_name: str) -> str:
    """Targeted RowID Scanner (오프셋 기반 타겟팅 UUID 고속 추출)"""
    return f"{API_BASE_URL}/tables/{table_name}/row_ids/target"

def get_audit_log_recent_url(limit: int = 50) -> str:
    """전역 최신 감사 로그 목록 조회 엔드포인트"""
    return f"{API_BASE_URL}/audit_logs/recent?limit={limit}"

def get_row_index_discovery_url(table_name: str, row_id: str) -> str:
    """특정 행의 현재 오프셋 위치 검색 엔드포인트"""
    return f"{API_BASE_URL}/tables/{table_name}/row_index/{row_id}"

def get_cell_history_url(table_name: str, row_id: str, col_name: str) -> str:
    """특정 셀의 전체 변경 이력(Lineage) 조회 엔드포인트"""
    return f"{API_BASE_URL}/tables/{table_name}/rows/{row_id}/cells/{col_name}/history"

def get_dashboard_summary_url() -> str:
    """대시보드 통계 요약 조회 엔드포인트"""
    return f"{API_BASE_URL}/dashboard/summary"
