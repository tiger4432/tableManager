# 🧩 Enrichment Queue — 클라이언트 구현계획서 (Client PM)

> **Status:** 📝 계획(코드 미수정) | **작성:** 2026-07-25 | **Owner:** Client PM
> **기준 스펙:** [ENRICHMENT_QUEUE_SPEC.md](../../docs/spec/ENRICHMENT_QUEUE_SPEC.md) §3·§4·§9 (🟢 확정)
> **담당 범위:** ① `enrichment.html` 전용 페이지 ② 메인 그리드 "결손 N건" 배지 (스펙 §9-4 소유 분할)
> **전제:** Server PM이 dedup mapper + 파생 테이블(`table_config.json` 등록, target 필드 = 네이티브 컬럼)을 제공. 파생 테이블은 보통 테이블이므로 기존 REST/WS/레이어링이 그대로 적용.

---

## 0. 사전 조사 요약 (Pre-Flight 결과)

| 확인 항목 | 결과 | 근거 |
|---|---|---|
| 별도 페이지 선례 | `admin.html`/`map_editor.html`은 `state.js`·`dom.js`를 **임포트하지 않고** 자체 모듈 지역 상태 사용 | frontend.md §3 주석, admin.js:2-3 |
| Vite 멀티페이지 | `vite.config.js` `rollupOptions.input`에 엔트리 3개(main/admin/map_editor) | vite.config.js:16-20 |
| 결손 필터 서버 지원 | **`GET /tables/{t}/data`의 `filters` 파라미터가 AG-Grid `blank`/`notBlank` 타입을 이미 지원** (네이티브 컬럼 대상, `IS NULL OR = ''`) | server/main.py:798-855 |
| 카운트 | 같은 엔드포인트 응답의 `total` (서버측 5초 캐시) | main.py:1042, backend.md §2 |
| 저장 계약 | `PUT /tables/{t}/data/updates` — `{updates:[{row_id, updates:{col:val}, source_name:'user', updated_by}], silent}` → source=user(priority 0) 기록 | api.js:285-307 (handleCellEdit) |
| 페이지 서빙 | dist 파일은 FastAPI fallback `/{file:path}`로 서빙 (nav 링크가 `/map_editor.html` 직접 파일 참조 중) | index.html:73, backend.md §2 |

**결론: 워크리스트 조회·결손 카운트·입력 저장은 기존 계약 100% 재사용 가능. 신규 API는 "규칙 메타"와 "참조뷰 쿼리" 2개만 필요.**

---

## 1. 페이지 구조 — `enrichment.html` + `src/enrichment.js`

### 1.1 파일 구성

| 파일 | 성격 | 내용 |
|---|---|---|
| `client2/enrichment.html` | 신설 | 3구역 레이아웃 마크업. index.html과 동일한 폰트(Outfit/JetBrains Mono)·다크 글래스 디자인 토큰 재사용 |
| `client2/src/enrichment.js` | 신설 | 페이지 오케스트레이터. **admin.js/map_editor.js 선례를 따라 자체 모듈 지역 상태** (`state.js`/`dom.js`/`api.js` 미임포트 — 이들은 메인 페이지 DOM에 강결합) |
| `client2/vite.config.js` | 1줄 추가 | `input.enrichment: resolve(__dirname, 'enrichment.html')` |
| 재사용 | `config.js`(`API_BASE`, `CURRENT_USER`, `pageLimit`), `utils.js`(`showToast`, `getLocalTimeString`), AG-Grid Community(기존 의존성) | |
| 미사용 | `websocket.js`(state.js 강결합 — v1은 map_editor 선례처럼 REST-only), `grid.js`(메인 그리드 전용) | |

### 1.2 3구역 레이아웃 (스펙 §9-2)

```
┌─ header: 규칙 선택 드롭다운 + 진행률(채운 키/전체 유니크 키) + 잔여 N건 ─┐
│ [A] 워크리스트          │ [B] 판단·입력           │ [C] 참조뷰            │
│ AG-Grid                 │ 선택 항목 상세          │ 규칙의 reference_views │
│ 파생 테이블             │ (판단키 + list_columns) │ 별 탭/스택 패널        │
│ target IS NULL 필터     │ target 입력 필드(들)    │ 판단키 파라미터로      │
│ 청크 페칭(§5)           │ [컨베이어] Enter → 저장  │ 서버 바인딩 조회       │
│                         │ → 자동 다음 항목 포커스  │ (선택 변경 시 갱신)    │
└─────────────────────────┴─────────────────────────┴───────────────────────┘
```

