# 📝 Agent Excel — 소스 코드 리뷰 요약

**담당 영역**: `ExcelTableView` 및 `Batch API` 연동 로직
**주요 파일**: `client/main.py`, `client/models/table_model.py`

---

## 1. 클래스 구조 및 핵심 역할
### `ExcelTableView (QTableView)`
- **역할**: 표준 `QTableView`를 확장하여 엑셀 스타일의 키보드 인터랙션 지원.
- **핵심 메서드**:
  - `keyPressEvent`: `Ctrl+C`, `Ctrl+V` 단축키를 가로채어 커스텀 로직 실행.
  - `copy_selection`: 선택된 인덱스들을 순회하며 `TSV(Tab-Separated Values)` 형식으로 클립보드에 저장.
  - `paste_selection`: 클립보드의 TSV 데이터를 파싱(행은 `\n`, 열은 `\t`)하여 2차원 리스트 생성 후 모델의 `bulkUpdateData`로 전달.

### `BatchApiUpdateWorker (QRunnable)`
- **역할**: 메인 스레드 차단 없이 백그라운드에서 서버와 데이터 동기화.
- **I/O 형식**: 
  - **In**: `list[dict]` (각 사전은 `row_id`, `column_name`, `value` 포함)
  - **Process**: `PUT /tables/{name}/cells/batch` 서버 엔드포인트 호출.

---

## 2. 데이터 I/O 형식 (Protocol)
### 배치 업데이트 페이로드 (JSON)
```json
{
  "updates": [
    { "row_id": "uuid-1", "column_name": "name", "value": "NewVal" },
    ...
  ]
}
```

---

## 3. 유지보수 포인트
- **붙여넣기 로직**: 현재는 시작 셀부터 오른쪽/아래로 덮어쓰는 방식입니다. `proxyModel`이 적용되어 있어도 `sourceModel()`을 찾아가서 원본 데이터를 수정하도록 설계되었습니다 (`mapper` 이슈 방지).
- **에러 핸들링**: API 실패 시 시그널을 통해 UI에 알림을 주며, 실제 모델 데이터는 서버 응답 성공 시에만 갱신됩니다.
