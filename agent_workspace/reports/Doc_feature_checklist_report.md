# doc-keeper 보고 — 기능 인벤토리 + QA 체크리스트 문서 신설 (2026-07-25)

## 1. 산출물 / 갱신 파일

| 파일 | 조치 |
|---|---|
| `docs/qa/FEATURE_CHECKLIST.md` | **신설** — §1 기능 인벤토리(서브시스템 10그룹, 기능당 설명+진입 경로+CODE_MAP 참조), §2 QA 체크리스트(14그룹, 정상 1+에지 1~2, `- [ ]`, 클릭 수준 절차). 🎯 마킹으로 핵심가치 항목(SLO 100ms·멱등성·레이어링 보존·소스 삭제 폴백) 릴리스 블로커화. 상단 Living 배지 + "doc-keeper가 코드맵과 같은 사이클로 갱신" 유지 규율 명기 |
| `docs/README.md` | §3.5 QA 섹션 신설·등재(🟢) + 이력 인덱스 건수 185→186 정정 |
| `docs/process/DOC_OWNERSHIP.md` | "QA 기능 점검" 소유 행 추가(Owner: Integrity/QA, 갱신 doc-keeper 전담) |
| `docs/history/20260725_143000_feature_checklist_doc_created.md` | 히스토리 기록(스니펫 포함) |
| `docs/history/README.md` | gen_index 재생성(186 entries) |

코드·config 무접촉. 커밋 안 함(총괄 검수 대기).

## 2. 정보 출처

SSOT §1·§6, CODE_MAP(전 섹션), frontend.md, INGESTION_GUIDE(§1.5 std/§1.6 온보딩), AUTO_UPDATE_GUIDE, ENRICHMENT_QUEUE_SPEC, PROJECT_STATUS(이슈 #0/#2/#6/#7), history `20260725_130000`. 소스는 UI 진입 경로 확정용으로만 최소 확인: `client2/index.html`·`enrichment.html`의 버튼/입력 id Grep, `grid.js` floatingFilter 확인, nav 메뉴 링크 확인 — 전량 읽기 없음.

## 3. client-pm 확인 필요 목록 (본문에 `<!-- TODO: client-pm 확인 -->` 주석 배치)

문서·코드맵만으로 확신할 수 없어 추측을 배제한 항목. 총괄이 client-pm에 이관해 보강 요망:

1. **소스 모달 트리거** — 셀에서 소스 목록 모달을 여는 정확한 조작(우클릭/버튼/단축키). (§1.1, §2.2)
2. **핀 설정/해제 UI 절차** — 소스 모달 내 어떤 컨트롤인지. (§1.1)
3. **소스 삭제 UI** — 삭제 버튼 위치, 일괄 삭제 UI, 실패 시 에러 표출 방식(토스트/모달). (§1.1, §2.2)
4. **범위 일괄 적용 트리거** — `applyValueToSelectedRange`의 입력 UI(입력창/단축키). (§1.1)
5. **스마트 페이스트 발동 조건** — 행 수 임계와 유형 선택 모달의 선택지 의미. (§1.1, §2.3)
6. **컬럼 선택 상태 유지 범위** — 새로고침/테이블 전환 시 유지 여부. (§1.1)
7. **view-mode-select 옵션 목록과 의미**. (§1.1)
8. **결손 배지 표시 조건** — 파생 테이블 화면에서만인지, 원본 테이블에서도인지. (§1.6)
9. **맵 에디터 버튼 라벨** — 저장 버튼·엣지 도구·엑셀 복사 버튼의 실제 명칭/위치, 저장 전 확인 UI. (§1.7)
10. **페이지별 테마 토글 유무** — admin/map_editor/enrichment 각 페이지에 토글 버튼이 있는지(index는 확인됨). (§1.10, §2.12)

## 4. 발견한 불일치 (참고)

- `docs/architecture/frontend.md` §2 진입점 표가 **3페이지(index/admin/map_editor)로 낡음** — `vite.config.js`는 enrichment 포함 4엔트리(실확인). §3 모듈 표의 줄수도 CODE_MAP과 어긋남(예: ui.js 325 vs ~408, admin.js 1420 vs ~1433). frontend.md는 Client PM/UI 소유 리빙 문서 — 본 위임 범위(체크리스트 신설) 밖이라 미수정. 다음 frontend 문서 동기화 위임 시 함께 정정 권고.
- `docs/README.md` 이력 인덱스 건수 하드코딩(185)이 어긋나 있었음 → 186으로 정정 완료. 매번 어긋나는 구조이므로 건수 표기를 빼는 것도 고려 대상.

## 5. PROJECT_STATUS 반영 초안 (직접 수정 금지 지시 — 총괄이 반영)

"✅ 최근 완료" 표에 추가:

```markdown
| 2026-07-25 | 문서/QA | **기능 인벤토리 + QA 수동 점검 체크리스트 신설** — `docs/qa/FEATURE_CHECKLIST.md`(서브시스템별 기능 지도 + 정상/에지 점검 절차, SLO·멱등성 🎯 블로커 마킹, doc-keeper 유지 사이클 명기), README/DOC_OWNERSHIP 배선. 클라 UI 세부 10건은 client-pm 보강 대기(TODO 주석) | [20260725_143000](../history/20260725_143000_feature_checklist_doc_created.md) |
```

필요 시 "다음 단계"에 한 줄: `FEATURE_CHECKLIST의 client-pm TODO 10건 보강 이관`.

## 6. SSOT 관련 제안

- SSOT 변경 없음(신규 문서는 SSOT §6을 링크로 소비만 함). 다만 SSOT §3이 "진입점 3개"로 서술 — enrichment.html이 4번째 엔트리로 승격된 현실(vite.config.js 4엔트리)과 미세 상충. **SSOT는 총괄 소유이므로 수정하지 않음** — §3 문장을 "진입점 4개(index/admin/map_editor/enrichment)"로 고치는 초안만 제안.

## 7. 교훈 제안 (doc-keeper 전용, 총괄 검수 후 memory 반영)

- **제안**: 사용자 관점 기능 문서를 쓸 때 UI 진입 경로는 CODE_MAP·가이드만으로 확정 불가한 경우가 많다 — `*.html`의 버튼/입력 id Grep(전량 읽기 아님)이 저비용 확정 수단이며, 그래도 불확실하면 추측 대신 `client-pm 확인` TODO로 넘긴다.