- **[A] 워크리스트**: AG-Grid(기존 의존성, 가상 DOM 렌더 공짜). 데이터는 `GET /tables/{derived}/data` + `filters`(target blank) + `order_by=row_id&order_desc=false`. 표시 컬럼 = `decision_key` + `list_columns`(규칙 메타 기반 동적 컬럼). 읽기 전용(입력은 [B]에서만 — 그리드 인라인 편집과 컨베이어 흐름 충돌 방지).
- **[B] 판단·입력**: 워크리스트 행 선택 시 판단키·단서를 크게 표시, `target_fields` 각각의 입력 필드. **Enter → 저장(§3) → 낙관적 행 제거 → 다음 행 자동 선택·포커스**(컨베이어). Esc = 입력 취소, ↑/↓ = 항목 이동.
- **[C] 참조뷰**: 규칙 메타의 `reference_views` 배열대로 탭(또는 세로 스택) 패널 생성. 선택 항목의 판단키 값을 파라미터로 신규 API(§4-D) 호출 → 소형 read-only 테이블 렌더. 선택 변경 시 세션 가드 토큰으로 stale 응답 폐기.
- **진입 파라미터**: `enrichment.html?rule={rule_id}` — 규칙 메타 로드 후 해당 규칙 자동 선택(없으면 첫 규칙). `URLSearchParams` 사용(main.js:67 선례).
- **디자인**: 프리미엄 표준 준수 — 기존 글래스 패널 토큰·마이크로 애니메이션(항목 완료 시 fade-out 슬라이드, 진행률 바 트랜지션). 구현 후 시각 검증 스크린샷 보고.

---

## 2. 메인 그리드 "결손 N건" 배지

| 항목 | 설계 |
|---|---|
| 위치 | `index.html` 헤더 `log-indicator-area` — 기존 `tx-pending-badge`(index.html:29) 바로 옆, 동일한 `glass-log-badge` 스타일 계열(warning 색상). "발견은 그리드" 동선상 가장 눈에 띄는 기존 배지 슬롯 |
| 마크업 | `<span id="enrichment-badge" style="display:none">🧩 결손 N건</span>` (클릭 가능, hover 마이크로 애니메이션) |
| DOM 접근 | `dom.js` `elements`에 `enrichmentBadge` 게터 1개 추가 (일원화 규칙 준수) |
| 갱신 로직 | `ui.js`에 `updateEnrichmentBadge()` 신설: ① 규칙 메타(§4-A)에서 현재 테이블이 어느 규칙의 source/파생 테이블인지 판정 ② 해당 규칙 파생 테이블에 `GET /tables/{derived}/data?limit=1&filters={target: blank}` → `total`만 사용 ③ 0건이면 숨김 |
| 호출 시점 | `api.js switchTable()` 말미에서 **fire-and-forget 비동기 호출**(테이블 전환 블로킹 금지) + `websocket.js`의 `batch_refresh_required`/`batch_row_*` 수신 시 현재 테이블이 관련 규칙이면 재조회(기존 핸들러에 1줄 훅). 폴링 없음 |
| 클릭 | `location.href = '/enrichment.html?rule={rule_id}'` (nav 드롭다운의 `/map_editor.html` 직접 링크 선례). 규칙 여러 개면 첫 규칙 또는 소형 드롭다운 |
| 안전 가드 | 규칙 메타 API 404/미배포 시 조용히 숨김(콘솔 스팸 금지) — **서버 구현보다 먼저 배포돼도 무해** |
| 부가 | nav 드롭다운(index.html:72-76)에 `🧩 Enrichment Queue` 링크 1줄 추가(배지 없이도 진입 가능) |

---

## 3. 입력 저장 경로 (기존 계약 재사용 — 신규 없음)

1. **저장**: [B]에서 Enter → `PUT /tables/{derived}/data/updates`
   ```json
   { "updates": [ { "row_id": "<선택 행 row_id>", "updates": { "wafer_id": "W123" },
                    "source_name": "user", "updated_by": CURRENT_USER } ], "silent": false }
   ```
   handleCellEdit(api.js:285-307)와 동일 계약 — 서버가 CellSource(user, priority 0) 기록, 재인제션이 사람값을 못 덮음(레이어링 불변식). 셀 계약 `{value,is_overwrite,priority_source}`은 서버 응답/재조회 시 그대로 유지되므로 클라이언트가 형태를 만들 일 없음.
