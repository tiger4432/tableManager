# 2026-07-17 어드민 대시보드 맵퍼 파일 로딩 실패 버그 수정

## 1. 개요 및 동기
* **현상**: `Chain Rules` 탭에서 룰을 선택하고 `🛠️ Edit Mapper Code` 버튼을 눌렀을 때, 모나코 에디터 화면에 `❌ Failed to load file` 에러가 발생하며 코드가 정상 로드되지 못하는 오류가 발생했습니다.
* **원인**: 
  * 백엔드 API `/admin/scripts/code` 의 경로 보안 필터(Whitelist)는 파일 경로가 반드시 `mappers/` 또는 `ingestion_workspace/` 로 시작하는 상대 경로일 때만 접근을 승인하도록 제어되어 있습니다.
  * 그러나 프론트엔드 연동 로직에서 `server/mappers/production_mapper.py` 와 같이 `server/` 접두사를 포함한 전체 경로로 조립하여 요청을 보냄으로써 백엔드 화이트리스트 검증을 통과하지 못해 400 Bad Request 에러를 내뱉고 파일 로딩에 실패한 결함이었습니다.

---

## 2. 주요 코드 변경 사항

### 어드민 클라이언트 스크립트 맵퍼 경로 계산 구문 패치 (`client2/src/admin.js`)
기존에 불필요하게 꼽히던 `server/` 접두사 경로 조립 연산을 제외하여, 백엔드 경로 승인 필터를 우아하게 우회 충족시키는 상대 경로(`mappers/production_mapper.py`)로 유추 및 전송하도록 수정했습니다.

```javascript
// client2/src/admin.js

// [수정 전]
  const inlineEditBtn = document.getElementById('inline-edit-mapper-btn');
  if (inlineEditBtn) {
    let modulePath = rule.mapper_module || '';
    if (modulePath.startsWith('mappers.')) {
      modulePath = modulePath.replace('mappers.', 'server/mappers/') + '.py';
    } else {
      modulePath = `server/${modulePath.replace(/\./g, '/')}.py`;
    }
    inlineEditBtn.addEventListener('click', () => {
      openInlineEditor(modulePath);
    });
  }

// [수정 후]
  const inlineEditBtn = document.getElementById('inline-edit-mapper-btn');
  if (inlineEditBtn) {
    let modulePath = rule.mapper_module || '';
    if (modulePath.startsWith('mappers.')) {
      modulePath = modulePath.replace('mappers.', 'mappers/') + '.py';
    } else {
      modulePath = `${modulePath.replace(/\./g, '/')}.py`;
    }
    inlineEditBtn.addEventListener('click', () => {
      openInlineEditor(modulePath);
    });
  }
```

---

## 3. 빌드 및 배포 적용
* **Vite 리빌드**: 수정 완료 후 `client2` 패키지 디렉토리에서 `npm run build` 번들링 빌드 처리를 완료하여 실서버 서비스 파일인 `dist/admin.html` 및 `dist/assets/admin-*.js` 파일에 신규 UI/UX 개선 기능을 안전하게 주입 배포했습니다.
