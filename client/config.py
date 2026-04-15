import os
import sys

# ── 네트워크 환경 설정 ──
# 루프백 주소(127.0.0.1) 통신 시 프록시 간섭을 원천 차단하여 통신 안정성 확보
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

# ── 서버 접속 설정 ──
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000

# 베이스 주소 정의
API_BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
WS_BASE_URL = f"ws://{SERVER_HOST}:{SERVER_PORT}/ws"

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

def get_single_row_url(table_name: str, row_id: str) -> str:
    """특정 행 단건 조회 엔드포인트 (WS 부상 시 사용)"""
    return f"{API_BASE_URL}/tables/{table_name}/{row_id}"