2. **낙관적 갱신**: 200 응답 → 워크리스트에서 해당 행 `applyTransaction({remove})` + 잔여 카운트 −1 + 진행률 갱신 + 다음 행 선택. 실패 시 입력 유지 + 토스트 + 행 잔존.
3. **컨베이어 소진 보충**: 행 제거로 로컬 버퍼가 임계치(예: 50행) 미만이 되면 **`skip=0`부터 재페치**. 채워진 행은 결손 필터에서 빠지므로 `skip=0`이 항상 "다음 미처리 키들"을 반환 — skip 보정 문제 원천 회피(§5).
4. **다중 target_fields**: 필드별 입력 렌더. 전부 채워 저장하면 1회 요청에 `updates`로 합침(판단 1회 = 요청 1회).
5. **Tx 모드 없음**: 이 페이지는 즉시 저장(컨베이어 특성상 스테이징 무의미). 메인 그리드 Tx 모드와 무관.

---

## 4. [초안 제안] 필요 서버 API — 총괄 계약 설계 입력용

> 아래는 **제안일 뿐 확정 아님**. 신규는 2개(A, D)만이며 나머지는 기존 재사용.

| # | 용도 | 제안 | 신규 여부 |
|---|---|---|---|
| **A** | **규칙 메타** (페이지 초기화·배지 판정에 필수) | `GET /enrichment/rules` → `enrichment_rules.json` 내용 + **`derived_table` 명시 필드**. 응답 예: `{rules:[{rule_id, source_table, derived_table, decision_key[], target_fields[], list_columns[], reference_views:[{label, query_ref, params[]}]}]}`. 선례: `/admin/chain/rules`(main.py:2484) | 🆕 **신규 필요** |
| **B** | 워크리스트 조회 | `GET /tables/{derived}/data?skip&limit&order_by=row_id&filters={"<target>":{"type":"blank"}}` — **서버 blank 필터 지원 확인 완료**(main.py:846-850). 다중 target은 filters 딕셔너리에 컬럼별 blank 나열(AND) | ✅ 재사용 |
| **C** | 결손 카운트(배지) | B와 동일 엔드포인트 `limit=1`의 `total`(5초 캐시). *(선택)* 다규칙 일괄이 필요해지면 `GET /enrichment/pending_counts` → `{rule_id: count}` — v1엔 불요 판단 | ✅ 재사용 (신규는 옵션) |
| **D** | **참조뷰 조회** | `GET /enrichment/rules/{rule_id}/references/{ref_index}?params=<urlencoded JSON: {decision_key_col: value}>` → `{columns:[], rows:[], total}` (서버측 LIMIT ~200 강제). 쿼리 본문(`query_ref`)은 서버 config에만 존재 — **클라이언트는 SQL을 절대 보내지 않고 규칙ID+인덱스+키값만 전송**(인젝션 면역). 파라미터 바인딩 방식은 스펙 §9-5 위임사항 — Server PM과 조율 필요 | 🆕 **신규 필요** |
| **E** | 저장 | `PUT /tables/{derived}/data/updates` (§3) | ✅ 재사용 |

**총괄 확인 요청 사항:**
1. A의 `derived_table` 필드 — 스펙 §5 config 예시에 파생 테이블명이 없음. 클라이언트가 B/C/E를 쏘려면 필수.
2. `pending_when` 정합 — 클라이언트는 "target 컬럼 blank"로 결손 필터를 구성한다. v1에서 `pending_when`을 이 의미로 제약하거나, A 응답에 서버 계산 필터 모델을 내려주는 것 중 택일.
3. D의 파라미터 바인딩 형식(스펙 §9-5 위임분) — Server PM과 3자 확정.
4. `/enrichment.html` 서빙 — dist fallback으로 될 것으로 보이나(`/map_editor.html` 선례), Server PM 측 확인 1건.

---

## 5. 확장성 (헌장 §2 — "수만 유니크 키에도 안전한가")

