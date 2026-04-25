# 셀(Cell) 조작 및 편집

## 1. 단일 셀 변경
### 📍 트리거 포인트
`ApiLazyTableModel.setData()` (사용자가 표에서 직접 셀 더블 클릭 및 수정 후 엔터)

### ⚙️ 동작 방식
1. Qt 프레임워크가 모델의 `setData`를 호출하여 새로 입력된 `value`를 전달합니다.
2. 시스템 컬럼(`created_at`, `updated_at`, `row_id` 등)은 수정이 불가하도록 막습니다.
3. 기존 값과 동일한 경우 무시하고, 변경된 경우 `ApiGeneralUpdateWorker`를 통해 `PUT` 요청을 발생시킵니다.
4. 서버 응답이 성공하면 `_on_update_finished` 슬롯이 호출되어 데이터 딕셔너리의 `is_overwrite` 플래그를 활성화하고 (배경색 주황색 등으로 강조 표기), `dataChanged` 시그널을 통해 UI를 갱신합니다.

## 2. 다중 셀 변경 및 붙여넣기 (Paste)
### 📍 트리거 포인트
`ExcelTableView.paste_selection()` (단축키: `Ctrl + V`)

### ⚙️ 동작 방식
1. **클립보드 파싱**: `QGuiApplication.clipboard().text()`를 통해 데이터를 가져오고, 탭(`\t`)과 줄바꿈(`\n`) 기준으로 2차원 매트릭스로 파싱합니다.
2. **Anchor 획득**: 사용자가 선택한 영역 중 가장 왼쪽 상단(min_row, min_col)을 기준으로 붙여넣을 범위를 산정합니다.
3. **절대 좌표 타겟팅**: 단순한 행/열 인덱스가 아닌, `proxy_model.mapToSource`와 내부 데이터를 참조해 타겟 위치의 고유 `row_id`와 컬럼 식별자(`col_name`)를 직접 확보합니다. (이는 정렬/검색 상태에서 붙여넣기를 수행하더라도 엉뚱한 행에 데이터가 덮어씌워지지 않도록 하는 핵심 방어 기제입니다.)
4. **일괄 업데이트 큐잉**: 매핑된 딕셔너리(`mapped_updates`)를 구성한 뒤, `source_model.applyMappedUpdates`를 호출하여 여러 건의 셀 수정을 하나의 API 배치 요청으로 묶어 전송합니다.
5. **웹소켓 처리**: `batch_row_upsert` 이벤트가 브로드캐스트되며, UI는 최신화됩니다.
