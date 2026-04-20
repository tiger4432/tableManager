# 2026-04-21: Addition of Server Asset Migration Utility

## 1. 개요
타 서버에서 운영 중이던 AssyManager 서버의 핵심 설정 및 워크스페이스 구조를 현재 서버로 안전하게 이관하기 위한 유틸리티 스크립트를 추가함.

## 2. 주요 기능 (`server/scripts/migrate_assets.py`)
- **--source <path>**: 이전 서버의 루트 경로를 인자로 받아 이관을 수행함.
- **자동 백업**: 이관 전 로컬의 `config` 및 `ingestion_workspace` 폴더를 `*.bak_YYYYMMDD_HHMMSS` 형식으로 백업하여 데이터 유실을 방지함.
- **선택적 이관 (Archive Exclusion)**: 사용자의 요청에 따라 `ingestion_workspace` 내부의 `archives` 폴더는 이관 대상에서 제외하여 스토리지 낭비를 방지하고 복사 속도를 최적화함.
- **타겟 자산**: `table_config.json`, 테이블별 `raws`, `scripts`, `config` 폴더를 모두 이관함.

## 3. 사용 예시
```bash
python server/scripts/migrate_assets.py --source /path/to/old/server
```

## 4. 기대 효과
- 서버 환경 이전 또는 로컬 테스트 환경 구축 시 수동 복사로 인한 실수 방지.
- 대용량 아카이브를 제외한 핵심 자산 위주의 빠른 마이그레이션 가능.
