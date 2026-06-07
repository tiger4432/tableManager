# 변경 이력: 파일 업로드 인제션 시 실제 파일명 추출 및 소스 트래킹 반영

- **작성일**: 2026년 6월 8일
- **작성자**: Antigravity
- **상태**: 완료

## 1. 개요 및 목적
- **현상**: 기존의 파일 업로드 인제션 진행 시, 업로드 과정에서 고유화된 파일명(`user(username)_orig_name_abcdef12.xlsx` 등)이 생성되는데, 이를 파싱 및 DB 적재할 때 데이터 원천(`source_name`) 정보가 `"pipeline_parser"` 또는 `"batch_ingester"` 등의 일반 명칭으로만 고정되어 저장되었습니다. 이로 인해 셀 상세 원천 정보 조회 시 실제 업로드했던 원천 파일이 무엇이었는지 파악하기 어려웠습니다.
- **해결 방안**: 
  1. `BasePipelineParser` 베이스 클래스에 파일명 정규화 헬퍼 함수(`get_basename`)를 추가하여, 업로드 경로에서 유저명 접두사(`user(name)_`) 및 UUID 8자리 접미사를 제거한 순수 원본 파일명만 추출할 수 있게 하였습니다.
  2. 디렉토리 감시자(`directory_watcher.py`)가 파일 유입 감지 후 적재 요청을 수행할 때, 해당 원본 파일명을 `_send_to_upsert`로 전달하여 DB 적재 시 셀 원천 소스 명칭(`source_name`)으로 저장하도록 연계 수정했습니다.

## 2. 세부 변경 사항

### BasePipelineParser 원본 파일명 추출 기능 추가 (`server/parsers/pipeline_base.py`)
- `BasePipelineParser` 클래스에 정적 메서드 `get_basename(file_path: str) -> str`을 신설했습니다.
- 정규식(Regex)을 이용해 파일명에서 유저 접두사 및 UUID 접미사를 완벽히 소거하고 파일 확장자와 함께 반환하도록 작성했습니다.

### 감시 프로세스 소스 명칭 연동 수정 (`server/parsers/directory_watcher.py`)
- `_send_to_upsert` 메서드 서명에 `filename: str = None` 파라미터를 추가했습니다.
- 파일 파싱 처리 함수(`process_with_retry`)에서 `_send_to_upsert`를 호출할 때 감지된 파일명을 함께 주입하도록 수정했습니다.
- 전달된 파일명이 존재하는 경우 `BasePipelineParser.get_basename`을 호출해 변환된 원본 명칭을 `GeneralUpdateItem`의 `source_name`으로 설정하여 DB에 입력되도록 하였습니다.

## 3. 검증 결과
- **효과**: 원천 데이터 업로드 인제션 시, 셀의 원천 데이터 맵(`sources`)에 `"pipeline_parser"` 대신 실제 업로드된 원본 파일명(예: `"production_plan.xlsx"`)이 키 값으로 보존됩니다. 따라서 사용자가 셀의 원천 데이터를 조회할 때 어떤 업로드 파일에 의해 유입된 데이터인지 직관적으로 추적할 수 있습니다.
- **테스트 생략**: 사용자의 지침에 따라 자동화 테스트 수행은 생략되었습니다.
