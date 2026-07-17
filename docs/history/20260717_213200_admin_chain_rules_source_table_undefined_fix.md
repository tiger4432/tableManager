# 2026-07-17 어드민 대시보드 체인 룰 소스 테이블 undefined 렌더링 버그 수정

## 1. 개요 및 동기
* **현상**: Ingestion Outbox 어드민 대시보드 대시보드의 `Chain Rules` 탭 조회 시, 테이블 내 `SOURCE TABLE` 컬럼에 소스 테이블명이 인쇄되지 않고 `undefined` 로 출력되는 현상이 보고되었습니다.
* **원인**: 백엔드 설정 파일(`chain_rules.json`) 및 API 엔드포인트(`/admin/chain/rules`)에서 소스 테이블은 `"trigger_table"` 이라는 키로 제공되고 있으나, 프론트엔드 어드민 제어 스크립트(`client2/src/admin.js`) 내의 렌더링 로직(`renderChainTable`)에서 `rule.source_table` 이라는 유효하지 않은 속성에 접근하려다 발생한 데이터 키 미스매치 결함이었습니다.

---

## 2. 주요 코드 변경 사항

### 어드민 클라이언트 스크립트 렌더링 구문 패치 (`client2/src/admin.js`)
기존에 존재하지 않던 `rule.source_table` 속성을 백엔드 규격에 맞는 `rule.trigger_table` 로 변경하여 그리드를 올바르게 렌더링하도록 핫픽스를 적용했습니다.

```javascript
// client2/src/admin.js

// [수정 전]
    row.innerHTML = `
      <td style="font-weight: bold; color: var(--color-primary);">${rule.name}</td>
      <td style="font-family: var(--font-mono); font-size: 0.85rem; font-weight: 500;">${rule.source_table}</td>
      <td style="font-family: var(--font-mono); font-size: 0.85rem; font-weight: 500;">${rule.target_table}</td>
      <td style="text-align: center;">${activeBadge}</td>
    `;

// [수정 후]
    row.innerHTML = `
      <td style="font-weight: bold; color: var(--color-primary);">${rule.name}</td>
      <td style="font-family: var(--font-mono); font-size: 0.85rem; font-weight: 500;">${rule.trigger_table}</td>
      <td style="font-family: var(--font-mono); font-size: 0.85rem; font-weight: 500;">${rule.target_table}</td>
      <td style="text-align: center;">${activeBadge}</td>
    `;
```

---

## 3. 검증 및 빌드 적용
* **프론트엔드 리빌드**: 수정 완료 후 `client2` 패키지 루트에서 `npm run build` 명령을 실행하여 번들링 컴파일을 무사히 통과하였으며, 최종 `dist/assets/admin-*.js` 파일에 핫픽스 로직이 정상 주입 서빙되도록 적용을 완료했습니다.