- **전량 로드 금지**: 워크리스트는 `pageLimit`(1000) 청크 페칭 + `order_by=row_id`(안정 정렬 tie-breaker). "Load All" 류 버튼 없음.
- **깊은 skip 회피**: 컨베이어는 항상 **앞에서 소비**(row_id asc + 결손 필터에서 완료 행이 자동 이탈) → 보충 페치는 항상 `skip=0`. 큰 OFFSET이 구조적으로 발생하지 않음.
- **세션 가드**: 규칙 전환/재페치마다 UUID 토큰 발급, 응답 도착 시 토큰 불일치면 폐기(메인 그리드 검색 가드 패턴 동일).
- **참조뷰**: 서버 LIMIT 강제(D), 클라이언트는 받은 만큼만 렌더. 선택 변경 debounce(150ms)로 연타 시 요청 폭주 방지.
- **배지**: `limit=1` + 서버 5초 카운트 캐시 → 1,000만 행 원본과 무관하게 파생 테이블 카운트만 조회. 폴링 없이 이벤트(테이블 전환/WS) 기반.
- **DOM**: [A]는 AG-Grid 가상 렌더, [B]/[C]는 선택 항목 1건 분량만 — 수만 키에서도 DOM 노드 수 상수.

---

## 6. 단계 분할 & 검증

| 단계 | 내용 | 선행 조건 | 검증 |
|---|---|---|---|
| **①. 페이지 골격 + 워크리스트 + 컨베이어 입력** | enrichment.html/js, vite 엔트리, 규칙 메타 소비(A), 워크리스트(B), 저장(E)+낙관적 제거+skip=0 보충, 진행률 | Server: 파생 테이블 + A | `npm run dev`로 시드된 파생 테이블 대상: 값 입력→행 이탈→메인 그리드에서 `priority_source='user'` 표시 확인, 재인제션 후 사람값 보존 확인, 1만 행 시드로 스크롤/보충 프리징 없음 확인 |
| **②. 참조뷰** | [C] 구역, D 호출+파라미터 바인딩, 세션 가드, 디자인 폴리시(마이크로 애니메이션) | 총괄이 D 계약 확정 + Server 구현 | 항목 선택→참조뷰 로드 시간 로그, 연속 선택 시 stale 응답 미표시, 시각 검증 스크린샷 |
| **③. 그리드 배지 + 마감** | index.html 배지, dom.js 게터, ui.js `updateEnrichmentBadge`, switchTable/WS 훅, nav 링크, `npm run build`+dist 커밋, 히스토리+`gen_index.py`, frontend.md 갱신 | ①② 완료 | 배지 카운트 = 워크리스트 잔여 일치, 클릭 진입, 규칙 없는 테이블에서 숨김, **A 미배포 상태에서 메인 그리드 무영향(가드) 확인**, 기존 3페이지 빌드 산출 회귀 없음 |

각 단계 종료 시 보고서 갱신 + 시각 검증 결과 첨부. ①은 A만 있으면 착수 가능 — **D 계약 확정을 기다리지 않도록 ②와 분리**했다.

## 7. 사이드이펙트 체크 (StableDevelopmentProtocol §1)

| 변경 | 2차 효과 | 처리 |
|---|---|---|
| vite.config.js 엔트리 추가 | 빌드 산출물 구조 변화 | 순수 추가. `npm run build` 후 기존 index/admin/map_editor 해시·서빙 회귀 확인 |
| index.html 배지 + dom.js 게터 | 헤더 레이아웃/기존 게터 | span 1개+게터 1개 순수 추가. flex 줄바꿈 시각 확인 |
| api.js switchTable 훅 | 테이블 전환 지연 | fire-and-forget(await 없음), 실패 무음 처리 |
| websocket.js 수신 훅 | 델타 반영 경로 | 기존 핸들러 말미 1줄(배지 갱신 호출) — 그리드 트랜잭션 로직 미접촉 |
| 신규 페이지 자체 | 메인 그리드 공유 상태 | state.js 미임포트(admin 선례)라 공유 가변 상태 오염 없음. WS 미사용이라 이벤트 흐름 무영향 |
| 계약 | 셀 형태·WS 이벤트·기존 REST | **전부 불변**. 신규 A/D만 총괄 승인 대상 |

## 8. 리스크

1. **A/D 계약 미확정이 크리티컬 패스** — 특히 A의 `derived_table` 필드와 D의 바인딩 형식. 총괄 조율 선행 필요(§4 확인 요청 1·3).
2. `pending_when` 의미 불일치 가능성(§4 확인 요청 2) — v1은 "target blank"로 고정 제안.
3. 다중 사용자 동시 편집 — 같은 키를 두 명이 채우면 나중 저장이 승리(레이어링+감사로그가 추적). v1 허용, 필요 시 WS 구독을 후속으로.
4. blank 필터는 `NULL OR ''` 판정 — 파생 테이블 시드 시 target을 NULL로 생성하면 무해. Server PM에 공유.
