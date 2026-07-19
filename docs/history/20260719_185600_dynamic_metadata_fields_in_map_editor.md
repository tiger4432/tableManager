# 2026-07-19 18:56:00 - 격자 맵 에디터 내 동적 메타데이터(Metadata) 입력 지원 기능 추가

## 1. 개요 및 동기
* **배경**: 이전 버전의 맵 에디터에서는 단일한 `Base Key` 입력란만 하드코딩되어 제공되었습니다.
* **문제점**: 데이터베이스 테이블에 따라 `base id`, `mid id`, `base lot` 등 여러 개의 다양한 메타데이터 키들이 조합되어 맵이 정의되어야 하거나, 다양한 커스텀 컬럼을 입력해야 하는 비즈니스 요구사항을 수용할 수 없었습니다.
* **해결 방안**: 선택된 테이블의 스키마를 정밀 스캔하여, 좌표 컬럼(X, Y) 및 셀 값(Value) 컬럼과 시스템 컬럼을 제외한 **모든 일반 필드를 동적 메타데이터 입력란으로 자동 추출 및 생성**해 주는 완전 가변식 메타데이터 입력 아키텍처를 구현했습니다.

---

## 2. 주요 구현 사항

### A. 스키마 기반 동적 입력 폼 렌더링 (`client2/src/map_editor.js`)
* 선택된 테이블의 컬럼 및 타입을 파악하고, Advanced Column Mapping 정보에 기반해 좌표/값 매핑 컬럼을 제외한 필드에 대해 실시간으로 HTML Input 엘리먼트를 동적 생성합니다.

```javascript
function renderMetadataInputs() {
  const container = el.metadataContainer;
  if (!container || !tableSchema) return;
  container.innerHTML = '';

  const cols = tableSchema.columns || [];
  const xCol = el.colMapX.value;
  const yCol = el.colMapY.value;
  const valCol = el.colMapVal.value;

  const systemCols = [
    'created_at', 'updated_at', 'row_id', 'business_key_val',
    'is_graph_synced', 'needs_graph_rollback', 'graph_synced_at'
  ];

  const metaCols = cols.filter(col => {
    return !systemCols.includes(col) &&
           col !== xCol &&
           col !== yCol &&
           col !== valCol;
  });

  metaCols.forEach(col => {
    const colType = tableSchema.column_types[col] || 'string';
    const formGroup = document.createElement('div');
    formGroup.className = 'control-group-vertical';

    const label = document.createElement('label');
    label.htmlFor = `meta-input-${col}`;
    label.textContent = `${col} (${colType})`;

    const input = document.createElement('input');
    input.type = 'text';
    input.id = `meta-input-${col}`;
    input.className = 'glass-input w-full';
    input.placeholder = `${col} 값 입력`;
    
    formGroup.appendChild(label);
    formGroup.appendChild(input);
    container.appendChild(formGroup);
  });
}
```

### B. 가변 메타데이터 필터 조합을 통한 기존 데이터 로드
* 로드(Load) 수행 시, 생성된 동적 인풋 창들 중에서 사용자가 값을 입력한 필드만 추출하여 AG-Grid 규격의 텍스트 동등 매치 필터(`filterModel`)를 조합하고 백엔드에 Query를 쏘도록 수정했습니다.

```javascript
async function loadExistingMap() {
  const filterModel = {};
  const metaInputs = document.querySelectorAll('[id^="meta-input-"]');
  let hasFilter = false;

  metaInputs.forEach(input => {
    const col = input.id.replace('meta-input-', '');
    const val = input.value.trim();
    if (val) {
      hasFilter = true;
      filterModel[col] = {
        filterType: 'text',
        type: 'equals',
        filter: val
      };
    }
  });

  if (!hasFilter) {
    alert('기존 맵 데이터를 로드하기 위해 하나 이상의 메타데이터 필드 값을 입력하십시오.');
    return;
  }
  // ... API Fetch 및 격자 복원 연동
}
```

### C. 동적 맵 적재(Push) 데이터 조립
* 페인팅된 셀들을 백엔드에 밀어 넣을 때, 입력된 메타데이터 값들을 스키마 타입에 맞춰 형변환(숫자 여부 등)한 뒤 모든 적재용 레코드 오브젝트에 통합 병합(`...metaValues`)하여 Push하도록 처리했습니다.

```javascript
  // updates 배열 루프 내에서
  const updateItem = {
    updates: {
      [xCol]: xParsed,
      [yCol]: yParsed,
      [valCol]: valParsed,
      ...metaValues // 동적 수집된 base_id, mid_id, base_lot 등의 값 병합
    },
    source_name: 'user',
    updated_by: CURRENT_USER
  };
```

---

## 3. 아키텍처 영향 보고
* **유연한 스키마 확장성**: 이제 데이터베이스 테이블이 `base`, `mid`, `lot`, `device` 등 몇 개의 메타데이터 필드를 갖든 간에 소스코드를 전혀 수정하지 않고도 신규 테이블을 맵 에디터에 그대로 등록하여 사용 가능합니다.
* **안전한 빌드**: Vite를 이용해 `dist/map_editor.html` 및 리소스 번들을 완벽하게 다시 컴파일 및 패키징 완료했습니다.
