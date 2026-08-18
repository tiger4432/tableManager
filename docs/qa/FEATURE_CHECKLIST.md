# ✅ FEATURE_CHECKLIST — 기능 인벤토리 + QA 수동 점검 체크리스트

> **Status:** 🟢 Living | **Last-verified:** 2026-08-19 (§1.14 신규 3행 · L1-bis/L5/A2/A3의 은퇴 경로 표시 · **§1.13 L7 신설** — 그룹 단위 소스) | **Owner:** Integrity/QA | 갱신 **doc-keeper 전담** · 정합 감사 **doc-auditor**
>
> **이번 라운드 (2026-08-11 2차 · `3d43a6c`)**: ⚠️ **Map Editor 2에는 여전히 §1/§2 행이 없습니다**(2026-08-05 결정 유지 — 화면이 매일 바뀌는 중이라 지금 쓰면 내일 낡는다). 다만 이번 커밋이 고친 것은 적어 둔다: 확정 키 조립이 **룰 선언을 arity 무관하게** 따르게 됐다(옛 코드는 arity 2 전용이라 컬럼 1개짜리 운영 룰을 한 번도 확정시키지 못했다) · 룰 채택 실패가 빈 목록 대신 사유(`정렬 규칙 없음`/`규칙 선택 필요`)를 낸다. 설계 서술은 [architecture/frontend §4.2](../architecture/frontend.md), 계약은 [spec/MAP_ALIGNMENT_SPEC §5](../spec/MAP_ALIGNMENT_SPEC.md).
>
> **직전 라운드 (2026-08-11 1차)**: §1.2에 **히스토리 페이징(더 보기)** 신규 행 + 글로벌 타임라인 행에 bounded-scan 캐비앗(`fde424c` — `/audit_logs/recent`도 바디 엔벨로프가 됐다, 리스트 키 `groups`). §1.6 Enrichment Queue — **컨베이어 입력·결손 배지 취소선**(둘 다 UI가 삭제됐다, `ab36fab`+`5116f67`) + **그리드 사이드바 참조뷰** 신규 행(`1e29078`). §2.8-ter에 세 번째 config 도메인 `binding`(`68db020`) 점검 5건 신설.
>
> 🔴 **§2.0 자동 게이트의 정본은 `client2/package.json`의 `prebuild` 한 줄이고 이 문서는 사본입니다** — 계약을 추가·삭제하는 커밋은 §2.0의 **산문과 코드 샘플을 함께** 고쳐야 합니다(독자가 자기 출력과 대조하는 것은 샘플입니다). 그리고 **사용자 눈에 보이는 기능이 착지하면 §1의 인벤토리 행이 먼저 필요합니다** — 행이 없으면 그 기능은 회귀 점검에서 구조적으로 빠집니다.
>
> **이번 라운드 (2026-08-05 · 2차 — `b9a0ab1`)**
> - **§2.9에 점검 항목 둘 신설.** ① **고른 프레임은 골랐다고 기록된다**(`frame_chosen_from`) — 🔴 **채점의 핵심은 「표지가 실리는가」가 아니라 *양방향*이다**: 표지 없는 맵을 이어서 열었을 때 직전 맵의 표지가 묻어 나오면 회귀다. ② **빈 프레임 칸은 0으로 지어내지 않고 이름을 대며 거절한다** — 🔴 종전에는 지어낸 `0`이 **입력칸에 되쓰여** 조작자 자신의 값처럼 보였다.
> - ⚠️ **어느 쪽도 서버 반응을 채점하지 않습니다** — `frame_chosen_from`을 읽는 서버 코드는 **0건**이라 「서버가 반응하지 않는다」는 지금 회귀가 아닙니다. 그 사실을 항목 안에 적어 두었습니다.
> - ⚠️ **정렬 캔버스의 웨이퍼 테두리 삭제(`d4e0fed`)에는 항목을 만들지 않았습니다** — 아래 「Map Editor 2에 아직 행이 없다」와 같은 이유이고, 설계 판정은 [architecture/frontend §4.2](../architecture/frontend.md)가 소유합니다.
>
> **직전 라운드 (2026-08-05 · 1차 — `98b48e9`·`f6406b1`)**
> - 🔴 **좌표계 선택 모달의 트리거가 넓어졌고, 이 문서의 세 자리가 그 확대를 모르고 있었습니다**(§2.9 두 항목 · §2.1 자동 등록 토글). 이제 **규격 행이 없는 맵만이 아니라 행이 있어도 START X,Y를 읽을 수 없는 맵**이 모달로 옵니다. 🔴 **자동 등록 토글 점검이 특히 위험했습니다** — 「모달이 떴다」만으로 자동 등록이 꺼졌다고 판정하면 **오진**입니다. 신규 점검 항목 하나(`98b48e9`)를 §2.9에 넣었고, **가장 중요한 축은 `grid_start_x: null`** 쪽입니다(`Number(null) === 0`이라 **화면이 멀쩡한 채** 44셀이 전부 다른 칸에 앉고 Push가 0을 영속화했습니다).
> - **§2.15에 스키마 드리프트 부팅 점검 7항 신설**(`f6406b1`). 🔴 점검자에게 가장 중요한 두 줄: **거절하지 않고 뜨는 것이 정답**이고(막으면 컬럼 하나가 무인 재기동에 스택 전체를 죽여 놓을 권한을 갖습니다), **`/health`로 이 축을 점검할 수 없습니다**(드리프트난 스택은 정상 200을 답합니다).
> - ⚠️ **Map Editor 2(맵 정렬 화면)에는 아직 §1 인벤토리 행도 §2 점검 항목도 없습니다** — 화면이 매일 바뀌는 중이라 지금 쓰면 내일 낡습니다. **총괄이 「프레임을 확정할 수 있다」를 선언하는 라운드에 넣는 것이 이 문서의 규율에 맞습니다**(행이 없으면 회귀 점검에서 구조적으로 빠진다는 위 경고와 상충하므로, **대기 상태임을 여기 적어 둡니다**).
>
> **그 앞 라운드 (2026-08-04)**
> - 🔴 **§2.16-quater(7c 어휘 엄격성)가 출하된 동작을 실패로 판정하라고 지시하고 있었습니다** — 「키 삭제도 `missing`이어야 한다」는 `2c2a777` 이후 거짓입니다. 그 항목에서 「키 삭제」를 빼고, **미선언 보조 역할 완화 점검을 별도 항목으로 신설**했습니다(부재 ≠ 고장 · `validate`도 마커를 실어야 함 · 화면이 `*`로 말해야 함 · 가드 쪽 회귀 · `total_chips` 예외). §1.5의 같은 문장도 정정.
> - 🔴 **§2.0에서 하네스 수를 삭제했습니다.** 세 번 적었고 세 번 낡았습니다 — 러너가 매 실행마다 찍는 수를 산문이 다시 적을 이유가 없습니다. 대신 **`ASSERTIONS` 프로토콜·단언 플로어·부채 산문의 무-수치 규율**을 적었습니다(`b322267`→`efc4514`): **종료 코드는 근거 없는 판결**이고, 그것만 읽던 러너가 죽은 하네스 셋을 부채로 위장시켰으며 27% 커버리지를 잃은 하네스에 「전부 초록」을 찍었습니다.
> - **§1.1 가상 조인 행에 숫자 expose 컬럼 착지 반영**(`5be96f5`).
> - **§1.3 신규 행 + §2.5 신규 3항 — 버전 게이트**(`092b83f`). ⚠️ **선언한 테이블이 없어 지금은 전 테이블 무동작**이므로, 점검하려면 **점검자가 먼저 켜야 합니다**(항목에 그 절차가 있습니다). 🔴 점검자에게 가장 중요한 두 줄: **더 높은 버전이 사람의 교정을 밀면 즉시 결함**이고(그것이 이 기능의 상위 제약입니다), **거절된 행이 반쯤 갱신돼 있으면 결함**입니다(판정은 행 단위·첫 셀 이전). 그리고 **파생 타깃 테이블에 켜면 파생이 멈추는 것이 정상 동작**이라 그 확인이 점검이 아니라 **선언 전 절차**입니다.
>
> **직전 라운드 (2026-07-31 · `9200f20`·`4b50135`·`fbc1053`·`1948338`·`9c6a1c9`)**
> - **§1.1 가상 조인 행 갱신 + §2.2-bis 전면 개정 — 가상 전용 컬럼이 화면에 떴습니다.** 「겹친 컬럼만 눈에 보인다」는 **거짓이 됐습니다.** 🔴 점검자에게 가장 중요한 세 줄: **복사한 직사각형이 선택한 그것과 같아야** 하고(거르면 가운데가 빠져 오른쪽이 밀립니다), **가상 컬럼에 걸친 붙여넣기·delete·Ctrl+Enter는 400이 아니라 「그 컬럼만 조용히 빠지고 나머지는 저장」**이어야 하며, **`미상` 섞인 숫자 컬럼 정렬에서 미해결 행이 흩어지면 결함**입니다.
> - **§1.1·§2.2-bis에 미해결 2건 명시** — **CSV 추출에 가상 컬럼이 없고**, **`미상` 행을 찾을 방법이 없습니다**(필터 없음). 「나중에 될 것」이 아니라 **지금의 한계**로 적었습니다.
> - **§1.8 신규 행 + §2.8-quinquies 신설 — 소급 적용 어드민 API 3라우트**(`fbc1053`). ⚠️ **화면(버튼)은 `77d27d3` 기준 없습니다**(작업 진행 중) — 지금의 점검은 `curl`입니다. 🔴 가장 중요한 한 줄: **`count`가 수만 주고 `count_kind`를 안 주면 결함**입니다(다섯 중 넷은 요청 경로에서 정확할 수 없고, 정확한 척하는 수가 이 라운드가 막는 대상입니다).
> - **§1.12 라우트 수 정정 「16개」→ 22개**, strict 2 → **3**(`POST /admin/retroactive/{op}/run` 추가). §2.16의 strict 점검 항목도 셋으로 늘렸습니다.
> - **§2.0 하네스 게이트 수 정정 16/11 → 18/13** (2026-08-04에 그 수를 통째로 삭제했습니다).
>
> **그 앞 라운드 (2026-07-31 · `d70a33d` · `9d7d9a4`)**
> - **§1.1 신규 행 + §2.2-bis 신설 — 가상 조인 컬럼** (`d70a33d`). 선언만 검증하던 기능이 **실제로 실행**되면서 그리드에 값이 나타났는데 §1에 행이 없어 회귀 점검에서 통째로 빠져 있었습니다. 🔴 점검자에게 가장 중요한 두 줄: **왼쪽 값이 있는 셀은 손대지 않아야** 하고(있는데 조인 값으로 바뀌면 결함), **가상 전용 컬럼 쓰기의 200 + 무변화는 실패**입니다(그 침묵이 이 검사가 막는 대상). 겹친 컬럼만 눈에 보이는 상태라는 것도 함께 적었습니다(`/schema` 미구현).
> - **§1.7 신규 행 — 「기하 편집은 저장 좌표를 지킨다」.** 반응은 함수 하나이고 **부르는 자리가 넷**(규격 6칸 · 파생 직후 · 유효 다이 지정 · **격자 `COLS`/`ROWS`**)입니다. 행이 없어 이 축 전체가 §1 인벤토리에서 빠져 있었습니다.
> - **§2.9 신규 2항 — 치수 편집의 좌표 보존 / 치수가 규칙 ⑤를 덮지 않을 것.** 🔴 점검자에게 가장 중요한 한 줄: **실측 36건 중 20건은 원래 아무 일도 일어나지 않으므로 초록이 통과의 증거가 아닙니다**(이 라운드의 첫 픽스처가 그 20건에 앉아 수리 전에 이미 초록이었습니다).
> - **§2.9 신규 1항 + §1.7 엑셀 복사 행 — 상단 병합이 DOE 보조표 위를 지나가지 않을 것**(`groupMinCols` 하한은 유지, 되붙이기는 영향 없음).
> - **§2.0 하네스 게이트 수 정정 — 15/10 → 16/11.** 수는 `client2/tests/*.mjs` − `KNOWN_RED`이고, 같은 디렉터리의 `seam_7b_oracle.py`는 파이썬이라 **스캔되지 않습니다**(파일 17개 ≠ 하네스 17개). 부채 항목의 「N개 실패」는 **정적 문자열**이라 실측과 이미 갈렸다는 경고를 함께 적었습니다.
> - **F9 ⏳ 표기 해제 (`93610cb`)** — §1.8 기능 행과 §2.8-ter 진입 문단. 진입은 **어드민 Overview 탭의 세 번째 계기 줄**이고, `curl`은 이제 「화면이 지어낸 문장인가」를 가르는 **대조용**입니다. INV-F9-4가 `PENDING`에서 **실행 채점**으로 바뀐 것도 반영.
> - **§2.8-quater 신설 — 조회 실패의 다섯 갈래** (`1dc761b`+`cde3398`). 🔴 **401은 `WWW-Authenticate: X-Admin-Token`이 붙어 있을 때만 우리 게이트**이고, 그 구별이 없어 2026-07-30에 오후 하나를 썼습니다. **교차 출처에서는 CORS `expose_headers`가 없으면 브라우저가 그 헤더를 지우므로** vite dev 오리진에서만 나타나는 오표시가 생깁니다 — 두 오리진에서 각각 점검하도록 항목을 나눴습니다.
>
> **이전 라운드 기록은 [`docs/history/`](../history/)에 있습니다** — 🔴 이 헤더에 쌓지 마십시오(2026-07-30에 7,068자까지 자랐습니다). `Last-verified`는 **날짜 · 이번 라운드에 바뀐 것**까지입니다.
>
> **유지 규율:** 새 기능이 병합·커밋되면 총괄이 doc-keeper에 위임하는 **코드맵 갱신과 같은 사이클**로 이 문서에도 해당 기능 행(§1)과 점검 항목(§2)을 추가한다. 구현 에이전트는 이 문서를 직접 수정하지 않는다.
> **사용법:** §1은 "무엇이 있는가"(기능 지도), §2는 "어떻게 확인하는가"(릴리스 전/회귀 수동 점검). 체크박스는 점검 회차마다 복사해 사용하고 이 원본은 비워 둔다.

---

## 1. 기능 인벤토리 (서브시스템별)

> 진입 경로의 페이지: 메인 그리드 `/`(index.html) · 어드민 `/admin.html` · 맵 에디터 `/map_editor.html` · 인리치먼트 `/enrichment.html` · 그래프 뷰어 `/graph.html` · 추적 리포트 `/trace.html`. 페이지 간 이동은 메인 그리드 우상단 **🧭 Menu** 드롭다운(추적은 「🕸️ 추적」 버튼/메뉴). 코드 열은 [CODE_MAP](../architecture/CODE_MAP.md)의 섹션 참조(소스 전량 읽기 금지).

### 1.1 데이터 그리드 (메인 페이지 `/`)

| 기능 | 설명 | 진입 경로 | 코드 (CODE_MAP) |
|---|---|---|---|
| 테이블 조회 | 테이블 선택 → 페이지네이션+필터+정렬 조회, 셀 객체 `{value,is_overwrite,priority_source}` 병합 표시 | 툴바 `table-select` 드롭다운 | `api.fetchData` → GET `/tables/{t}/data` → `fetch_and_merge_metadata`(§1.1/1.2) · `grid.ensureCellObject`(§7) |
| 셀 편집 | 셀 더블클릭 → 값 입력 → Enter. source=user(priority 0)로 저장되어 자동값을 이김 | 그리드 셀 직접 편집 | `api.handleCellEdit` → PUT `/tables/{t}/data/updates` → `crud.apply_batch_updates`(§2) |
| 범위 일괄 적용 | 범위 선택 후 값 1개를 범위 전체에 적용 | 범위 선택(**마우스 드래그 / Shift+클릭 / `Shift`+방향키** — 2026-07-30 키보드 경로 추가) → 셀 편집 시작(더블클릭/타이핑) → **Ctrl+Enter** 로 편집값을 범위 전체에 적용(시스템 컬럼 제외, Tx 모드면 스테이징) | `ui.applyValueToSelectedRange`(§7) · `grid.js` `defaultColDef.suppressKeyboardEvent` · `grid.js` `extendRangeByKeyboard` |
| 키보드 범위 선택 (2026-07-30) | **손이 키보드를 떠나지 않고** 범위를 잡는다 — 마우스 누름은 공수 계기에서 키 1점 대비 3점이라, 드래그가 필요한 일괄 채우기는 이득 대부분을 반납한다 | 셀에 포커스 → `Shift`+방향키로 사각형 확장(앵커는 포커스 셀, 가장자리에서 클램프) → 값 타이핑 → **Ctrl+Enter**. **평범한 방향키는 범위를 해제**(해제하지 않으면 사용자가 떠난 사각형이 다음 Ctrl+Enter를 받아 의도 밖 셀을 덮어쓴다) · `Esc`도 해제 | `grid.js` `extendRangeByKeyboard`/`visibleRangeColIds` — 선택 모델은 기존 `state.dragStartCell`/`dragEndCell` 재사용(두 번째 범위 구현을 만들지 않음), 렌더는 `clipboard.isCellInRange`/`refreshSelectedRangeDiff` |
| **값 제안 셀 에디터** (F3 · `77a2c15` → Escape 시정 `d5f75a8` · 2026-07-30) | `string` 선언 컬럼의 셀 에디터가 **접두 제안 목록**을 띄우고 **`Enter` 한 번이 후보 채택과 셀 확정을 동시에** 한다(타이머 아님 — AG-Grid가 `suppressKeyboardEvent`를 `cellCtrl.onKeyDown`보다 먼저 부르므로 **같은 이벤트가 확정까지** 수행). 여는 최소 접두 **1**(서버 기본 `min_prefix_length: 0`보다 엄격 — 빈 접두의 첫 후보는 임의 표본이라 `Enter`의 뜻이 사라진다), 요청 한도 **12**, 표시 8행, 디바운스 90ms 트레일링. 컬럼별 학습(플로어·4연속 4xx 비활성·쿨다운)은 **TTL 60초로 만료**(핫리로드되는 `table_config`를 클라 래치가 면제받지 않게) | 그리드 셀 편집 시작 → 1글자 이상 타이핑 | `value_suggest.SuggestCellEditor`/`handleEditorKey` · `grid.buildColumnDefs`(`cellEditor` 갈아끼움) + `defaultColDef.suppressKeyboardEvent` 첫 분기 · `server/value_suggest.py` · [frontend §3.3](../architecture/frontend.md) |
| **가상 조인 컬럼 (2026-07-31 `d70a33d`)** | 선언된 다른 테이블의 컬럼을 **저장하지 않고 조회 시점에** 이 표에 붙인다. 승인된 선언(오른쪽에 조인 키 UNIQUE 인덱스)만 실행된다. **왼쪽에 같은 이름의 컬럼이 있으면 부재일 때만 채운다** — 왼쪽 값 있음 → 그대로 · 비었음 → 조인 값 · 둘 다 없음 → `unresolved_label`(기본 `미상`). 조인이 만든 셀에만 `sources.virtual_join`이 붙어 기존 소스 표시로 어느 쪽 값인지 읽힌다(새 UI 0) | (자동) 테이블 조회 시 — 선언은 `server/config/virtual_join_rules.json` | `virtual_join_executor.attach`(읽기 경로 `fetch_and_merge_metadata`) · `crud.refuse_virtual_join_columns`(쓰기 거부) · [config/virtual_join_rules §4-bis](../guide/config/virtual_join_rules.md) |
| **가상 조인 컬럼이 화면에 뜬다 (2026-07-31 `9200f20`+`4b50135`)** | 왼쪽에 **실재하지 않는** 노출 컬럼(`virtual_only`)이 그리드 **맨 뒤에 덧붙어** 그려진다. 헤더 `🔗`, 색은 시스템 컬럼과 같은 회색, 툴팁이 **오른쪽 테이블과 선언 이름**을 말한다(서버의 쓰기 거부 문구는 「조인 원본에서 고치라」고만 하고 어느 테이블인지 지목하지 못하므로 그 답이 있는 자리는 여기뿐). `/schema`가 **`columns`가 아니라 별도 키 `virtual_columns`로** 알리므로, 이 키를 무시하는 소비자는 **키가 없던 때와 글자 그대로 같게** 동작한다(맵 push 게이트의 「보호 없는 데이터 컬럼」 계수 불변). 🔴 **읽기 전용을 지키는 것은 여전히 쓰기 깔때기 하나**이고 화면의 회색·`editable:false`·`isVirtualColumn` 술어는 **되돌아올 400을 제안하지 않기 위한 것**이다 — 붙여넣기·delete 비우기·Ctrl+Enter 일괄이 각각 가드를 갖는 이유는 **그 셋이 컬럼 목록이 아니라 그리드 컬럼 id로 배치를 만들기** 때문. **복사는 반대**로 가상 이름을 받아들인다(거르면 블록 가운데가 빠져 오른쪽이 한 칸 밀린 직사각형을 돌려준다). 정렬은 전용 비교기(숫자 컬럼에 `미상`이 섞이면 기본 비교가 전부 동률로 만들어 흩어진다). ✅ **검색·필터·CSV 착지**(`cd3e0f4` — 해석값이 SQL 표현식으로 내려가 `미상` 행은 `equals 미상`으로 찾고, CSV 추출이 화면과 같은 값을 싣는다) ✅ **숫자 expose 컬럼 착지**(2026-08-04 N7 — 이전에는 PostgreSQL 타입 오류로 조회 500. 비교 철자는 INT 접기 `3.0`→`3` → [config/virtual_join_rules §4-ter](../guide/config/virtual_join_rules.md)) → 남은 미해결은 [config/virtual_join_rules §9](../guide/config/virtual_join_rules.md) | (자동) 테이블 조회 시 | `main.get_table_schema`(`virtual_columns`) · `virtual_join_executor.announced_columns` · `grid.buildColumnDefs`(append) · `state.isVirtualColumn` · `clipboard.js` 5경로 · `ui.applyValueToSelectedRange` · [backend §2.2](../architecture/backend.md) · [frontend §3.4](../architecture/frontend.md) · 하네스 `client2/tests/virtual_column_render_harness.mjs` |
| 셀 소스 레이어링 조회 | 한 셀에 겹친 소스(파일명·user·collision_merge 등) 목록 확인 | 셀(또는 드래그 범위) **우클릭** → 컨텍스트 메뉴 "📚 데이터 원천(Sources) 관리" — 단일 셀은 소스별 값/타임스탬프, 범위는 배치 모드(소스별 통합 뷰) | `main.openSourcesModal/refreshSourcesList`(§7) · GET `/tables/{t}/{r}/{c}/sources`(§1.3) |
| 수동 우선순위 핀(Pin) | 특정 소스를 표시값으로 강제 고정(우선순위 무시) | 소스 모달의 소스 행별 "📍 Pin" 버튼 — 클릭 시 핀("📌 Pinned" 표시), 핀 상태에서 재클릭 시 해제(토글). 범위 선택이면 선택 셀 전체 일괄 핀 | PUT `.../priority`(단일/배치) → `crud.set_cell_manual_priority_batch`(§1.3/§2) |
| 소스 삭제 | 셀에서 특정 소스 레이어 제거 → 표시값이 차순위 소스로 재계산 | 소스 모달의 소스 행별 "🗑️ Delete" 버튼 → `confirm()` 확인창 → 삭제. 범위 선택이면 같은 버튼이 선택 셀 전체 배치 삭제 | DELETE `.../sources/{s}` · POST `.../sources/delete/batch` → `crud.delete_cell_source_batch` → `compute_priority_value`(§1.3/§2) |
| 행 추가/삭제 | 빈 행 N개 생성 / 선택 행 일괄 삭제(감사 로그 포함) | 툴바 `add-row-btn` / `delete-row-btn` | `api.addRows`/`deleteSelectedRows` → POST `rows`·`rows/batch_delete`(§1.2) |
| 엑셀형 클립보드 | 드래그 범위 선택 → Ctrl+C(TSV 복사)/Ctrl+V(붙여넣기). 헤더 포함 복사 토글 | 그리드 드래그 + Ctrl+C/V, 설정 메뉴 `copy-header-toggle` | `clipboard.setupClipboardHandlers/getRangeSelectedTSV`(§7) |
| 스마트 페이스트(인제션 경유) | 클립보드 내용을 임시 파일(`web_smart_paste_*.{txt,html,csv,json,rtf}`)로 만들어 파일 인제션 경로로 업로드(파서 처리). 행 수 임계 없음 — 자동 발동 아닌 수동 실행 | **`Ctrl+Shift+V`가 본동선**(직행). 우클릭 → "📋 파서로 붙여넣기 (Smart Paste)"는 **클립보드를 읽지 못하고** 다음 붙여넣기를 예약(걸쇠)한 뒤 누를 키를 토스트로 안내한다 — 평문 HTTP에서는 `navigator.clipboard`가 없어 **버튼이 읽는 것 자체가 불가능**하기 때문(`execCommand('paste')`도 차단). 텍스트 계열 포맷이 2개 이상이면 유형 선택 모달(Plain Text/HTML Table/RTF/CSV/JSON), 1개면 즉시 진행. 취소는 Esc | `main.smartPasteFromPasteEvent`(읽기) / `smartPasteViaIngestion`(클릭 진입) / `uploadSmartPastePayload` / `showClipboardTypeModal`(§7) · `clipboard.registerSmartPasteHandler` · `state.smartPasteArmedUntil`/`smartPasteArmedTable` · POST `/tables/{t}/upload` |
| 파일 업로드 | 브라우저에서 파일 선택 → 해당 테이블 워크스페이스로 투입(이후 인제션 파이프라인) | 툴바 파일 업로드(`toolbar-file-input`) | POST `/tables/{t}/upload`(§1.2) |
| 컬럼 선택(표시 토글) | 표시할 컬럼 선택/전체/해제. 선택 상태는 AG-Grid 인메모리 컬럼 상태에만 유지(localStorage 미저장) — **새로고침 시 전체 표시로 초기화**, 테이블 전환 시 컬럼 정의 재구축으로 유지 비보장 | 툴바 `column-selector-btn` → 드롭다운 체크리스트(`col-select-all/none-btn`) | `main.setupEventListeners`(§7) — `gridApi.setColumnsVisible` |
| 페이징/뷰 모드 | 페이지 이동(이전/다음/번호 입력), 뷰 모드 전환, 전체 로드, CSV export. 뷰 모드 2종: `📄 Paging`(pagination — 하단 페이지 컨트롤 표시) / `♾️ Scroll`(infinite — 페이지 컨트롤 숨김, 스크롤 하단 도달 시 다음 청크 자동 로드) | 하단 `prev/next-page-btn`·`page-input`·`view-mode-select`·`load-all-btn`·`load-csv-btn` | `state.currentSkip/pageCache`·`grid.updateViewModeUI`(§7) · GET `/tables/{t}/export`(§1.2) |
| 컬럼 필터/정렬 | 컬럼 헤더 아래 플로팅 필터(텍스트/숫자 타입별), 헤더 클릭 정렬, 최신순 토글 | AG-Grid 헤더 필터 행, 설정 메뉴 `sort-latest-toggle` | `grid.buildColumnDefs`(floatingFilter) · `main.get_column_filter_condition`(서버, §1.1) |
| 트랜잭션 모드 | 편집을 로컬 스테이징 후 일괄 커밋/롤백 | 설정 메뉴 `tx-mode-toggle` → `tx-apply-btn`/`tx-discard-btn` | `main.applyPendingTxEdits/discardPendingTxEdits` · `ui.updateTxModeUI/setTransactionFilter`(§7) |
| ⚰️ ~~그래프 수동 동기화~~ | **[2026-08-14 `2ec78b9`] 은퇴** — `POST /api/graph/sync`가 410이다(프록시 대상 워커가 스택에 없다). §1.9 참조 | ~~툴바 `graph-sync-btn`~~ | — |

### 1.2 변경 이력 (타임라인)

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 글로벌 타임라인 | 최근 트랜잭션 그룹 이력 + 상세 펼침. **[2026-08-11 `dab9152`+`2630790`+`fde424c`] discovery는 bounded scan**(`recent_max_scan_rows` 기본 500,000행 천장) — 대량 인제션 직후 **목록이 실제로 짧게 보일 수 있고, 그 자체는 정상**이다. 점검 방법: 응답 **바디**의 `truncated`가 천장에 걸리면 `true`(리스트 키는 `groups`, 그룹마다 자기 `logs`를 갖는다 — `body.logs`가 아니다). 바디는 CORS와 무관해 교차 출처에서도 그대로 읽힌다. 같은 사실이 `X-Audit-Truncated` **헤더**로도 나가지만(폐기 아님, 병행 발행) 그쪽은 CORS 미노출로 교차 출처에서 지워진다([backend §2](../architecture/backend.md#이력--감사) 참조) — 클라는 헤더가 아니라 바디를 읽으므로 오늘은 무해. ⚠️ **이 라우트에는 `truncated:true`+`next_cursor:null`인 정상 제3상태가 있다**(라이브 병합이 재개 위치를 자름) — 페이저가 없는 오늘은 리더가 이를 "안 잘림"으로 접어 화면에 안 드러나지만, **더 보기 컨트롤을 이 탭에 추가하면 그 접기부터 다시 볼 것** | 메인 우측 History 패널 `tab-global` | `timeline.loadHistory` → GET `/audit_logs/recent`·`/transaction/{tx}`(§1.3/§7) |
| 셀/행 타임라인 | 선택 셀·행의 변경 계보. **[2026-08-11] 응답이 엔벨로프**(`{logs, truncated, next_cursor, limit, returned}`) — 아래 「히스토리 페이징」 행 참조 | 셀 선택 후 `tab-cell` / `tab-row` | GET `/tables/{t}/rows/{r}/history`·`.../cells/{c}/history`(§1.3) |
| **히스토리 페이징(더 보기)** (2026-08-11 `dab9152` 신설) | 200건(기본)을 넘는 행/셀 이력은 목록 끝에 `일부만 (N건) · 더 보기` 한 줄이 붙는다(새 패널·새 모드 없음) — 클릭 시 `next_cursor`로 다음 페이지를 이어 붙인다. 점검: ① 200건 초과 이력에서 그 줄이 뜨는가 ② 클릭이 **같은 행을 중복 없이** 이어 붙이는가 ③ 이력 200건 이하인 셀/행에서는 그 줄이 **안 뜨는가**(`truncated: false`) ④ 테이블 전환 등으로 세션이 바뀐 뒤 오래된 "더 보기" 응답이 도착해도 새 화면을 오염시키지 않는가(세션 토큰은 요청 전 + `res.json()` 이후 두 번 확인) | 셀/행 타임라인 패널 하단 | `timeline.readHistoryPage` + 목록 끝 `<li>`(§7) · `server/audit_history.py` |
| 로그→셀 점프 | 이력 항목 클릭 시 해당 셀로 그리드 내비게이션(페이지 이동 포함) | 타임라인 항목 클릭 | `timeline.navigateToLog` + navigator 단계 함수(§7) |
| DELETE/CREATE 이력 영속 | 행 생성·삭제·소스 삭제·핀 변경도 DB AuditLog에 영속(재시작 후 보존, 이슈 #6 수정) | (내부) | `crud.bulk_insert_audit_logs` 적재 경로(§2) |

### 1.3 파일 인제션 파이프라인

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 커스텀 파서 인제션 | `raws/` 드롭 → `scripts/*.py`의 `match()` 매칭 파서로 파싱·적재 → `archives/` 이동 | `server/ingestion_workspace/<table>/raws/`에 파일 드롭(또는 웹 업로드) | `IngestionHandler.process_with_retry/_discover_and_execute_pipeline`(§3) · [INGESTION_GUIDE](../guide/INGESTION_GUIDE.md) |
| 표준(std) 파서 폴백 | 무스크립트 CSV/TSV/TXT — 헤더가 `display_columns`와 일치하면 스트리밍 적재. 키 결측 행은 스킵+카운트 | 커스텀 파서 무매칭 시 자동 | `std_parser.parse_std_file` · `_resolve_rows/_try_std_parse`(§3/§5) · [INGESTION_GUIDE §1.5](../guide/INGESTION_GUIDE.md) |
| err 격리 + 실패 로그 | 처리 불가 파일은 `err/`로 이동 + `FileIngestionLog` FAILED 기록 | (자동) 어드민 File 탭에서 확인 | `_move_to_err_folder/_log_ingestion_failure`(§3) · [FAILURE_MANAGEMENT_SPEC](../spec/FAILURE_MANAGEMENT_SPEC.md) |
| 실패 재시도(재처리) | 아카이브/실패 파일을 어드민에서 동기 재실행 | 어드민 File 탭 재시도 버튼 | POST `/admin/file-ingestion/retry-failed` → `process_archived_file_sync`(§1.4/§3) |
| 워크스페이스 자동 생성 | `table_config.json` 등록만으로 폴더 스캐폴딩 + 런타임 감시 등록(SYSTEM_RELOAD). 신규 워크스페이스에 config.json은 **더 이상 생성하지 않음**(2026-07-25 폐지) | config 등록 → 자동 | `WorkspaceWatcher._provision_workspaces/sync_new_workspaces`(§3) · [INGESTION_GUIDE §1.6](../guide/INGESTION_GUIDE.md) |
| 워크스페이스 별칭·std_parse 글로벌화 | 폴더명≠테이블명 매핑은 `table_config.json` 테이블 항목의 `workspace_name` 별칭으로, std 파서 옵트아웃은 같은 항목의 `std_parse: false`로 선언(**핫리로드 — 파일 단위 스냅샷 반영**). 무효 별칭(섀도잉·중복·경로 탈출)은 무시+ERROR 1회. 레거시 워크스페이스 `config.json`은 하위호환 읽기+deprecation 경고, 충돌 시 글로벌 승리 | config 등록만 (워크스페이스 config.json 폐지) | `find_workspace_alias/resolve_workspace_root/_snapshot_table_context`(§3) · [INGESTION_GUIDE §1.5](../guide/INGESTION_GUIDE.md) |
| 인제션 진행 토스트 | 파싱·적재 진행률/완료가 그리드 화면에 실시간 표시 | (자동) 메인 페이지 | `utils.showIngestionProgress` · WS `file_ingestion_progress/completed`(§7) |
| 기동/주기 스윕 (이벤트 유실 안전망) | 기동 시·신규 워크스페이스 등록 시 `raws/` 직속 기존 파일을 mtime 순으로 자동 처리 + 300s 주기 잔류 재스캔. (mtime,size) 시그니처로 잔류 파일 무한 재시도 차단, 이벤트 경로와 동일 처리(`_handle_event` 재사용, 락으로 이중 진입 가드) | (자동) 서버 기동만 | `WorkspaceWatcher.sweep_existing_files(_async)/_periodic_sweep_loop`(§3) |
| 대형 파일 heavy 레인 (P1, 2026-07-26) | 크기 임계(기본 10MB, `config/ingestion_settings.json` `heavy_file_mb` — 파일 경계 핫리로드) 초과 파일을 전용 큐/워커(`watcher-heavy-lane` 1개)로 격리 — 대형 파일이 **타 테이블 파일을 막지 않음**(드릴 실측 180배 개선). 같은 워크스페이스 후속 파일은 크기 무관 큐 후미(FIFO 보존), 스윕 경로도 자동 라우팅. heavy끼리는 직렬(알려진 제약) | (자동) 임계 초과 파일 드롭 | `HeavyIngestionLane/_route_and_process/get_workspace_serial_lock`(§3) · [INGESTION_GUIDE §1.7](../guide/INGESTION_GUIDE.md) |
| 오프셋 체크포인트 재개 (P2, 2026-07-26) | 재기동/중단 후 **중단 지점부터** 이어서 적재(종전에는 0행부터 전량 재처리). 오프셋 갱신이 청크 upsert와 **같은 트랜잭션**이라 "커밋된 행 수 == 기록된 오프셋" 성립. 재개는 시그니처+`total_rows`+`source_kind`+오프셋 범위가 전부 일치할 때만 하고, 불일치는 0부터 + **사유를 로그·`FileIngestionLog.detail`·완료 통지에 명시**(조용한 재처리 금지). heavy/normal·스윕·관리자 재시도 4경로 동일. ⚠️ **라이브 드릴 미실행(재기동 대기)** | (자동) 대형 파일 처리 중 서버 중단 후 재기동 | `server/ingestion_checkpoint.py`(§5) · `_plan_checkpoint/_send_to_upsert`(§3) · [INGESTION_GUIDE §1.8](../guide/INGESTION_GUIDE.md) |
| 파일 해시 dedup (P2, 2026-07-26) | 파일 전체 sha256(`sha256:<size>:<digest>`, 500MB 0.535s 실측)로 **동일 내용 재투입을 skip** — archives 이동 + `FileIngestionLog(SKIPPED, 사유)`. ⚠️ **WS 통지의 `status`는 `SUCCESS`**(수신부가 비-SUCCESS를 일괄 실패로 렌더링하므로 오표기 방지), 사유는 `detail`. 강제 재처리 3경로: 파일명 `__force__` / `dedup_by_signature:false` / 관리자 재시도. ⚠️ **라이브 드릴 미실행** | (자동) 같은 파일 재투입 | `ingestion_checkpoint.compute_file_signature` · `_try_dedup_skip`(§3) · [INGESTION_GUIDE §1.8](../guide/INGESTION_GUIDE.md) |
| 폴더 드롭 평탄화 (2026-07-28 `0c6ac1a`) | `raws/`에 다중 층위 폴더로 들어온 파일을 뽑아 루트로 승격, 폴더 계층은 제거(**평탄화 후 폐기** — 폴더는 영구 구조로 감시하지 않음). 트리 정온 게이트(1s 스냅샷 연속 2회 동일, 최대 600s), 충돌은 덮어쓰지 않고 상대 경로 `~` 접두 개명(`__` 금지 — `force` 폴더명이 `__force__` 토큰을 조작함), 빈 폴더만 `os.rmdir`(내용물 있는 폴더는 구조적으로 삭제 불가), 잠긴 파일은 가지째 보존+경고 후 300s 스윕 재시도, 정크(`Thumbs.db`/`desktop.ini`/`.DS_Store`/`._*`) 폐기. 핫 토글 `flatten_nested_dirs`(기본 on). 하류 파이프라인(heavy 레인·파서·체크포인트/dedup·archives/err) 무변경 | (자동) `raws/`에 폴더 드롭 | `IngestionHandler.request_flatten/_flatten_directory`(§3) · [INGESTION_GUIDE §1.9](../guide/INGESTION_GUIDE.md) |
| **맵 메타 자동 등록 (M3, 2026-07-29 `ab6ac02`)** | 인제션(**파일 워처·체인 워커 양쪽**)이 `map_key_columns` 선언 + 좌표 바인딩 해석 가능한 테이블에 적재하면, 배치의 **각 distinct 맵 키**에 대해 `wafer_map_metadata` 행을 **부재일 때만** 생성. 종전에는 수동 에디터 push만 메타를 등록해 `bonding_map` 39만 키에 메타 9행이었고 실사용 대부분이 '화면기준' 폴백으로 떨어졌다. 등록 내용은 **정직한 최소치**(배치 x/y bbox 격자·회전 0·마스크 중립 물리 어휘 — 실제 웨이퍼 원은 **추측하지 않음**, M4 방향), 소스 `auto_map_meta` = **최하위 우선순위**라 사용자 편집이 항상 이김. **절대 덮어쓰지 않음.** 확장성은 distinct 키당 인덱스 존재확인 1회 + 프로세스 수명 캐시. 실패해도 데이터 적재는 정상 완료(격리). 끄는 법 `ingestion_settings.json` `auto_register_map_meta: false`(기본 true, 핫리로드). ⚠️ **기존 메타 없는 키의 소급 백필은 미실행(M4 결정)** | (자동) 맵 테이블에 파일/체인 적재 | `server/map_meta_registrar.py` `MapMetaCollector`(§5) · `_send_to_upsert`(§3) · `process_chain_transaction_group` · [INGESTION_GUIDE §1.10](../guide/INGESTION_GUIDE.md) |
| **버전 게이트 (2026-08-04 `092b83f`)** ⚠️ **선언한 테이블 0 — 전 테이블 무동작** | `table_config.json`에 `"version_column": "<컬럼>"`을 선언한 테이블은, **기계가 이미 있는 행을 덮어쓸 때** 「들어온 버전 > 저장된 버전」일 때만 반영. 낮은 버전이 늦게 와도 현재 값을 되돌리지 못한다(종전에는 마지막 쓰기가 이겨 철 지난 파일 재투입이 무기록으로 값을 과거로 돌렸다). 🔴 **레이어링 *앞*의 거부권이지 승급권이 아니다** — 통과한 행도 셀별 우선순위를 그대로 지나가므로 **더 높은 버전도 사람의 교정을 밀지 못하고**, `user` 소스는 게이트에 닿지도 않는다. 판정은 **행 단위·행 확정 직후·첫 셀 이전**(반쯤 갱신된 행이 생기지 않는다). 같음·부재·해석불가·종류불일치는 각자의 **이름으로 거절**되고, 저장 측에 버전이 없으면 **채택 후 기록**(`row_version_absent`). 비교는 값에서 정해지고 텍스트 비교가 아니다(`'10' > '9'`, ISO 오프셋은 UTC로 접힘). 로그는 행별 0줄 + (테이블,사유)당 프로세스 첫 목격 WARNING + 배치당 INFO. 🔴 **버전 게이트를 건 테이블이 동시에 체인/결손보정 타깃이면 그 파생 쓰기가 전부 거절된다** — 선언 **전** 확인 절차가 있다 | (자동) 선언한 테이블에 파일/체인 적재 | `crud.version_gate_verdict`/`parse_version_key`/`log_version_gate_summary`(§5) · 회귀 그물 `server/tests/test_version_gated_overwrite.py` · **운영자 정본 [guide/config/table_config §7](../guide/config/table_config.md)** · 레이어링 관점 [architecture/data_model §2.1-bis](../architecture/data_model.md) |
| 진행 중 인제션 가시화 + 재기동 경고 (P1) | watcher가 상태(QUEUED/PROCESSING/FINISHED)를 push → 웹서버 인메모리 레지스트리 → `GET /admin/file-ingestion/active`. admin File 탭 진행 섹션(HEAVY/normal 배지·진행률 바·경과, 5s 경량 갱신) + 재기동 경고 배너("재기동 시 처음부터 재처리") + 헬스 스트립/Overview warn. WS 계약 무변경 | 어드민 File 탭 (진행 중일 때 자동 표시) | `ingestion_activity.py`(§5) · `admin.renderActiveIngestions`(§7) · `/internal/events/ingestion-state`(§1.4) |

### 1.4 Auto-Update 스케줄러

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 주석 기반 크론 수집 | `auto_update/*.py` 상단 `# schedule:` 주석대로 주기 실행 → `out` 변수(또는 stdout)를 CSV로 `raws/` 드롭 | 스크립트 배치(무설정) | `run_auto_update.py`(§6) · [AUTO_UPDATE_GUIDE](../guide/AUTO_UPDATE_GUIDE.md) |
| 핫 리로드 | 스크립트/스케줄 주석 수정 시 재기동 없이 다음 실행에 반영(mtime 폴링) | 파일 저장만 | 동상 |
| 즉시 실행/상태 | 어드민에서 스크립트 상태 확인·즉시 실행. **즉시 실행은 active 여부 무관**(수동 실행은 명시적 의도) | 어드민 AutoUpdate 탭 | GET `/admin/auto-update/status` · POST `.../run-now`(§1.4) |
| 수집기 Active 토글 | 수집기별 스케줄 활성/비활성 스위치 — 제어 파일(`config/auto_update_control.json`, 원자적 쓰기·fail-open)에 영속, 스케줄러가 매 틱 읽어 비활성은 SKIPPED 스킵+next_run 전진(**핫 반영, 재기동 불필요**·재활성화 시 백로그 폭주 없음). 비활성 행은 dim 표시, Overview 카드·헬스 스트립에 active/total | 어드민 AutoUpdate 탭 행별 Active 스위치 | `admin.toggleCollectorActive`(§7) · POST `/admin/auto-update/toggle`(§1.4) · `utils/auto_update_control.py`(§6) |

### 1.5 체인 인제션 (파생 데이터)

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 규칙 기반 파생 | 원본 테이블 변경(outbox NOTIFY) → `chain_rules.json` 매칭 맵퍼 실행 → 파생 테이블 업서트 → WS 위임 | (자동) 원본 테이블 인제션/편집 | `chain_ingestion_worker.process_chain_transaction_group`(§4) · [chain_ingestion_guide](../guide/chain_ingestion_guide.md) |
| 지연 SLO 100ms | 원본 커밋 → 파생 반영·통지까지 100ms 목표(정상 실측 31ms). `[Latency]`/`[Warmup]` 상시 계측 | (자동) 워커 로그 | `_dispatch_broadcasts/warmup_worker`(§4) · 이슈 #0 종결 기록 |
| 순환 차단 | source=chain_ingestion 이벤트는 재트리거하지 않음(무한 체인 방지) | (내부 불변식) | `process_chain_transaction_group`(§4) |
| 실패 그룹 격리 | 실패 tx 그룹은 skip하고 후속 그룹 진행(HOL 블로킹 제거), 미전달 통지는 스윕 안전망 | (자동) | `process_pending_groups/sweep_undelivered_broadcasts`(§4) |

### 1.6 Enrichment Queue (결손 보정 워크리스트)

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| dedup 파생(워크리스트 소스) | 대량 원본 → 판단키당 1행 파생 테이블 투영(체인 룰 자동 파생, 멱등 count 집계) | (자동) 원본 인제션 시 | `enrichment_mapper.map_enrichment_dedup` · `enrichment_config.load_enrichment_chain_rules`(§5) · [ENRICHMENT_QUEUE_SPEC](../spec/ENRICHMENT_QUEUE_SPEC.md) |
| ~~컨베이어 입력~~ 🗄️ **화면 자체가 없다** (2026-08-11 `ab36fab`) | ~~결손(blank) 판단키만 순차 제시 → target 입력 → Enter 저장 → 자동 다음 항목~~ — `enrichment.html`이 vite 진입점째 삭제됐다(그 전날 `1e29078`이 먼저 배지·nav 링크만 걷었다). 🔴 **대체 없음** — 커밋 스스로 "opening the fill-in worklist for a named rule; no replacement was built for it"이라고 적는다. `target`을 한 줄씩 타이핑해 채우는 워크플로 자체가 이 시점부터 **UI에 없다**(값 제안 셀 에디터로 그리드에서 직접 채우는 것은 가능 — §3.3). `client2/src/enrichment.js`는 소스에 남아 있지만 **어떤 HTML도 그것을 진입점으로 갖지 않는다**(vite `rollupOptions.input`에서 빠짐, 죽은 모듈). 이 행을 점검표에서 지우지 않고 취소선으로 남기는 이유는 **다음 사람이 이 워크플로가 있는 줄 알고 찾다가 없어서 결함으로 오인**하지 않게 하기 위해서다 | ~~`/enrichment.html`~~ (404) | ~~`enrichment.fetchWorklist/onInputKeydown/saveCurrent`~~(§7) |
| **그리드 사이드바 참조뷰** (2026-08-11 `1e29078` 신설 — 위 항목의 *조회* 절반을 대체) | 선택한 행의 판단키로 참조뷰를 조회 — 예전 컨베이어의 참조 패널과 **같은 백엔드 라우트**를 쓰지만, 이제 메인 그리드 History 패널의 탭 하나다(Cell/Row History 옆). 셀 클릭 시 자동 갱신(`refreshReferenceForSelection`), 테이블 전환 시 그 테이블에 해당 규칙이 있으면 탭이 나타나고 없으면 숨는다(`syncReferenceViewRule`). 판단키가 비어 있으면 조회하지 않고 이유를 말로 표시. 복사는 브라우저 네이티브에 맡긴다(그리드의 자체 클립보드 핸들러가 이 패널 안 텍스트 선택을 가로채지 않도록 격리 — `installReferenceKeyboardIsolation`) | 메인 우측 History 패널 신규 탭 `tab-reference` | `enrichment_reference_view.js`(`showReferenceView`/`syncReferenceViewRule`/`refreshReferenceForSelection`) · GET `/enrichment/rules/{r}/references/{i}`(§1.4/§5/§7) |
| ~~결손 배지~~ 🗄️ **삭제됨** (2026-08-11 `5116f67`) | ~~메인 그리드에 "🧩 결손 N건" 배지 → 클릭 시 해당 규칙 컨베이어로 진입~~ — 배지·클릭 핸들러·`updateEnrichmentBadge`/`notifyEnrichmentTableEvent`(호출자 0건이던 죽은 함수) 전부 제거됐다. 결손을 발견하는 경로는 지금 **그리드 필터**(`?enrichment_queue=<규칙명>`, 아래는 그대로 유효)뿐이고 원클릭 배지 진입은 없다 | ~~메인 툴바 `enrichment-badge`~~ | ~~`ui.updateEnrichmentBadge/notifyEnrichmentTableEvent`~~ |
| 결손 술어(그리드 필터) | 표시 조건: 현재 테이블이 규칙의 **source_table 또는 derived_table 어느 쪽과 일치해도** 적용 가능. **[2026-07-28 `1fefd12`, 2026-08-04/08-05 재정] 결손 술어는 이름으로 요청한다 — `GET /tables/{t}/data?enrichment_queue=<규칙명>`**(= target **하나라도** blank. 종전 `queue_filters`는 필터 dict라 소비자가 논리곱해 「target **전부** blank」가 됐고, target이 둘인 규칙(라이브 2건 모두)에서 한 칸만 채워도 행이 큐를 떠났다 — 서버가 규칙의 `target_fields`로 OR-of-blank를 조성하고 클라는 재구성하지 않는다. 판단키 notBlank는 진행률 분모와 모집단이 갈려 100% 결함을 냈으므로 빠졌다 — 빈 판단키 행은 **큐에 포함**되고 「판단키 없음 N건」은 `&enrichment_queue_scope=blank_key`의 `total`을 **그대로 읽는다**, [ENRICHMENT_QUEUE_SPEC §5.1](../spec/ENRICHMENT_QUEUE_SPEC.md)) — 어드민 카운트가 **같은 서버 술어**를 소비해(`client2/src/enrichment_queue.js` 단일 철자, `admin.js`가 임포트) 수치가 갈릴 수 없음. **[2026-08-11] 이 술어를 메인 그리드에서 직접 거는 UI 컨트롤은 없다** — 배지가 없어졌으므로 `?enrichment_queue=` 쿼리 파라미터를 붙일 수단은 URL을 직접 조작하거나 어드민 Enrichment 탭의 카운트를 보는 것뿐이다 | (URL 파라미터, 전용 UI 컨트롤 없음) | `main.apply_enrichment_queue_predicate`(§1.1) · `client2/src/enrichment_queue.js`의 `queueQuery` |
| 레이어링 보존 | 사람이 채운 값은 source=user(priority 0) — 재인제션·dedup 재실행이 덮지 못함 | (불변식) | `compute_priority_value`(§2) · 스펙 §6 |
| **① 후보 1개 자동 확정 (2026-07-30)** | 참조뷰에 `candidate_for: {target: 뷰_컬럼}`이 **선언된** 경우에만, 그 뷰가 판단키에 대해 **유일값 하나**를 낼 때 체인 워커가 target을 **부재 시에만** 채움. 규칙별 노브 `auto_confirm` **기본 OFF**(이 필드의 blank가 큐 소속을 정의하므로 오확정은 항목을 워크리스트에서 빼버린다 - M3 `auto_register_map_meta`와 형태는 같고 기본값만 다름). 소스 `enrichment_auto_confirm` = `SOURCE_PRIORITY` 미등재 = **최하위(99)** 라 사람 편집이 항상 이김. **컬럼명 유추 없음** - 같은 규칙의 두 뷰가 모두 `wafer_id`를 갖고 한쪽은 후보 N개인 실제 config가 그 근거. 거절은 전부 이름 있음(`ambiguous`=사람의 판단 · `view_error`/`missing_bind`=평가 불가 → 살아남은 뷰가 값 1개를 내도 **거절** · `cell_has_provenance`=사람이 지운 값 보호 · `over_cap` · **[2026-08-05] `no_decision_key`**=판단키가 **전부** 비어 물어볼 것이 없음 · **`no_row_identity`**=row_id도 business key도 없어 쓰면 채우는 게 아니라 **새 행이 생김**). **[2026-08-05] 판단키가 일부만 있는 행도 남은 키로 확정하며**, 그 셀만 소스명이 `enrichment_auto_confirm_partial_key`(같은 서열 99). 작업 단위 상한 `enrichment_auto_confirm_max_keys`(기본 200) 초과분은 **큐에 남고 건수 로그** | (자동) 원본 인제션 시 · 측정은 `enrichment_insights.py confirm --ignore-knob` | `enrichment_candidates.resolve_target_candidate/AutoConfirmCollector` · 체인 훅 `process_chain_transaction_group` · [ENRICHMENT_QUEUE_SPEC §5.2](../spec/ENRICHMENT_QUEUE_SPEC.md) · [config/enrichment_rules §7](../guide/config/enrichment_rules.md) |
| **④ 결손 원인 분류 (2026-07-30, 읽기 전용)** | 큐를 원인별로 나눔: `mapping_gap_same_name`(**소스에 값이 있는데 안 옮겨졌다 = 파이프라인 버그**, 사람이 갚을 일이 아님) · `resolvable_from_reference`(①이 처리) · `ambiguous_reference`(진짜 사람의 판단) · `no_evidence`(소스에 원래 없다) · `no_source_rows` · `unprobed`(탐색 예산 초과 — 다른 분류로 접어넣지 않음). 한계 명시: 버그 분류는 **소스의 같은 컬럼명**으로만 판정하며 다른 이름은 **추측하지 않음** | `enrichment_insights.py classify <규칙>` | `enrichment_analysis.classify_queue` · [ENRICHMENT_QUEUE_SPEC §5.4](../spec/ENRICHMENT_QUEUE_SPEC.md) |
| **② 반복 판단 → 룰 승격 제안 (2026-07-30, 제안만)** | 사람이 채운 셀(`CellSource.source_name == 'user'`)만 훑어 `decision_key`의 **진부분집합 → target** 함수적 종속을 찾고 **`reference_views` 항목 + `candidate_for`** 형태로 제안(이 시스템이 이미 실행하는 형태 — 새 맵퍼 없음, ①이 실행). **config는 절대 쓰지 않음.** 충돌(같은 선행부 → 서로 다른 값)이 하나라도 있으면 제안하지 않고 **거절 이유를 보고**. 단일 컬럼 판단키는 `no_proper_subset` | `enrichment_insights.py propose <규칙> --min-support N` | `enrichment_analysis.analyze_promotions` · [ENRICHMENT_QUEUE_SPEC §5.3](../spec/ENRICHMENT_QUEUE_SPEC.md) |

### 1.7 웨이퍼 맵 에디터 (`/map_editor.html`)

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 맵 로드/저장 | 테이블 데이터 → 캔버스 맵(REST pull), 편집 후 저장(REST push, 배치 업서트). **WS 미사용** | 로드: 좌측 패널 "📂 Load Existing Map" → 로드 방식 선택 모달(📐 Standard / ⚙️ Use Current Left Panel Settings / ❌ Cancel). 저장: 작업영역 툴바 "⚡ Push Map Data" → **[Gate 4 `deed6d2`] 대상이 로그형(맵 계약 밖 데이터 컬럼 보유)이면 모든 다이얼로그 이전에 거부**(table_config `map_push_ok: true` 선언 테이블만 소실 confirm 1회로 완화) → 메타데이터 필드 미입력 시 `alert` 차단, 이후 `confirm("총 N건의 활성 맵 데이터를 '{table}' 테이블에 덮어쓰기 적재(Clean Replace)하시겠습니까?")` 확인 후 전송. 서버 응답 `scope: {filters, deleted, inserted}`가 실제 purge 범위 보고(범위 미파생 = 400, 무음 no-op 폐기) | `loadExistingMap/pushMapData`(§7) · [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md) |
| 지오메트리 프리셋 | 웨이퍼 지오메트리 프리셋 저장/불러오기/삭제 | 프리셋 UI | `/map-presets` CRUD · `fetchAndRenderPresets/saveCustomPreset`(§1.4/§7) |
| **프리셋은 기하만 말한다 — 방향은 운영자의 것** (`02a72c6`, 2026-07-30) | `maps.json`은 운영자가 편집하므로 프리셋이 `rotation`/`side`를 **선언할 수는** 있다. **읽되 적용하지 않는다** — 회전 버튼과 front/back 라디오로 운영자가 이미 방향을 소유하고 있고, 프리셋이 그것을 다시 주장하는 것은 **동의 없이 화면이 움직이는 것**이며 방향이 바뀌면 **모든 셀 번호가 다시 매겨진다**. 선언값이 현재 화면과 **다를 때만** info 토스트 1회로 알린다(확인창·새 컨트롤 0). 확인할 것: ① `rotation`을 선언한 프리셋을 골라도 **화면 회전이 그대로인가** ② 그때 **토스트가 뜨는가**(조용히 무시하면 회귀 — 「무시했다」는 말해야 한다) ③ 선언이 현재 화면과 **같으면 토스트가 안 뜨는가** ④ 적용 지점이 `applyPresetObject` **하나인가**(프리셋 UI·라우팅·자재 프레임·📐 표준 네 호출자 전부 같은 동작) | 규격 프리셋 드롭다운 · 로드 시 라우팅 · 자재 프레임 빈 맵 열기 | `applyPresetObject`(§7) · 토스트 `dedupeKey: 'preset_orientation_ignored'` · [MAP_EDITOR_SPEC §4-bis.4](../spec/MAP_EDITOR_SPEC.md) |
| **좌표 규약 — 화면이 기준, 저장 좌표는 칸수** (사용자 확정 2026-07-30 · `019140c`) | 🔴 **이 표의 다른 모든 맵 행이 이 다섯 줄 위에 서 있다**: ① 화면이 기준(저장은 화면을 따라간다 — **결함은 화면이 *말없이* 움직이는 것**) ② 표시 = 오리진 + DB 값(**한 수량**이다) ③ `start_x/start_y` = **유효 다이 영역**의 최소 열·행이자 **운영자의 선언**(편집기가 자동으로 쓰지 않는다) ④ 오리진 = start가 (0,0)으로 읽히는 칸 ⑤ **저장 좌표 = 오리진 기준 칸수, mm 아님**(칸수에 피치를 곱해 mm로 읽으면 **없는 결함이 만들어진다** — 그렇게 추론한 라운드가 기각됐다). **메타 없는 맵의 📐 표준 분기 회귀 점검**: 로드된 셀의 칸 안 번호가 **DB에 저장된 x/y와 같은가**(달라지면 `019140c`가 고친 결함의 재발 — 종전에는 `startX=0`을 세우고 모든 좌표에서 `minX`를 빼면서 **되더하지 않았고**, 표시와 저장이 한 수량이라 화면이 그것을 드러내지 못했다). ⚠️ **피해 규모는 커밋 메시지의 수를 믿지 말 것** — *"맵 4개 · 셀 1,923 중 451이 Push 도달"*은 감사 추적 실측(`source_name='user'` 239 에피소드)에서 **재현되지 않았다**. **노출은 실재, 실현은 미확인**이고 대비의 전문은 [MAP_EDITOR_SPEC §4-bis.3-bis](../spec/MAP_EDITOR_SPEC.md)에 있다. 만약 손상이 있었다면 `replace_map`이 이력째 하드 삭제하므로 **행 상태로는 판정할 수 없다** | 📂 Load → 📐 표준(메타 없는 맵) | `loadExistingMap`의 `standard` 분기 · `getVisualCoords`/`getCellFromVisualCoords`(§7) · 회귀 그물 `client2/tests/standard_frame_origin_harness.mjs`(19단언 · 변이 7/7) · [MAP_EDITOR_SPEC §1의 0) / §4-bis.3-bis](../spec/MAP_EDITOR_SPEC.md) |
| **기하 편집은 저장 좌표를 지킨다 — 반응 하나, 부르는 자리 넷** (`4761a3a` + **`9d7d9a4`** 2026-07-31) | 원점 상자가 셀 밑에서 움직이는 편집에서 **각 셀을 자기 저장 좌표가 가리키는 칸으로 다시 앉힌다**(`reseatCellsToStoredCoords` — 새 컨트롤 0개·확인창 0개). 해당 입력 **8칸**: 웨이퍼 직경·칩 X/Y·offset X/Y·edge margin **+ 격자 `COLS`·`ROWS`**(뒤의 둘이 `9d7d9a4`에서 합류 — 종전에는 clamp 후 재렌더만 했고, 그것이 같은 결함 계급의 네 번째 자리였다). 규격 프리셋은 `applyPresetObject` → `applyPhysicalGeometry`로 같은 반응을 탄다. 🔴 **회전·면·Y 반전·`START X,Y`는 반대다** — 그쪽은 좌표가 바뀌는 것이 정상이라 이 반응이 돌면 회귀다(규칙 ④가 규칙 ⑤를 덮은 것). 확인할 것: ① 칠한 맵에서 `COLS`를 한 칸 고치고 `⚡ Push` → **x/y가 고치기 전과 같은가** ② 셀이 **화면에서 움직이는가**(§2.9의 상쇄 주의와 함께 읽을 것) ③ `#grid-y-invert` 토글에서 **이 반응이 돌지 않는가** ④ 반응 시점 — 규격 6칸은 **키스트로크마다**, 치수 2칸은 **blur/Enter** ⑤ 🎯 **상쇄 절반을 피할 것**: 실측 36건 중 **20건은 원래 아무 일도 일어나지 않으므로**(`9d7d9a4`) 초록이 곧 통과의 증거가 아니다 | 좌측 패널 물리 규격 6칸 · 격자 `COLS`/`ROWS` · 규격 프리셋 드롭다운 | `reseatCellsToStoredCoords`/`cellsSeatedUnder`/`seatingSnapshot`(§7) · [MAP_EDITOR_SPEC §5.7-ter](../spec/MAP_EDITOR_SPEC.md) · 사용자 안내 [VALID_DIE_MAP_GUIDE §4-bis.1-bis](../guide/VALID_DIE_MAP_GUIDE.md) · 회귀 그물 `client2/tests/geometry_origin_reseat_harness.mjs`(치수 축 케이스 `1d`/`1d2`/`1e`) |
| 브러시 페인팅/레전드 | 셀 값 브러시 페인팅, 레전드 편집(localStorage `map_legend_{table}` 유지). **[U6 `95bf072`] 빈 맵 시드·자동 추가 값의 색/설명·값 컬럼 자동 탐지 목록이 전부 서버 선언**(paint-rules의 `default_legend`/`value_column_candidates` — [MAP_EDITOR_SPEC §5.6](../spec/MAP_EDITOR_SPEC.md)) — 클라 builtin 목록·고정 E1/E2 색 삭제 | 레전드 테이블·브러시 선택 | `selectBrush/renderLegendTable/load·saveLegendToStorage/autoAddLegendValue`(§7) |
| 좌표 변환(회전/면반전) | FRONT/BACK 전환·회전 시 **다이 인덱스** 불변(칩 스탬프, 워터마크 표시) | FRONT/BACK 툴바 칩·회전 컨트롤 | `getDieIndex` 계열(구 `getPhysicalCoords` — 2026-07-31 개명, [MAP_EDITOR_SPEC §1-bis](../spec/MAP_EDITOR_SPEC.md)) · 같은 문서 불변식 |
| 엣지 자동 페인팅 | 엣지 셀 분류·선택·E1/E2 자동 페인팅 | 작업영역 툴바 "🔍 Select Tools" 드롭다운 → "✔️ Select E1" / "✔️ Select E2" / "⚡ Auto-Paint E1/E2" (같은 드롭다운에 "📍 Set Origin (0,0)") | `getEdgeClassification/selectEdgeCells/autoPaintE1E2`(§7) |
| 엑셀 복사 (+ **COPY HEADER MODE**) | 그리드를 클립보드로 복사 — `text/plain`(TSV)과 `text/html`(서식) **둘 다** 싣는다. **COPY HEADER MODE 토글**(`localStorage['mapCopyHeader']`)을 켜면 사용자 회사 본딩맵 양식으로 나간다: 상단 `TITLE`(`테이블 · 맵키`) + 열 그룹 띠(맵키 그룹·1H·MID·TOP) + 우측 보조표 `VALUE \| COUNT \| STACK \| DESC`. `COUNT`는 범례 뱃지·DOE 패널·Push와 **같은 집계**(`eachSavableCell`). **[`5a14e77`] 열 폭은 글자 수 비례 병합**(`headerSpanFor`+`distributeSpans`, 최대 잔여법으로 모든 행의 열 합계 일치) — 종전에는 헤더 칸 = 맵 셀 하나(32px)라 `MIDLOT_01`이 잘렸다. **[`9d7d9a4`] 상단 병합은 맵 격자에서 끝난다**(`max(visualCols, groupMinCols)`) — 종전에는 TITLE·그룹 띠가 `totalCols`에 걸려 **인쇄물에서 DOE 보조표 위를 지나갔다**(실측 23열 맵이 32열, 51열 맵이 60열을 병합). 남는 열은 병합이 아니라 **개별 빈 칸**이라 행 폭은 여전히 `totalCols`이고 **읽기는 영향이 없다**(`VALUE` 열 자리가 안 움직임) | 작업영역 툴바 "🛠️ Edit Grid" 드롭다운 → "📋 Copy to Excel" (+ COPY HEADER 체크박스) | `copyGridToExcel`(§7) · [MAP_EDITOR_SPEC §4-ter](../spec/MAP_EDITOR_SPEC.md) |
| **회사 양식 되붙이기 (Ctrl+V)** (F1ⓑ, `c9bf2c7` 2026-07-30) | 위 양식을 **격자로 되읽는다** — 왕복의 나머지 절반. 격자는 **빈 칸까지** 복원, DOE는 `VALUE`·`STACK`·`DESC`만 복원. **`COUNT`는 알아보되 버리고**(칠한 셀 수는 격자에서 센다), **자재(1H/MID/TOP)·COLOR는 왕복하지 않는다**(상단 그룹 띠는 의도적으로 읽지 않음 — 평문에서 "빈 그룹"과 "병합 연장"이 같은 문자라 구별 불가). 🔴 **붙여넣기는 값을 지우지 않는다**(복사본에 없는 값 = "말하지 않은 것"). 거부 **다섯** 갈래: 열 수 · 행 수 · 정체(TITLE) · **프레임 지문 불일치** · **프레임 지문 부재**(`ae2811c` 신설) — 노치 `D`는 치수가 같은 채 회전/면만 바뀐 경우를 잡는 유일한 신호이고, **자리가 격자 밖이면 대조 자체가 불가능하므로 거부한다**(종전에는 통과 후 확인창 경고 한 줄이었고, 실측 12×10 마스크 없는 격자에서 rot 0 복사본을 rot 180에 붙여 **물리 키 120개 전부의 값이 바뀌었다**). 🔴 **점검 시 반드시 확인**: 선언 맵 **179개 중 노치 on-grid는 27개** — **나머지 152개에서 붙여넣기는 정상적으로 거부되는 것이 맞다**(고장 아님). 지문 술어는 복사·붙여넣기 공유(`notchMarkCell` — **칠해진 노치 셀은 지문 없음**이라 "회전·면이 다릅니다"가 아니라 부재 사유로 거부되고, 값이 진짜 `D`인 셀은 **비워지지 않는다**). 노치는 적용 시 **버려진다**(안 그러면 저장 불가 셀이 생겨 적재 대조 게이트가 그 맵을 영구 거절) | **Ctrl+V** — 새 버튼·메뉴 **0개**(운영은 평문 HTTP라 `navigator.clipboard` 부재, `execCommand('paste')` 차단 → 네이티브 `paste` 이벤트가 유일). 확인창 **1회**, **서버 쓰기 0** | `onMapGridPaste`/`readCompanyMapBlock`/`checkPasteAgainstFrame`/`applyPastedGridRows`/`applyPastedAuxRows`(§7) · [MAP_EDITOR_SPEC §4-ter](../spec/MAP_EDITOR_SPEC.md) · 사용자 안내 [DOE_GUIDE §4.2](../guide/DOE_GUIDE.md) |
| **로드 시 프리셋 라우팅** (F5 서버 `50bddda` + **클라 `73b5925`** 2026-07-30) | `(table, map_key)` → 이 맵을 열 물리 규격(프리셋)을 **선언에서** 결정. 순서가 계약: ①제품코드 조회 테이블 → ②순서 있는 텍스트 패턴(첫 매치 승리) → ③라우팅 없음. **절대 우선순위 `wafer_map_metadata` > 라우팅 > 패널**을 서버가 강제(등록된 규격이 있으면 `meta_present` + preset `null`). ①의 미선언·miss·테이블 부재는 **전부 정상 경로**(조회 테이블은 운영에만 있고 불완전) — 경고 아님, 결과는 `lookup.status`로만. ✅ **클라 절반 착지(`73b5925`)** — 소비자는 `loadExistingMap` **한 곳**(`applyRoutedPreset`), `!loadedGridMeta`일 때 **좌표계 선택 모달·`standard`/`current` 분기보다 앞**에서 호출(그 분기가 패널을 읽으므로 그 순서여야 "라우팅 > 패널"이 성립). **로드당 1회.** 점검할 것: ① 메타 있는 맵은 요청 자체가 안 나가는가 ② 메타 없는 맵에서 **좌표계 선택 모달은 여전히 뜨는가**(폐기되지 않았고 ⚙️의 뜻만 "라우팅이 채운 규격"으로 바뀜) ③ 적용 시 **알림이 남는가**(`c24d47b` 토스트 정리에서 명시적으로 유지 — 적용은 눈에 보이는 변화다) ④ HTTP 실패·`status != ok`가 **강등 없이 조용히** 종전 동작(패널 그대로)으로 가는가 | 맵 로드(📂 Load) — 새 컨트롤 0개, 끄는 스위치 없음(라우팅은 첫 열기 기본값이고 실제로 만드는 것은 첫 ⚡ Push) | `server/map_preset_routing.py` · `applyRoutedPreset`(§7) · `GET /api/maps/preset-routing`(§1.2) · [MAP_EDITOR_SPEC §5.8/§5.8-bis](../spec/MAP_EDITOR_SPEC.md) · 선언 절차 [config/map_overlay_config §2-bis](../guide/config/map_overlay_config.md) |
| **유효 다이 맵 (M4 — 원이 아닌 모양)** (`4d973d6`+`91386f0` → 채택 `73b5925`→`ae2811c`→`7873070`→`d4b9660` → 🔴 **채택 전량 철회 `61440e6`+`94b9baa`**) | "이 셀이 유효한가"의 근거를 **원 기하 대신 다른 맵 하나**로 둔다(`valid_die_ref`). 지정 없는 맵은 **완전 무변경**(순 가산). 저작은 프리셋 드롭다운의 `🧩 유효 다이 맵 만들기` → 평소처럼 칠하고 `⚡ Push` → 쓸 맵의 `🎯 유효 다이 맵` 칸에서 **고르면 곧 적용**되고 `⚡ Push` 또는 `📐 규격만 저장`으로 기록. 참조는 **1단계까지**(순환·자기참조 거부), 참조가 안 풀리면 **조용히 원으로 돌아가지 않고 이름을 대며 거부**(`이 유효 다이 맵을 valid_die_ref에서 찾을 수 없습니다 ― 키 「…」로 등록된 맵 규격(wafer_map_metadata)이 없습니다`, 칩은 `⚠️ 유효 다이 맵 미해석`). 🔴 **[2026-08-04 `5b15c24`] 하루 전의 `🎯 APPLY`/`💾 SAVE` 두 버튼은 삭제됐다** — 점검 항목에서 그 두 버튼을 찾지 말 것. 확인할 것: ⑧ 목록이 완전할 때 **`<select>`가 뜨고 고르는 즉시 적용되는가** ⑨ 목록이 잘렸거나·읽지 못했거나·지금 키가 목록에 없을 때 **텍스트 입력으로 폴백**하고 **`Enter`에만** 반응하는가(타이핑 중·다른 칸으로 이동에 반응하면 회귀) ⑩ `📐 규격만 저장`이 **셀을 하나도 쓰지 않고**, 신원을 **지금 화면의 맵 키**에서 읽으며, 등록이 없으면 확인창이 **「새로 등록」이라고 말하는가**(오타 난 키로 새 등록을 만들 수 있는 자리다) ⑪ 미저장 경고가 **셀이 안 바뀐 경우에 `📐 규격만 저장`을 이름으로 부르는가**(두 문 모두 — 뒤로 가기·다른 맵 로드). 🔴 **점검의 핵심 — 참조가 이 맵과 정렬되지 않을 때: 아무것도 채택하지 않지만 셀은 자기 좌표를 따라간다**(사용자 지시 2026-07-30 · `7a9c2b0`+`da8f390`). 치수도 물리 규격도 회전·면도 **`START X,Y`도** 가져오지 않으므로 **거절도 확인창도 없고**, 마스크는 참조 자신의 격자 기준으로 그려진다. 확인할 것: ① 🎯 **`⚡ Push`가 쓰는 x/y가 지정 전과 완전히 같은가** — 이 라운드에서 유일하게 중요한 축이다(눈으로 보는 법은 §2.9). ② **격자 크기 입력칸·회전·면·`START X,Y`가 한 글자도 안 바뀌는가**(바뀌면 채택이 되살아난 것 = 회귀). 🔴 **칠한 셀은 움직이는 것이 정상이다** — 각 셀이 자기 저장 좌표가 가리키는 칸으로 다시 앉는다(종전 이 항목은 *"셀 위치가 한 픽셀도 안 움직이는가"*였고 `da8f390` 이후 **거짓**이다. 셀이 안 움직이면 오히려 좌표가 깨진 것이다) ③ 알림이 **info 토스트 1회**인가(확인창이면 회귀 · 같은 지정 반복에 중복 안 뜸 — `dedupeKey: 'valid_die_frame_differs'`) ④ 🎯 **크기가 같아도 원점이 어긋나면 알리는가** — 알람 축은 치수가 아니라 **원점**이다(`7a9c2b0`. 크기 비교만 하면 회귀 — 실측 `MID_01 ← 4MAIN_DT`가 같은 크기·다른 원점이다) ⑤ 치수가 다르다는 이유로 **거절하지 않는가**(거절하면 회귀 — 사용자가 두 번 뒤집은 동작이다) ⑥ 참조 메타의 `grid_cols/rows`가 **1~100 정수 밖**이면 셀 조회 전에 거절하는가(1024×1024 메타 행으로 확인 — clamp하면 회귀. **이것이 살아 있는 유일한 거절이다**) ⑦ 콘솔에 **`[유효다이] 1)`~`7)`** 이 찍히는가(사용자가 이 줄로 QA한다 — 빠지면 진단 수단이 사라진다) | 프리셋 드롭다운 `🧩 템플릿 만들기` · 물리 규격 블록 `🎯 유효 다이 맵`(**컨트롤 하나 · 버튼 0개** — 목록이 완전하면 `<select>`로 뜨고 **고르는 즉시 적용**, 아니면 텍스트 입력으로 폴백해 **`Enter`만** 적용. 목록 상한 500) · 되돌리기 = `-- 원 기하 (지정 없음) --` 또는 칸 비우고 `Enter` → **`⚡ Push` 또는 `📐 규격만 저장`** | `resolveValidDie`/`renderValidDieKeyControl`/`onValidDieRefChanged`/`saveMapSpecOnly`/`frameDimBounds`/`isValidDieAt`(§7) · `map_overlay.resolve_valid_die_basis`(§5) · [MAP_EDITOR_SPEC §5.7/§5.7-b/§5.7-bis](../spec/MAP_EDITOR_SPEC.md) · 사용자 안내 [VALID_DIE_MAP_GUIDE](../guide/VALID_DIE_MAP_GUIDE.md) · 회귀 그물 `client2/tests/valid_die_frame_adoption_harness.mjs`(🔴 **점수를 여기 적지 않는다** — 종전 「192 단언 · 변이 16/16」은 두 라운드 만에 낡았다. 인용해야 하면 돌려 보고 인용할 것) · 양측 채점 `contracts/map_seam/`. ⚠️ `adoptFrameSpec`/`storedCoordRepositionPlan`/`applyStoredCoordReposition`/`repositionRefusalReason`/`adoptionCoordinateCost`/`dbCoordsByPhysKey`/`announceFrameAdoption`은 **소스에 없다**(`client2/src/` 0건). ⚠️ **`btn-valid-die-apply`/`btn-valid-die-save`도 없다**(2026-08-04 `5b15c24`에 삭제) |
| 테이블 간 맵 이월 | 테이블 A→B 전환 시 유지/초기화 확인창(컬럼명 상이 시 Advanced Column Mapping 수동 확인 필요 — 이슈 #2) | 테이블 전환 시 자동 확인창 | history `a41007e` |
| 페인트 잠금 (M2, 2026-07-26) | 특정 값(기본 `F`)의 셀을 편집 불가로 잠금. **선언 정본이 서버**(`config/map_overlay_config.json`의 `paint_lock`)로 이동 — 종전 클라 하드코딩 `'F'` 대체. **조용한 fail-open 제거**: 404/405만 "선언 없음"(해제), 네트워크·5xx는 직전 잠금 유지 + `⚠ 잠금 규칙 미확인` 툴바 칩 + 경고 토스트. 모든 편집 경로가 `isProtectedFCell` 단일 관문 통과. ⚠️ **콜드 스타트(페이지 로드 후 첫 조회 실패)는 아직 잠금 없이 시작**(QA C4 미해소 — 칩은 뜨나 잠기지는 않음) | (자동) 맵 로드 시 규칙 조회 · 툴바 잠금 칩 | `fetchPaintRules/isProtectedFCell`(§7) · GET `/api/maps/paint-rules`(§1.2) · `map_overlay.get_paint_rules`(§5) |
| **범용 맵 오버레이** (M2 → `7d931dc` 클라 일원화, 2026-07-26) | 임의의 맵을 임의의 맵 위에 겹쳐 본다(계획 전용 아님, **맵 인프라**). **좌표 변환은 클라 단일 구현** — 소스 원본 좌표를 소스 자신의 `wafer_map_metadata` 프레임으로 해석해 투영하므로, 사용자가 화면 규격(회전·면·치수·물리값)을 바꾸면 **메인 맵과 오버레이가 함께 움직인다**. ✅ **[2026-07-31 `cd3e0f4` 규칙 6] 셀 크기가 다른 맵도 겹친다** — 다이 인덱스가 아니라 **절대 웨이퍼 mm**를 거쳐 앉힌다(`projectCellsToWaferMm` → `seatWaferMmInFrame`). 🔴 **점검: 종전의 「소스·타깃 `cols×rows`가 다르면 거절」은 이제 회귀다** — 거절이 남은 자리는 **치수가 `1~100` 정수 밖**(온전성 가드 — 1024×1024 메타 행이 104만 칸 동기 루프를 돌린다)과 **피치를 확정할 수 없음** 둘뿐이다. ⚠️ **소스 메타가 격자만 선언하고 `phys_chip_x/y`를 비우면 타깃 화면 피치로 메꿔져 「화면은 완벽히 정렬돼 보이고 값은 전부 틀린」다**(실측 600칸 중 570칸) — 그 조합을 한 번 확인할 것. 셀 상한 2,000(메인 로드와 동일, 초과 시 `truncated`). 레이어별 색점 마커·표시 토글·정렬 상태 칩(`align.origin` 기준 — `무보정`/`정렬됨 N°`). 명명된 실패 status **4종**(`meta_unavailable`/`binding_unavailable`/`align_unavailable`/`no_data`, + IO 실패는 일반 `error`) 전부 **그리지 않고 목록에 행으로 남음**(재시도 버튼 유지). *(구 `align_unconfirmed`·`align_override_declared`는 서버 선언 레이어와 함께 2026-07-27 삭제 — 물어볼 선언이 없어졌고 REST 왕복도 하나 줄었다)* **[F1/F2 `17f65bd`] 좌표 바인딩은 이제 서버가 해석해 서빙한다**(paint-rules의 `binding` — 선언 > 유도, `{x,y,val,key_columns,source}`): 클라 자체 유도 ~40줄과 대소문자 무시 x/y 매칭기가 **삭제**됐고, 그래서 `table_bindings`에 선언만 있으면 대문자·한글·숫자 시작 테이블명이나 `tx`/`ty` 좌표도 **선언만으로 로드·오버레이된다**(사용자가 보고한 "오버레이 설정이 안 먹는다"의 실제 원인 — 서버는 존중하는데 클라가 읽지 않았다). 값 컬럼이 후보에 하나도 안 맞아 **추측**된 경우 `source: "fallback_guess"`로 표기되며 **오버레이 경로는 거부**한다(로드 경로는 경고 후 진행) — 추측 컬럼을 칠하면 미끼 셀이 된다 `📥 가져오기`는 `gridData`로만 반영(서버 쓰기 없음, 잠금 존중, 격자 밖 제외). **메인 맵 로드와 코드 경로 완전 분리**. **기준이 바뀌면 해제**(맵 로드·테이블 전환·프레임 진입). ⚠️ 정렬은 `wafer_map_metadata` 등록 맵에서만 실제로 일한다(§5.0 — 미등록은 `무보정` 폴백) | 맵 에디터 오버레이 블록 `＋ 겹치기` | `addOverlayLayer/projectCellsToPhys/syncOverlayGeometry/importOverlayToGrid`(§7) · GET `/api/maps/overlay`(§1.2 — **맵 에디터 클라는 이 엔드포인트를 호출하지 않는다**. 선언 probe가 사라지면서 마지막 호출처가 없어졌고, 서버 경로는 `bonding_plan`/`transfer_plan` 가용량 산출이 쓴다) · `server/map_overlay.py`(§5) · [MAP_EDITOR_SPEC §5](../spec/MAP_EDITOR_SPEC.md) |
| **전사 계획 사이드바** (M2-v2, 2026-07-26) | **「계획 = 지금 열어 편집 중인 그 맵」** — `bonding_map`을 열면 본딩 계획, `dt_map`을 열면 DT 계획. stage는 열린 테이블에서 유도(선택 UI 없음), `plan_id`·계획 맵 사본 없음. legend = **DOE 아코디언**(값 = 조건군 = `map_split_registry` 행 하나). **[ZONE 2026-07-28 `b35bc9f` — band 모델 대체]** 층 구조는 행의 **`stack`(총 층수) + 고정 구역 셋**(`mat_1h`=1층 · `mat_top`=STACK층 · `mat_mid`=그 사이 전부, 1H/TOP이 비면 MID가 그 끝까지)이고, 수량은 저장하지 않고 파생한다(`칠한 셀 수 × 구역 층 수`, 매당 `ceil` — 합을 먼저 내고 나눔). **[U9 2026-07-28] STACK `0` = 상태 표시 값(마커)** — 구역 해당 없음·소요 0·롤업 부재, 마커 행은 V6(구역에 자재가 남은 모순) 하나에만 답한다. 검증 규칙은 V1~V6(정본 `contracts/doe_band_rules/vectors.json` v3)이며 **보고만 하고 저장을 막지 않는다** — 저장을 막는 것은 데이터 보호 게이트 4종(zone 컬럼 없음 · legacy 해석 불가 · 적재 대조 · 로그형 대상, [MAP_EDITOR_SPEC §6.0-ter](../spec/MAP_EDITOR_SPEC.md)). 🗄️ `bands`는 폐기·읽기 전용(표현 불가 레거시 행은 접지 않고 거부). 패널은 서버에 직접 쓰지 않고 legend 저장 경로 하나로 씁니다. 자재 목록 DOE별 그룹 + `openMaterial`이 맵 간 이동의 유일 허브(브레드크럼·뒤로가기). 자재 가용은 `가용 = 총 − (fail ∪ 기전사)`. **서버가 degraded면 `remaining`이 `null`로 오고 클라는 이를 초록으로 뒤집지 않는다.** **[7c `ab6ac02`] 소모 기록이 아예 없는 사이트는 `transfer_log: "none"`을 선언**해 `connected(untracked)`(강등 아님)로 갈 수 있다 — `transferred`는 가짜 0이 아니라 `null`, `remaining`은 `null` + 진짜 상한 `remaining_upper_bound` + 경고 `transfer_untracked`(클라는 `미상` 대신 `≤N` 렌더 가능). **정확히 문자열 `"none"`만 이 선언이고 JSON `null`·`"None"`처럼 값이 있는데 그 값이 아닌 형태는 `missing` 그대로**. ⚠️ **[2026-08-04 정정] 「키 삭제」는 여기서 빠졌습니다** — 키 부재는 이제 `not_declared`이고 `remaining`이 **숫자**로 나갑니다(아래 완화 항목 · [MAP_EDITOR_SPEC §6.2-ter](../spec/MAP_EDITOR_SPEC.md)). 두 선언은 답이 다릅니다: `"none"` = 「추적을 안 한다 → 상한만 안다」, 키 부재 = 「그 표가 없다 → 그 감산 없이 센다」. **[2026-08-04 `2c2a777`+`101311f`] 보조 역할 미선언 완화** — `transfer_log`·`origin_log`·`fail_sources`·`process_history`의 **키가 아예 없으면** 강등이 아니라 `not_declared`이고 가용이 **숫자**로 나가며, 빠진 감산의 이름이 `inactive_subtractions`로 실립니다(요약·`scope=lot`·M1 `core-summary`·**`validate`** 전부). 클라는 가용·잔여 칸에 **`*` 각주 표시**를 붙이고 ② 각주에 그 이름을 그대로 인쇄합니다. 🔴 **`total_chips`는 예외로 계속 필수**입니다. **[7b `ab6ac02`] 풀 바인드·맵 정체성 조합은 선언 컬럼 타입으로 캐노니컬화**된다(`number` 선언이면 `'01'`=`' 1 '`=`1.0`=`'1'`) — 패딩 어긋남으로 가용이 0으로 보이거나 메타를 못 찾던 결함의 수리. 검증/경고 UI는 **미구현**(사용자 지시 보류 — `__held_*` 구역) | 맵 에디터 우측 사이드바(맵 로드 시 자동) | `transfer_plan.js`(§7) · GET `/api/transfer-plan/{stages,source-summary,validate}`(§1.2) · `server/transfer_plan.py`(§5) · [MAP_EDITOR_SPEC §6](../spec/MAP_EDITOR_SPEC.md) |
| 본딩 실험계획 (M1) — **UI 대체됨** | M1의 조회 전용 Info 패널(`bonding_plan.js`/`.css`)은 `8e34804`에서 **삭제**되고 위 전사 계획 사이드바로 대체됐습니다. **서버 API `GET /api/bonding-plan/core-summary`와 `server/bonding_plan.py`는 존치**하며, `transfer_plan`의 core-kind 경로가 여기에 위임합니다 | (직접 UI 없음 — 전사 계획 경유) | `server/bonding_plan.py`(§5) · GET `/api/bonding-plan/core-summary`(§1.2) |

### 1.8 어드민 대시보드 (`/admin.html`) — 파이프라인 생애주기 5탭 IA (2026-07-25 재편)

탭 축은 **파이프라인 생애주기 5탭**(`#overview/#file/#chain/#autoupdate/#enrichment`) + 코드 에디터 **공용 뷰**(`#editor=<path>` 딥링크). 구 해시 별칭(`#outbox→#chain` 등) 호환 유지.

> 🔒 **2026-07-27(`90e284f`)부터 아래 탭이 부르는 `/admin/*` API는 전부 공유 토큰 게이트 뒤에 있다.** 페이지(`GET /admin.html`) 자체는 열려 있으므로 화면은 뜨지만, 토큰이 없으면 **모든 표가 비어 있고** 클라가 토큰을 한 번 묻는다. 게이트 자체와 점검 절차는 **§1.12 / §2.16**에 있고, 이 절은 게이트를 통과한 뒤의 기능만 다룬다.

> ⚠️ **아래 표는 3열이다. 네 번째 셀을 쓰면 렌더러가 그것을 조용히 버린다** — 2026-07-31 이전 F9 행이 정확히 그 상태였고 **「코드」 칸이 화면에서 통째로 사라져 있었다.** 진입 경로와 코드는 **마지막 칸 안에서** `·`로 나눠 쓴다.

| 탭/기능 | 설명 | 진입 경로 · 코드 |
|---|---|---|
| Overview | 파이프라인 4카드(File/Chain/AutoUpdate/Enrichment) 헬스 요약 + 최근 이벤트 + 각 탭 딥링크. 상단 파이프라인 헬스 스트립 공용 | `fetchOverview/renderOverview` · `parseRoute/applyRoute/switchTab`(§7) |
| Overview 상단 **핵심가치 #1 두 줄** | **재교정률**(사람이 같은 셀을 두 번 이상 고친 비율 — 보조 계기) + **교정 공수**(한 교정 완료까지의 상호작용 점수 = 정본 계기, 2026-07-29 신설). 두 줄이 `/dashboard/summary` **한 응답**을 공유하고 5분 스로틀 하나를 쓴다(무거운 엔드포인트라 Overview 자동 갱신 루프에 태우지 않음). 점검 시 확인할 것: ① 값 옆에 **분모/커버리지가 항상 함께** 있는가 ② 값이 없을 때 `0`이 아니라 **`—` + 사유**인가 — 특히 `measured_ratio === 0`(사람 교정은 있는데 계측 0건 = **수집 중단**)이 danger 톤 경고로 뜨는가, 응답에 `effort` 필드가 아예 없을 때 "교정 없음"이 아니라 "**서버가 보고하지 않음**"이라고 하는가 ③ 카드·패널·차트·새 탭이 생기지 않았는가(한 줄 유지) | `renderRecorrection`/`renderEffort`/`refreshCoreValueLines`(§7) · [frontend §5](../architecture/frontend.md) |
| File | 파일 인제션 로그/실패 목록·재처리 + 워크스페이스 현황 + 파서 스크립트 편집 딥링크 | `renderFileTable/retryFileIngestion/renderWorkspaceTable/selectFileRow` · `/admin/file-ingestion/*` |
| Chain | outbox 실패/대기 트랜잭션 재시도 + 체인 룰·맵퍼 목록 + 이벤트 진단(Edit Mapper 딥링크) | `renderOutboxTable/renderChainTable/renderMapperTable/showEventDiagnostics` · `/admin/outbox/*`·`/admin/chain/rules`·`/admin/mappers/list` |
| AutoUpdate | 수집기 상태·즉시 실행·**Active 토글**(§1.4) + 산출물 인제션 실패 교집합(`renderLinkedFailTable`) | `renderAutoUpdateTable/toggleCollectorActive/runAutoUpdateNow` · `/admin/auto-update/*` |
| Enrichment | 규칙별 결손 현황(15s TTL 캐시 — 스트립·탭·Overview 공용) + 컨베이어 딥링크 | `renderEnrichmentTable/fetchEnrichmentStatus` · `/enrichment/rules` |
| Code Editor(공용 뷰) | Monaco(CDN) 파일 피커 + 스크립트 편집·저장(인라인 폴백, dirty confirm) — 각 탭에서 `#editor=<path>` 딥링크 진입 | `initMonacoEditor/populateEditorPicker/selectEditorFile/saveScriptCode` · `/admin/scripts/*` |
| Config Reload | `table_config.json` 등 핫리로드(+SYSTEM_RELOAD 전파로 워커도 리로드, 신규 테이블 물리 CREATE 포함). 🔴 **이 버튼은 쓰기 전용이다** — 캐시를 갱신하고 워커에 이벤트를 뿌린 뒤 **무엇이 먹었는지 아무것도 돌려주지 않는다.** 그 공백을 메우는 것이 아래 행이므로 **둘은 짝으로 읽는다** | `reloadSystemConfigs` → POST `/admin/reload-configs`(§1.4) |
| **config 선언의 효과 조회 (F9, 2026-07-30 서버 · **2026-07-31 화면 착지** `93610cb`)** | 「내가 쓴 config가 먹었나」에 제품이 답한다. `GET /admin/config/resolve`가 선언을 **세 모집단**으로 나눠 돌려준다 — `effective` · `ineffective`(+ **명명된 사유**) · `rejected`(+ 사유) + `settings`(실효값과 **그 값이 온 파일**, 파일 부재로 기본값인 경우 포함). ✅ **진입은 어드민 Overview 탭의 세 번째 계기 줄**이다(`admin.js`의 `refreshConfigResolve` → 뷰 모델 `config_resolve_view.js`). 1분 스로틀 · `Reload Configs`를 누르면 force로 즉시 다시 읽는다. 🔴 사람이 읽을 문장(`detail`)은 **서버가 만들고 클라는 그대로 렌더해야 한다**(계약) — 클라가 「효과 없음」을 자기 규칙으로 판정하면 하드코딩 사본 계급이 재발한다. 사유 어휘는 닫혀 있고 **전부 런타임 열화 어휘 재사용**(`not_declared`·`mapping_unavailable`·`scope_unresolved`·`not_reached` — 새 단어 0). ⚠️ **`scope_unresolved`는 켜기 전 경고**: 선언 뷰가 판단키의 일부만으로 조회하면 런타임은 `ambiguous`가 아니라 `single`을 내므로 실행 중에는 보이지 않는다. DB 질의 0건(config만). 드라이런은 별도 라우트이고 **HTTP에 쓰기 경로가 없다**. ⚠️ **등록된 도메인은 2026-07-31 실측 `enrichment` · `virtual_join` 둘**이고 나머지는 같은 틀로 붙는다 — 도메인을 추가하면 [DOC_OWNERSHIP](../process/DOC_OWNERSHIP.md)의 해당 행과 이 행을 함께 고친다 | 진입: `GET /admin/config/resolve` · `GET /admin/enrichment/auto-confirm/dry-run?rule=`(어드민 토큰) — 코드: `config_resolve_report.resolve_report` · 점검 §2.8-ter · [ENRICHMENT_QUEUE_SPEC §5.2-bis](../spec/ENRICHMENT_QUEUE_SPEC.md) · [CONFIG_GUIDE §4.2-bis](../guide/CONFIG_GUIDE.md) · [config/enrichment_rules §7.3-bis](../guide/config/enrichment_rules.md) · 계약 `contracts/config_resolve_report/` |
| **소급 적용(backfill) 어드민 API — ⚠️ 화면은 아직 없다 (2026-07-31 `fbc1053`)** | CLI에만 있던 **소급 5종**(R1 재적용 · R2 소스 회수 · enrichment 파생행 생성 · 단일 후보 자동 확정 · 그래프 고아 스윕)에 **인벤토리·건수·실행** 라우트가 생겼다. ⚠️ **어드민 화면의 버튼은 `77d27d3` 기준 아직 없다**(그리는 클라 코드가 커밋 트리에 없다 — **다만 화면 작업이 진행 중이므로 인용 전 `client2/src`에서 grep할 것**) — **지금의 점검은 `curl`이다.** 🔴 **인벤토리·건수 응답이 `deletes`·`restartable`·`commit_granularity`를 실어 나른다**: 확인 문구 하나로 다섯 버튼을 덮으면 그 하나가 틀리기 때문이다(넷은 청크 커밋이라 이어서 재실행되지만 **고아 스윕만 삭제 루프가 끝난 뒤 한 번 커밋**해 중단 시 전부 롤백). 🔴 **모든 건수가 `count_kind`를 함께 답한다**(`exact`/`sample`/`upper_bound`) — 다섯 중 넷은 요청 경로에서 정확할 수 없고 **어느 것도 정확한 척하지 않는다**. 실행은 **아웃박스 한 줄 + 즉시 반환**이고 실제 실행은 스케줄러 전용 스레드(동시 1건). **새 연산은 하나도 구현하지 않았다** — 카운트는 각 연산 자신의 dry-run, 실행은 같은 함수의 `apply=True` | 진입: `curl -H "X-Admin-Token: …"` → `GET /admin/retroactive/operations` · `.../{op}/count` · `POST .../{op}/run`(**strict 토큰**) — 코드: `server/retroactive.py`(등록부) · `run_auto_update.start_retroactive_run` · 점검 §2.8-quinquies · [BACKFILL_GUIDE §7](../guide/BACKFILL_GUIDE.md) · [backend §2](../architecture/backend.md) · [AUTO_UPDATE_GUIDE §4-quater](../guide/AUTO_UPDATE_GUIDE.md) |

### 1.9 ⚰️ ~~온톨로지 그래프 (승격·뷰어·추적)~~ — **은퇴 · 점검 대상 아님** (2026-08-14 `2ec78b9` · R-2026-08-14-H)

> 🔴 **이 절의 모든 행은 «지금 돌리면 실패하는 점검»입니다 — 실행하지 마십시오.** 워커가 스택에서 빠지고, `graph_nodes`·`graph_edges`·`graph_sync_state`가 **DROP**됐으며(약 841 MB), 라우트 일곱이 **410**을 답합니다. 후계 점검은 **§1.13 원장** 쪽입니다.
>
> ✅ **대신 점검할 것 하나** — **은퇴가 정직하게 보이는가**: ① `GET /graph/stats` → **410**이고 본문에 `reason: "old_graph_branch_retired"`·`successor: "/api/ledger/trace"`가 있다(404도 200도 아니다) ② 응답 헤더에 **`Cache-Control: no-store`** ③ `graph.html`을 딥링크로 열면 **묘비**가 뜨고 구조 뷰로 가는 링크가 있다 ④ 메인 그리드 nav에 「🕸️ 추적」이 **없고**, 행 선택 버튼도 **뜨지 않는다**(클라 변경 0줄 자기 치유) ⑤ **재기동 후에도 세 표가 다시 생기지 않는다** — 이것이 봉인된 부활 경로 셋의 회귀 점검이고, 실패하면 화면이 「그래프가 아직 비어 있습니다」로 **은퇴를 「아직 안 됨」으로** 말한다. 자동 그물은 `server/tests/test_graph_branch_retired.py`.

<details>
<summary>⚪ 이하 원문(역사 기록)</summary>

#### ~~1.9 온톨로지 그래프 (승격·뷰어·추적)~~

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| ~~온톨로지 그래프 승격·재동기화·고아 스윕~~ | ⚰️ 2026-08-16 실행 코드와 `ontology_mapping.json` 설정을 제거했습니다. `/graph/*`와 `/api/graph/sync`는 SPA HTML 200 오인을 막는 410 종료 계약만 유지합니다 | 사용 금지 | [retired graph sync archive](../_archive/retired_graph_sync/README.md) · 후계 [LEDGER_GUIDE](../guide/LEDGER_GUIDE.md) |
| 서브그래프 뷰어 | stats 카운트 카드 + identity 자동완성 검색 + k-hop(1\|2) 이웃 탐색을 BFS 동심원 캔버스로 렌더(무라이브러리). 팬·줌, truncated 배지, user provenance 엣지 강조. **노드 클릭=선택**(Connections 테이블), **중심 이동은 더블클릭/시드 버튼**(2026-07-25 `18218da`부터 UX 변경) | `/graph.html`(🧭 Menu 또는 추적 리포트 크로스링크 `?label=&identity=`) | `graph_viewer.js`(§7) · GET `/graph/stats·neighbors·nodes/search`(§1.5) |
| 뷰어 Connections 테이블 + 검색 시드 연동 | 노드 클릭 → 우측 패널에 선택 노드 정보 + 관계 테이블(방향 →/←/⟲·엣지 type·상대 노드 요약·event_time). 비중심 노드는 서브그래프 단면 즉시 표시 후 depth-1 재조회로 전체 이웃 보강, 80행 단위 "더 보기". **행 클릭 → 해당 노드 중심 재조회 + URL `?label=&identity=` push + 검색바 반영**(뒤로가기 복원 지원). 패널 접기 토글 | 뷰어 캔버스 노드 클릭 | `selectNode/fetchNodeConnections/renderConnBlock/syncUrl`(§7 graph_viewer.js) |
| 뷰어 라벨 노드 리스트 | stats 라벨 카드 클릭 → 그 라벨의 노드 목록 테이블(identity 오름차순, 서버 페이지 200 + "더 보기", 로드수/총수 헤더) → 행 클릭 시 중심 탐색, back으로 Stats 복귀. 서버는 빈 q + label 리스팅(캡 200 — 자동완성 캡 50 불변, 전 테이블 덤프 금지) | 뷰어 첫 화면 라벨 카드 클릭 | `openLabelNodes/fetchLabelNodesPage/renderLabelNodesBlock`(§7 graph_viewer.js) · GET `/graph/nodes/search`(§1.5) |
| 객체 중심 추적 리포트 | 멀티 시드(≤20) BFS 합집합 → 라벨별 그룹 테이블 + event_time 타임라인. depth 1..3·시간 범위·타입 필터, missing seeds 분리 표시, 뷰어 양방향 크로스링크 | `/trace.html` — 메인 그리드 행 선택 → 「🕸️ 추적」 버튼(새 탭, 선택 행→identity 시드) | `trace.js`/`trace_core.js`/`trace_launch.js`(§7) · POST `/graph/trace`·GET `/graph/mapping-summary`(§1.5) |
| 추적 진입점 자동 표시 | `mapping-summary`로 현재 테이블의 매핑 활성 여부를 판정해 「🕸️ 추적」 버튼 노출/숨김. **[`530fdfd`] 같은 응답이 `rejected[]`·`rejected_count`·`source{path, exists}`를 함께 싣는다** — 컬럼 하나 rename에 그 테이블의 온톨로지가 통째로 사라지던 것이 표면에 안 나왔기 때문. 점검: **정상 상태에서 `rejected`는 반드시 비어 있어야** 하고(늘 뭔가 들어 있는 사유 목록은 곧 무시당한다), **파일 부재는 거부가 아니라 `source.exists: false`로만** 나오는가 | (자동) 메인 그리드 툴바 | `trace_launch.refreshTraceEntry`(§7) · GET `/graph/mapping-summary`(§1.5) |
| **칩 추적 (`GET /graph/chip-trace`)** — 경계 계약 (`8670e3b`+`ae2811c` 2026-07-30) | 칩(`CoreCell`) 1개의 이력을 **웨이퍼 스코프**로 추적. **BFS가 아니라 고정 형상**이고 **depth 파라미터가 없다** — 같은 시드의 `POST /graph/trace` depth 2는 1,000 노드 캡을 태우고 그중 **994개가 형제 CoreCell**(남의 칩)이며, 엣지 타입 필터로 막으면 홍수가 **더 커진다**(1,341→11,549, `Eqp` degree 10,284로 우회). 3다리: ① 칩 자신(`BONDED_TO→BaseCell`·`TRANSFERRED_TO→DtCell`) ② 웨이퍼(`FROM_CORE→Core` ← `PERFORMED_ON`) ③ 잎(`USED_KNOB`/`USED_RECIPE`/`EXECUTED_BY` — **되확장 금지**). 실측 234노드/694엣지·57ms·무관 노드 0. 🔴 **점검의 핵심은 "빈 홉이 없는가"다** — 다리마다 `recorded`·`none_recorded`(선언 있고 행 0)·`not_declared`(매핑이 그 쌍을 더는 선언 안 함)·**`mapping_unavailable`**(선언을 **읽지 못했다** — 매핑 파일 저장 중/거부/부재. 확인: 파일을 잠깐 깨뜨리면 `not_declared`가 아니라 이쪽이 나오는가, 그리고 `recorded`/`none_recorded`는 **강등되지 않는가**)·**`not_reached`+`blocked_by`**(앵커 다리가 죽어 **묻지 않았다**. 확인: `PERFORMED_ON`을 rename하면 잎이 `USED_KNOB: none_recorded, count 0`이 **아니라** `not_reached`로 나오는가 — 종전 버그가 "이 웨이퍼는 knob을 쓰지 않았다"고 주장했다) 중 하나를 말한다. 스코프는 `scope_unresolved`(Core 주장 0개 또는 2개 이상, **또는 그 다리가 잘림** — 라이브 2,687셀이 소스 파일별 복수 `FROM_CORE`를 가진다). **절단은 상태가 아니라 다리별 `truncated`+`capped_at`**이고 `count`(주장 수)≠`node_ids`(개체 수)는 **의도**다 | 아직 전용 UI 없음 — REST 직접 호출(`?identity=<CoreCell identity>`). 시드 부재 404 | `main.py get_chip_trace`/`_chip_trace_leg`/`_chip_trace_declaration`(§1.5) · [ONTOLOGY_GRAPH_SPEC §7.5d](../spec/ONTOLOGY_GRAPH_SPEC.md) · [backend §2 그래프 조회](../architecture/backend.md) |

</details>

### 1.13 정준 원장 (ledger) — 슬라이스 1 · 2026-08-13 신설

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| **L1 원장 저장·번역기** (`f896020`+`bee1aeb`) | `ledger_events`(월 파티션·`PK (id, occurred_at)`) + 봉투 + **닫힌 술어 어휘** + 게이트 + `lot_event` 번역기. 점검할 것: ① **관계가 없으면 아무것도 안 깨지는가**(부팅 시 `server/ledger`를 import하는 프로세스가 없어야 한다) ② **중복 판정이 해시가 아니라 컬럼 일곱**인가(해시 키는 파이썬과 jsonb가 다르게 철자해 **모든 행이 새 행으로 보이면서 조용히** 실패한다) ③ **게이트가 진짜 데이터를 거절하는가** — 실측에서 `parent_lot`을 이미 든 행에 누가 `child_lot`을 손으로 넣어 두었고, 「부모 먼저, 없으면 자식」식 순서는 그 행의 웨이퍼 25장을 **소스가 주장한 적 없는 혈통에** 조용히 붙인다. 🔴 **모든 불완전을 거절하면 안 된다** — 두 번째 편집 행은 「참이지만 불완전」이라 `incomplete`로 «세어져» 사슬이 **이유와 함께 끊긴** 모습으로 나온다(간극이 아니라) ④ **멱등을 두 그물로 «따로»** 보이는가(커서 = 2회차 0행 읽음 / `uq_ledger_atom` = 커서 리셋 후 시도 633·삽입 0·중복 633) ⑤ **운영 노트의 「0 유실」이 참인가** — 원자가 되기 «전»의 거절은 `atoms_lost`에 기여하지 않아 26개가 안 쓰인 채 「0 유실」로 보고됐었다(지금은 `source_rows`와 `built_atoms_discarded`가 별개의 수다) | CLI 백필 · 마이그레이션 `add_ledger_events.py`(`--report`) | `server/ledger/*` · `server/config/ledger_config.json` · [data_model §1.1-ter](../architecture/data_model.md) |
| **L2 혈통 조회 API** (`01452d5` · **2026-08-13 `5bacdfc`로 확장**) | `GET /api/ledger/trace?lot=&slot=` → `hops[]`(`state`=`resolved`\|**`contested`**\|`candidate`\|`unresolvable` · `predicate` · `reason` · **`basis`**={`kind`:`convention`\|`measured`, `name`} \| `null` · `occurred_at`) + `terminal_reason`. 🔴 **`contested`는 `candidate`의 강한 형태가 아니다** — 계급이 승자를 **선언**했고 하위 계급이 반대한다(`candidate`는 최상위 계급이 갈려 **아무도 선언하지 않았다**). **둘 다면 `candidate`.** 🔴 **`basis`는 `state`에서 유도되지 않는다** — 아무도 다투지 않는 관례 기반 홉은 `resolved`, 완전 실측 홉과 **같은 단어**다. 🔴 **빈 `hops`는 가능한 답이 아니다** — **빈 원장**에 물어도 lot을 이름 대는 `unresolvable` 홉 하나가 나오는지 확인(그 문이 테스트 하나로 잠겨 있다). ② **catch-all «위»에 등록됐는가** — 라우트가 JSON을 돌려주는지, `index.html`을 200으로 돌려주지 않는지(`/health`가 겪은 그 모양) ③ **관계가 없으면 500이 아니라 503 + 관계 이름**인가 ④ 🔴 **렌더 시각이 «선언된» 존인가** — PostgreSQL 세션 타임존을 UTC·America/Los_Angeles·Asia/Seoul로 바꿔도 **렌더 문자열이 안 움직여야** 한다(그 전에는 세션의 기본값이 우연히 맞아 통과하고 있었다) ⑤ 못 쓰는 존은 기본값으로 떨어지지 않고 **거절**하는가 | REST 직접 호출 | `server/ledger_trace.py`·`ledger_trace_router.py` · [backend §2](../architecture/backend.md) |
| **L3 혈통 화면** (`d9b98ab`) | `/ledger.html` — 랏 하나(`LOT/02`·`LOT 02`도 받는다)를 치면 홉 카드 사슬. 점검: ① **끊긴 사슬이 «내용»으로 그려지는가**(모르는 랏 = 간극 홉 + 종료 사유이지 빈 화면·토스트가 아니다) ② 🔴 **관례 홉과 실측 홉이 «반대로» 표시되지 않는가** — 소박한 `reason.includes('convention:')`은 판정을 **뒤집는다**(승자의 근거는 접미로 붙고 다투어진 홉의 reason은 **패자들**의 근거를 나열한다). 경합 홉을 **실제로 만들어** 보고 확인할 것. **2026-08-14부터 화면은 `hop.basis` 필드를 «소비»한다**(파싱하지 않는다 — 접미 판독은 `basis` 키가 **아예 없는** 옛 서버에서만 살아 있고, `basis: null`은 「근거 없음」이라 그대로 받는다) ②-bis 🔴 **`resolved` 홉 «둘»을 나란히 놓고 보라 — 하나는 관례 기반, 하나는 실측 기반**(`ledger_trace_contested.json`이 그 쌍을 갖고 있다). **상태 단어가 같으므로** 둘이 같아 보이면 이 화면의 존재 이유가 사라진다: 관례 쪽만 점선 레일·점선 테두리·`가정 ·` 칩, 실측 쪽은 실선·`근거 ·` 칩이어야 한다 ②-ter 🔴 **`contested` 홉이 「그냥 확정」으로 읽히지 않는가** — 배지는 `확정 · 반대 N종`(N = `n-1`), 톤은 이견 색, 요약 칩은 `반대 N`이고 **`확정`에 접히지 않는다.** ⚠️ 그리고 그 홉의 reason은 **패자의** `convention:`을 담고 있으므로 **점선으로 표시되면 안 된다** ②-quater 🔴 **유일한 혈통 걸음이 `contested`인 사슬에 「등재됐으나 혈통 주장 없음」이 씌워지지 않는가** — 워크는 `contested`·`candidate` 홉에서도 부모로 **이동**한다. 이 결함은 `candidate`에서 이미 살아 있었다 ③ **신호 둘이 직교인가**(색 = 상태, 무늬 = 근거) ④ 🔴 **컨트롤이 하나인가** — 빌드된 페이지에서 `querySelectorAll('input,select,textarea,button').length === 1`. `Enter`가 확정이고 **URL이 다시 쓰여 답이 곧 링크**다(그래서 제출 버튼도 히스토리 컨트롤도 없다) ⑤ 🔴 **「없음」 넷이 넷으로 읽히는가**(`92b3b47`) — **원자 0인 원장**과 **가득 찬 원장의 없는 랏**은 추적이 **바이트 단위로 같은 답**을 낸다. 그러니 두 상황을 각각 만들어 «화면»이 다른지 볼 것(`GET /api/ledger/coverage`의 `state`가 유일한 판별자이고, 그 라우트가 죽으면 `unknown`으로 강등돼 예전 화면이 나와야 한다 — 지어낸 진단이 아니라) ⑥ 🔴 **없는 랏이 막다른 길이 아닌가**(2026-08-13) — 랏을 **일부러 잘못 쳐서** 종단 블록 **아래**에 `물을 수 있는 랏` + 표본 링크가 나오는지, 그 링크를 **눌러서 진짜 사슬이 나오는지**. ⚠️ 함께 볼 것 넷: **위가 아니라 아래**여야 하고(진단보다 먼저 나온 탈출구는 진단 «대신» 읽힌다), **두 번째 문장이 붙지 않아야** 하며(홉과 종단이 이미 「원장에 없음」이라 말한다), **빈/부재 원장에서는 아무것도 안 나와야** 하고(없는 랏 목록은 그것들이 «있다»는 주장이다), **컨트롤 수는 그대로 1**이어야 한다 | `/ledger.html`(🧭 Menu) | `client2/src/ledger_trace*.js` · 하네스 `client2/tests/ledger_trace_harness.mjs` · [frontend §6.1](../architecture/frontend.md) |
| **L1-bis 거절이 «반쪽»을 남기지 않는다** (2026-08-13 `f313279`+`eb1ae8b`) | 게이트의 전부-아니면-전무가 **어느 파편에든** 걸린다(R-2026-08-13-H)는 것과, `subject_types`가 **문다**(R-D)는 것. 점검: ① 🔴 **거절 팔에서 «셋을 따로»** 단언하라 — 원자 0개 · 거절이 **세어졌음** · 거절이 **이름 대어졌음**(보고·로그·커서 내역 셋 다). 어느 하나는 **틀린 이유로도 참일 수 있다** ② 🔴 **거절 팔 «앞에» 대조군 런을 돌려라** — 잃을 원자가 실제로 거기 있었다는 증명이 없으면 「0개」는 아무것도 말하지 않는다 ③ **통과 팔도 초록인지** 보라(`Equipment`를 선언에 넣으면 같은 원자가 거절 0으로 착지한다) — 빨강만 보면 「가드가 전부를 거절한다」와 구별이 안 된다 ④ 🔴 **거절된 분자가 «메모»를 안 남기는가** — register 메모가 남으면 그 랏은 아무것도 안 쓴 분자에 의해 등록됨으로 표시되고 **이후 누구도 등록하지 않는다** ⑤ ⚠️ **주입 항목이 «수용»에서 정상 반환하는가** — 공유 하네스 둘이 `AssertionError`를 **성공으로 친다.** 가드가 꺼진 채 초록이던 항목이 실제로 있었고, 형제 다섯이 같은 모양으로 눈이 멀어 있을 것으로 보고됐다 ⑥ **옛 단수 `subject_type`이 «에러»인가**(무시도 승계도 아니다) | CLI 백필 · `pytest server/tests/test_ledger_l1_{unit,pg}.py` | `server/ledger/gate.py` · ⚰️ `lot_event_translator.py`는 **트리에 없다**(`e47d325`) — 오늘 그 해석을 하는 곳은 `server/mappers/ledger_v2_lot_event_role_mapper.py`다 · [spec §3.3-bis·§3.5-bis](../spec/LEDGER_TECHNICAL_SPEC.md) |
| **L2-bis `/coverage`와 거절 «내역»** (2026-08-13 `0198e7e`) | `GET /api/ledger/coverage`가 `atoms`·`partitions`·`cursors[]`·`last_atom`을 함께 낸다. 점검: ① 🔴 **`refusals_unaccounted`를 «부호»로 읽는가** — 이 박스 두 라이브 커서 행은 지금 **`1`을 읽고 그것이 정상이다**(컬럼보다 오래된 집계). **「1건 거절, 사유 없음」으로 렌더되면 결함** ② 🔴 **마이그레이션을 «안 돌린» 상태에서 500이 아닌가** — 읽는 쪽이 `pg_attribute`를 먼저 묻는지 확인(그 상태에서 `refusal_reasons` 키가 **아예 없어야** 하고 `{}`로 나오면 안 된다) ③ 🔴 **`NULL`과 `{}`가 화면에서 다른가**(배포 이력 대 「0건」) ④ **깨끗한 런이 기존 항목을 다시 안 찍는가**(바이트 동일) · **`molecules_per_transaction=1`로 여러 플러시를 강제해도 과다 계수가 없는가**(누계 대신 델타를 쓰면 여기서 터진다) ⑤ ⚠️ **`atoms.exact`가 «언제나» false인가** — 대량 쓰기 직후 그 수를 「원장이 행을 잃었다」로 읽지 말 것. `unanalyzed_partitions > 0`은 **못 본 파티션 수**다 ⑥ **부재·공백에 200과 `state`인가**(에러가 아니다) | REST 직접 호출 · `pytest server/tests/test_ledger_trace_pg.py` | `server/ledger_trace.py` · 마이그레이션 `add_ledger_refusal_reasons.py` · [backend §2](../architecture/backend.md) · [spec §6.4-bis](../spec/LEDGER_TECHNICAL_SPEC.md) |
| **L4 공정·레시피 어휘** (2026-08-14) | 어휘가 **일곱 → 아홉**(`processed_with`·`has_param`) + 개체 타입 **`Recipe`**. 점검: ① 🔴 **수를 못박는 테스트가 «이름 그대로» 아홉을 못박는가** — `test_v0_vocabulary_is_exactly_seven_words`가 **완화된 것이 아니라 판정을 적은 것**이어야 하고, **원래 일곱이 여전히 `since: 1`**인 것까지 단언해야 한다(조용히 완화된 옛 테스트 «옆»에 새 테스트가 서면 다음 사람은 판정이 있었다는 사실 자체를 못 본다). **열 번째 낱말을 넣어 실제로 빨간지** 볼 것 ② 🔴 **`value` 목적어의 `required`를 «양팔»로** — 온전한 payload는 위반 0, 필드 하나 뺀 payload는 **그 이름을 대며** 거절 ③ 🔴 **`0`과 `False`를 «따로» 태워라** — 존재 검사이지 진리값 검사가 아니다. 진리값으로 잘못 쓰면 **그 둘만** 거절되므로 온전한 payload 하나로는 두 철자가 구별되지 않는다. **빈 문자열은 여전히 거절** ④ **`Recipe`의 `rev`가 subject 키에 있는가** — 같은 레시피의 두 개정이 **두 subject**여야 한다(속성이면 rev5를 적는 순간 rev4로 돌았던 웨이퍼의 근거가 도달 불가능해진다) ⑤ 🔴 **「실측이 설정값을 이긴다」에 랭킹 코드가 «0줄»인가** — `params_actual`은 계급 2, `params_setpoint`+`inferred: true`는 계급 3이고 **`ledger_trace`는 한 줄도 안 바뀌었어야** 한다. 🔴 **초록만 보면 아무것도 증명 못 한다**: 계급 경계를 뺀 **뮤턴트를 같이 돌려 «반대» 답이 나와야** 한다(둘이 같은 답이면 그 단언은 계급이 아니라 산술에 대한 것). 실측 149/149·뮤턴트 149/149 불일치 — ⚠️ **합성·이 박스** | `pytest server/tests/test_ledger_l1_unit.py` · `python server/scripts/seed_syn_process_ledger.py --prove` | `server/ledger/vocabulary.py` · [spec §3.7·§4.1-bis](../spec/LEDGER_TECHNICAL_SPEC.md) · [LEDGER_GUIDE §3 ①·§3-bis](../guide/LEDGER_GUIDE.md) |
| **F1 결함 «종류» 레지스트리** (2026-08-14) | `server/finding_kinds.py` + 두 번째 종류 `delam_obs`(SCAT). 점검: ① 🔴 **`kind_clean`이 «스캔됨 MINUS 발견됨»인가** — `NOT EXISTS(finding)`로 쓰면 **한 번도 안 본 패키지가 「깨끗함」으로 흘러든다.** 실측(종류 `void`): 발견 46,899 · 스캔·깨끗 28,101 · **한 번도 안 봄 280,001** — 틀린 철자는 그 28만을 통째로 옮긴다. 🔴 **철자가 «둘»이므로 «둘 다» 채점하라**: 참조 `finding_kinds.population_ctes`와 화면 경로 `server/ledger_siblings.py`의 자체 조립(시간 창 때문에 갈렸고 그 분리에는 이유가 있다). **한쪽만 보면 다른 쪽이 규칙을 어겨도 초록이다** ①-bis **분모 없는 종류에서 깨끗·미스캔 칸이 `0`이 아니라 `null`인가** — `0`은 「깨끗한 것이 없었다」는 **주장**이다 ② 🔴 **종류를 바꿨을 때 «분모»가 실제로 움직이는가** — `void`는 `sat`, `delam`은 `scat`이다. **같은 method를 공유하면 종류를 바꿔도 같은 런을 세어**, 초록이 일반화의 증거가 못 된다 ③ 🔴 **`observed_by` 키를 «지웠을» 때 로드가 거절되는가** — **부재 ≠ 빈 목록**이고, 빈 목록은 「분모 없음 — 대조 불가」로 **렌더돼야** 한다(빈 패널도, 지어낸 분모 위의 비율도 아니다) ④ **미선언 종류가 기본값으로 «안» 떨어지고 이름을 대며 거절하는가**(URL 오타가 void의 숫자를 오타 난 제목 아래 그리면 화면의 모든 수가 다른 것에 대한 참이다) ⑤ **`finding_kind='void'` 리터럴이 `DEFAULT_KIND` 말고 «어디에도» 없는가**(`grep`) — 있으면 일반화가 소실된 것이다 ⑥ **`delam_obs`가 `create_missing_dynamic_tables`로 생겼는가** — `sync_dynamic_tables_schema`는 `ADD COLUMN`만이라 **없는 테이블에 아무 일도 안 하고 그 무동작은 조용하다** ⑦ ⚠️ **`delam_obs`에는 파서도 면적 식 인덱스도 아직 없다**(생산자는 합성 생성기뿐) | `pytest server/tests/test_finding_kinds.py`(7건) | `server/finding_kinds.py` · `server/config/table_config.json`(`delam_obs`) · [data_model §1.2-bis.1](../architecture/data_model.md) · [CONFIG_GUIDE §1·§5.8-ter](../guide/CONFIG_GUIDE.md) |
| **L5 결함 관측의 원장 번역 + 걷기 선언** (2026-08-14 3차 · `0a86651` · R-2026-08-14-D·E) | 술어 **`observed`**(어휘 열하나) · 두 번째 문법 `kind: "observation"` · 소스 둘(`void_obs`·`delam_obs`) · **걷기 의미론이 술어 선언으로**. 점검: ① 🔴 **걷기가 관측을 «인출조차» 안 하는가** — `observed`는 `traversable: None`이다. **원장에 관측 원자를 «채운 상태»에서** 3홉 추적을 태워 응답의 관측 수가 **0**인지 볼 것(실측: 주장 174 / 관측 0 · 5.2–5.8 ms 정상 상태). ⚠️ **첫 호출 225 ms는 config·존·plan 워밍업이라 그 수를 회귀로 읽지 말 것.** 🔴 **빈 원장에서 태우면 아무것도 증명 못 한다** — 인출 대상이 없을 때는 두 철자가 같은 답을 낸다 ② 🔴 **파생 목록이 옛 리터럴과 «같은 답»인가** — 걷기 술어를 선언에서 뽑도록 바꾼 이관의 합격 조건은 **동작 불변**이고, 낱말 하나라도 늘거나 줄면 그것은 말 없는 동작 변경이다 ③ 🔴 **걷기 선언 검사가 «양방향»인가** — `traversable` 미선언은 로드 거절, `True`인데 `direction` 없으면 거절, **`traversable`이 아닌데 `direction`이 있어도** 거절(아무도 안 걷는 엣지의 방향은 미끼 필드다) ④ 🔴 **런을 못 푸는 발견이 «거절»인가** — 세상의 시각은 `inspection_run.observed_at`이고 `void_obs.updated_at`은 **도착 시각**이다. 도착 시각으로 도장 찍힌 원자가 하나라도 나오면 결함 ⑤ 🔴 **커서가 키셋인가, 그리고 `lag_basis`가 그렇게 «말하는가»** — 관측 커서는 `world_time_lag_seconds`를 낼 수 없고 **`null` + `arrival_watermark`**가 정답이다(도착 뒤처짐을 세계시각 이름으로 보고하면 「소스가 조용하다」와 「번역기가 멈췄다」가 구별되지 않는다). ⚠️ **시각 커서로 되돌리면 대량 적재가 «쪼갤 수 없는 한 그룹»이 된다**(실측 91,756행 / 서로 다른 `updated_at` 92개) ⑥ **`class`를 양팔로** — 선언된 값은 payload에 실리고 **밖의 값은 종류 이름과 선언 집합을 대며 거절**(초록 한쪽만 보면 「class를 안 읽는 번역기」와 구별이 안 된다) ⑦ **`/kinds`가 `in_ledger`와 `ledger_state`를 «둘 다»** 내는가 — 백필 전에는 `declared_only`(선언됐고 0), 후에는 `flowing`. 🔴 **`ledger_atoms`의 `null`과 `0`을 같게 렌더하면 결함** ⑧ **드리프트에 새 소스가 «안» 들어가는가** — `/structure`의 `drift.undeclared_sources`에 `void_obs`·`delam_obs`가 보이면 「번역기는 자기 소스를 선언한다」가 깨진 것이다 | ⚰️ **[2026-08-19] 이 행의 진입 경로는 지금 돌지 않는다** — `python -m ledger.backfill --source void_obs\|delam_obs`는 두 이름이 `server/config/ontology/ledger_config.json`의 `sources`에 없어 `undeclared_source`로 거절된다(무엇이 선언돼 있는지는 `python -m ledger.setup`). 남은 실행 가능한 점검은 `pytest server/tests/test_ledger_observed_unit.py`와 **이미 적재된 원자에 대한** REST `/api/ledger/{kinds,structure,trace}`다 | ⚰️ `server/ledger/observation_translator.py`는 **트리에 없다**(`e47d325`) · `vocabulary.py`·`config.py`·`backfill.py` · `server/ledger_trace.py`·`ledger_kinds.py` · [spec §3.7-quinquies·§4.8](../spec/LEDGER_TECHNICAL_SPEC.md) · [ONTOLOGY_LEDGER_SETUP](../guide/ONTOLOGY_LEDGER_SETUP.md) · [LEDGER_GUIDE §4.7](../guide/LEDGER_GUIDE.md) |
| **L6 3축 맵이 «코어축»을 처음 그린다 — 픽스처 세트 정비** (2026-08-14 `50a21c7` · **라우트 코드 0줄**) | `GET /api/ledger/lot_map`의 DT축이 `no_frame` → `ready`(15×10), 코어축이 `unreachable` → `ready`가 됐다. 🔴 **바뀐 것은 코드가 아니라 «선언과 값»이다** — `bonding_log`의 코어 컬럼 넷이 `table_config.json`에 없어서 모든 writer의 셀이 **200과 함께 드롭**되고 있었다(물리 컬럼은 이미 있었다). 점검: ① 🔴 **음성 케이스가 살아 있는가** — **안 심은 랏의 코어축은 여전히 `unreachable`/`no_live_bridge`**여야 한다. 실측으로 코어 컬럼을 가진 것은 `bonding_log` 368,371행 중 **84,600행 · 본딩 랏 108개 중 24개**뿐이다. **축이 항상 `ready`가 되면 이 라우트가 「없으면 없다고」 말하는 능력을 잃는다** ② 🔴 **본딩 슬롯 하나를 집었을 때 셀은 나오는데 격자는 `frame_ambiguous_across_slots`로 «거절»되는가** — 칩 141개가 코어 웨이퍼 **29장**에서 오므로 그것이 정직한 답이다. 첫 슬롯을 골라 겹쳐 그리면 **좌표는 전부 진짜인데 그림이 허구**가 된다(이 결함은 실제로 있었다) ③ 🔴 **팬아웃을 「1」로 가정하지도, 「균등 분할」로 가정하지도 마라** — DT→코어 실측 **k=1×230 · k=2×213 · k=3×108 · k=4×49**이고 **1이 포함된 것이 의도**(테이프가 정말 한 장에서 올 수 있다), 지분은 **불균등**이다 ④ 🔴 **셀 위치로 소유자를 «추론»하지 않는가** — 기여 셀이 테이프 전체에 흩어져 있으므로, 위치로 유추하는 소비자는 저장된 provenance를 읽는 소비자와 여기서 갈린다 ⑤ 🔴 **「다대다를 지원한다」고 쓰지 마라 — 첫 홉은 «아직» 아니다.** 본딩→DT의 차수는 **두 값밖에 없고 사이가 비어 있다**(실측 2026-08-14, 이 박스): 합성 웨이퍼 **2,575장 전부 k=25**(min = max)이고 나머지 **k=1은 웨이퍼 120장뿐인데 그것이 실데이터 5,296행**이다 — **그 120장에는 코어 컬럼이 0행 채워져 있다.** ⚠️ **표 전체를 훑으면 1이 보이므로 「변이가 있다」로 오독하기 쉽다**: 그 1은 이 픽스처가 «모델링한» 것이 아니라 손대지 않은 실데이터의 퇴화 케이스이고, **2와 24 사이는 여전히 표본이 0**이다. 그래서 「many」를 하드코딩한 소비자와 세는 소비자가 **여전히 구별되지 않는다**. 고치려면 `bonding_log.dt_slot` 재작성이 필요하고 그것은 거기서 파생된 **`dt_slot → package_gate` 원자 64,375개를 거짓으로** 만든다(그래서 안 고쳤고, 숨기지도 않았다) ⑥ 🔴 **`dt_map.core_lot`은 여전히 «전 행 NULL»이다**(실측 5,619행 · 0행) — 선언만 고쳐졌고 그 표는 `[DERIVED]`라 **다음 체인 패스**가 채운다. **「고쳐졌다」고 읽으면 거짓이다** | REST 직접 호출 · `python server/scripts/seed_syn_world.py --prove` | `server/ledger_lots.py` · `server/scripts/seed_syn_world.py`·`syn_world_prove.py` · [backend §2](../architecture/backend.md) · [data_model §3.3](../architecture/data_model.md) |
| **C1 마킹 대조 + 놀라움 표** (2026-08-14 밤 · `66e2925`·`5ea29b6`·`f21a916`·`60c7c93`) | 화면 서술 [frontend §6.4](../architecture/frontend.md), 라우트 [backend §2 `/siblings`](../architecture/backend.md). 점검: ① 🔴 **scope가 못 찾은 값을 흡수하지 않는가** — `scope=bond_lot:<실재>,<오타>`가 `ready`로 하나만 계산하고 침묵하면 결함이다. 오타는 「이 축에 없음」으로, 창 밖은 「이 창에 단위 0」으로 **이름 불려야** 하고, 전부 탈락이면 두 값을 이름 댄 `empty`다. **정상 입력만으로는 이 축이 채점되지 않는다** — 못 찾는 값을 섞어라 ② 🔴 **`scope=wafer:<id>`가 1 vs 2,599인가** — 랏(25장·50장)으로 불리면 마킹 축 결함이다(두 id는 2 vs 2,598) ③ 🔴 **수치 후보가 «주어당 한 값»으로 접히는가** — 원자 141개 웨이퍼가 관측 141이면 원자 수가 표본 수 행세를 하는 것이다. 그리고 **둘째 승격 임계가 어디에도 없어야** 하며, 배율로 평평한데 표준편차로 갈라지는 필드는 **화면에 두 수와 함께 이름 불려야** 한다 ④ 🔴 **랏 N개 마킹이 대조 요청 «하나»인가** — 마킹 5랏이 130 fetch(맵 125장)면 회귀다. 마킹을 바꾸면 다시 묻는 것이 전부여야 한다 ⑤ **2장 마킹 = 우측 쌍 레일**이 둘째 체크 «즉시»(표 데이터에서) 뜨고, 3장 이상은 조용히 딴 일을 하지 않고 그렇게 말하며, 그룹 랭킹은 남는가. ⚠️ **창 너비 1256px에서도** 레일이 뜨는가(브레이크포인트 결함이 실제로 있었다) ⑥ 🔴 **잘림이 `shown < scored`에서도 우는가** — 서버가 짧게 주고 플래그를 잊어도 부분 목록이 완전한 것으로 통과하면 안 된다 ⑦ **`wafer` URL 파라미터가 왕복하는가** — 차게 붙여넣어 바이트 동일, **마킹 토글·열 편집을 살아남고**, `/lots` 질의에는 안 실린다 ⑧ 🔴 **마스크**: `frame.valid_die_ref.map_id`가 실리면 마스크가 그려지고, `mask_absent`는 라이브에서 도달 불가(픽스처 전용)다. ⚠️ **유효 다이 플로어 시더를 순진 `--apply`로 재실행하지 마라**(R-2026-08-14-K — 기존 마스크가 말없이 바뀐다) ⑨ ⏳ **마킹 단위 승격은 여전히 설계다.** ⚠️ **여정 대조는 «서버 절반»이 착지했다**(아래 J1) — 화면은 아직 없으므로, **화면에 여정 축이 보이면** 이 표가 낡은 것이니 총괄에 보고 | `pytest server/tests/test_ledger_walk_contrast.py` · `node client2/tests/surprise_harness.mjs` · 브라우저(격리 8081) | `server/ledger_walk_contrast.py` · `server/config/sample/siblings_axes.json.sample` · `client2/src/surprise_*.js`·`contrast_*.js` · [SCENARIO_CONSOLE_BRIEF P0-2/P0-3](../process/SCENARIO_CONSOLE_BRIEF.md) |
| **J1 여정 대조 — 주어 «둘» 전용 읽기** (2026-08-14 밤 · `server/ledger_journey.py` · 브리프 P0-3) | `GET /api/ledger/journey?scope=&finding=&window=` — 두 주어가 걸은 공정 구간을 **순서로** 답한다. 라우트 [backend §2](../architecture/backend.md) · 의미론 [spec §4.9](../spec/LEDGER_TECHNICAL_SPEC.md) · 읽는 법 [LEDGER_GUIDE §4.6-quater](../guide/LEDGER_GUIDE.md). ⚠️ **화면은 없다 — REST로만 채점한다.** 점검: ① 🔴 **집단 통계가 «부재»인가, `null`인가** — 응답 전체를 **재귀로 훑어** `enrichment`·`enrichment_ci`·`rate`·`rate_delta`·`std_diff`·`case`·`control`·`candidates`·`min_support` 키가 **하나도 없는지** 본다. **최상위만 보면 안 된다**(값이 항목 안에 숨는다). `null`로 나오면 결함이다 — 있는 필드는 언젠가 렌더되고 웨이퍼 두 장 위의 신뢰구간은 에러보다 나쁘다 ② 🔴 **`gates`가 «둘»인가**(`upstream`·`mechanism`) — 셋째(실재/「우연 아님」)가 **빈 값으로라도** 있으면 결함. `statistics.state`가 `not_applicable`로 **그렇게 말하는지**까지 ③ 🔴 **arity 거절을 «양팔»로** — 웨이퍼 셋을 마킹하면 422 `scope_is_not_a_pair` + `arity_resolved: 3` + **주어 이름**, 실재 하나 + **오타 하나**면 `arity_resolved: 1`(오타가 «흡수»되어 200이 나오면 C1 ①과 같은 결함이다). 🔴 **정상 쌍만 태우면 이 축은 채점되지 않는다** ④ 🔴 **빈칸 셋을 «따로» 만들어 보라** — `segment_absent`(한쪽에 그 step 원자가 아예 없는 쌍 — 실측 `SYN-BW-101-06` vs `-15`의 `MI_THICKNESS`) · `not_recorded`(둘 다 걸은 구간에서 한쪽만 없는 잎 — `SYN-BW-001-01` vs `-02`의 `params_actual.*`) · **`recorded`인 `0`**(같은 구간의 `params_setpoint.purge_delay_s = 0`). **셋이 같은 낱말로 오면 결함**이고, ⚠️ **`recorded_null`은 이 박스에 표본이 0이라 「안 나온다」를 결함으로 읽지 말 것**(명시적 JSON null 0건) ⑤ 🔴 **서수가 «등급 안에서» 매겨지는가** — 장비 로그와 레시피 책이 같은 step을 말하는 주어를 골라, **한 물리적 런이 두 구간으로 쪼개지지 않는지** 본다(실측 `SYN-BW-101-06`의 BONDING: 08-10 01:05/01:45 관측 · 08-12 01:05/01:45 추론 = **원자 넷·런 둘**). 쪼개지면 그룹 키에 등급이 새어 든 것이다 ⑥ **육하원칙 여섯이 «답하거나 없다고 말하는가»** — 빈칸·키 누락 0건이고 `six_completeness.complete`가 **측정값**인지(전부 `true`로 하드코딩되면 이 필드는 장식이다). 🔴 **「왜」의 `is_missing_record`가 «항상 false»인가** — 「물리 모델에 아직 없음」이 「기록 없음」과 같은 문구·같은 색으로 오면 층 위반이고, `_WHY_STATE`의 `declared_no_path`(모델이 아니라고 답함)와 `not_declared`(아무도 안 물음)가 **한 낱말로 접히면** 결함 ⑦ 🔴 **선언을 «지웠을 때» 무엇이 사라지는가 — 두 실험을 «따로» 하라.** ⓐ **이름 블록 셋만** 비우면(`step_labels`·`family_labels`·`field_labels`) **구간·항목 수가 그대로**이고 이름만 원시 경로가 되어야 한다 — 하나라도 줄면 선언이 «필터»로 작동한 것이고 그것이 이 파일이 되지 말아야 할 그것이다. ⓑ **`segments`를 비우면**(또는 라이브·`.sample` 둘 다 치우면) 500도 빈 `ready`도 아니고 **200 + `state:"absent"` + `reason:"no_journey_predicate_declared"` + `segments: []`**여야 한다. ⚠️ **코드·`.sample`의 산문은 「파일을 통째로 지워도 구간·항목·값이 안 준다」고 적고 있으나 ⓑ에서 거짓이다** — 그 문장을 근거로 채점하지 말 것 ⑧ **`origin`이 `live`/`sample`을 구별하는가** — 운영자가 안 고친 파일을 고쳤다고 믿는 자리다 ⑨ **`position_basis: "inference"`인 구간이 `notes[]`에 이름 불리는가** — 순서가 이 응답의 주된 주장이므로 그것이 거짓말할 수 있는 유일한 방식에 이름이 붙어야 한다 | REST 직접 호출(격리 8081 권장) | `server/ledger_journey.py` · `server/ledger_trace_router.py` · `server/config/sample/ledger_journey.json.sample` · [CONFIG_GUIDE §1](../guide/CONFIG_GUIDE.md) · [SCENARIO_CONSOLE_BRIEF P0-3](../process/SCENARIO_CONSOLE_BRIEF.md) |
| **A1 어드민에서 «낱말을 선언한다»** (2026-08-15 · R-2026-08-15-M · `server/ledger_admin.py`·`ledger/dry_run.py`) | 어휘의 **온톨로지 층**이 config가 됐다(`server/config/ledger_vocabulary.json`). 계약 [spec §3.7-sexies·§4.7 ⑪](../spec/LEDGER_TECHNICAL_SPEC.md) · 절차 [ONTOLOGY_LEDGER_SETUP §4](../guide/ONTOLOGY_LEDGER_SETUP.md) · 라우트 [backend §2](../architecture/backend.md) · 선언 [CONFIG_GUIDE §1](../guide/CONFIG_GUIDE.md). **여정 하나를 끝까지 태운다 — 조각으로 채점하지 마라**: 선언 → 드라이런 → 저장 → resolve → `/structure` → 은퇴. 점검: ① 🔴 **드라이런이 정말 «쓰기 0»인가 — 코드를 읽어 판정하지 말고 «세어라».** 드라이런 «전후»로 `ledger_events` 행 수를 재고 같은지 본다. 그리고 **트랜잭션 읽기전용이 걸렸는지를 서버에게 되물었는지**(`read_only_enforced`) — 🔴 **「우리 코드가 INSERT를 안 부른다」는 약속이지 사실이 아니다.** ⚠️ **세션 스코프로 바뀌어 있으면 결함이다**(커넥션이 풀링이라 남의 쓰기가 죽는다 — 다른 요청을 «동시에» 태워 확인) ② 🔴 **미리보기가 «진짜 번역기»를 태우는가** — 원자가 **봉투 형태 그대로**(이름 고침·요약 0 · `derivation`과 `molecule_ref` 동반) 오고 `atoms_by_predicate`가 실제 선언을 따르는지. **가짜 미리보기는 조용한 거짓말이라 이 화면의 존재 이유가 사라진다** ②-bis 🔴 **드라이런의 거절이 `/health`의 프로세스 계수기를 «안» 올리는가** — 일부러 거절되는 선언으로 드라이런을 3회 돌리고 `/health`·`/coverage`의 거절 수가 그대로인지(`gate.captured()`). **시험 삼아 눌러 본 것이 운영 계기를 오염시키면 다음 사람이 없는 사고를 조사한다** ③ 🔴 **드라이런 없는 저장이 «불가능»한가** — 지문 없이 `POST /save`, 그리고 **드라이런 후 선언을 한 글자 고쳐서** 저장(`dry_run_stale`). **뒤엣것이 진짜 축이다**(앞엣것만 막는 구현은 흔하다) ④ 🔴 **서명 완결을 «필드마다» 태워라** — 여덟 중 하나씩 빼고 여덟 번. 거절이 **필드 이름을 대는지**, 코드가 `vocabulary.DECL_REFUSALS` 안에 있는지(밖의 코드는 화면이 렌더할 수 없다) ⑤ 🔴 **`traversable`은 «키의 부재»와 «명시적 null»이 다른 답인가** — 키를 지우면 거절, `"traversable": null`은 수용. **둘이 같은 답이면 「생각 안 했다」와 「걷기가 절대 인출 안 함」이 한 선언이 된 것**이고, 그러면 §3.7-quinquies의 삼상태가 그 자리에서 무너진다 ⑥ 🔴 **`traversable: true`가 «저장하는 날» 이름 대어 거절되는가**(`traversable_true_unavailable`) — 받아 두면 추적 화면이 **다음 요청**에 죽고 그때 원인은 저장한 사람에게서 멀어져 있다 ⑦ 🔴 **정준 층에 «문이 없는가»** — `register`·`pin`·`same_as`와 **개체 타입**을 화면·라우트로 늘리려 시도해 전부 막히는지. `/admin/ledger/vocabulary`가 그 항목들을 `editable: false`로 내는지 ⑧ 🔴 **저장이 «재기동 없이» 먹는가 — 세 프로세스를 따로 보라.** 저장 직후 ⓐ `/admin/config/resolve?domain=ledger`가 유효로 세고 ⓑ `GET /api/ledger/structure`에 그 낱말이 **`origin: "config"`로 «보이고»** ⓒ 게이트가 그 낱말의 원자를 받는가(체인 워커 프로세스). **ⓑ가 빠지면 운영자에게는 저장 실패와 구별되지 않는다** ⑨ 🔴 **은퇴가 «발화만» 막는가** — 은퇴 후 그 낱말로 원자를 만들려 하면 거절, **그러나 이미 실린 원자는 `/trace`·`/structure`에서 그대로 읽혀야** 한다. ⚠️ **성공 문장이 저장과 «반대»인지도 보라**(은퇴는 유효 목록에서 빠지는 것이 성공이다 — 같은 문장을 쓰면 성공한 은퇴가 실패로 읽힌다). **DELETE 라우트가 0개인지 `grep`** ⑩ 🔴 **확장 파일을 «깨뜨려» 보라** — 깨진 JSON에서 500이 아니라 **코드 집합으로 강등**되고, 그 강등을 `/admin/config/resolve?domain=ledger`가 **사유와 함께 말하는지**. 🔴 **절반만 실리면 프로세스마다 다른 낱말을 인정하므로 「통째로 무시」가 정답이다** ⑪ 🔴 **`.sample`이 «폴백하지 않는가»** — 라이브를 치우고 `.sample`만 둔 상태에서 그 낱말이 어휘에 **없어야** 한다. 이 저장소의 다른 거의 모든 config와 «반대»라 순진한 리팩터가 폴백을 되살리기 쉽다 ⑫ 🔴 **[2026-08-15 3차 정정 — 이 항목의 전제가 «바뀌었다»] 「효과없음: 발화하는 번역기 없음」은 이제 «사라질 수 있고, 사라지는 것이 정답인 경우»가 있다.** 넷째 문법 `declared`가 착지해 그 낱말을 내는 소스를 선언할 수 있다(아래 A2). 그러므로 **양팔로** 채점하라: ⓐ 낱말만 등재한 상태에서 resolve가 그 문장을 **이름 대어** 말하는가(부재를 지우지 않는가) · ⓑ 그 낱말을 `emit`하는 `declared` 소스를 선언하고 저장하면 그 문장이 **스스로 사라지는가**(안 사라지면 resolve가 `emit`을 안 읽는 것이다). ⚠️ **`derivation`(원장을 걸어 추론하는 문법)은 여전히 미구현이고 `unsupported_kinds`에 남아야 한다 — `declared`와 «다른 것»이다.** 둘이 화면에서 한 낱말로 접히면 결함 | 브라우저 어드민(격리 8081) + REST · `pytest server/tests/test_ledger_admin_setup.py`·`test_ledger_dry_run_pg.py`·`test_admin_auth.py` | `server/ledger_admin.py` · `server/ledger/dry_run.py`·`vocabulary.py` · `server/config/ledger_vocabulary.json(.sample)` · `server/config_resolve_report.py` |
| ⚰️ **A2 «코드 0줄»로 테이블 하나를 원장에 붙인다 + 집계 단위가 웨이퍼 조회에 나타난다** (2026-08-15 3차 · R-2026-08-15-N ② · R-2026-08-15-O · `ledger/vocabulary.py`) | 🔴 **[2026-08-19] 이 행의 ①~⑦은 은퇴한 문법을 채점한다** — `declared_translator.py`가 트리에 없고(`e47d325`) `kind` 디스패치도 `backfill.py`에서 빠졌다(`d7bfcd0`). **오늘의 「코드 0줄」은 이 문법이 아니라** 범용 `direct-join@1`/`declarative-role@1`이고, 그 여정의 점검은 [ONTOLOGY_LEDGER_SETUP §14](../guide/ONTOLOGY_LEDGER_SETUP.md)의 `test_ledger_zero_python_source.py`가 소유한다. ⑧~⑫(뿌리 키 롤업)은 그와 별개로 **여전히 유효하다.** 이하 원문: 넷째 소스 문법 **`declared`**(선언이 곧 번역기 — 계약 [spec §3.8](../spec/LEDGER_TECHNICAL_SPEC.md) · 키 표 [ONTOLOGY_LEDGER_SETUP §3.4](../guide/ONTOLOGY_LEDGER_SETUP.md))와 **뿌리 키 롤업**([spec §3.7-septies](../spec/LEDGER_TECHNICAL_SPEC.md)). **여정 하나를 통째로 태운다**: 대장 테이블 하나를 `kind: "declared"`로 선언 → 드라이런에 **진짜 원자**가 나오고 → 백필 후 그 원자가 **웨이퍼 스코프 여정에 보인다.** 점검: ① 🔴 **정말 코드가 0줄인가** — 이 여정 어디에서도 파이썬 파일을 새로 만들거나 고치지 않았는지. **새 파일이 하나라도 필요했으면 이 문법은 자기 약속을 못 지킨 것**이다 ② 🔴 **`occurred_at_basis`를 «지웠을 때» 거절되는가** — 기본값으로 안 떨어지고(R-…-N ②), 그리고 **`row_created`로 선언했을 때 그 사실이 원자에서 읽히는가**(`object_payload->>'occurred_at_basis'`). ⚠️ **`value` 목적어 원자에서만 읽힌다** — `entity_ref` payload는 모양이 엄격 검사돼 여분 키가 (옳게) 거절되므로 **거기 없는 것은 결함이 아니다** ③ 🔴 **`when`을 «세 가지로» 망가뜨려라** — 연산자 0개 · 2개 · **오타 하나**(`euqals`). 셋 다 거절이어야 한다. 🔴 **오타 팔이 진짜 축이다**: 무시된 연산자는 조건을 **「항상 참」**으로 만들어 **아무도 요청하지 않은 원자를 낳고**, 그 실패는 거절이 아니라 **조용한 초과 발화**라 초록으로 위장한다 ④ 🔴 **없는 컬럼을 `"$col"`로 부르면 «거절»인가** — 빈 값으로 풀리면 「모양은 멀쩡한데 아무것도 안 가리키는 원자」가 나온다. 리터럴(`"leg"`)과 이스케이프(`"$$"`)도 같이 태울 것 ⑤ 🔴 **파생이 규칙 이름으로 «질의»되는가** — `WHERE source_translator_ver LIKE '%#<rule>'`이 그 규칙의 원자 전량인지, 그리고 **config에서 규칙을 지우면 그 파생이 즉시 거절되는지**. ⚠️ **한 소스 안 `rule` 중복은 로드 거절** ⑥ **선언끼리의 모순이 «저장 시점에» 잡히는가** — `emit[].subject.type`을 `subject_types` 밖 값으로 두면 백필까지 가지 않고 거절되는지 ⑦ **규칙에 하나도 안 걸린 행이 «거절이 아니라 세어지는가»**(`rows_matching_nothing`) — 「1,181행이 왜 원자 40개인가」에 드라이런이 그 수로 답하는지 ⑧ 🔴 **롤업: 「보이던 것이 안 사라지고, 안 보이던 것이 보이는가»** — 뿌리(`Wafer`) 스코프로 여정·걷기 대조를 물어 **`WaferLeg` 원자가 «함께» 오는지**(실측 기준: 원자 42개 · 뿌리 웨이퍼 6장). 🔴 **롤업 «없는» 주어로도 태워라** — 아무 관계도 선언 안 한 타입의 답이 **한 건도 안 변해야** 한다(안 그러면 롤업이 필터가 아니라 확대기다) ⑨ 🔴 **응답 «형태»가 안 바뀌었는지 확인하라** — 이 변경은 **간극을 메우는 것**이지 계약 변경이 아니다. 이름 바뀐 필드·재구조화된 블록이 하나라도 있으면 그것은 별개의 사고다 ⑩ 🔴 **관계는 «선언»이지 유추가 아님을 «음성»으로 확인하라** — `Die`의 키도 `Wafer`의 상위집합이다. 다이 원자가 웨이퍼 스코프 답에 섞여 들어오면 누군가 키 포함으로 유추한 것이고, 그 규모는 구성상 1.6억이다 ⑪ **캐시가 «같이» 비는가** — `/admin/reload-configs` 뒤에 걷기 집합과 롤업 집합이 둘 다 새 선언 위에서 도는지(`reset_walk_cache()` 하나가 둘을 비운다) ⑫ ⚠️ **`bonding_map`을 config에 «쓰지 마라»** — 그 워크스루는 소유자가 직접 한다(브리핑 §6-3). 점검용 선언은 별개 이름으로 만들고 끝나면 치울 것 | 어드민 화면(격리 8081) + REST · `pytest server/tests/test_ledger_admin_setup.py` | ⚰️ `server/ledger/declared_translator.py`는 **트리에 없다** · `config.py`·`backfill.py`·`dry_run.py` · `server/ledger/vocabulary.py` · `server/ledger_trace.py`·`ledger_journey.py`·`ledger_walk_contrast.py` · [spec §3.7-septies·§3.8](../spec/LEDGER_TECHNICAL_SPEC.md) · [ONTOLOGY_LEDGER_SETUP §3.4·§4](../guide/ONTOLOGY_LEDGER_SETUP.md) |
| **L7 두 번째 소스가 «그룹 단위»로 돈다 — `basis` 시각 · 페이지 키 · 쪼갬 가드** (2026-08-19 · `55560ad`·`7a743a1` · 소유자 판정) | `dt_job`은 **여러 행이 한 사건**인 첫 소스이고, 그 행들이 한 인제션 배치에 다 들어온다는 보장이 없다. 점검: ① 🔴 **두 적재 시각에 걸친 job이 «사건 하나»이고 시각이 «가장 이른» 것인가** — 둘로 쪼개지면 각 원자의 수가 **인제션 배치의 행 수**가 된다(실측 2026-08-19: 396 job 중 26개가 걸쳤고, 그렇게 만들어진 「다이 59개」·「13개」 12건이 원장에 들어갔다. 답은 72다). 늦은 쪽으로 접으면 조각이 하나 더 오는 날 **같은 사건의 시각이 움직여** 원자가 새 id로 중복된다 ② 🔴 **같은 행을 `column`(세계 시각)으로 선언하면 «여전히 거절»인가** — 세계 시각이 한 사건 안에서 둘이면 그룹이 틀린 것이라 어떤 집계도 못 고친다. 접는 것은 `basis` 경로뿐이고, **두 갈래가 갈려 있다는 것이 이 규칙의 전부**다 ③ 🔴 **완주 후 job 수 == `has_netdie` 수 == `register` 수이고, 어떤 job도 같은 술어를 둘 갖지 않는가** — 그리고 **각 count가 그 job의 실제 행 수와 같은가**(합계가 맞는 것으로는 부족하다: 59+13도 72다) ④ 🔴 **다시 돌리면 «0행»을 쓰는가** — `min`을 고른 이유 자체가 재실행 안정성이다. 커서가 끝에 있으면 아무것도 안 읽어 **아무것도 증명 못 한다**; 전량을 다시 태우거나 읽기 전용 재생으로 **dedupe 튜플이 이미 있는지**를 확인할 것 ⑤ 🔴 **페이지 키를 시각 컬럼으로 되돌리면 가드가 «우는가»** — `backfill._page_key`를 `occurred_at.column`으로 돌려 재생하면 `source_event_split_across_batches`가 떠야 한다(실측: 배치 #1, 완료 14그룹 시점). **한 번도 빨개진 적 없는 점검은 점검이 아니다** ⑥ 🔴 **③의 수를 «표»에서 시작해 센다.** `dt_log`의 job 집합에서 시작해 원장을 왼쪽 조인하는 것과, 원장에서 시작해 세는 것은 다른 질문이다. **원장에서 세면 원장에 «없는» job이 안 보인다** — 그 방향으로는 396개가 다 빠져도 「불일치 0」이 나온다. 반대 방향(표에 없는데 원장에만 있는 job)도 같이 볼 것 | `conda run -n assy_manager python -m ledger.backfill --source dt_job` (⚠️ `--reset-cursor`·`--from`은 거절된다 — 커서를 되감으려면 별도 승인) · `python task/evidence/ledger_atom_baseline.py <dest>` + `ledger_atom_diff.py`(①②는 여기서 DB 없이 채점된다: `dtjob_group_*` · `refuse_two_world_times_in_one_group`) · `pytest server/tests/test_ledger_source_preparation.py server/tests/test_ledger_setup_boundary.py` | `server/ledger/source_preparation.py`(`_event_frames` — 선언별 시각) · `server/ledger/backfill.py`(`_page_key` · `_run_v2_lineage`의 `completed_groups`) · `server/mappers/ledger_v2_dt_job_mapper.py` · `task/evidence/ledger_atom_baseline.py` · [ONTOLOGY_LEDGER_SETUP §7](../guide/ONTOLOGY_LEDGER_SETUP.md) · [CODE_MAP `backfill.py`](../architecture/CODE_MAP.md) |
| **void(보이드) 스키마** (`346aa88` · **2026-08-14부터 종류 «둘» 중 하나**) | `inspection_run`(분모) + `void_obs`(관측). 점검: ① 🔴 **깨끗한 스캔(보이드 0건)이 «런 행»을 만드는가** — 이 설계의 존재 이유가 그 행이고, 그것을 잃는 결함이 실제로 있었으며 **무음이었다** ② 🔴 **같은 파일을 두 `raws/`에 모두** 넣었는가(워처는 테이블당 핸들러 하나) ③ **등급·면적 컬럼이 0개인가**(`grade|pass|fail|verdict|area|yield`) ④ **면적 질의가 식 인덱스를 타는가**(`EXPLAIN`) ⑤ **단위 없는 파일이 거절되는가**(추측 금지) ⑥ **소수점 쉼표 파일이 «행 arity»에서 거절되는가** — 밀린 값들도 전부 유효한 숫자라 어떤 수치 검사도 발화하지 않는다 ⑦ ⚠️ **`bonding_log`와는 아직 조인되지 않는다**(웨이퍼 신원 ↔ 카세트 위치) | `ingestion_workspace/{void_obs,inspection_run}/raws/` | `server/parsers/void_sat_format.py` · [INGESTION_GUIDE §1.11](../guide/INGESTION_GUIDE.md) · 켜는 순서 [OPERATOR_RUNBOOK §4](../process/OPERATOR_RUNBOOK.md) |

#### A3 Source Contract·Python 번역기 템플릿

> 🔴 **[2026-08-19] 이 소절의 절반은 지금 «태울 수 없다».** `POST /admin/ledger/dry-run`은
> 소스 미리보기에 대해 `DryRunUnavailable`을 먼저 던지고(`ab8657f`), Template Method
> 기반(`translator_pattern.py`)은 트리에 없다(`e47d325`). 채점 불가 항목을 지우지 않고
> 표시해 두는 이유는, **아래 삭제선 항목이 다시 초록이 되는 날 그것이 「v2 미리보기 라우트가
> 배선됐다」는 신호**이기 때문이다.

- [ ] `GET /admin/ledger/sources`의 각 kind가 실제 translator profile을 함께 제공한다. (여전히 유효 — `source_contract.PROFILE_META`가 그대로 서빙된다)
- [ ] ~~표본에 나오지 않은 가능한 Claim 충돌도 source 행을 읽기 전에 `translator_vocabulary_mismatch`로 거절된다.~~ → **도달 경로 없음**(호출이 그 앞에서 `DryRunUnavailable`).
- [ ] ~~dry-run 응답에 정적 `source_contract.emissions[]`와 실제 `atoms_rendered[]`가 함께 있고 쓰기는 0이다.~~ → **소스 대상 dry-run이 그 필드를 더 이상 내지 않는다.**
- [ ] ~~Template Method의 늦은 거절이 해당 분자의 first-sight register 메모를 남기지 않는다.~~ → **그 베이스 클래스가 없다.**
- [ ] `emit_register: false`와 datetime cursor 첫 페이지가 선언대로 동작한다.
- [ ] `pytest server/tests/test_ledger_source_contract.py`가 통과한다.
- [ ] 🔴 **쓰기 없는 v2 미리보기의 오늘 자리**: `ledger/setup.py`의 `preview_selected_cursor_batch`. **부르는 HTTP 라우트가 아직 없다** — 라우트가 생기면 위 삭제선 셋을 v2 표현으로 되살릴 것.

### 1.14 Ontology Config Explorer — 2026-08-18 신설

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| **Compiled config 탐색** | SourcePlan·Registry·Mapping·Binding을 server-side 검색하고 실제 reference/Used by/leaf pointer/current route와 다른 path를 표시한다. wrong kind/version/signature/unresolved를 구별한다 | `/admin.html#ontology` | `server/ledger/config_explorer.py` · `client2/src/ontology_explorer*` |
| **File-backed transfer 왕복** | 운영 밖 sample을 production loader/compiler로 열어 `CoreDie→DTDie→BondComponent→FinalChip`, DTJob/LotSlot, transferred_to, VerifiedJoin, SourcePlan을 모두 왕복한다. 🔴 **[2026-08-18] 이 샘플은 「다른 공장」이고 자기 `table_config.json`을 든다** — 이름이 같아도 운영 `dt_log`/`dt_inventory`와 **같은 표가 아니다**(컬럼이 겹치지 않는다). ⚠️ **그 사본이 종전 `ledger_config.tables`에 있을 땐 아무것도 대조하지 않아, 어디에도 없는 컬럼 이름이 초록으로 통과했다** | QA sample app | `server/config/sample/ontology/transfer_explorer/` · `server/tests/support/transfer_explorer_table_config.json` · `server/tests/support/ontology_explorer_sample.py` |
| **안전한 초안 lifecycle** | active/draft 분리 → 동일 compiler preview → immutable review → explicit revise → base/hash CAS + consumer convergence. dirty 이동은 유지/폐기/취소, invalid/stale은 active fallback | 같은 화면의 `초안 편집` | `server/ledger/config_drafts.py` · `/admin/ontology-explorer/*` |
| **삭제가 무엇을 데려가는지 이름 댄다** (2026-08-19 · `943cc64`) | `deletion_plan`이 **남는 것을 걸어** 함께 죽는 선언을 전수 나열한다. 점검: ① 🔴 **in-degree를 게이트로 쓰지 않는가** — 참조하는 것들이 **전부 같이 죽는** 삭제는 막을 이유가 없다. 그것을 막으면 화면이 정당한 삭제를 거절한다 ② 🔴 **참조를 «옮겨 주지» 않는가** — 남의 선언을 대신 고쳐 쓰는 것은 이 화면의 일이 아니고, 거절문이 「먼저 repoint하라」고 말해야 한다 ③ 지우지도 초안을 만들지도 않는가(읽기 전용) | ⚠️ **화면 없음** — `GET /admin/ontology-explorer/deletion-preview?targets=…`를 직접 호출 | `server/ledger/config_explorer.py`(`deletion_plan`·`referrers`·`require_no_referrers`) · `config_explorer_service.py` · `ontology_config_explorer_router.py` |
| **컬럼 후보 옆의 «숫자»** (2026-08-19 · `0f99b2d`) | 후보 컬럼마다 **실제로 값이 든 행 수**, `combination`을 주면 그 정렬의 **실측 유일성**. 🔴 **오타 방지 기능이 아니다** — 컴파일을 통과하고 실행되고 아무것도 안 내는 config가 이 숫자 하나로 보인다. 점검: ① 🔴 **0/N 컬럼을 골랐을 때 화면에 그 수가 보이는가**(거절은 나오지 «않는다» — 그것이 이 기능의 존재 이유다) ② `combination`의 중복 수가 백필 «전»에 나오는가(정렬 계약은 백필 도중에 깨진다) ③ `table_config.json`에 없는 relation은 `undeclared_relation`으로 **이름 대어 거절**되는가(조용히 후보 0개가 아니다) ④ ⚠️ **비싼 읽기다** — 정확한 수라 표 스캔 한 번이 들고 측정 컬럼 수에 상한(`MAX_MEASURED_COLUMNS`)이 있다. 쓰기·커서 이동 0 | ⚠️ **화면 없음** — `GET /admin/ontology-explorer/columns?relation=<표>[&combination=…]` | `server/ledger/column_stats.py` · `config_explorer_service.column_picker` |
| **mapper가 선언 이름을 모른다 — `sentence`** (2026-08-19 · `71865b7`·`77cf39a`) | `SentenceShape`/`ProfileSentences`. 점검: ① 🔴 **predicate·entity type·`mapping_id` 철자가 mapper 파일에 «없는가»**(`grep`) — 하나라도 있으면 「다른 스키마 환경에서 코드 0줄」이 깨진다 ② 🔴 **모양이 같은 mapping 둘에서 `sentence`를 지우면 «compile 시점에» `ambiguous_sentence`인가** — 먼저 걸린 쪽을 대표로 뽑으면 셋째가 들어오는 날 **이미 돌던 전부**가 깨진다 ③ **모양이 이미 유일한 mapping이 `sentence` 없이도 통과하는가**(선택 필드다) ④ 한 `SentenceShape` 인스턴스를 두 속성에 바인딩하면 클래스 생성 시점에 `ambiguous_sentence_shape`인가 | `pytest server/tests/test_ledger_setup_*.py` | `server/ledger/roleframe.py` · `server/ledger/setup_bundle.py`(`_sentence_signature`·`_ambiguous_sentences`) · `server/mappers/ledger_v2_lot_event_role_mapper.py` · [ONTOLOGY_LEDGER_SETUP §7.6](../guide/ONTOLOGY_LEDGER_SETUP.md) |

자동 점검: mixed context token과 늦은 응답이 Inspector를 바꾸지 않는지, 정/역참조가 1:1인지,
10,000-node에서 검색/Used by payload 상한이 지켜지는지, strict-token route 목록에 revise 포함
초안 route가 모두 포함되는지, empty/mismatched consumer 수렴이 rollback하는지 확인한다.
file-backed Mapping의 entity role이 `CoreDie→DTDie→BondComponent→FinalChip`으로 연속인지,
같은 reference leaf의 target/status 교체가 `modified`인지도 직접 단언한다.
수동 점검: 1920×1080·700×900·320×800 overflow 0, hover/focus, keyboard, exact back/forward,
dirty 3선택, ACTIVE/DRAFT, review→revise와 reviewed JSON read-only를 확인한다. 저장 후 다시
편집한 buffer는 keep→다른 선언→back→forward→back에서도 text/cursor/dirty/draft target이
동일해야 한다.

### 1.10 듀얼 테마 / 실시간 동기화 / 데스크톱 래퍼

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 듀얼 테마(라이트/다크) | 토큰 SSOT `tokens.css` + `theme.js`. 기본 라이트, localStorage로 페이지 간 유지, AG-Grid 무재생성 재도색, FOUC 방지 스탬프 | 테마 토글 버튼(`data-theme-toggle`) — **4개 페이지(index/admin/map_editor/enrichment) 모두** 각 헤더/툴바에 존재 | `theme.js`·`tokens.css`(§7) |
| WS 실시간 반영 | 편집·인제션·체인 결과를 전 클라이언트에 델타 반영(`batch_row_create/upsert/delete`, `batch_refresh_required`) + 셀 플래시, 지수 백오프 재연결. 행 정체는 `getRowId`(`row_id`)가 강제 — 중복 행이 구조적으로 막힌다 | (자동) 메인 그리드 | `websocket.js`(§7) · `ConnectionManager`(§1.1) · **[frontend §3.1](../architecture/frontend.md)**(무결성 3문제 — 구 `DATA_SYNC_SPEC`은 아카이브 대기) |
| 데스크톱 래퍼 | QtWebEngine 셸(`?client=desktop`): OS 드래그앤드롭 업로드, 네이티브 다운로드 다이얼로그, F12 DevTools, `assymanager://` URI | `python run_decoupled_app.py`(셸 포함 기동) · 배포는 GET `/api/download/client` | `client/desktop_wrapper.py` · [frontend §1](../architecture/frontend.md) |
| **셸의 서버 주소 해석** (`e9b3a36` 2026-07-30) | 셸이 어느 서버를 보는지의 **유일한 결정 지점**. 종전에는 주소가 **두 곳에 하드코딩돼 서로 달랐고**(업로드 `127.0.0.1:8080` / 페이지 `localhost:8080`), git에 추적되던 `client/client_settings.json`(`server_host`/`server_port` 보유)은 **한 번도 읽히지 않았다.** 지금 순서는 **`--server` → `ASSY_SERVER` → `client_settings.json` → `127.0.0.1:8080`**이고 조립 지점은 `base_url()` 하나다(페이지와 업로드가 같은 `self.server_base`를 읽는다). 점검할 것: ① **시작 로그 1줄**에 해석 주소 + `source`(`arg`\|`env`\|`client_settings.json`\|`default`)가 나오는가 — `source`가 없으면 운영자는 "내 편집이 무시됐다"를 알 수 없다 ② **잘못된 선언은 조용한 강등이 아니라 거절**(stderr + QMessageBox + `exit 2`)인가: 파싱 불가 JSON(줄·열 지목) · 비숫자/범위 밖 포트(**`0` 포함 — 미상 ≠ 0**) · 빈 host · `bool` 포트(`bool`은 `int` 하위형이라 명시 배제) · `https` 스킴(조용한 다운그레이드 금지) ③ **파일 부재·빈 파일·서버 키 미선언은 정상 설정**이라 조용히 기본값을 쓰는가(무회귀) ④ 빈 `ASSY_SERVER`가 **미선언으로** 취급되는가(`set ASSY_SERVER=`가 Windows의 해제 방식) ⑤ 거절 문구가 **ASCII**인가 — 이 프로세스의 stdout은 런처 아래 cp949 파이프라 비-ASCII `print`는 거절을 `UnicodeEncodeError` 트레이스백으로 바꾼다(한국어는 QMessageBox에 있다) | `--print-target`(해석·출력 후 종료, GUI·HKCU 미접촉 — **헤드리스 점검 경로**) | `resolve_server_target`/`base_url`/`settings_file_path`(`client/desktop_wrapper.py`) · **[frontend §1.1](../architecture/frontend.md)**(정본) · 설정 파일 소유는 [DOC_OWNERSHIP](../process/DOC_OWNERSHIP.md) |
| **상호작용 계측기**(핵심가치 #1 정본 계기 수집) | 키·마우스·화면이동 원시 카운트를 기존 `PUT .../data/updates`에 선택 필드 `effort`로 편승(별도 요청 0건, 화면 표시 0건). 교정 쓰기 **7경로**(그리드 5 + Enrichment 1 + 맵 Push 1) + **읽기 화면 3개**(admin·graph·trace — `effort` 페이로드 없이 이동만 계측). 점검할 불변식 6가지 — ① **실패 저장은 리셋하지 않는다**(재시도 공수는 진짜 공수) ② **200이어도 서버가 기록 안 했으면 리셋하지 않는다**(`effort_recorded=false` = no-op 저장; 리셋하면 두 번 시도한 교정이 가장 싸게 기록된다) ③ **누적 0이면 `effort` 필드를 아예 안 보낸다**(0을 보내면 "측정된 0점 교정"으로 기록돼 기준선이 유령으로 내려간다) ④ **존재하지 않는 라우트를 지목한 허용목록 항목은 콘솔 에러**로 뜬다(조용히 무력화되면 오타와 정상이 구별되지 않는다) ⑤ **이동은 대칭이어야 한다** — `grid→graph`만 세고 `graph→grid`를 안 세면 왕복이 절반 값으로 남는다(읽기 화면에서 「메인으로」를 눌러 카운터가 실제로 늘어나는지 확인) ⑥ **`window.__assyEffort.getConfig().loaded`가 운영 빌드에서 읽혀야 한다**(트리셰이킹으로 사라지면 "목록이 빔"과 "설정 못 받음"을 구별할 수 없다). ⚠️ 새 서브컨텍스트로 `countNav`를 부르면 같은 변경에서 `ROUTE_IDS`에도 등록 | (자동·비가시) 전 페이지 · 집계 결과는 어드민 Overview 「교정 공수」 줄(§1.8) | `effort_meter.js`(§7) · [frontend §3.2](../architecture/frontend.md) · [guide/config/effort_metric](../guide/config/effort_metric.md) · 하니스 `client2/tests/effort_meter_harness.mjs`(110 단언·변이 6종), `effort_instrument_harness.mjs`(28 검사·변이 9종) |

### 1.11 운영 감시 (프로세스 감시 · 헬스 · 격리 환경) — 2026-07-27 신설

> UI가 아니라 **운영 표면**이다. 화면이 멀쩡한데 데이터가 안 들어오는 상태를 밖에서 알아채는 것이 목적.

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 자식 프로세스 감시·자동 재시작 | ⚠️ **[2026-08-14] 수를 여기 적지 않는다 — 정본은 `run_decoupled_app.py`의 `specs`다**(그래프 싱크 워커 은퇴로 백엔드 자식이 다섯에서 넷이 됐고, 이 자리의 「5~6」은 그 라운드에 낡았다). 런처가 자식을 1초 주기로 감시. 죽으면 백오프 재시작(2/4/8/16/32초), **6번째 연속 실패에서 영구 `FAILED`**(배너 로그 + `/health` 503). 60초 이상 살아 있었으면 예산 회복. 데스크톱 셸 종료 = 전체 종료 | `python run_decoupled_app.py` (상태 파일 `config/supervisor_status.json`) | `server/process_supervisor.py` · [backend §1.3](../architecture/backend.md) |
| 워커 진행 박동 | 런처가 띄우는 워커 **3종**(`watcher`/`chain`/`scheduler`)이 **자기 작업 루프 안에서** 박동한다(⚰️ **[2026-08-14] 종전 여기 있던 `graph`는 스택에서 빠졌다**). 원장 백필도 돌 때 `ledger` 이름으로 박동한다. pid가 아니라 진행이 신호라 **살아 있는 채 멈춘 워커**(`wedged`)를 잡는다. 정체 임계 60초. 상태값은 **8종**(`ok`·`starting`·`missing`·`foreign_beat`·`wedged`·`stale`·`stalled`·`down` — [backend §1.3](../architecture/backend.md)). ⚠️ **`stalled`는 별개 검출기**: 박동은 신선한데 claim한 작업이 **300초** 무진행인 경우로, 워처의 재시도 폴러가 계속 박동하는 동안 인제션이 멈춰 있던 실제 사고를 잡는다 | (자동) `config/worker_heartbeats/*.json` | `server/utils/heartbeat.py` |
| 헬스 엔드포인트 | **항상 JSON**, 정상 200 / `unhealthy` 503. `checks{database, workers, outbox, supervisor}` + 사람이 읽는 `problems[]`. DB 프로브 2초 타임아웃·중복 프로브 차단 | `GET /health` | `server/health.py` · `main.py` |
| outbox 적체 판정 | **크기가 아니라 나이**(5분 degraded / 15분 unhealthy). 정상적인 10만 행 적재가 outbox 11.6만 행을 만들기 때문에 크기 임계는 큰 파일마다 오경보한다 | 위 응답의 `checks.outbox` | `health.probe_outbox` |
| 격리 개발/검증 환경 | 스냅샷 DB(`assy_qa`) + 별도 포트(:8081/:8091) + 별도 데이터 루트(`dev_env/`). `up`은 워처·스케줄러를 **일부러 안 띄운다**. 드릴용 워처는 별도 동사이며 **운영을 향하면 기동을 거부** | `python server/scripts/dev_env/devenv.py {snapshot,up,status,env,down,watcher-up,watcher-down}` | `server/scripts/dev_env/devenv.py` · `iso_watcher.py` · `server/paths.py` · [DEPLOY_SETUP §5](../guide/DEPLOY_SETUP.md) |
| **업무 키 유일성 강제 (D3, 2026-08-07)** | `business_key_val`에 테이블별 `uq_bk_<table>` UNIQUE 인덱스를 만들어 「업무 키 하나에 행 하나」를 **데이터베이스가 강제**하게 한다. 종전에는 아무 제약도 없었고(실측: 그 컬럼을 언급하는 인덱스 50개 중 unique **0개**) 쓰기 경로가 먼저 조회했기 때문에 우연히 성립했을 뿐이라, **프로세스 둘이 같은 키를 동시에 쓰면 한 업무 키에 두 행이 조용히** 생겼다(실측 재현: 5,000건 배치·실제 프로세스 둘 → 인덱스 없이 **2행**, 인덱스와 함께 **1행 + 회복 로그 1줄**, 3회 반복 동일). 인덱스가 있으면 `apply_batch_updates`가 `IntegrityError`를 잡아 롤백 후 배치를 재실행하고, 새 스냅샷의 프리페치가 상대가 커밋한 행을 봐서 **거기에 병합**한다. 🔴 **테이블별로 먼저 세고 나서 만든다** — 중복이 있는 테이블은 이름·건수·문제 키와 함께 거부되고 **나머지는 계속 진행**한다. 업무 키가 NULL인 행은 여러 개여도 된다(빈 행 추가 기능이 그런 행을 만든다). ⚠️ **신규 생성 DB는 마이그레이션을 돌리기 전까지 무방비**다(`create_all`은 기존 테이블에 인덱스를 안 만들어서 `models.py` 선언이 답이 아니다) | `python server/migrations/add_business_key_unique_index.py` (인수 없으면 읽기 전용 사전점검 — **[2026-08-13 `b1dd2f0`] 그 「읽기 전용」이 이제 증명된 성질이다**: 연결이 `transaction_read_only`를 **되읽어** `on`이 아니거나 답하지 못하면 **거절**하고, 쓰기용 엔진은 `--apply` 갈래 안에서만 열린다. 점검만 하는 실행은 쓰기 가능한 연결을 아예 만들지 않는다 → [POSTGRES_OPERATIONS §3.1 「읽기 전용 가드」](../guide/POSTGRES_OPERATIONS_GUIDE.md)) | `server/migrations/add_business_key_unique_index.py` · `crud.apply_batch_updates`/`_is_business_key_unique_violation`(§5) · 회귀 그물 `server/tests/test_business_key_conflict_retry.py` + `test_business_key_unique_migration.py` · [POSTGRES_OPERATIONS §3.1](../guide/POSTGRES_OPERATIONS_GUIDE.md) · [data_model §3.1](../architecture/data_model.md) |
| 제품 소유 테이블 설치 | 제품이 정의하는 4종을 사이트 `table_config.json`에 **바이트 스플라이스 병합**(현장 항목 무접촉, dry run 기본, 백업, 드리프트는 보고만) | `python server/scripts/install_product_tables.py [--apply]` | `server/product_tables.py` · `server/scripts/install_product_tables.py` · [CONFIG_GUIDE §5.8-ter](../guide/CONFIG_GUIDE.md) |

### 1.12 접근 통제 (어드민 토큰 · 내부 IPC · 정적 서빙 봉쇄) — 2026-07-27 신설 (`90e284f`)

> **로그인 화면도 사용자 계정도 없다.** 사내 2~5명 공유 전제라 **공유 비밀 하나**를 헤더로 제시하는 형태다(SSOT §8 · [PRODUCTION_READINESS C1](../process/PRODUCTION_READINESS.md)).
> ⚠️ **이 절은 반드시 사내망 평문 HTTP 주소(`http://<사내IP>:8080`)에서 점검한다.** 게이트를 뚫는 쪽도, 뚫린 것을 보는 쪽도 그 주소로 들어온다. `localhost`에서만 확인한 결과는 이 절의 어떤 항목도 증명하지 못한다.

| 기능 | 설명 | 진입 경로 | 코드 |
|---|---|---|---|
| 어드민 공유 토큰 게이트 | `/admin/*` **API 라우트 전부**(2026-07-31 실측 **22개** — `@app.<verb>("/admin` 세기, 페이지 서빙 2개 제외)가 `ASSY_ADMIN_TOKEN` 환경변수 + `X-Admin-Token` 헤더 필요(비교 `secrets.compare_digest`). ⚠️ **이 수는 admin 라우트가 추가되는 커밋마다 낡는다** — 커버리지 판정의 정본은 수가 아니라 **`test_admin_auth.py`가 FastAPI 라우트 테이블을 열거하는 단언**이다. **조회도 포함** — 소스 코드 반환·파이프라인 열거도 유출이다. 미제시 **401**, 불일치 **403**. 예외는 페이지 서빙 `GET /admin`·`/admin.html` 2개(브라우저 내비게이션이라 헤더를 붙일 수 없고, 표시 데이터는 전부 게이트된 JSON에서 온다) | 서버 환경변수 | `server/admin_auth.py` · [backend §API](../architecture/backend.md) · [DEPLOY_SETUP §1-4](../guide/DEPLOY_SETUP.md) |
| 미설정 시 **부분** fail-closed | 토큰이 없으면 **strict 3라우트**(`POST /admin/scripts/code` · `POST /admin/auto-update/run-now` · **`POST /admin/retroactive/{op}/run`** — 2026-07-31 추가)만 **503**, 나머지는 **열린 채 동작**. 전부 잠그면 운영자가 **고치러 들어갈 페이지에서 잠긴다** — 의도된 비대칭이다. 🔴 **소급 실행이 strict인 이유는 코드 실행이라서가 아니다** — 테이블 전체 재작성·소스 주장 회수·노드 삭제이고 **같은 아웃박스로 같은 스케줄러 프로세스에 닿는다**(피해 계급이 같다). 목록의 정본은 `test_admin_auth.STRICT_ADMIN_ROUTES` | (자동) 기동 시 | `require_admin_token{,_strict}` |
| 비-ASCII 토큰 거부 | HTTP 헤더는 latin-1 디코딩이라 **한글·이모지 토큰은 구조적으로 인증 불가**. 서버가 기동 시 **거부하고 미설정 상태로 취급**하며 배너를 `ERROR`로 남긴다. 조용히 admin 라우트 전부를 죽이고 "토큰이 틀렸다"고 답하는 **복구 불능 상태**를 만들지 않기 위함 | 기동 로그 `[admin-auth]` | `token_is_unusable`/`startup_banner` |
| `/internal/events/*` 게이트 | 워커→웹서버 IPC 4개도 **같은 토큰**. `broadcast`는 임의 dict를 **접속 중인 전 클라이언트 그리드에 중계**하고 `audit_cache`에 주입하므로, 조회 admin만 잠그는 것은 거꾸로였다. 워커 3종은 **런처 환경을 상속**해 자동으로 헤더를 붙인다 | (자동) 워커 기동 | `internal_event_headers()` · `run_watcher`/`chain_ingestion_worker` (⚰️ **[2026-08-14] `graph_sync_worker`는 스택에서 빠졌다**) |
| **통지 4xx가 누가 거절했는지 말한다** (2026-07-30 `23a346d`) | `/internal/events/*`의 401/403 로그에 **`admin-gate=yes\|no`**가 붙는다. 판정은 게이트가 **자기 거부에만** 다는 `WWW-Authenticate: X-Admin-Token` 헤더 하나이고(대소문자 무시 **정확 일치** — 프록시의 `WWW-Authenticate: Basic realm=…`이 우리 것으로 읽히면 안 된다), `admin-gate=yes`면 **토큰 지문**과 모집단별 REMEDY가 함께 나온다(403 = 양쪽 토큰 다름 / 401+지문 있음 = 전송 중 탈락 / 401+`none` = 이 프로세스에 변수 없음 / 401+`unusable-non-ascii` = 비-ASCII라 헤더를 못 만듦). 🔴 **`admin-gate=no`면 토큰을 아무리 만져도 안 고쳐진다** — 앞단(프록시·방화벽·포트를 뺏은 다른 프로세스)이 답한 것이다. 2026-07-30 인시던트의 3시간이 이 한 줄이 없어서 들었다 | 워커 로그 | `admin_auth.internal_event_failure_note` · [DEPLOY_SETUP §1-4/§1-5](../guide/DEPLOY_SETUP.md) |
| **loopback HTTP는 프록시를 참조하지 않는다** (2026-07-30 `23a346d`) | 워커→웹서버 호출의 세션은 **`internal_event_client.internal_event_session()` 하나**에서만 나오고 `trust_env=False`다(환경변수·Windows 프록시 레지스트리 **둘 다** 차단, 스레드 로컬). 웹서버→GraphSync의 `httpx`도 같다. 원 사고: 레지스트리 `ProxyOverride`의 `<local>`은 **점 없는 호스트명만** 우회시켜 `localhost`는 통과하고 **`127.0.0.1`은 프록시로 나갔다** → 사설 주소 중계 거부 403(게이트 없는 `/health`까지). 🔴 **네 번째 발신자가 기억해야 하는 규칙이 아니라 테스트다** — 같은 결함이 발신자별로 세 번 재발해, 이제 발신자가 세션을 직접 만들면 `test_admin_auth.py`가 실패한다. 기동 시 데몬 3종이 `/health` 프로브 + `proxy-env` 요약을 찍는다 | (자동) 데몬 기동 로그 `[internal-events]` | `server/internal_event_client.py` · `test_admin_auth.py::test_no_sender_builds_its_own_client` · [PRIMITIVES §6](../architecture/PRIMITIVES.md) |
| 정적 폴백 봉쇄 (traversal 차단) | SPA catch-all이 **결과 기반 containment 검사** 후에만 파일을 낸다. 이전에는 **무인증으로 임의 파일**(`table_config.json`, `Windows/win.ini`, 게이트 자신의 소스)이 200이었다 — 잠근 조회 라우트가 지키던 바로 그 바이트가 옆문으로 나가고 있었다. 탈출은 **403이 아니라 404**(탈출이 파싱됐다는 사실조차 확인해 주지 않는다) | `GET /{경로}` | `main.py serve_static_or_index` · `_resolve_admin_script_path`(재사용된 원형) |
| 클라 토큰 흐름 | 게이트 거부에만 붙는 **`WWW-Authenticate: X-Admin-Token`** 헤더로 판정 → `prompt` 1회 → `localStorage['assy.adminToken']` 보관 → 이후 `X-Admin-Token` 헤더 전송. **새 화면·탭·설정 패널 없음**(구현은 `adminFetch()` 하나) | 어드민 페이지 최초 진입 | `client2/src/admin.js adminFetch` · [frontend §5](../architecture/frontend.md) |
| 서빙되는 것은 **번들**이다 | 서버가 보내는 것은 `client2/src/admin.js`가 아니라 git에 올라간 `client2/dist/assets/admin-*.js`다. 소스만 고치고 번들을 안 올리면 **토큰을 켜는 순간 어드민이 죽는다**(401은 오는데 물어보는 코드가 서빙 파일에 없어 프롬프트가 안 뜬다) | `cd client2 && npm run build` | 판정: `grep -c X-Admin-Token client2/dist/assets/admin-*.js` |
| 회귀 방어(범위 있음) | `test_admin_auth.py`가 FastAPI 라우트 테이블을 **열거**해 커버리지를 단언 — 나중에 추가되는 admin 라우트는 무방비 배포 대신 스위트를 빨갛게 만든다. ⚠️ **WebSocket 라우트와 mount는 걸리지 않는다**(`route.methods`가 `None`) — 그 축은 사람이 봐야 한다(§2.16) | `pytest server/tests/test_admin_auth.py` | `ADMIN_GATES` |

---

## 2. QA 수동 점검 체크리스트

> **사전 조건:** `python run_decoupled_app.py`로 전체 스택 기동(웹 :8080 + 워커 4종). 체인/인리치먼트 항목은 로컬 스모크 규칙(`line_model_owner_attribution`: `production_plan` → `line_model_registry`, gitignored config) 기준 — 환경에 규칙이 없으면 해당 항목은 N/A 처리.
> **핵심가치 직결 항목**은 🎯로 표시(실시간 SLO·멱등성·레이어링 보존 — 실패 시 릴리스 블로커).

### 2.0 자동 게이트 — 손으로 점검하기 **전에** 통과시킬 것

> 수동 점검은 자동 게이트가 초록일 때만 의미가 있습니다. **채점은 두 갈래이고, 한쪽만 돌리면 절반만 검증됩니다.**

- [ ] 🎯 **서버 절반**: `conda run -n assy_manager pytest server/tests/` 통과. ⚠️ **시스템 `python`으로 돌리지 말 것** — `psycopg2` 부재 등으로 거짓 실패가 납니다.
- [ ] 🎯 **클라 절반 = 빌드 게이트**(`5a14e77` 2026-07-30 신설 · `77a2c15`에서 **3행으로 늘었습니다**): `cd client2 && npm run build` 성공. `prebuild`가 `check:clipboard && check:contracts && check:harnesses`를 먼저 돌리고, 하나라도 발산하면 **`dist/`가 생성되지 않습니다.** (2026-07-30 밤 — `check:suggest-keys`가 목록에서 빠졌지만 **약해진 게 아닙니다**: 그 하네스가 `client2/tests/` 안에 있어 신설 `check:harnesses`의 발견식 스캔에 잡힙니다.)
  ```bash
  cd client2 && npm run check:contracts       # ✓ 6 contracts, no divergence.
  cd client2 && npm run check:suggest-keys    # 값 제안 키보드 계약 + 변이 스윕
  ```
  - ⚠️ **게이트 목록의 정본은 `client2/package.json`의 `prebuild` 한 줄입니다.** 이 체크리스트의 목록은 사본이고, 실제로 **두 번** 낡았습니다(2행이라고 적힌 채 3행이 됐고, 그다음엔 3행의 **구성이 바뀌었습니다**). 항목 수만 세지 말고 `prebuild` 한 줄을 그대로 읽으십시오.
- [ ] 🎯 **하네스 게이트**(`check:harnesses` 2026-07-30 밤 신설): 러너가 출력하는 **`N harnesses ― M gated, K known-red`** 줄과 **강제 항목이 전부 초록인지**를 눈으로 확인하십시오. 🔴 **이 문서는 그 수를 적지 않습니다** — 세 번 적었고 세 번 낡았으며 그중 한 번은 **적힌 그 시점에 이미 틀렸습니다**(하네스를 하나 더한 커밋을 아무도 세지 않았습니다). 러너가 매 실행마다 찍는 수를 산문이 다시 적을 이유가 없습니다. ⚠️ 수는 `client2/tests/*.mjs` − `KNOWN_RED`이고, 같은 디렉터리의 **`seam_7b_oracle.py`는 파이썬이라 스캔되지 않습니다**(파일 수 ≠ 하네스 수).
  - 🔴 **`ASSERTIONS <ran> <failed>` 줄을 함께 보십시오**(`b322267`). **종료 코드는 근거 없는 판결입니다** — 「단언에 닿기 전에 죽어서 빨강」과 「N개 단언으로 빨강」이 구분되지 않아 **죽은 하네스 셋이 부채로 위장**하고 있었습니다. 초록인데 그 줄이 없거나 `ran=0`이면 **BLOCKING**입니다.
  - 🔴 **초록 하네스도 플로어가 있습니다**(`efc4514`). 기록된 최소 `ran` 아래로 떨어지면 **하네스 자신이 exit 0이어도 BLOCKING**입니다 — 실측으로 15개 중 4개를 지운 하네스가 `11 passed, 0 failed`로 깨끗하게 초록이었고, 종전 러너는 그 27% 커버리지 상실 위에 「every gated harness is green」을 찍었습니다. **상승은 보고만 하고 막지 않습니다.**
  - ⚠️ **부채 항목의 산문에는 수가 없습니다**(`db46525`) — 러너가 같은 줄에 실측치를 나란히 찍습니다. 인용할 일이 있으면 그 출력을 읽으십시오. 종전 정적 문자열 「28」이 실측 42와 갈린 채 살아남아 보드까지 41을 찍게 만들었습니다.
  - 🔴 **부채 목록은 스크립트 안에 사유와 함께 적혀 있습니다** — 조용한 skip이 아니라 드러난 빚입니다. 부채 항목이 초록으로 돌아오면 러너가 「목록에서 빼라」를 출력하므로, 그 줄이 보이면 **그때 빼는 것이 절차입니다.** 이 게이트가 없던 동안 거의 전부를 아무도 부르지 않았고, `split_registry_harness.mjs`는 몇 주, `company_roundtrip`/`copy_header_count`는 한 커밋 동안 죽은 채였습니다.
  - 🔴 **`check:suggest-keys`의 판정은 "통과"가 아니라 "APPLIED == CAUGHT"입니다.** 모든 점검에 변이(mutation)가 짝지어져 있는데, **변이가 소스 드리프트로 적용되지 않으면 조용한 무장 해제**입니다(`cb8f01a`: 18개 중 8개가 적용조차 안 되면서 베이스라인은 초록이었습니다). 출력의 APPLIED와 CAUGHT 수를 **둘 다** 확인하십시오.
  - ⚠️ 이 하네스는 AG-Grid 키보드 파이프라인의 **모델** 위에서 돕니다. AG-Grid가 호출 순서를 바꾸면 하네스는 초록인 채 제품이 깨지므로, **브라우저 실측 키스트로크 수가 1차 증거**이고 이것은 그 아래의 회귀 그물입니다(§2.1의 F3 항목).
  - **2026-07-30 이전에는 계약 클라 하네스를 아무것도 실행하지 않았습니다** — `pytest`는 서버 절반만 채점하고 `client2`에 스크립트가 없었습니다. 그 조건이 `split_registry_harness.mjs`를 심볼 개명 이후 **몇 주 동안 예외로 죽어 있게** 두었습니다(부르는 사람이 없어 실패가 보이지 않음).
  - 🔴 **"0개, 전부 초록"은 통과가 아닙니다.** 러너는 `contracts/*/client_harness.mjs`를 **발견식으로 스캔**하며 하나도 못 찾으면 `exit 1`입니다 — 출력의 계약 **개수**를 눈으로 확인하십시오(2026-08-04 실측 **6**: `band_arithmetic`·**`blank_predicate`**·`config_resolve_report`·`doe_band_rules`·`legend_map_scope`·`map_seam`). ⚠️ **계약을 추가·삭제하는 커밋은 이 숫자를 바꾼다 — 같은 커밋에서 위 샘플과 이 줄을 함께 고친다.** 틀린 기대값은 점검을 **무장해제한다**: 기대값이 실제보다 작으면 스캔이 조용히 비어도 눈이 그것을 통과시킨다. (실제로 한 번 일어났고, 이 문서에서 **산문만 고치고 위 코드 샘플을 그대로 둔** 두 번째 사례까지 있었다 — 독자가 자기 출력과 대조하는 것은 **샘플**이므로 샘플이 load-bearing 쪽이다.)
  - 계약이 발산하면 **벡터를 고쳐 통과시키지 말 것**. 구현을 고치거나, 계약이 바뀐 것이면 총괄에 가져갑니다.
- [ ] **빌드 성공 ≠ 번들 커밋**: 서버가 서빙하는 것은 `dist/`입니다. 소스를 고쳤으면 빌드 후 `client2/dist/`를 함께 커밋했는지 확인(§2.16 A의 번들 선행 확인과 같은 규율).

### 2.1 데이터 그리드 — 조회/편집

- [ ] **조회 정상**: `/` 접속 → `table-select`에서 테이블 선택 → 그리드에 데이터 표시, 하단에 페이지/건수 표시.
- [ ] **편집 정상**: 셀 더블클릭 → 값 변경 → Enter → 값 반영 + 셀에 오버라이트 표시(스타일 변화) + History 패널에 이력 즉시 추가.
- [ ] **편집 에지 — 숫자 검증**: 숫자 타입 컬럼에 문자열 입력 → 거부(토스트/원복)되고 서버에 저장되지 않음.
- [ ] 🎯 **편집 에지 — 자동값 우선순위**: 파일 인제션으로 채워진 셀을 수동 편집 → 같은 파일 재드롭 → 수동 값이 유지됨(user가 parser를 이김).
- [ ] **필터/정렬**: 컬럼 플로팅 필터에 조건 입력 → 결과 축소, 헤더 클릭 → 정렬 토글. 필터+페이지 이동 조합 시 결과 일관.
- [ ] **페이징**: 다음/이전 페이지 이동, 페이지 번호 직접 입력, 마지막 페이지에서 다음 버튼 동작(비정상 점프 없음).
- [ ] **CSV export**: `load-csv-btn` → 현재 테이블 CSV 다운로드, 행 수가 화면 총계와 일치.
- [ ] **CSV export 상한 (2026-08-11)**: 조건에 걸리는 행이 `main.EXPORT_MAX_ROWS`(1,000,000)를 넘으면 **파일이 안 만들어지고 413**이다 — **잘린 CSV를 주지 않는다.** 점검: ① 상한 초과 조건에서 다운로드 시도 → 파일이 생기지 않고 실패 토스트 ② 필터를 좁혀 상한 이하로 만들면 정상 다운로드 ③ 상한 이하 추출에서 `X-Total-Rows`가 **실제 받은 행 수와 같다**(예전엔 100만으로 깎여 진행률이 100%를 넘었다). ⚠️ **알려진 클라 공백**: `main.js`의 catch가 응답 바디를 안 읽어 토스트가 `❌ CSV 다운로드 중 오류 발생`로만 뜬다 — 서버는 초과 행수와 상한을 `detail`에 담아 보내므로, 그 문구를 띄우는 것은 클라 쪽 후속 작업이다.

#### 값 제안 셀 에디터 (F3 `77a2c15` + Escape 시정 `d5f75a8`) 🎯

> ⚠️ **점검 전에 반드시**: `switchTable`이 **`txModeActive`를 강제로 다시 켭니다**(`client2/src/api.js:70-71` — 대기 편집 폐기와 한 쌍). 편집 E2E는 **표를 바꾼 뒤마다 토글을 다시 끌 것.** 이 함정으로 에이전트 두 명이 각각 한 회차를 날렸습니다: 편집이 스테이징만 되고 서버에 안 가는데 화면은 정상처럼 보입니다.
>
> 판정은 **키스트로크 수**로 씁니다("동작했다"가 아니라 "몇 번 눌렀나"). 계수 규칙은 `effort_meter`와 같습니다 — 단독 수식키 제외.

- [ ] 🎯 **1글자 → 목록 + `Enter` 1회로 확정**: `string` 컬럼 셀에서 **1글자** 입력 → 목록이 뜨고 **첫 후보가 하이라이트** → `Enter` **한 번**에 그 후보가 셀에 확정된다. **두 번 필요하면 결함입니다**(채택과 확정이 갈렸다는 뜻 — `suppressKeyboardEvent`가 `'accepted'`를 못 돌려주고 있습니다).
- [ ] **`↓` 이동 후 `Enter`**: `↓`로 후보를 옮기고 `Enter` → 하이라이트된 그 후보로 확정. 화살표는 캐럿을 입력 앞/뒤로 튕기지 않는다.
- [ ] 🎯 **`Esc` 1회는 목록만 닫고 글자를 보존한다 — 그리고 타이밍에 무관해야 한다**: ⓐ 빠르게 타이핑해 **목록이 뜬 상태**에서 `Esc` → 목록만 닫히고 **타이핑한 글자가 남는다**(그 상태에서 `Enter`면 내가 친 값이 저장). ⓑ **느리게 타이핑해 목록이 아직 안 뜬 상태**에서 `Esc` → **ⓐ와 같아야 한다.** 🔴 **이 두 타이밍이 갈리는 것이 원래 결함이었습니다** — 종전에는 `listOpen`을 물어서, 목록이 화면에 있었는지가 디바운스+왕복시간의 함수였고 한쪽은 글자를 **버렸습니다**.
- [ ] **`Esc` 2회는 편집 취소**: engaged된 셀에서 `Esc` 두 번 → 두 번째가 AG-Grid의 평범한 편집 취소(원래 값 복귀). ⚠️ **취소에 두 번이 필요한 것은 의도된 대가**입니다(결정성을 그 키 하나보다 값어치 있게 봤습니다). 다만 **제안이 한 번도 engaged되지 않은 컬럼**(미선언·서버 플로어 미달·쿨다운)에서는 **첫 `Esc`가 곧 취소**이고 화면에는 그 차이가 보이지 않습니다 — 알려진 비균일성이므로 결함으로 올리지 마십시오.
- [ ] **`Esc` 후 `↓`는 목록을 다시 연다**: `Esc`로 닫은 뒤 `↓` → 추가 타이핑 없이 목록 재개. `↑`는 열지 않는다(자기가 쓴 글자를 지키려는 사람에게 안전한 방향 하나).
- [ ] **`Tab`은 채택 + 이동**: 하이라이트 상태에서 `Tab` → 후보가 확정되고 다음 셀로 이동(한 번 누름).
- [ ] **`Ctrl+Enter`는 채택값으로 범위 일괄**: 범위를 잡고 편집 시작 → 타이핑 → `Ctrl+Enter` → **하이라이트된 후보값**이 범위 전체에 채워진다(입력에 남은 부분 접두가 아님).
- [ ] **한글 IME**: 한글을 조합하는 중의 `Enter`는 **IME 것**(음절 확정)이라 후보를 대입하지 않는다. 조합이 끝난 뒤의 `Enter`부터 제안 계약이 적용된다.
- [ ] **제안 불가 컬럼은 평범히 동작**: 미선언 컬럼·`number`·`datetime` 컬럼에서 편집 → **목록 없이** 종전 그대로. 토스트도 에러도 뜨지 않는다(제안할 수 없는 컬럼의 망가진 드롭다운은 없는 것보다 나쁩니다).
- [ ] **진단 창이 실제로 존재한다**: 콘솔에서 `window.__assySuggest.getSuggestStats()` → 요청/로컬 축소/중단/거부/불가 카운트가 나온다. `undefined`면 계측이 dist에 없는 것이므로 그 자체가 결함입니다(`847ceaf`).

### 2.2 데이터 그리드 — 소스 레이어링/핀

- [ ] **소스 목록**: 여러 소스가 쌓인 셀(파일 2회 상이 값 인제션 + 수동 편집으로 준비)을 **우클릭 → "📚 데이터 원천(Sources) 관리"** → 모달에 소스별 값 표시(값에 마우스 오버 시 갱신자/시각 툴팁).
- [ ] 🎯 **소스 삭제 → 차순위 폴백**: 최우선 소스(user)의 "🗑️ Delete" → confirm 승인 → 표시값이 차순위 소스(예: pipeline_parser) 값으로 즉시 재계산되어 표시됨.
- [ ] **소스 삭제 에지 — 없는 소스**: 이미 삭제된(또는 존재하지 않는) 소스를 다시 삭제 시도 → 하단 상태 로그에 "❌ Failed to delete cell source" 표시(토스트/모달 아님 — 무음 실패는 아님), 그리드 값 불변.
- [ ] **핀 설정**: 하위 우선순위 소스의 "📍 Pin" 클릭 → 표시값이 핀 소스 값으로 전환("📌 Pinned" 활성 표시). 재클릭으로 핀 해제 → 기본 우선순위 규칙으로 복귀.
- [ ] **핀 이력**: 핀 설정/해제가 History 패널과 셀 이력에 기록됨(서버 재시작 후에도 조회됨 — 이슈 #6 회귀 확인).
- [ ] 🎯 **셀 이력이 비는 행 — 두 상태가 다르게 그려진다 (2026-08-11 서버 → 2026-08-12 화면 착지)**: 인제션·체인으로만 채워진 행(예: 파일로 방금 적재한 행)의 아무 셀이나 골라 **Cell History** 탭 → **`이 셀 기록 없음` + `행 이력 N건 보기` 버튼**이 보인다(빈 화면이 아니다). 그 버튼 **1클릭**으로 **Row History** 탭이 열리고 `ROW_UPDATE` 기록 N건이 보인다. 이것은 이력 유실이 아니라 **기계 쓰기가 셀 단위로 기록되지 않기 때문**이다(`column_name='ROW_UPDATE'` — [backend §이력/감사](../architecture/backend.md)). 대조군: **감사 기록이 아예 없는 행**의 셀 탭 → **`기록 없음`만** 뜨고 버튼은 없다. **둘이 같은 문구로 보이면 회귀다.** ✅ **서버**: 셀 라우트 응답의 `row_history_total`이 행 탭 건수와 같다(행 라우트에는 `null`). ⚠️ **`row_history_truncated: true`면 문구가 `N건 이상`이어야 한다** — 그 수는 하한이다(서버 프로브 상한 1000). 격리 `assy_qa`에는 1000건을 넘는 행이 없어 이 분기는 라이브로 못 밟는다(`client2/tests/history_paging_harness.mjs` I4가 대신 잡는다).

### 2.2-bis 가상 조인 컬럼 🎯 (2026-07-31 `d70a33d` → 화면 착지 `9200f20`+`4b50135`)

> **준비**: `virtual_join_rules.json`에 선언 1건 + 오른쪽 테이블에 조인 키 UNIQUE 인덱스.
> `GET /admin/config/virtual-join/verify`가 `accepted`여야 아래가 성립한다(거부면 아무것도 붙지 않는 것이 정상).
> **선언 하나에 `collide` 컬럼과 `virtual_only` 컬럼을 둘 다 노출해 두면** A(값 병합)와 B(화면·쓰기 노출)를 한 번에 본다.

**A. 값 병합 — 서버 계약**

- [ ] 🎯 **부재일 때만 채운다**: 왼쪽에 **값이 있는** 행 → 그 값이 **그대로** 보인다(조인 값으로 바뀌지 않는다). 왼쪽이 **빈** 행 → 조인 값이 보인다. 오른쪽 행이 없거나 그 값이 비어 있으면 **`미상`**.
- [ ] 🎯 **`미상`은 두 경우를 덮는다**: 오른쪽 행 자체가 없는 행과, **오른쪽 행은 있는데 값이 빈** 행이 **둘 다** `미상`이어야 한다. 후자가 빈칸으로 보이면 ②가 새고 있는 것이다.
- [ ] **출처가 셀 단위로 읽힌다**: 조인이 채운 셀을 우클릭 → 소스 목록에 `virtual_join`. **왼쪽 값이 이긴 셀에는 `virtual_join`이 없어야 한다**(참여했다가 진 것은 출처가 아니다).
- [ ] **행이 증발하지 않는다**: 오른쪽에 짝이 없는 행도 페이지에 그대로 있다(INNER로 바뀌면 조용히 사라진다). 조인 전후 **행 수가 같아야** 한다.
- [ ] 🎯 **겹친 컬럼은 편집된다**: 조인 값이 보이는 셀을 편집 → 저장되고, 다시 조회하면 **내가 쓴 값**이 보인다(그 쓰기가 조인 값을 덮는 유일한 방법). 편집한 값이 다음 조회에서 조인 값으로 되돌아가면 결함이다.
- [ ] **가상 전용 컬럼 쓰기는 400**: 왼쪽에 실재하지 않는 `expose` 컬럼을 페이로드에 넣어 `PUT /tables/{t}/data/updates` → **400**, 메시지가 그 컬럼명을 지목한다. 🔴 **200 + 무변화는 실패다**(그것이 이 검사가 막는 바로 그 침묵이다).
- [ ] **선언을 고치면 다음 조회에 반영**: 선언 수정 → `POST /admin/reload-configs` → 다음 조회에 즉시 반영. 승인되지 않은(인덱스 없는) 선언은 **아무것도 붙이지 않는다**.
- [ ] **조인이 죽어도 그리드는 산다**: 선언 파일을 일부러 깨뜨려도 그리드는 정상 조회되고 조인 컬럼만 빠진다(서버 로그에 `[VirtualJoin]`).

**B. 화면과 쓰기 노출 — 클라 계약** (`9200f20`+`4b50135`)

- [ ] **`/schema`가 별도 키로 알린다**: `curl .../tables/{t}/schema` → **`columns`에는 가상 컬럼 이름이 없고** `virtual_columns[]`에 `{name, type, editable:false, right_table, rule, unresolved_label}`이 있다. 🔴 **`columns`에 섞여 있으면 결함**이다(그 배열의 뜻이 「저장하는 컬럼」이고 소비자 넷이 그 뜻에 기댄다). 승인된 조인이 없는 테이블에서도 **키는 있고 `[]`**여야 한다.
- [ ] **`collide`만 있는 선언은 스키마 응답을 바꾸지 않는다**: 겹친 컬럼만 노출하는 선언으로 바꾸고 `/schema`를 다시 받으면 **본문이 선언 전과 동일**하다(가상 컬럼 알림 0건). 같은 컬럼이 두 번 알려지면 「이 컬럼은 저장되는가」에 두 답이 생긴다.
- [ ] 🎯 **그리드 맨 뒤에 뜨고, 앞 컬럼은 자리가 안 바뀐다**: 가상 전용 컬럼이 **저장 컬럼들 뒤에** 헤더 `🔗` + 회색으로 나타난다. **첫 컬럼의 체크박스가 그대로**인지 확인(중간에 끼면 체크박스가 다른 컬럼으로 옮겨간다). 툴팁에 **오른쪽 테이블 이름과 선언 이름**이 있다.
- [ ] **편집이 제안되지 않는다**: 그 셀을 더블클릭해도 에디터가 열리지 않는다.
- [ ] 🎯 **붙여넣기가 통째로 죽지 않는다**: 저장 컬럼 2개 + 가상 컬럼 1개에 **걸치는** 범위를 잡고 Ctrl+V → **저장 컬럼은 저장되고 가상 컬럼만 빠진다.** 🔴 **전체가 400으로 실패하면 결함**이다(서버 거부는 배치 단위라, 클라가 미리 빼지 않으면 **한 셀 때문에 붙여넣기 전체를 잃는다**).
- [ ] 🎯 **delete 비우기와 Ctrl+Enter 일괄도 같다**: 같은 걸친 범위에서 ⓐ Delete로 비우기 ⓑ 값 타이핑 후 Ctrl+Enter → 둘 다 **저장 컬럼만 반영되고 가상 컬럼은 무변화**. 🔴 이 셋은 `editable`을 읽지 않고 **그리드 컬럼 id로 배치를 만들므로** 각자 가드를 갖는다 — 하나만 고쳐져 있으면 나머지가 샌다.
- [ ] 🎯 **복사한 직사각형이 선택한 그것과 같다**: 가상 컬럼을 **가운데에 포함**하도록 범위를 잡고 Ctrl+C → 엑셀에 붙여넣어 **열 개수와 열 순서가 화면과 일치**하는지 본다. 🔴 **가상 컬럼이 빠지고 오른쪽이 한 칸씩 밀려 오면 결함**이다(선택하지 않은 직사각형을 돌려준 것 — 조용한 데이터 오독). 복사는 읽기이므로 가상 컬럼도 **포함되는 것이 정답**이다.
- [ ] **`미상`이 숫자 컬럼에서 살아남는다**: `type`이 `number`인 가상 컬럼에서 미해결 행의 셀이 **`미상` 그대로** 보인다(`NaN`·`0`·빈칸이면 결함).
- [ ] 🎯 **정렬에서 미해결 행이 뭉친다**: 그 숫자 컬럼을 오름차순 정렬 → **`미상` 행이 한 덩어리로 맨 아래**에 모인다. 🔴 **숫자들 사이에 흩어지면 결함**이다(기본 비교로는 `미상`이 모든 숫자와 동률이 된다). 내림차순에서는 맨 위로 온다.
- [ ] 🎯 **필터가 화면의 값을 찾는다** (`cd3e0f4`): 조인 해석 컬럼(collide 포함)의 헤더 필터에서 `equals 미상` → **미해결 행만** 나오고 `Matches:`도 같이 줄어든다(화면만 걸러지고 카운트가 전량이면 결함). 🔴 **Blank/NotBlank는 그 컬럼의 필터 목록에 없어야 한다** — 해석값은 결코 빈 값이 아니므로(마지막 팔이 `미상`) Blank는 0건, NotBlank는 전량을 돌려주는 거짓 컨트롤이다. 일반 저장 컬럼에는 둘 다 **있어야 한다**(그쪽은 진짜로 빌 수 있다).
- [ ] 🎯 **숫자 컬럼은 화면의 철자로 찾는다** (2026-08-04 N7): `type: number`인 가상 컬럼에 저장값 `3.0`이 있으면 화면은 `3`으로 보이고, **`equals 3`이 그 행을 찾는다**(`3.0`으로는 못 찾는 것이 정답 — 아무도 보지 않는 철자다). `2.5`는 그대로 `2.5`. 🔴 이 수정 전에는 숫자 expose 컬럼 조회 자체가 **PostgreSQL 500**이었다(§4-ter).
- [ ] **CSV 추출이 화면과 같다** (`cd3e0f4`): `load-csv-btn`으로 받은 CSV에 가상 컬럼 열이 **있고**, 셀 값이 화면과 같다 — 미해결 행은 `미상`, 숫자는 INT 철자(`3`, `3.0`이 아니라). 🔴 컬럼이 있는데 화면이 `미상`인 자리가 빈칸이면 결함이다(저장 원값을 실은 것).
- [ ] **검색 드롭다운에 안 뜬다**: 툴바 검색의 컬럼 목록에 가상 컬럼이 **없다**. 🔴 있으면 결함이다 — 그 이름은 SQL이 닿지 못해 **조건이 하나도 안 걸리고 전체 테이블이 「검색됐다」며 돌아온다.**
- [ ] **맵 push 게이트 산술이 그대로다**: `map_push_ok`가 false인 맵 테이블에 가상 컬럼을 붙여도 ⚡ Push의 거절/확인 동작이 **선언 전과 같다**(가상 컬럼은 저장되지 않으므로 push가 파괴할 수 있는 컬럼이 아니다).

### 2.3 데이터 그리드 — 행/클립보드/컬럼/Tx 모드

- [ ] **행 추가**: `add-row-btn` → 빈 행 생성 → 비즈니스 키 입력 → 저장됨. 다른 브라우저 창에도 행 추가 반영.
- [ ] **행 삭제**: 행 선택 → `delete-row-btn` → 삭제 + 글로벌 타임라인에 DELETE 이력(비즈니스 키 표시).
- [ ] **클립보드 복사**: 셀 범위 드래그 → Ctrl+C → 엑셀에 붙여넣기 시 TSV 형태 일치. `copy-header-toggle` 켜면 헤더 포함.
  - ⚠️ **반드시 사내망 평문 HTTP 주소(`http://<사내IP>:8080`)에서 점검**할 것. `localhost`/`127.0.0.1`은 보안 컨텍스트라 `navigator.clipboard`가 살아 있어 **운영 결함이 재현되지 않는다**(2026-07-27 실제 사례).
- [ ] **행 단위 복사**: 셀 범위 선택을 해제한 상태에서 행 체크박스로 행 선택 → Ctrl+C → 행 전체 TSV. ⚠️ 셀 범위/단일 셀 선택이 남아 있으면 범위 복사가 우선(`clipboard.js:569`)이라 행 복사가 실행되지 않는다.
- [ ] **클립보드 붙여넣기**: 엑셀에서 복사한 2×2 범위를 그리드에 Ctrl+V → 해당 범위 셀 값 갱신 + 이력 기록.
- [ ] **스마트 페이스트 — 단축키(본동선)**: 엑셀에서 표 복사 → 그리드에서 `Ctrl+Shift+V` → (엑셀 복사본은 다중 포맷이므로) 유형 선택 모달에서 포맷 선택 → 업로드 성공 토스트 → 인제션 파이프라인 경유 적재·그리드 반영.
  - ⚠️ 브라우저가 `Ctrl+Shift+V`를 붙여넣기 명령으로 번역하지 않으면 **아무 일도 안 일어나는 대신** 0.6초 뒤 「이어서 Ctrl+V 를 눌러 주세요」 토스트가 뜬다. **그 상태에서 Ctrl+V를 눌러 완료되는지까지가 이 항목**이다.
- [ ] **스마트 페이스트 — 우클릭 진입**: 우클릭 → "📋 파서로 붙여넣기 (Smart Paste)" → 「이 환경(평문 HTTP)에서는 버튼이 클립보드를 읽을 수 없습니다. 지금 Ctrl+V 를 눌러 주세요」 토스트 → Ctrl+V → 위와 동일하게 완료. **메뉴 클릭만으로 조용히 끝나면 결함**이다.
- [ ] **스마트 페이스트 — 걸쇠 회수**: ① 안내 토스트는 붙여넣기가 완료되는 즉시 사라진다(안내가 화면에 남으면 결함). ② Esc를 누르면 예약이 풀리고, 이후 Ctrl+V는 **평범한 범위 붙여넣기**로 동작한다. ③ 예약 후 **테이블을 바꾸고** Ctrl+V를 누르면 업로드하지 않고 「테이블이 [A] → [B] 로 바뀌어 취소했습니다」로 거절한다(**엉뚱한 테이블 적재 방지 — 실패하면 데이터 사고**).
- [ ] **스마트 페이스트 — 거절 문구**: 이미지만 복사한 상태에서 실행 → 「클립보드에 텍스트 형식이 없습니다. (감지된 형식: …)」. 빈 클립보드 → 「클립보드가 비어 있습니다」. **일반 오류 토스트로 끝나면 결함**(사용자가 스스로 고칠 수 없어 문의가 된다).
  - ⚠️ **반드시 사내망 평문 HTTP 주소에서 점검**할 것. `localhost`/`127.0.0.1`은 보안 컨텍스트라 `navigator.clipboard`가 살아 있어 버튼이 그냥 읽어버린다 — **운영 동선(걸쇠)이 재현되지 않는다.** 위 **클립보드 붙여넣기**(Ctrl+V)는 별개 경로이며 평문 HTTP에서도 정상.
- [ ] **컬럼 선택**: `column-selector-btn` → 일부 컬럼 해제 → 그리드에서 숨김. 전체 선택/해제 버튼 동작.
- [ ] **Tx 모드**: 설정 메뉴 `tx-mode-toggle` ON → 셀 2~3개 편집(서버 미반영 스테이징 표시) → `tx-apply-btn` → 일괄 커밋(단일 트랜잭션 이력). ON 상태에서 `tx-discard-btn` → 편집 전량 원복.
- [ ] **Tx 모드 에지 — 이탈 경고**: Tx 편집 pending 상태에서 페이지 새로고침 시도 → 이탈 경고(beforeunload) 표시.

### 2.4 변경 이력

- [ ] **글로벌 타임라인**: 편집 직후 History 패널 `tab-global`에 트랜잭션 그룹 표시, 펼치면 셀 단위 old→new 표시.
- [ ] **셀/행 타임라인**: 셀 선택 → `tab-cell`에 해당 셀 계보만, `tab-row`에 해당 행 변경만 표시.
- [ ] **로그→셀 점프**: 다른 페이지에 있는 행의 이력 항목 클릭 → 해당 페이지로 이동 + 대상 셀 하이라이트/스크롤.
- [ ] **이력 영속 에지**: 행 삭제 후 서버 재시작 → 글로벌 타임라인에 DELETE 이력이 여전히 조회됨.

### 2.5 파일 인제션

- [ ] **커스텀 파서 정상**: 커스텀 스크립트가 있는 워크스페이스 `raws/`에 매칭 파일 드롭 → 파싱·적재 → `archives/` 이동 + 그리드에 진행 토스트→완료.
- [ ] **std 폴백 정상**: 스크립트 없는(또는 무매칭) 테이블에 스키마 헤더와 일치하는 CSV 드롭 → 적재 성공. 미지 컬럼이 섞인 파일도 알려진 컬럼만 적재.
- [ ] **std 에지 — 키 결측 행**: 비즈니스 키가 빈 행(소계/각주)이 섞인 CSV 드롭 → 해당 행만 스킵되고 완료 메시지에 "키 결측으로 N행 스킵" 표시. 재드롭해도 고아 행 미생성.
- [ ] **err 격리**: 헤더에 비즈니스 키 컬럼이 없는 CSV 드롭 → `err/`로 이동 + 어드민 File 탭에 FAILED 로그.
- [ ] 🎯 **멱등성 — 재드롭 무중복**: 동일 파일을 `raws/`에 2회 드롭 → 행 수 불변(비즈니스 키 업서트), 신규/변경 셀만 이력 추가. 중복 행·중복 outbox 브로드캐스트 없음.
- [ ] **실패 재시도**: err 원인(예: 스크립트 버그) 수정 후 어드민 File 탭에서 재시도 → 성공 전환 + 데이터 적재.
- [ ] **워크스페이스 자동 생성**: `table_config.json`에 테이블 추가 → `/admin/reload-configs` → 워크스페이스 폴더 자동 생성·감시 시작 + 물리 테이블 즉시 CREATE(이슈 #7 해소 — 재기동 없이 조회 정상).
- [ ] **기동 스윕**: 서버 정지 상태에서 `raws/`에 파일을 미리 넣고 기동 → 기동 직후 자동 처리·아카이브(이벤트 없이도 적재). 신규 워크스페이스 런타임 등록 시에도 기존 파일 스윕.
- [ ] **워크스페이스 별칭**: 테이블 항목에 `workspace_name` 별칭 지정 + 리로드 → 별칭 폴더로 워크스페이스 생성·감시, 그 폴더 드롭이 해당 테이블로 적재. 어드민 File 탭 워크스페이스 현황에 테이블명 정상 표시. 실패 재시도(retry-failed)도 별칭 워크스페이스를 정확히 역조회.
- [ ] **별칭 에지 — 섀도잉 무효**: 별칭을 다른 실존 테이블명과 동일하게(또는 두 테이블이 같은 별칭을) 선언 → 별칭 무시 + ERROR 로그 1회(로그 홍수 없음), 폴더명 규약으로 동작.
- [ ] **std_parse 옵트아웃 핫리로드**: 테이블 항목에 `"std_parse": false` 추가 + 리로드 → **재기동 없이** 다음 파일부터 std 폴백 비활성(무매칭 파일은 err/ 격리). 처리 도중이던 파일은 시작 시점 config로 완결. 문자열 `"false"` 등 비-bool 값은 무시 + 경고 1회.
- [ ] **레거시 config.json 하위호환 에지**: 워크스페이스 `config/config.json`이 있는 기존 워크스페이스 → 계속 동작하되 기동 로그에 deprecation WARNING **1회**(sensor_config.json 등 다른 파일에는 미발화). 글로벌 `table_config.json`과 충돌 시 글로벌 값 승리. 신규 자동 생성 워크스페이스에는 config.json이 생성되지 않음.
- [ ] **스윕 에지 — 잔류 파일 무한 재시도 없음**: 처리 불가 파일이 `raws/`에 남아도 300s 주기 스윕이 동일 (mtime,size) 파일을 반복 재시도하지 않음(워커 로그 확인). 파일 수정(mtime 변경) 시에는 재처리됨.
- [ ] 🎯 **heavy 레인 — 교차 비차단**: 임계 초과 대형 CSV(>10MB) 투입 → watcher 로그 `🐘 Routed to heavy lane queue (size, ...)` → heavy 진행 중 **다른 테이블** 소형 CSV 투입 → 수 초 내 완료(분 단위 대기 없음 — 드릴 기준 ~2.3s).
- [ ] 🎯 **heavy 레인 — 같은 테이블 순서 보존**: heavy 진행 중 **같은 테이블**에 소형 파일 투입 → `(workspace-order)` 재라우팅 로그 → heavy 완료 후 처리(추월 없음), 최종 행 수·bk 중복 0 확인.
- [ ] **heavy 진행 가시화**: heavy 진행 중 admin File 탭 → 진행 중 섹션에 HEAVY 배지(재라우팅 소형은 normal 배지)·진행률 바·행 카운트 표시 + 재기동 경고 배너 + 헬스 스트립 File 카드 warn. 완료 시 목록 자동 소거·경고 소멸.
- [ ] **heavy 임계 핫리로드**: `config/ingestion_settings.json`의 `heavy_file_mb` 변경 → 재기동 없이 **다음 파일부터** 반영. 무효값(문자열/0 이하)은 기본 10MB + 경고 1회.
- [ ] **heavy 스윕 라우팅**: watcher 정지 → raws/에 대형+소형 배치 → 기동 → 스윕이 대형만 heavy로 보내고 소형·타 테이블이 선완료.
- [ ] 🎯 **[P2] 체크포인트 재개**(재기동 후 최초 드릴): 대형 파일 처리 도중 watcher 강제 종료 → 재기동 → 로그에 `[resume]`과 재개 오프셋 → **처음부터가 아니라 이어서** 적재되고 최종 행 수·bk 중복 0. `file_ingestion_checkpoints`의 `processed_rows`가 실제 커밋 행 수와 일치.
- [ ] **[P2] 재개 거부 표면화**: 같은 파일명으로 **내용이 다른** 파일 투입(시그니처·total_rows 불일치) → 0부터 재처리 + 로그·`FileIngestionLog.detail`·완료 통지에 `[resume-abort] … 사유:` 명시(조용히 재처리되면 실패).
- [ ] 🎯 **[P2] 해시 dedup**: 이미 적재 완료한 파일을 그대로 재투입 → skip + archives 이동 + `FileIngestionLog(SKIPPED)` + 사유 detail. **클라 알림이 "실패"로 보이지 않는지** 확인(통지 status는 SUCCESS).
- [ ] **[P2] 강제 재처리 3경로**: ① 파일명에 `__force__` 포함 ② `ingestion_settings.json`의 `dedup_by_signature: false` ③ 어드민 재시도 — 셋 다 skip을 우회해 재적재. **②는 tier 1까지 함께 꺼야 한다**(아래 항목 참조 — 안 그러면 「전역 강제 재처리」가 경로+stat 빠른 스킵에 조용히 막힌다).
- [ ] 🎯 **[Tier 1] 해시 없는 스킵**(2026-08-13, 마이그레이션 `add_ingestion_ledger_path_stat.sql` 선행): `archive_processed_files: false`로 두고 파일을 적재 → **파일이 `raws/`에 그대로 남는다** → 워처 재기동 → 같은 파일이 **다시 적재되지 않는다**. 🔴 **「안 일어났다」를 증거로 삼지 말 것** — `dedup_by_path_stat: false`로 바꿔 같은 시나리오를 다시 돌려 **해시가 도는데도 적재는 안 되는지**(tier 2가 잡는지) 확인해야 앞의 초록이 「스윕이 아무 일도 안 했다」와 구별된다.
- [ ] **[Tier 1] 내용이 바뀌면 다시 들어온다**: 같은 경로의 파일을 **내용만 바꿔** 덮어쓰기 → 다음 스윕에 재적재. (mtime·size가 **둘 다 그대로**인 채 내용만 바뀌면 tier 1이 놓치는 것이 **선언된 실패 방향**이다 — 결함이 아니라 거래이고, 되돌리는 스위치가 `dedup_by_path_stat: false`.)
- [ ] 🔴 **[Tier 1] 실패의 가시성 — `err/` 없이도 「무엇이 왜」에 답할 수 있는가**: `archive_processed_files: false`에서 파서가 거부할 파일을 투입 → 파일은 제자리에 남고 ① `file_ingestion_checkpoints`에 `status='FAILED'` 행(`filepath`=그 파일, `note`=사유) ② `file_ingestion_logs`에 `status='FAILED'` + 트레이스. **다음 스윕이 그 파일을 다시 시도하지 않는지**(무한 재시도 방지) 확인하고, **파일을 고치면 다시 걸리는지**(영구 봉인 아님)도 확인.
- [ ] ⚠️ **[Tier 1] `__force__` 파일을 치우지 않으면 매 스윕 재적재된다**: `archive_processed_files: false`에서 `__force__` 파일을 남겨 두고 스윕 2회 → 2회 다 적재된다(설계대로 — 토큰은 「항상 다시 넣어라」이고 옮기지 않으면 멈출 것이 없다). 운영 절차에 **1회 처리 후 토큰 제거/파일 이동**이 들어 있는지 확인.
- [ ] 🎯 **[Tier 1 끌어올리기, `831ab68`] 재기동 첫 스윕이 «빨라졌는지»가 아니라 «같은 일을 하는지»**: `archive_processed_files: false`로 트리를 채운 뒤 워처 재기동 → 스윕 로그가 한 줄로 `후보 N개 · M개 already concluded (tier-1, batched) · K개 dispatched`를 말하고 **재적재 0건**. 🔴 **대조군 없이 초록으로 읽지 말 것** — 같은 트리를 **전부 새 파일**로 갈아 콜드 스윕을 돌려 **시간이 그대로인지**(격리 실측 1.0배) 확인해야 「빨라졌다」와 「일을 안 한다」가 구별된다.
- [ ] 🔴 **[Tier 1 끌어올리기] 걸러진 파일도 «이동»은 갚는다** — 회귀가 실제로 한 번 난 자리다: `archive_processed_files: **true**`(옮기는 모드)에서 이미 종결된 파일을 `raws/`에 남겨 두고(예: 아카이브 이동이 잠금으로 실패했던 파일) 스윕 → **그 파일이 `archives/`(실패 이력이면 `err/`)로 옮겨진다.** 🔴 **그대로 `raws/`에 남으면 결함**이다 — 중첩 인제션에서는 **그 디렉터리 통째로** 영구 잔류한다.
- [ ] **[Tier 1 끌어올리기] 걸러진 파일은 조용하다**: 위 시나리오에서 **파일당 로그 한 줄이 생기지 않는지** 확인(스윕당 한 줄 요약만). 파일을 안 옮기는 모드에서는 히트가 **파일마다 매 스윕** 나므로, 한 줄씩 찍으면 5분마다 수만 줄이 실제 사건을 묻는다.
- [ ] **[Tier 1 끌어올리기] 폴더 드롭에도 같은 관문이 있다**: 중첩 폴더를 `archive_processed_files: false`로 적재한 뒤 **같은 트리를 다시 트리거** → 트리 로그의 `dispatched` 수가 **후보 수가 아니라 실제 내려간 수**이고 `already concluded`가 함께 찍힌다. (이 루프는 인메모리 캐시가 없어 **매 사이클** 비용을 내던 자리다.)
- [ ] **[Tier 1 끌어올리기] 끄는 스위치는 여전히 둘뿐**: `dedup_by_path_stat: false` 또는 `dedup_by_signature: false` → 배치 관문도 **함께 꺼진다**(전량 개별 디스패치). 🔴 **세 번째 노브가 생겼다면 회귀다** — 전역 강제 재처리가 빠른 길에 조용히 막힌다.
- [ ] **[P2] 감사 총계(이슈 #10)**: 멀티 target-table 체인이 걸린 트랜잭션 유발 → 타임라인의 tx 총건수가 **마지막 메시지 값이 아니라 누적 합**으로 표시.
- [ ] **폴더 드롭 평탄화(`0c6ac1a`)**: 2층 이상 중첩 폴더(파일 수 개 포함)를 `raws/`에 드롭 → 파일이 루트로 승격돼 전부 적재·아카이브, 폴더는 제거. 루트에 동명 파일을 미리 두고 재드롭 → **둘 다 생존**(폴더 쪽이 `상위~하위~파일` 개명 — 덮어쓰기 0건), 개명 로그 확인.
- [ ] **평탄화 — 잠긴 파일 가지 보존**: 폴더 내 파일 하나를 다른 프로세스로 잠근 채 드롭 → 나머지는 승격·적재되고 **잠긴 파일과 그 폴더 가지는 삭제되지 않고 남으며** warning 로그, 잠금 해제 후 300s 주기 스윕이 잔여분을 마저 처리. (내용물 있는 폴더가 지워졌다면 rmdir-only 계약 위반 — 즉시 결함.)
- [ ] **평탄화 — 토글 오프 핫 반영**: `ingestion_settings.json`에 `"flatten_nested_dirs": false` → **재기동 없이** 다음 폴더 드롭부터 종전 동작(폴더 무시)으로 복귀, `true` 복원 시 재개.
- [ ] **평탄화 — force 토큰 조작 금지**: `force`라는 이름의 폴더에 평범한 파일을 넣어 드롭 → 개명 결과에 `__force__` 토큰이 **합성되지 않아** dedup skip이 정상 동작(파일명 자체에 사용자가 적은 `__force__`는 유지).
- [ ] **맵 메타 자동 등록 — 양방향 토글(M3 `ab6ac02`)** 🎯: `auto_register_map_meta: true`(기본)에서 **새 맵 키**를 파일로 적재 → 맵 에디터에서 그 키를 열면 **좌표계 선택 모달 없이** 바로 열린다(메타가 생겼다는 관찰 가능한 증거). `false`로 바꾸고 또 다른 새 키를 적재 → **모달이 돌아온다**. ⚠️ **이 점검이 성립하려면 등록된 행의 `grid_start_x/y`가 실제로 읽혀야 한다**(`98b48e9` — 행이 있어도 START를 못 읽으면 모달이 뜨는 것이 정답이므로, 「모달이 떴다」만으로 자동 등록이 꺼졌다고 판정하면 오진이다. `wafer_map_metadata` 행을 함께 볼 것). 체인 워커 경로(체인 룰 타깃이 맵 테이블)도 같은 결과인지 별도로 확인 — 양쪽에 훅이 붙어 있다.
- [ ] **맵 메타 자동 등록 — absent-only 불변식(M3)** 🔴: 에디터에서 회전·물리 규격을 **손으로 등록/수정한** 맵 키에 같은 키의 데이터를 다시 적재 → **메타가 절대 바뀌지 않아야 한다**(사용자 등록이 정본, 생성 소스는 `auto_map_meta` = 최하위 우선순위). 자동 생성된 메타를 나중에 사용자가 고치면 그 편집이 이긴다. 그리고 **`wafer_map_metadata` 자신에 적재해도 자기 등록이 유발되지 않는다**(재귀 가드).
- [ ] **맵 메타 자동 등록 — 실패 격리·비용(M3)**: 메타 등록이 실패하도록 만들어도(예: 메타 테이블 권한 회수) **파일/체인 적재 자체는 정상 완료**되고 로그만 남는다. 대량 적재 시 존재 확인이 **행마다가 아니라 distinct 키당 1회**인지 쿼리 로그로 확인(같은 맵 재적재는 추가 쿼리 0회 — 프로세스 수명 캐시).

#### 버전 게이트 (`092b83f`) 🎯 — ⚠️ **선언한 테이블이 없어 점검자가 먼저 켜야 합니다**

> **준비.** 재투입해도 안전한 테이블 하나를 골라 **§7.2의 확인 한 줄**([config/table_config](../guide/config/table_config.md))을 먼저 돌리고 — **`chain`·`enrich` 둘 다 `none`인 테이블**을 고르십시오 — `table_config.json`에 `"version_column": "<버전컬럼>"`을 추가합니다. 점검이 끝나면 그 줄을 **지웁니다**(§7.8: 데이터 모양을 안 바꾸므로 즉시 원복).

- [ ] 🔴 **사람의 교정이 더 높은 버전에 밀리지 않을 것** (이 기능의 **상위 제약**): 버전 N으로 적재 → 그리드에서 셀 하나를 고침 → **버전 N+1**로 같은 키를 적재. **고친 셀은 사람 값 그대로**이고 **손대지 않은 셀만 앞으로 나아가야** 합니다. 사람 값이 기계 값으로 바뀌면 **즉시 결함**입니다(행 전체가 얼어붙는 것도 결함 — 나머지 셀은 갱신돼야 합니다).
- [ ] **낮은 버전은 막히고, 높은 버전은 들어올 것**: 버전 5 적재 → 버전 3 재투입 → **값 불변** + 워커 로그에 `[VersionGate] ... 'version_older' ...` WARNING 1줄 + 배치 INFO 1줄. 이어서 버전 7 투입 → 반영. **거절된 행이 반쯤 갱신돼 있으면 결함**입니다(어느 컬럼도 움직이면 안 됩니다 — 이력 타임라인에 그 tx가 없어야 합니다).
- [ ] **게이트를 건 테이블도 사람에게는 계속 편집 가능할 것**: 그 테이블의 셀을 그리드에서 편집 → 정상 저장되고 **`[VersionGate]` 줄이 한 줄도 남지 않아야** 합니다(`user` 소스는 게이트에 닿지 않습니다). 편집이 거절되면 결함입니다.
- [ ] **선언을 지우면 즉시 종전 동작**: `version_column` 줄 삭제 → watcher 반영(약 1초) → 낮은 버전 재투입이 다시 반영됨. 재기동·마이그레이션 없이 되돌아가야 합니다.

### 2.6 Auto-Update

- [ ] **크론 실행**: `# schedule: */5 * * * *` 스크립트 배치 → 주기 도래 시 `raws/`에 CSV 생성 → 인제션까지 연쇄 완료.
- [ ] **핫 리로드 에지**: 스크립트의 schedule 주석 변경 → 재기동 없이 다음 실행 타이밍이 변경(스케줄러 로그 확인).
- [ ] **즉시 실행**: 어드민 AutoUpdate 탭에서 run-now → 즉시 수집·드롭·적재.
- [ ] **Active 토글**: AutoUpdate 탭에서 수집기 Active 스위치 OFF → 다음 주기에 실행되지 않고 상태가 SKIPPED(next_run은 전진), 행 dim 표시 + Overview 카드 active/total 감소. **OFF 상태에서도 run-now는 실행됨**(툴팁 확인). ON 복귀 → 다음 주기 정상 실행 1회(밀린 주기 몰아 실행 없음). 재기동 없이 전 과정 핫 반영.
- [ ] **토글 에지 — 제어 파일 부재**: `config/auto_update_control.json` 삭제 후 status 조회 → 전 수집기 active(fail-open), 에러 없음.
- [ ] **[2026-07-27] 헬퍼 함수 수집기**: 헬퍼를 **다른 함수 안에서** 호출하는 스크립트(`def a(): ...` / `def b(): return a()` / `out = b()`) 배치 → 주기 도래 시 CSV 정상 생성. (모듈 레벨 호출은 결함 축이 아니므로 반드시 함수 안에서 호출할 것.)
- [ ] **[2026-07-27] 실패는 실패로**: 예외를 던지는 수집기 배치 → 어드민 AutoUpdate 탭 상태가 **FAIL**, `last_error`에 트레이스백 노출. "Skipping file generation" 후 SUCCESS로 끝나지 않는지 확인.
- [ ] **[2026-07-27] print 수집기 회귀**: `out` 없이 `print(...)`만 하는 수집기 → 여전히 stdout 폴백으로 CSV 생성, 로그에 **ERROR 없음**.
- [ ] **[2026-07-27] `sys.exit(0)` 격리**: `out` 설정 후 `sys.exit(0)`으로 끝나는 수집기 → CSV 정상 생성 + **스케줄러 데몬이 죽지 않음**(이후 주기 계속 동작, `/health` 스케줄러 하트비트 유지).
- [ ] **[2026-07-27] `out = None`은 실패**: fetch 실패 시 `out = None`을 대입하는 수집기(예: `bonding_map/fetch_data.py`의 네트워크를 끊고 실행) → 어드민 상태 **FAIL** + `last_error`에 사유. **스크립트가 재실행되지 않는지**(외부 API 2차 호출 없음) 스크립트 자체 로그/카운터로 확인. `SUCCESS`로 끝나면 회귀.
- [ ] **[2026-07-27] 0건 관용구**: `out = []` / `out = ""` 수집기 → 파일 미생성이지만 **SUCCESS**(실패로 뒤집히지 않았는지 확인).
- [ ] **[2026-07-27] 부작용 2회 실행**: 실행 횟수를 파일에 기록하는 print 수집기(`out` 미사용, 헬퍼 함수 포함) 1주기 → 카운터 **2 증가**가 정상임을 확인. ack POST·커서 전진형 수집기는 `out` 방식으로 이전해야 함을 경고.

### 2.7 체인 인제션 + 실시간 SLO

- [ ] **파생 정상**: 원본 테이블(스모크: `production_plan`)에 행 인제션/편집 → 파생 테이블(`line_model_registry`)에 규칙대로 파생 행 생성/갱신.
- [ ] 🎯 **SLO 100ms**: 원본 편집 커밋 → 파생 반영 WS 통지까지 워커 `[Latency]` 로그 기준 100ms 이내(정상 상태 기대치 ~31ms). 재기동 직후 첫 체인은 ~600ms까지 허용(웜업 잔여, 알려짐).
- [ ] 🎯 **순환 차단**: 파생 테이블 갱신이 다시 체인을 트리거하지 않음(워커 로그에 재귀 처리 없음, outbox 무한 증가 없음).
- [ ] **멱등성 — 체인 재실행**: 동일 원본 재드롭 → 파생 테이블 행 수 불변, count류 집계값 정확(중복 가산 없음).
- [ ] **실패 격리 에지**: 맵퍼 예외를 유발하는 그룹 발생 시 해당 그룹만 실패(어드민 Chain 탭 outbox FAILED)하고 이후 정상 그룹은 계속 처리됨.
- [ ] **대형 tx 통지 비동결(인시던트 `cc57b64` 회귀)**: 수만 행 파일 재인제션 등 대형 tx 발생 시 :8080이 동결되지 않고(`[Latency] notify=` 정상), 히스토리 패널 트랜잭션 총계는 실건수(`total_log_count`) 표기 — 로그 항목 자체는 500건까지만 보존(부분 보존이 정상). ⚠️ 알려진 잔여: 멀티 target-table tx 총계 과소(이슈 #10, D-1).

**축약 아웃박스 (2026-08-07 OUTBOX-④)** — 대량 인제션 이벤트가 값을 싣지 않고 `row_ids`를 지목한다. 상세는 [architecture/event_driven_backend §2.4](../architecture/event_driven_backend.md).

- [ ] 🎯 **파일 인제션은 축약된다**: 1,000행 파일 드롭 → `database_outbox`에 그 tx의 행이 **1건**(`payload`에 `row_ids`/`row_count`가 있고 `data`가 **없다**). 🔴 1,000건이면 회귀다(opt-in이 안 걸린 것).
- [ ] 🎯 **사람 경로는 축약되지 않는다**: 그리드 셀 편집·맵 Push → 그 tx의 outbox 행이 **행마다 1건**이고 `data`를 나른다. 🔴 **여기가 축약되면 즉시 NO-GO다** — 기본값이 `per_row`인 이유이고, 화면에 못 닿는 교정은 교정 루프를 끊는다(핵심가치 #3).
- [ ] **파생은 그대로 난다**: 축약된 원본 인제션 뒤에도 파생 테이블이 규칙대로 채워진다(체인 워커가 본 테이블을 다시 읽어 매퍼에 같은 중첩 payload를 준다). 사용자 맵퍼(`server/mappers/`)를 고치지 않았는데 값이 비면 회귀다.
- [ ] ⚰️ **[2026-08-14 `2ec78b9`] 이 항목은 «점검 대상이 아닙니다»** — 그래프 승격이 은퇴하고 저장소가 DROP됐습니다. 🔴 **다만 이 항목이 검증하던 «진짜 성질」은 남습니다**: 축약 이벤트의 `updated_by`가 서로 다른 주체(워처/체인)를 섞지 않는가 — 그 성질은 이제 체인 워커 쪽에서 확인하십시오. ~~**그래프도 그대로 승격된다**: 축약 이벤트로 들어온 행들이 `graph_nodes`/`graph_edges`에 나타나고,~~ 엣지의 `updated_by`가 **그 행을 쓴 주체**다. 🔴 서로 다른 두 주체(워처/체인)가 같은 테이블에 연달아 쓴 뒤 **뒤쪽 행들이 앞쪽 주체 이름을 달고 있으면 회귀다**(조용한 결함 — 아무것도 실패하지 않는다).
- [ ] **실패는 청크째 격리되지 않는다**: 맵퍼 예외를 유발하는 행 하나를 포함한 축약 청크 → 3회 재시도 후 부모가 FAILED가 되고 `error_log.reexpanded_into`가 행 수를 적으며, `<tx>#row#` id를 가진 per-row 이벤트들이 PENDING으로 생긴다. 이어서 **문제 행 하나만** FAILED로 남고 나머지는 성공한다.
- [ ] **재시도 버튼이 outbox를 불리지 않는다**: 이미 재확장된 FAILED 부모에 `/admin/outbox/retry-failed`를 눌러도 `skipped_reexpanded`가 응답에 오고 **outbox 행 수가 늘지 않는다.** 🔴 늘면 클릭마다 1,000배다.

**브로드캐스트 복구 (2026-08-04 `2aab7e2`)** — 허브가 몇 초 깜박이는 것만으로 통지가 영구 유실되던 자리.

- [ ] 🎯 **허브를 잠깐 내리고 파일을 드롭한다**(웹서버만 정지, 워처는 살려 둔 채) → 워처 로그에 실패가 남고, **`database_outbox`에 `event_type='BROADCAST_RECOVERY'` 행**이 생긴다(`processed_chain=true` · `status='SUCCESS'` · `broadcast_at IS NULL`). 허브를 되살리면 **5초 안에** 그 행이 확정되고 화면이 갱신된다. 🔴 **마커가 안 생기면 회귀다** — 그것이 「로그하고 버렸다」의 모양이다.
- [ ] **마커는 작다**: 그 행의 `payload` 키가 **정확히 `{endpoint, reason, marker}`**이고 실패한 통지의 페이로드가 **복사돼 있지 않다.** 🔴 batch-refresh 페이로드는 감사 로그 500건까지 나르므로, 복사하는 순간 복구 경로가 다음 인시던트가 된다(2026-07-25, 약 50 MB).
- [ ] 🎯 **규칙에 안 걸리는 미전달 행도 발사된다**: 체인 규칙의 트리거가 **아닌** 테이블에 미전달 행을 만든다 → 스윕이 **그 테이블 이름으로** `batch_refresh_required`를 쏜다. 🔴 **아무것도 안 쏘고 `broadcast_at`만 찍히면 회귀다** — 그것이 복구 스윕이 복구 대상을 조용히 소각하던 모양이다. 발사 집합은 `체인 타깃 ∪ 미전달 행이 기록된 테이블`이다.
- [ ] **스윕이 자기를 물지 않는다**: 위 상태에서 스윕을 5회 더 돌려도 **발사 수가 늘지 않는다**(무한 스윕을 막는 것은 「발사 안 함」이 아니라 「확정을 찍는 것」).
- [ ] **테이블당 한 번**: 한 테이블에 미전달 행 200건 → 발사는 **1건**.
- [ ] **실패하면 확정하지 않는다**: 통지가 실패하는 상태에서 스윕 → `broadcast_at`이 **전부 NULL로 남는다**. 이후 정상 상태의 스윕이 확정한다.
- [ ] **마커는 데이터 변경으로 읽히지 않는다**: `BROADCAST_RECOVERY`가 `CONTROL_EVENT_TYPES`에 있어 **체인 큐가 건너뛰고**, `CREATE`/`EDIT`/`DELETE`가 아니라 **그래프 승격도 건너뛴다**.
- [ ] **마커를 못 써도 인제션은 안 죽는다**: DB 쓰기가 실패하는 상황을 만들어도 워처가 살아 있고, ERROR 한 줄(「그 통지는 이제 복구 불가」)만 남는다.

### 2.8 Enrichment Queue

- [ ] **워크리스트 정상**: 원본 인제션(결손 target 포함) → `/enrichment.html` → 규칙 선택 → 결손 판단키만 목록에 표시(dedup — 원본 5행 → 유니크 3행 등 압축 확인).
- [ ] **컨베이어 저장**: 항목 선택 → target 입력 → Enter → 저장 + 자동으로 다음 항목 포커스. 채운 항목은 워크리스트에서 사라짐.
- [ ] **참조뷰**: 항목 선택 시 참조 탭에 판단키 기반 조회 결과 표시. 빠르게 항목을 연속 이동해도 이전 항목의 참조 결과가 뒤늦게 덮어쓰지 않음(stale 가드).
- [ ] **참조뷰 에지 — 오류 상태**: 참조뷰 파라미터 불충분/규칙 부재 시 로딩/빈/오류 상태 UI가 구분 표시(빈 화면 방치 금지).
- [ ] **결손 배지**: 메인 그리드에서 파생 테이블 선택 → "🧩 결손 N건" 배지 표시, N이 워크리스트 잔여와 일치. 클릭 → 해당 규칙 컨베이어로 진입. 규칙 API 부재 환경에서는 배지 무음 비활성.
- [ ] 🎯 **레이어링 보존**: 컨베이어로 채운 값 위에 원본 재드롭(체인 dedup 재실행) → 사람 값 유지(user > chain_ingestion).
- [ ] 🎯 **① 자동 확정 — 양방향 토글**: 규칙의 뷰에 `candidate_for`를 선언하고 `auto_confirm: true` → 후보가 1개인 판단키의 새 원본을 적재하면 target이 **자동으로 채워져 워크리스트에서 빠진다**. `auto_confirm`을 `false`로 바꾸고 다른 새 키를 적재 → **빈 채로 워크리스트에 남는다**(꺼짐/켜짐의 관찰 지점).
- [ ] 🎯 **① 모호는 자동 확정하지 않는다**: 같은 판단키에 후보가 2개인 키는 노브가 켜져 있어도 **빈 채로 큐에 남는다**(선언한 뷰를 하나 더 늘려 일부러 모호하게 만들어 확인 — 자동 확정이 판단을 대신하지 않는다는 증거).
- [ ] **① 사람이 지운 값은 재확정하지 않는다**: 자동 확정된 셀을 사람이 **비우면** 표시는 blank가 되어 큐에 돌아오지만, 그 셀은 provenance가 있어 **다시 자동 확정되지 않는다**(`cell_has_provenance`).
- [ ] **① 켜기 전 측정**: `enrichment_insights.py confirm <규칙> --ignore-knob` → 아무것도 쓰지 않고 「몇 건이 사람 없이 해소되는가」가 나온다. 실행 후 DB가 변하지 않았는지 확인.
- [ ] 🎯 **① 뷰의 `limit`이 후보 판정을 자르지 않는다** (F9, 2026-07-30): 선언한 뷰의 `limit`을 2로 낮추고, 같은 판단키에 대해 **3번째 행이 다른 값**을 갖도록 참조 데이터를 만든다 → 판정은 `single`이 아니라 **`ambiguous`**여야 한다. (수리 전에는 상한 밖의 모순이 보이지 않아 `single`로 자동 확정됐다. 실측: `공정 이력` 뷰가 `limit: 50`인데 키당 69~217행이었다.)
- [ ] **① `support`는 전 결과의 건수**: 같은 값이 5행 있고 뷰 `limit`이 2여도 확정 결과의 `support`는 **5**다(표시 상한이 아니라 실제 근거 수).
- [ ] **④ 분류 수치의 정합**: `classify <규칙>`의 분류 합계 = `queue_size` = 워크리스트 잔여 건수(= 배지 N). 어긋나면 큐 술어(`queue_filters`)가 갈린 것이다. **[2026-08-04] `classify`는 빈 판단키 행까지 걷는 유일한 분석**이고 그것들을 `blank_decision_key`로 센다 — 그 몫을 빼고 세면 정확히 「판단키 없음 N건」만큼 어긋난다.
- [ ] 🎯 **빈 판단키 행: 보이고 · 이름 붙고 · 쓰기 경로엔 안 들어간다** (N36, 2026-08-04): 판단키가 빈 파생 행을 만든다(그리드 빈 행 추가 또는 target 인접 셀만 직접 편집) → ⓐ 워크리스트에 **뜬다**(종전엔 숨겨졌다) ⓑ 목록 **맨 뒤**에 있다(처리 가능한 행이 앞을 차지한다) ⓒ 헤더에 **「판단키 없음 N건」** 배지가 그 수만큼 뜬다 ⓓ 선택하면 참조뷰가 "근거 데이터 없음"이 아니라 **"판단키 없음 - 조회 불가"**라고 답한다(두 사실은 다르다) ⓔ **진행률이 100%가 아니다** - 미답 행이 남아 있으면 막대도 그렇게 읽혀야 한다 ⓕ **[2026-08-05 재정으로 뒤집힘]** `enrichment_insights.py confirm <규칙> --apply`를 돌리면 **남은 키로 판단이 되는 행은 채워진다**(자동 확정은 이제 `queue_filters` = 큐 전체를 걷는다). 채워진 셀의 `priority_source`는 **`enrichment_auto_confirm_partial_key`**여야 한다 - 평범한 자동확정과 이름이 같으면 나중에 골라낼 수 없다. **판단키가 전부 빈 행은 그대로 비어 있어야 한다**(`no_decision_key`), 그리고 빈 컬럼을 바인드하는 뷰밖에 없는 규칙도 그대로다(`missing_bind`).
- [ ] **② 제안은 config를 쓰지 않는다**: `propose <규칙>` 실행 전후로 `enrichment_rules.json`이 **바이트 단위로 동일**해야 한다. 제안된 `reference_views` 항목을 사람이 붙여넣으면 ①이 그것을 실행한다.
- [ ] 🎯 **참조 질의 실패가 세션을 죽이지 않는다** (`f9289f6`, Postgres에서만 재현): 어느 뷰의 `query`에 없는 컬럼을 넣어 일부러 실패시킨 뒤 **같은 요청 안에서 다음 조회가 정상 동작**하는지 본다(SAVEPOINT 격리). 회귀하면 증상이 조용하다 — 체인 워커의 부기 커밋이 무산되어 **그룹이 영원히 재처리**되면서도 실패로 보고되지 않는다(재시도 격리 카운터도 안 오른다).
- [ ] **집계 절단은 거절이다**: 뷰 `limit`을 1로 두고 같은 판단키에 서로 다른 값이 2종 이상 있게 만든다 → 자동 확정이 아니라 **`distinct_truncated`** 거절이어야 한다. (「>limit이면 어차피 `ambiguous`가 잡는다」는 틀렸다 — 잘려 온 값들이 공백·소수점 차이로 하나로 **접히면** `single`이 된다.)

> 📍 **선언의 효과 조회(F9)는 §2.8-ter에 있습니다** — config 도메인 일반의 점검이라 Enrichment 절 안이 아니라 **§2.8-bis 다음**이 자리입니다.

### 2.8-bis Chain Replay (R1 재적용 / R2 stale 소스 철회)

- [ ] **R1 dry-run은 쓰지 않는다**: `chain_replay_cli.py replay <룰>` → 보고만 나오고 타깃 테이블 행수·값이 변하지 않는다. 보고에 **`cells a human protects`** 수치가 함께 나온다.
- [ ] 🎯 **R1은 사람 값을 못 덮는다**: 타깃 셀을 사람이 편집한 뒤 `replay <룰> --apply` → **표시값이 그대로**다. 셀 이력/소스에는 `chain_ingestion` 레이어가 추가되지만 `user`(priority 0)가 계속 이긴다.
- [ ] 🎯 **R1은 빈 값을 쓰지 않는다**: 룰이 어떤 셀에 값을 더는 만들지 않으면 그 셀은 **기존 값이 유지**되고 보고에 **철회 후보**로 뜬다(빈 값 덮어쓰기 금지 — 그 진술은 R2의 것).
- [ ] **R1 자기 트리거 종료**: `trigger_table == target_table`인 룰(현 config의 `inv`)을 `replay --apply` → **시작 시점 행수만 스캔**하고 끝난다(자기 산출물을 다시 읽지 않는다). 보고에 `SELF-TRIGGERING` 표기.
- [ ] **R1 재적용 순서**: `chain_replay_cli.py list` → 생산자(`→ inventory_master`)가 소비자보다 먼저 나온다. `replay-all`은 각 룰을 **정확히 1회**만 실행.
- [ ] 🎯 **R2는 구멍을 남기지 않는다**: 셀에 소스가 둘인 상태(예: `pipeline_parser` + `custom_script`)에서 상위 소스를 `withdraw <테이블> <소스> --columns <컬럼> --apply` → **아래 레이어의 값이 드러난다**(빈칸이 되지 않는다).
- [ ] 🎯 **R2는 사람 값을 못 지운다**: `withdraw <테이블> user` → **거부**(에러 메시지가 이유를 말한다). 사람이 `manual_priority_source`로 핀한 셀은 `pinned_skipped`로 건너뛴다.
- [ ] **R2 철회는 무음이 아니다**: 값이 바뀐 셀을 그리드에서 눌러 **셀 이력 타임라인**에 `chain_replay_withdraw` / `withdraw:<소스명>` 항목이 보이는지 확인(빈칸이 데이터 유실과 구별되는 유일한 근거).
- [ ] **R2 범위**: `--columns`로 지정하지 않은 컬럼은 **손대지 않는다**. 선언되지 않은 컬럼명을 주면 거부.

### 2.8-ter 「내가 켠 config가 먹었나」 — 선언의 효과 조회 (F9, 2026-07-30)

> ✅ **화면이 착지했습니다**(2026-07-31 `93610cb` — 어드민 **Overview 탭의 세 번째 계기 줄**). 아래 「나온다」는 **응답 JSON과 그 화면 둘 다에** 나온다는 뜻이고, 둘이 갈리면 그것 자체가 결함입니다(계약: **문장은 서버가 만들고 클라는 그대로 렌더**).
> - **화면으로 점검하는 것이 1차**입니다. `curl`은 「화면이 지어낸 문장인가」를 가르는 대조용으로만 쓰십시오 — 화면에 있는 문장은 `curl` 응답의 `detail`에 **글자 그대로** 있어야 합니다.
> - ⚠️ **읽기 실패는 「설정이 멀쩡하다」가 아닙니다** — 대시(―)와 사유가 남습니다. 그 사유 다섯 갈래는 **§2.8-quater**에서 따로 점검합니다.
> 📍 이 절은 `enrichment` 도메인을 재료로 쓰지만 **점검 대상은 config 도메인 일반의 틀**입니다(도메인이 늘어도 응답 모양과 어휘는 그대로). 그래서 §2.8 안이 아니라 여기에 있습니다.

- [ ] 🎯 **켰는데 아무 일도 안 하는 상태가 응답에 나온다**: 규칙에 `auto_confirm: true`만 켜고 **`candidate_for`는 선언하지 않은 채** `GET /admin/config/resolve` → 그 규칙이 **`ineffective`**에 사유 **`not_declared`**로 나오고, 설명 문장이 「어떤 참조뷰도 candidate_for를 선언하지 않아 아무 효과가 없습니다」라고 말한다. (수리 전에는 데몬 로그 한 줄이 유일한 목격자였고, **라이브가 정확히 이 상태였다**.)
- [ ] **선언하면 `effective`로 옮겨간다**: 뷰에 `candidate_for`를 선언하고 리로드 → 같은 규칙이 `effective`로 이동하고 `ineffective`에서 사라진다(양방향 관찰 지점).
- [ ] 🎯 **함정이 켜기 전에 보인다**: 판단키가 (lot, slot)인데 **lot만으로 조회하는 뷰**에 `candidate_for`를 선언 → `effective`이되 경고 **`scope_unresolved`**가 붙고, 설명이 **구별하지 못하는 키 이름(slot)**을 지목한다. ⚠️ 이 경우 실행 중에는 아무 경고가 없다 — 결과가 `ambiguous`가 아니라 `single`로 나오기 때문이다(그 lot의 이력 행이 하나면 그 값이 전 슬롯에 쓰인다).
- [ ] **오타/타입 오류는 `rejected`**: `auto_confirm: "true"`(문자열)로 저장 → `rejected`에 사유 `mapping_unavailable`과 무시된 원값이 나온다. 규칙은 OFF로 동작한다.
- [ ] **전역 스위치가 꺼지면 `not_reached`**: `ingestion_settings.json`에 `enrichment_auto_confirm_enabled: false` → 규칙 선언이 완전해도 `ineffective` + `not_reached`(「선언이 없다」와 구별된다).
- [ ] **설정값이 어디서 왔는지 말한다**: `settings`에 전역 스위치와 `enrichment_auto_confirm_max_keys`의 **실효값 + 읽은 파일 경로**가 나온다. `ingestion_settings.json`이 **없으면** `origin: "default"`이고 소스 항목이 `exists: false`로 나온다(파일 부재는 오류가 아니다).
- [ ] 🎯 **`detail`은 운영자가 읽는 최종 문자열이다** (INV-F9-8, `f9289f6`): 위 사유들의 `detail`에 **Python repr**(`['slot']을(를)`)이나 **리터럴 마크다운**(`**…**`)이 섞여 있으면 결함이다. 클라가 자기 문장을 짓는 것이 금지돼 있어 **하류에 고칠 자리가 없다.** 되비추는 값은 운영자가 편집한 파일의 문법인 **JSON**으로 적힌다(JSON `true`는 `'true'`가 아니다).
- [ ] **드라이런이 숫자를 준다**: `GET /admin/enrichment/auto-confirm/dry-run?rule=<규칙>` → 「큐 N건 중 M건 확정 가능」. **쓰기는 일어나지 않는다**(실행 전후 DB 비교). 노브가 꺼져 있어도 측정된다.
- [ ] **드라이런에 쓰기 경로가 없다**: URL에 `apply=true`를 붙여도 아무 것도 쓰이지 않는다(파라미터 자체가 없다 — 쓰기는 CLI뿐).
- [ ] **선언이 없으면 500이 아니다**: `candidate_for` 없는 규칙에 드라이런 → 200 + `refused_reason: "not_declared"` (해석 보고서와 **같은 단어**).
- [ ] **클라가 사유 단어를 적어 두지 않는다**: `node contracts/config_resolve_report/client_harness.mjs` → INV-F9-7 초록(`client2/src` 전역에 사유 4단어가 **소스 리터럴로** 0건).
- [ ] 🎯 **INV-F9-4가 이제 실행 채점된다**(2026-07-31 — 종전 `PENDING`): 같은 하네스가 `config_resolve_view.js`를 **임포트해** 벡터 페이로드를 먹이고, 나오는 문자열 전부를 출처(`server`/`value`/`chrome`/`count`)로 채점한다. **`PENDING` 표기가 다시 나타나면 뷰 모델이 DOM 빌더 안으로 되돌아간 것**이다.

**세 번째 도메인 `binding` — 키를 지우면 상속한다 (2026-08-11 `68db020`)**

> `resolve_binding`(서버가 x/y/val/key_columns를 어디서 가져오는지 판정하는 함수)이 `table_config`의 값을 **관례로 조용히 대체**하던 것을 그만두고, 이제 `GET /admin/config/resolve?domain=binding`로 **키마다** 판정을 답한다. 우선순위는 **로컬 선언 > table_config 파생 > 이름으로 거절**이고, 관례 폴백(`or ["lot", "slot"]`류)은 삭제됐다.

- [ ] 🎯 **키를 지우면 상속이지 관례가 아니다**: `core_wafer_map`의 `key_columns` 선언을 지우고 `GET /admin/config/resolve?domain=binding` → 그 테이블의 `key_columns`가 **`table_config`에서 유도된 값**(`["wafer_id"]`)으로 나오고 origin이 `inherited`여야 한다. (수리 전에는 **은퇴한 관례값** `["lot","slot"]`이 아무 사유 없이 조용히 나갔다.)
- [ ] 🎯 **존재하지 않는 컬럼을 가리키면 거절이지 통과가 아니다**: `dt_log.x`를 존재하지 않는 컬럼명으로 선언 → `binding` 도메인 응답이 `x: refused`와 함께 테이블·키·컬럼명을 지목하는 서버 로그 줄을 남긴다(수리 전에는 존재하지 않는 컬럼이 그대로 바인딩에 들어갔다).
- [ ] **`val`은 상속하지 않는다**: 좌표 블록이 선언돼 있는데 `val`만 뺀 테이블은 `val: absent`로 남아야 한다(상속하면 "이 맵은 값이 없다"는 선언이 값 컬럼을 얻어 occupancy 맵이 value 맵으로 뒤집힌다) — `test_map_alignment_columns`가 이 축을 고정한다.
- [ ] **19/19 라이브 테이블이 그대로다**: 이미 완전히 선언된 테이블은 이 변경으로 `resolve_binding`/`resolve_binding_info` 응답이 **한 글자도** 안 움직여야 한다(회귀는 여기서 난다 — 파생 로직이 선언보다 먼저 평가되면 기존 선언이 조용히 밀린다).
- [ ] **`binding` 도메인이 응답의 `domains` 배열에서 마지막이다**: `contracts/config_resolve_report`가 `domains[0]`을 `enrichment`로 핀하므로, `binding`을 앞이나 중간에 등록하면 그 계약 하네스가 죽는다.

**표기 정규화 — 선언과 「무엇이 합쳐지는가」는 다른 질문이다 (2026-08-04 `8d306a5`)**

> 🔴 **`92b8d6f`의 파생 컬럼(`<컬럼>_norm`) 모델은 철회됐습니다.** 그리드에서 파생 컬럼을 찾거나 `server/scripts/rederive_notation_norm.py`를 돌리려 하면 **둘 다 없습니다.** 지금 확인할 것은 **저장되는 것이 없다**는 사실과 **비교의 양쪽이 접힌다**는 사실입니다.

- [ ] **선언은 한 줄이다**: `notation_rules.json`에 `{"columns": {"dt_log": {"core_lot": true}}}` → `GET /admin/config/resolve?domain=notation`이 `effective` 1건. `table_config.json`에 **아무것도 추가하지 않았는데** 유효해야 한다(추가가 필요하다고 나오면 옛 모델이 살아 있는 것).
- [ ] 🎯 **아무것도 저장되지 않는다**: 선언 전후로 그 테이블의 **컬럼 목록이 동일**하고(`information_schema`), 어떤 행의 값도 바뀌지 않는다. 그리드에 새 컬럼이 뜨면 회귀다.
- [ ] 🎯 **무엇이 합쳐지는지는 별도 라우트가 답한다**: `GET /admin/config/notation/preview?table=dt_log&column=core_lot` → **병합군**(한 접힌 값에 원본 표기 둘 이상)과 `variants` 목록. 🔴 원본→접힌값 **나열**만 돌아오면 회귀다(정작 중요한 줄이 나머지에 묻힌다). `table`만 주고 `column`을 빼면 **400**, 둘 다 빼면 **선언된 전 컬럼**.
- [ ] **미리보기는 조인이 쓰는 그 식으로 계산된다**: 파이썬에서 접은 값을 보여 주면, 운영자가 신뢰하는 화면이 조인이 쓰지 않는 답을 보여 주게 된다(그 자체가 이 기능이 없애려는 문제다).
- [ ] **`number` 컬럼은 거절된다**: `"number"`로 선언된 컬럼을 지목 → `rejected` + `not_text`. `zero_pad: true`는 `zero_pad_unimplemented`로 거절되되 **나머지 선언은 살아 있어야** 한다.
- [ ] **옛 문법은 이름 붙여 거절된다**: `{"core_lot": "core_lot_norm"}`(문자열 = 파생 컬럼) → `rejected` + `'derived' is no longer a thing …`. 조용히 무시되면 회귀다.
- [ ] 🎯 **한쪽만 선언해도 조인은 양쪽이 접힌다**: `dt_log.core_lot`만 선언하고 `core_wafer_map.core_lot`은 선언하지 않은 채 두 테이블 가상 조인 → `GET /admin/config/virtual-join/verify`의 `folded_join_key`가 **그 키를 접는 것으로** 보고한다. 🔴 **한쪽만 접히면 이미 맞고 있던 매치를 조용히 잃는다** — 그래서 한쪽만 접을 수 있는 경로가 있으면 그 자체가 회귀다.
- [ ] 🎯 **접힌 키는 함수 인덱스를 요구한다**: 위 상태에서 오른쪽에 **평범한 컬럼 UNIQUE만** 있으면 선언이 `no_unique_index`로 **거부**되고, 응답이 주는 DDL이 **함수 인덱스**(이름에 `_nf`)여야 한다. 🔴 **평범한 UNIQUE로 통과하면 회귀다** — 성능이 아니라 정확성 문제다(원본으로 다른 두 행이 접히면 한 값이라 팬아웃이 열린다).
- [ ] **파일이 없거나 깨져도 조회가 죽지 않는다**: 파일 삭제 → `선언 파일이 없습니다 …`, JSON 문법 오류 → `선언 파일을 읽지 못했습니다 …`. 두 경우 모두 조회는 **원본 비교로** 정상 동작한다(이 기능이 생기기 전과 같은 동작).

### 2.8-quater 조회가 실패했을 때 화면이 무엇을 말하는가 (F9 후속 · `1dc761b` + `cde3398` · 2026-07-31)

> 🔴 **점검 이유:** 종전에는 무엇이 잘못됐든 `조회 실패` 한 마디였습니다. 그 다섯 갈래는 **운영자의 손을 서로 다른 곳으로 보냅니다** — 뭉개면 엉뚱한 것을 고치러 갑니다.
> ⚠️ **이 절은 「설정이 멀쩡한가」를 묻지 않습니다.** 실패는 대시(―)와 사유를 남기고 **자동으로 펼치지 않습니다**(muted 톤 · 토스트·모달 없음). 화면이 침묵하면 그것이 회귀입니다.

| 상황 | 화면이 말해야 하는 것 | 운영자의 손이 가야 할 곳 |
|---|---|---|
| 응답 자체가 없음 | `서버에 연결할 수 없습니다 ― 서버가 실행 중인지 확인하세요` | 서버 프로세스 |
| `404` | `실행 중인 서버가 구버전입니다 ― 서버를 재시작하세요` | **배포** (서버가 「나에게 그 라우트가 없다」고 답한 것) |
| `401`·`403` **+ `WWW-Authenticate: X-Admin-Token`** | `관리자 토큰이 거부되었습니다 ― 새로고침 후 다시 입력하세요` | 토큰 |
| `401`·`403` **그 헤더 없이** | `관리자 게이트가 아닌 응답입니다 ― 프록시 등 앞단에 …` | **이 포트에 무엇이 답하는가** |
| 그 외(5xx 등) | `조회 실패` | 라우트는 있고 깨진 것 — **이것만이 진짜 조회 실패** |

- [ ] 🎯 **401 갈래가 상태코드가 아니라 헤더로 갈린다**: 토큰을 틀리게 넣어 게이트 401을 받는다 → 「관리자 토큰이 거부되었습니다」. 🔴 **`WWW-Authenticate` 없이 401을 내는 것을 앞단에 두고** 같은 조회를 한다 → 「관리자 게이트가 아닌 응답입니다」로 **갈려야 한다.**
  - **왜 이것이 가장 비싼 항목인가**: 포트 앞의 프록시는 **자기** `WWW-Authenticate: Basic realm=…`으로 답하고, 2026-07-30에 정확히 그것이 **인증 실패로 읽혀 오후 하나를 썼습니다**. 판정은 `admin.js`의 `isGateRejection`이고 **재사용이지 재유도가 아닙니다** — 사본이 생기면 두 판정이 갈립니다.
- [ ] 🎯 **vite dev 오리진(`:5173`)에서도 갈린다** (`cde3398`): 🔴 **브라우저는 노출되지 않은 응답 헤더를 교차 출처에서 지웁니다.** `WWW-Authenticate`가 CORS `expose_headers`에 없으면 **진짜 게이트 거부가 「앞단이 답했다」로 확신 있게 잘못 표시**됩니다. `:8080`/`:8081` 직접 서빙(같은 출처)에서는 원래 읽혔으므로 **이 결함은 dev 오리진에서만 보입니다** — 두 오리진에서 각각 확인하십시오.
  - 값에 비밀이 없습니다(원하는 헤더의 **이름**뿐). 노출 목록은 `server/main.py`의 `CORSMiddleware` 한 줄이 정본입니다.
- [ ] **`Server:` 헤더는 증거이지 문장이 아니다**: 앞단이 자기 이름을 대면 사유 문장 **옆에** 붙어 나온다(문장 자체는 고정 `CHROME` 항목 그대로). ⚠️ **`uvicorn`이면 표시되지 않는다** — 우리 서버가 자기 이름을 대는 것은 운영자에게 아무것도 알려 주지 않는다. 길이도 잘린다(의심받는 쪽이 준 입력이므로).
- [ ] 🎯 **실패한 조회는 다시 시도한다**: 서버를 내린 채 화면을 열어 실패를 만들고, 토큰을 새로 넣는다 → **스로틀 창을 기다리지 않고** 즉시 다시 읽는다(토큰 세대가 바뀐 것은 **시계가 아니라 원인**이 바뀐 것). 이어서 서버를 올린다 → 0s/30s/60s로 재시도해 복구된다.
  - 🔴 **회귀 형태**: 실패가 성공과 같은 침묵을 사면(시각을 **읽기 전에** 찍으면) 운영자가 시킨 대로 토큰을 넣고도 화면이 그대로여서 **「해도 안 된다」로 읽힙니다** — 실제로 그렇게 신고됐습니다.

### 2.8-quinquies 소급 적용 어드민 API 🎯 (2026-07-31 `fbc1053`)

> ⚠️ **`77d27d3` 기준 화면이 없습니다 — 이 절은 전부 `curl`입니다.** 라우트 셋이 착지했고 그것을 그리는 클라 코드는 커밋 트리에 없습니다(**화면 작업 진행 중** — 착지하면 이 서두와 §1.8 행을 함께 고치고 화면 항목을 여기 추가합니다).
> **사전 조건**: `ASSY_ADMIN_TOKEN` 설정 + 전체 스택 기동(실행 라우트는 **스케줄러 데몬**이 있어야 실제로 돕니다).
> **점검은 격리 환경(:8081)에서 하십시오** — 이 절의 실행 항목은 **진짜 쓰기**입니다.
> 운영자 절차 전문은 [BACKFILL_GUIDE §7](../guide/BACKFILL_GUIDE.md).

- [ ] **인벤토리에 넷이 다 있다**: `GET /admin/retroactive/operations` → `chain_replay`·`withdraw`·`enrichment_backfill`·`enrichment_confirm`. 각 항목에 `params`·`cli`·`cli_only`가 있다.
- [ ] 🎯 **연산 차이를 응답이 말한다**: 각 항목에 **`deletes`·`restartable`·`commit_granularity`**가 있고, 클라이언트가 확인 문구를 추측하지 않는다.
- [ ] **DB를 건드리지 않는다**: 인벤토리 호출은 config만 읽는다(DB를 내려도 200이면 정상).
- [ ] 🎯 **모든 카운트가 `count_kind`를 함께 준다**: 네 연산 각각 `GET /admin/retroactive/{op}/count` → 응답에 `count_kind`가 있고 값이 `exact`/`sample`/`upper_bound` 중 하나다. 🔴 **수만 있고 종류가 없으면 결함**이다.
  - `sample`이면 `scanned`·`truncated`가 함께 있고, **`detail` 문장이 「표본에 대한 수」라고 말한다.**
  - `upper_bound`면 `extra.why_upper_bound`가 **무엇이 빠졌는지를 말로** 설명한다.
- [ ] **`scan_limit`은 안 훑은 연산에서 `null`이다**: `withdraw` 응답의 `scan_limit`은 요청에 `?scan_limit=500`을 줘도 **`null`**이다. 🔴 요청한 예산을 그대로 되돌려주면 **하지 않은 표본을 했다고 말하는 것**이다.
- [ ] 🎯 **카운트는 쓰지 않는다**: 네 연산 모두 카운트를 두 번씩 돌린 뒤 대상 테이블의 행 수·값·`cell_sources` 건수가 **불변**이다. 🔴 **표시값만 보고 판정하지 마십시오** — R1은 레이어를 쓰고도 사람 값이 이겨 화면이 그대로일 수 있습니다. **`cell_sources`를 보십시오**.
- [ ] **오타는 조용히 무시되지 않는다**: `?rul=foo`처럼 **없는 파라미터 이름**을 주면 **400**이고 메시지가 허용 이름을 말한다. 🔴 조용히 무시되면 「0건」이 정답처럼 보인다.
- [ ] **노브가 꺼진 규칙은 수를 주되 막는다**: `auto_confirm`이 꺼진 규칙으로 `enrichment_confirm/count` → 수는 나오고(**「켜면 무슨 일이 일어나는가」**) `blocked_reason: "auto_confirm_off"`가 함께 온다.
- [ ] 🎯 **실행은 즉시 반환한다**: `POST /admin/retroactive/{op}/run` → **바로** `{"status":"queued","run_id":…}`. 응답이 실행이 끝날 때까지 붙잡혀 있으면 결함이다.
- [ ] 🎯 **실행 중에도 스케줄러가 살아 있다**: 큰 테이블에 실행을 걸고 그동안 `GET /health` → 스케줄러 워커가 **`ok`**다. 🔴 **`wedged`로 떨어지면 결함**이다(실행을 틱 스레드에서 돌린 것 — 버튼 한 번이 감시 표면을 죽인다). 크론 수집기도 그동안 정상 실행된다.
- [ ] **동시 실행은 거절이다**: 하나가 도는 중에 또 `run` → 데몬 로그에 **이미 실행 중이라는 경고**가 남고, 그 아웃박스 행은 **미처리로 남아 다음 틱에 집힌다**(조용히 사라지지 않는다).
- [ ] 🎯 **R2는 어드민을 거쳐도 사람 값을 못 지운다**: `POST .../withdraw/run`에 `{"params":{"table":"…","source":"user"}}` → **400**이고 메시지가 이유를 말한다. 사람이 핀한 셀도 건너뛴다(안전장치는 **라우트가 아니라 `withdraw_source` 안**에 있다).
- [ ] **토큰 미설정이면 실행만 503이다**: `ASSY_ADMIN_TOKEN`을 지우고 재기동 → `operations`·`count`는 **동작**하고 `run`만 **503**.
- [ ] **결과는 데몬 로그에 있다**: 실행 후 스케줄러 로그에 `[Retroactive] run_id=…`가 남고 완료/거절이 구별된다. **트리거 응답에는 결과가 없다**(그 응답만 보고 「됐다」고 결론짓지 말 것).
- [ ] 🔴 **CLI가 없어지지 않았다**: `operations` 응답의 `cli_only`에 `replay-all`·`--limit`·`--force-disabled`·`--label`·`--allow-production` 등이 나온다. 특히 **`--allow-production`은 CLI에만 있고**, 어드민 버튼과 매일 도는 스케줄러가 부르는 경로에는 그 관문이 **없다**(데몬이 이미 하는 일 이상은 아니지만 **CLI가 묻는 확인을 재현하지도 않는다**).

### 2.9 맵 에디터

- [ ] **로드/편집/저장**: 페이지 진입 → 테이블 선택 → 기존 맵 로드 → 브러시로 셀 페인팅 → 저장 → 재진입 시 편집 결과 유지 + 메인 그리드에서 동일 값 확인(배치 업서트 경유).
- [ ] **회전/면반전 불변식**: 회전·FRONT/BACK 전환 후에도 특정 칩의 물리 위치 표시가 일관(스펙 불변식). FRONT/BACK 워터마크·툴바 칩 표시.
- [ ] **프리셋**: 커스텀 지오메트리 프리셋 저장 → 목록 표시 → 삭제 동작.
- [ ] 🎯 **프리셋은 방향을 건드리지 않는다** (`02a72c6`): `maps.json`의 프리셋 하나에 `"rotation": 90`을 넣고, 화면을 0°로 둔 채 그 프리셋을 고른다 → **회전이 0° 그대로**이고 **info 토스트가 1회** 뜬다(「규격만 적용했습니다 — … 방향은 적용하지 않았습니다」). 화면이 90°로 돌면 회귀다. 이어서 화면을 90°로 맞추고 같은 프리셋을 다시 고르면 **토스트가 안 뜬다**(선언과 화면이 같으므로).
- [ ] 🎯 **📐 표준 로드가 좌표를 재번호하지 않는다** (`019140c`): `wafer_map_metadata`가 **없는** 맵을 `📂 Load` → `📐 표준`으로 연 뒤, 칠해진 셀 몇 개의 **칸 안 번호를 DB의 x/y와 직접 대조**한다 → 같아야 한다. ⚠️ **칸 안 번호는 빈 셀에만 그려지므로** 대조는 좌측 패널의 `START X/Y`가 **데이터의 최솟값**으로 채워졌는지로 갈음할 수 있다(`0/0`이면 회귀). 회귀하면 손상이 **한 번의 Push로 영구화되고 되돌릴 수 없다**.
- [ ] 🎯 **유효 다이 — 고르는 것이 곧 적용이고, 버튼은 없다 (2026-08-04 `5b15c24`)**: 🔴 **종전 이 자리는 `🎯 APPLY`/`💾 SAVE` 두 버튼을 누르라고 적고 있었고, 그 두 버튼은 삭제됐다.** ⓐ 키 칸에 포커스 → **맵 키 목록이 뜨고 요청 1건**(`wafer_map_metadata?filters=target_table equals valid_die_ref`, 상한 500). ⓑ 목록이 **완전**하면 컨트롤이 `<select>`이고 **고르는 즉시** 화면에 적용된다(확인창 없음, 서버 쓰기 0). ⓒ 목록이 잘렸거나·읽지 못했거나·**지금 지정된 키가 목록에 없으면** 텍스트 입력으로 바뀌고 **`Enter`에만** 반응한다 — 🔴 **타이핑 중이나 다른 칸으로 옮길 때 적용되면 회귀다**(`blur`/`change` 리스너는 없어야 한다). ⓓ 같은 칸에 다시 포커스 → **요청 0건**(완전한 목록만 캐시된다. 잘린 목록이면 다시 묻는 것이 정상). ⓔ 지정을 비우면 토스트가 **두 저장 버튼을 이름으로** 부른다(`📐 규격만 저장 또는 ⚡ Push로 저장하십시오`).
- [ ] 🎯 **`📐 규격만 저장` — 셀을 안 쓰고, 없는 등록을 만들 수 있다 (2026-08-04 `5b15c24`+`30284bf`)**: ⓐ 셀을 하나도 안 건드린 채 유효 다이만 고르고 `📐 규격만 저장` → 확인창이 **「셀은 하나도 쓰지 않습니다」**를 먼저 말하고, 저장 후 **셀 행 수가 그대로**다(메인 그리드에서 대조). ⓑ 🔴 **맵 키 칸을 아직 없는 이름으로 바꾸고** 누르면 확인창이 **「규격을 새로 등록합니다」**라고 말한다 — 등록된 것이면 **「갱신합니다」**. 두 문장이 구별되지 않으면 회귀다(오타 난 키로 새 등록이 생기는 자리다). ⓒ 맵 키 칸을 비우고 누르면 **거절**(`맵 키 칸을 채워야 …`). ⓓ 사전 조회를 실패시키면(네트워크 차단) **쓰지 않는다**. ⓔ 응답을 15초 이상 지연시키면 문구가 **「저장됐는지 확인이 필요합니다」**라고 말한다 — 🔴 **「기록되지 않았습니다」라고 단정하면 회귀다**(그 쓰기는 멱등이라 실제로 착지했을 수 있다).
- [ ] **미저장 경고가 싼 쪽을 이름으로 부른다**: 셀을 **안 바꾸고** 규격만 고친 뒤 ⓐ 뒤로 가기 ⓑ **다른 맵 로드**(`9e41995`) → 둘 다 확인창 가운데 줄이 `· 셀은 하나도 바뀌지 않았습니다 — [📐 규격만 저장]이면 충분합니다.` 셀을 바꿨으면 `· 셀 값이 바뀌었습니다 — [⚡ Push]로 저장하십시오.` **두 문 모두** 확인할 것 — 로드 쪽 문이 늦게 합류했다.
- [ ] 🎯 **참조가 안 풀리면 이름을 대고 거절한다**: 등록되지 않은 키를 넣고 적용 → 마스크가 **비지 않고** 토스트가 `이 유효 다이 맵을 valid_die_ref에서 찾을 수 없습니다 ― 키 「…」로 등록된 맵 규격(wafer_map_metadata)이 없습니다`를 말하고 칩이 `⚠️ 유효 다이 맵 미해석`이 된다. 🔴 **조용히 빈 마스크로 그려지면 회귀다.** 흔한 원인은 셀은 `valid_die_ref`에 있는데 **그 맵이 `wafer_map_metadata`에 등록돼 있지 않은 것**이다.
- [ ] **유효 다이 — 테이블 선택칸이 없다**: 저장 테이블은 **`valid_die_ref` 하나로 고정**이므로 테이블 `<select>`가 화면에 없어야 한다. 목록 조회도 **고정 테이블**에 묻고 **캔버스 테이블에는 절대 묻지 않는다**(Network 탭에서 확인).
- [ ] 🔴 **유효 다이 — 옛 선언이 조용히 재조준되지 않는다**: 이 규칙 이전에 저작된 선언(맨 문자열 = 「내 테이블의 맵」, 또는 다른 테이블을 가리키는 객체형)이 든 맵을 **키를 건드리지 않고** 저장한다 → **선언이 한 글자도 안 바뀌어야 한다.** 🔴 고정되는 것은 **저작**이지 저장 형식이 아니다 — 전량 재조준되면 남의 맵을 가리키던 참조가 통째로 끊어진다.
- [ ] 🎯 **유효 다이 지정 — 좌표는 고정, 칸은 따라간다** (`da8f390`): 격자나 원점이 다른 템플릿을 `🎯 유효 다이 맵`에 넣고 `⚡ Push` **전에** 관찰한다 → ① 좌측 패널의 격자 크기·회전·면·`START X,Y`가 **한 글자도 안 바뀐다** ② 칠한 셀은 **화면에서 이동한다**(정상 — 자기 좌표가 가리키는 칸으로 다시 앉은 것) ③ info 토스트 1회가 **이동 칸수**를 말한다 ④ `⚡ Push` 후 DB의 x/y가 **지정 전과 동일**하다. ②가 안 일어나면(셀이 안 움직이면) 좌표가 깨진 것이다.
- [ ] 🎯 **격자 `COLS`/`ROWS` 편집이 저장 좌표를 지킨다** (`9d7d9a4`): 셀이 칠해진 맵을 열고 **`COLS`를 한 칸 고친 뒤 칸을 벗어난다**(blur 또는 Enter — 타이핑 중에는 안 돈다) → ① 칠한 셀이 **화면에서 다시 앉는다** ② `⚡ Push` 페이로드의 x/y가 **고치기 전과 같다**(보는 법은 아래 「크기가 다른 참조」 항목의 ⓑ와 같다). 🔴 **치수를 아무거나 고르면 절반 넘게 헛짚는다** — 실측 36건 중 **16건만** 드리프트하고 **20건은 원래 아무 일도 일어나지 않으므로**(그 20건에서는 ①도 안 일어나는 것이 정상) **드리프트하는 조합인지 먼저 확인하고** 점검할 것. 🔴 **`box.minC`가 안 움직여도 전량이 드리프트할 수 있다**(`QERWER` 23→22열: 원점 그대로, 261칸 전부 재번호) — "화면 원점이 그대로니 괜찮다"로 판정하지 말 것.
- [ ] **치수 편집이 `Y 반전`·`START`를 덮지 않는다** (`9d7d9a4` · 규칙 ⑤): 같은 맵에서 `#grid-y-invert`를 토글하고 `START X/Y`를 고친다 → **좌표가 바뀌는 것이 정상**이고 재배치는 **돌지 않아야 한다**. 셀이 좌표를 따라 다시 앉으면 규칙 ④가 규칙 ⑤를 덮은 회귀다(같은 `inputsToRedraw` 배열에 있으므로 분기가 무너지기 쉬운 자리다).
- [ ] **정렬 알람은 원점을 본다** (`7a9c2b0`): 참조와 이 맵의 **격자 크기가 같은데 원점만 다른** 쌍으로 지정한다 → 알람이 **뜬다**. 크기 비교만 하던 종전 판정이 남아 있으면 조용히 지나간다(실측 사례 `MID_01 ← 4MAIN_DT`).
- [ ] **`[유효다이]` 콘솔 7줄**: 지정할 때 개발자 콘솔에 `1)`~`7)`이 순서대로 찍힌다(`7)`은 움직인 셀이 있을 때만). 사용자가 이 줄로 QA하므로 **누락은 진단 수단의 소실**이다. 표는 [VALID_DIE_MAP_GUIDE §4-bis.3](../guide/VALID_DIE_MAP_GUIDE.md).
**캔버스 축척 · 합성 규격 (2026-08-04 `102cdea`+`edc7ef6`+`cfc09de`+`cd37e2c`)**

- [ ] 🎯 **원이 원이고 셀이 피치를 따른다**: 물리 규격이 **선언된** 맵을 연다 → ① 웨이퍼 원이 **타원이 아니다** ② `phys_chip_x != phys_chip_y`인 맵에서 **셀이 직사각형**이다(정사각이면 회귀 — 축이 서로 다른 배율을 쓰고 있다는 뜻). 창을 리사이즈하고 스플리터를 움직여도 유지되는지.
- [ ] 🎯 **같은 웨이퍼는 같은 크기다**: 선언 지름이 같고 **피치·격자가 다른** 맵 둘을 번갈아 연다 → 원의 화면 크기가 **같다**. ⚠️ **예외 하나를 결함으로 열지 말 것** — 격자가 웨이퍼보다 커서 캔버스를 넘길 조합에서는 **격자가 축척을 가져가고 원이 작아지는 것이 정상**이다(넘친 칸은 저장 페이로드에서 사라지므로 그쪽이 우선이다).
- [ ] **여백은 맵이 아니다**: 격자가 캔버스보다 작아 여백이 생긴 맵에서 ① 여백 칸에 **격자선만 있고 채워지지 않는다** ② 여백을 클릭·드래그해도 **아무 셀도 칠해지지 않는다** ③ 범례 카운트·DOE 수량·Push 건수에 **포함되지 않는다** ④ 선언된 격자 둘레에 **굵은 외곽선**이 하나 있다.
- [ ] **오버레이 마커가 축별로 커진다**: 직사각 셀 맵에 오버레이를 얹는다 → 점이 **셀 비율을 따른다**(짧은 축만 따라가면 회귀).
- [ ] 🎯 **합성 규격은 정렬을 거절한다** (`auto_registered`): `wafer_map_metadata`에 `auto_registered: true`인 맵(= `chip 1×1`)을 **오버레이 소스나 타깃으로** 지정한다 → **겹치지 않고 사유를 말한다**(`미선언(자동 등록된 합성 규격)` — 🔴 **`auto_registered`라는 열거값이 화면에 그대로 나오면 회귀다**, 실제로 `소스 auto_registeredxauto_registered`가 사용자에게 나갔다). 🔴 **1mm 피치로 그럴듯하게 정렬되면 그것이 이 라운드가 없앤 결함이다.**
- [ ] **합성 규격 맵의 셀이 커 보이는 것은 정상이다**: 그런 맵(운영 실측 668행 중 **320행**)은 등방 정박 경로에 **닿지 않고** 비등방 폴백으로 떨어진다. 캔버스 안내가 `기하 규격 미선언 (자동 등록된 합성 규격) …`이라고 말하는지 확인 — 말하고 있으면 **결함이 아니라 표지의 결과**다.
- [ ] **표지는 왕복한다**: 그런 맵을 열어 `⚡ Push` 또는 `📐 규격만 저장` → 저장된 `grid_metadata`에 **`auto_registered`가 그대로 남는다**(빠지면 다음 로드에서 합성 규격이 **실측 규격으로 위장**한다).

- [ ] **레전드 유지**: 레전드 편집 → 새로고침 후 유지(localStorage). 테이블별로 분리 저장.
- [ ] **맵 이월 에지**: 편집 중 테이블 A→B 전환 → 유지/초기화 확인창 표시. (⚠️ 컬럼명이 크게 다르면 자동 정합 안 됨 — 이슈 #2, 저장 전 수동 매핑 확인.)
- [ ] **엑셀 복사**: 맵 그리드를 엑셀로 복사 → 셀 배치 일치.
- [ ] **COPY HEADER MODE — 열 폭(`5a14e77`)**: 토글을 켜고 `MIDLOT_01`처럼 **긴 라벨**이 나오는 맵을 복사 → 엑셀에서 라벨이 **잘리지 않고** 읽히며, **맵 셀 폭은 그대로**다(소스 상수 `HDR_COL_PX = 32` = `<td width: 32px>`. 긴 헤더 한 칸이 그 아래 그리드 열을 통째로 넓히면 회귀 — 종전 결함. `5a14e77`은 브라우저에서 실측: 344px 헤더가 더 이상 344px 그리드 열을 만들지 않는다). 표의 **모든 행이 같은 열 수**인지 확인(하나라도 어긋나면 엑셀이 표 전체를 민다). `1H`와 `MIDLOT_01`이 **같은 폭**이면 균등 분배 회귀다.
- [ ] 🎯 **COPY HEADER MODE — 상단 병합이 보조표를 넘지 않는다** (`9d7d9a4`): 토글을 켜고 복사 → **엑셀에 붙여넣고 인쇄 미리보기**로 본다 → TITLE 줄과 그룹 띠가 **맵 격자에서 끝나고** 우측 `VALUE | COUNT | STACK | DESC` 보조표 **위를 지나가지 않아야** 한다(종전 결함 — 실측 23열 맵이 32열, 51열 맵이 60열을 병합했다). 이어서 **표가 밀리지 않았는지**도 본다: 남는 열은 병합이 아니라 개별 빈 칸이므로 **모든 행의 열 수는 여전히 같아야** 한다(하나라도 어긋나면 엑셀이 표 전체를 민다). ⚠️ **격자가 아주 좁은 맵(열 3~5개)은 예외다** — 라벨 최소 폭(`groupMinCols`)이 하한이라 띠가 격자보다 넓은 것이 **정상**이고, 그때 격자에 맞춰 깎이면 `MIDLOT_01`이 다시 잘리는 회귀다. 되붙이기(Ctrl+V)는 이 변경의 **영향을 받지 않아야** 한다 — 같은 복사본으로 아래 왕복 항등 항목을 한 번 더 돌려 확인.
- [ ] 🎯 **회사 양식 왕복 — 항등(F1ⓑ `c9bf2c7`)**: COPY HEADER MODE로 실맵 복사 → `🧹 Clear Grid` → **Ctrl+V** → 확인창 1회 승인 → **다시 복사** → 두 클립보드 내용이 **바이트 동일**해야 한다(빈 칸 포함). ⚠️ 붙여넣기 도중·직후 **서버 요청이 0건**인지 네트워크 탭으로 확인(저장은 `⚡ Push`뿐 — INV-F1ⓑ-4).
- [ ] 🔴 **회사 양식 왕복 — 병합 압축 회귀(INV-F1ⓑ-3)**: 보조표에서 **STACK이 빈** DOE 행이 있는 복사본을 되붙인다 → DESC가 **STACK 칸으로 들어가면 안 된다**(빈 칸을 걷어내고 압축해 읽으면 그렇게 된다 — 화면은 멀쩡하고 값만 틀리는 부류). 읽기는 머리줄에서 배운 열 위치로만 해야 한다.
- [ ] 🔴 **회사 양식 왕복 — 프레임 지문(노치 `D`)**: rot **270**에서 복사 → 화면을 rot **90**으로 바꾼 뒤 붙여넣기 → **치수가 같은데도 거부**되고 사유가 노치 위치를 지목한다. 같은 축으로 rot 0↔180, front↔back도 확인. 노치가 격자 밖인 규격에서는 거부 대신 확인창이 *"회전·면은 대조하지 못했습니다"*라고 말한다(조용히 통과시키면 회귀).
- [ ] 🔴 **회사 양식 왕복 — 노치는 데이터가 아니다**: 붙여넣기 후 그 노치 자리에 **값이 생기지 않았는지** 확인하고, 이어서 `⚡ Push` → **적재 대조 게이트에 걸리지 않아야 한다**. 걸리면 노치를 데이터로 되쓴 회귀이며, 그 맵은 **영구 Push 거절 상태**가 된다. 확인창이 말한 "값 있는 셀 N칸"과 실제 놓인 칸 수도 일치해야 한다(노치 1칸 차이가 원 결함).
- [ ] 🔴 **회사 양식 왕복 — 삭제 권한 없음**: 값 3개짜리 DOE에서 복사 → 엑셀에서 **한 행을 지우고** 되붙이기 → 그 값이 **legend에서 사라지면 안 된다**(복사본에 없는 값 = "이 복사본이 말하지 않은 것"). 삭제는 DOE 패널 삭제 버튼만 한다.
- [ ] **회사 양식 왕복 — 왕복하지 않는 것**: 자재(1H/MID/TOP)를 채운 맵을 복사 → 표①의 자재를 지우고 되붙이기 → **자재는 복원되지 않는다**(상단 그룹 띠는 읽지 않으므로 — 결함이 아니라 명시된 계약). COLOR도 마찬가지로, 기존 값은 **자기 색을 유지**하고 새 값만 팔레트가 배정한다.
- [ ] **회사 양식 왕복 — 남의 클립보드는 조용히**: 다른 화면·다른 앱에서 긁은 표를 맵 화면에서 Ctrl+V → **토스트 없이 그냥 지나간다**(아무 붙여넣기에나 경고가 뜨면 회귀). 반대로 DOE 패널 안에서의 붙여넣기는 **패널이 처리**하고 격자가 가로채지 않는다. 입력 칸 포커스 중의 붙여넣기도 그 칸의 것이다.
- [ ] **머리줄 로스터 = 집합(`5a14e77`)**: `contracts/doe_band_rules` 하네스가 `IGNORED_HEADERS`를 **13개 정확히**로 단언한다(§2.0에서 함께 통과). 14번째를 넣거나 하나를 빼면 하네스가 빨개져야 한다 — 표본 단언이던 시절에는 `COUNT` 추가에 331 단언이 전부 초록이었다. ⚠️ 롤업 8단어(`MAT`·`BIN`·`MAP`·`가용`·`사용`·`사용≈`·`잔여`·`잔여≈`)는 **예비**다: `rollupToGrid`는 importer 0건이라 표②→표① 왕복은 **배선돼 있지 않다**. 그 단어들이 목록에 있다는 이유로 "②를 붙여넣을 수 있다"고 점검하지 말 것.
- [ ] **프리셋 라우팅 — 서버 단독(F5 `50bddda`)**: `map_overlay_config.json`에 `preset_routing`을 선언하고 `curl "…/api/maps/preset-routing?table=<t>&map_key=<k>"` → ⓐ 규칙에 맞는 랏은 `status: ok` + `preset_key`, ⓑ **`wafer_map_metadata`가 있는 맵은 `meta_present` + `preset_key: null`**(저장된 규격을 라우팅이 못 덮는다 — 뒤집히면 회귀), ⓒ 선언 없는 테이블은 `not_declared`, ⓓ 어느 규칙에도 안 걸리면 `no_match`. **`ok`가 아닌 모든 응답에서 `preset_key`/`preset`이 `null`**인지 확인(그럴듯한 프리셋을 지어내면 회귀 — 틀린 규격은 저장 가능 집합을 바꾼다). ①의 조회 테이블이 없거나 miss여도 **경고 로그가 뜨지 않고** 조용히 ②로 떨어지며 결과는 `lookup.status`에만 나온다. ✅ **이 항목은 서버 절반만 봅니다.** 종전에 여기 있던 *"HEAD `c9bf2c7` 기준 에디터 동작은 변하지 않는다(클라 절반 미착지)"*는 `73b5925` 이후 **거짓**입니다 — `applyRoutedPreset`가 `loadExistingMap`에서 로드당 1회 부르므로 **맵을 열면 규격이 실제로 바뀌고 알림이 남습니다**(그것이 정상). 화면 쪽 점검은 §1.7 프리셋 라우팅 행의 ①~④를 쓰십시오.
- [ ] 🔴 **유효 다이 — 크기가 다른 참조를 지정해도 저장 좌표가 안 움직인다 (F8 `61440e6`)**: 셀이 칠해진 맵(예: 45×45)을 열고, **격자 크기가 다른** 유효 다이 템플릿(예: 29×25)을 `🎯 유효 다이 맵` 칸에 지정. 기대 동작 — **거절 없음 · 확인창 없음 · 격자 크기 입력칸 불변 · 셀이 화면에서 안 움직임**, 마스크만 **눈에 띄게 밀려** 보이고 **info 토스트 1회**. 🎯 **핵심 축(눈으로 보는 법 3가지 — 하나만 해도 되지만 ⓑ가 가장 직접적이다)**:
  - ⓐ **구조적 확인(가장 쉬움)**: 좌측 패널의 `Grid Cols`/`Rows`가 그대로이고 셀이 캔버스에서 안 움직였으면 **저장 좌표도 안 움직인 것**이다 — DB x/y는 Push 시점에 **셀의 캔버스 칸**에서 유도되므로, 칸이 그대로면 좌표가 그대로다. 반대로 격자 크기 칸이 참조 값으로 바뀌었으면 **그 자체가 회귀**(채택 부활)다.
  - ⓑ **페이로드 직접 대조**: DevTools Network를 켜고 **지정 전에 한 번** `⚡ Push` → `replace_map` 요청 페이로드 저장. 지정 후 다시 `⚡ Push` → 두 페이로드의 x/y 집합이 **바이트 단위로 같아야** 한다. ⚠️ **물리 키로 대조하면 이 축은 원리적으로 보이지 않는다**(물리 키는 프레임이 바뀌어도 불변이다) — 반드시 **페이로드의 x/y**로 볼 것.
  - ⓒ **DB 확인**: 지정+Push 후 메인 그리드에서 그 맵 테이블의 x/y 컬럼을 열어 **지정 전 값과 대조**.
- [ ] **유효 다이 — 치수 차이로 거절하지 않는다**: 위와 같은 조합에서 *"격자 규격이 다릅니다"* 류 **거절이 뜨면 회귀**다(사용자가 두 번 뒤집은 동작 — `73b5925` 이전으로 되돌아간 것). 확인창이 떠도 회귀다: 읽기는 무마찰이 규율이고, 알림은 **토스트 1회**뿐이다.
- [ ] **유효 다이 — 살아 있는 유일한 거절(치수 정의역, H5)**: 참조 맵의 `wafer_map_metadata`에 `grid_cols=1024, grid_rows=1024`(또는 `0`·`45.5`) 행을 만들고 지정 → **참조 셀을 한 건도 조회하기 전에** 사유와 함께 거절되고 **에디터 격자는 그대로**여야 한다. Network 탭에 그 참조 테이블의 `/data` 요청이 **없어야** 한다(있으면 가드가 조회 뒤로 밀린 회귀). **clamp해서 통과시키면 회귀** — 잘린 치수로 만든 마스크는 화면이 멀쩡한 채 판정만 틀린다.
- [ ] **페인트 잠금**: 맵 로드 → 잠금 값(기본 `F`) 셀에 브러시·Fill·Auto-Paint·오버레이 가져오기 시도 → 전부 차단. `/api/maps/paint-rules`를 500으로 막고 재로드 → **잠금이 풀리지 않고** `⚠ 잠금 규칙 미확인` 칩 + 경고 토스트(fail-open 금지).
- [ ] **오버레이 — 기본 흐름**: `＋ 겹치기`로 다른 테이블/키 맵 추가 → 셀 마커 표시, 표시 토글·제거 동작, 정렬 상태 칩이 **`무보정`(identity) 또는 `정렬됨 N°`(derived)**로 표기. ⚠️ **`declared`는 정렬 어휘가 아니다** — 선언 정렬 레이어는 2026-07-27에 삭제됐고 `declared`가 나오는 곳은 **바인딩 출처**(`binding.source`)뿐이다. 두 어휘가 `derived`를 공유하니 무엇을 보고 있는지 먼저 확인할 것. **메인 맵의 테이블·규격·legend·brush가 하나도 변하지 않는지** 확인(경로 분리 불변식).
- [ ] 🎯 **오버레이 — 점은 자기 값의 색을 입는다 (2026-08-04 `376e1c8`)**: legend에 값 둘(예: `1`=초록, `F`=빨강)을 선언한 맵을 오버레이로 올린다 → **각 점이 자기 값의 색으로 칠해진다**(레이어 색이 아니라). 링은 계속 **레이어 색**이고 그 사이에 **흰 후광**이 있어 칸과 구별된다.
- [ ] 🎯 **선언 안 된 값은 색을 지어내지 않는다** 🔴: legend에 **없는** 값(예: `ZZ9`)이 든 맵을 오버레이로 올린다 → 그 점은 **속이 빈 링 점**으로 그려진다. 🔴 **팔레트 색이 찍히면 회귀다** — 지어낸 색은 아무것도 뜻하지 않으면서 **선언된 색처럼 읽힌다.** ⚠️ **안 그려지는 것도 회귀다**(데이터가 없는 것과 구별이 안 된다).
- [ ] 🎯 **비어 있는 이유를 화면이 말한다**: 위 상태에서 오버레이 행에 **`범례 밖 N종`** 칩이 뜨고, 툴팁이 값 이름들과 **처방**(「범례(2. Legend & DOE)에 값을 추가하면 그 색으로 칠해집니다」)을 말한다. 그 값을 legend에 추가하면 **그 자리에서** 칩이 줄고 점이 칠해진다(캐시하지 않고 매 렌더마다 다시 센다).
- [ ] **부재의 두 이유가 갈린다**: 「값이 여럿이라 비었다」(`overlayFanChip`)와 「선언이 없어 비었다」(`overlayLegendChip`)가 **다른 칩**으로 나온다. 픽셀은 같으므로 칩이 안 갈리면 운영자가 하나를 다른 하나로 고치려 든다.
- [ ] **한 칸에 값이 여럿이면 값이 같아도 안 칠한다**: 같은 값 두 개가 한 칸에 겹치면 **여전히 속이 빈 점**이어야 한다(대표를 고르는 순간 그 점은 자기가 하나인 척한다).
- [ ] **맵의 legend가 사이트 기본을 이긴다**: 같은 값을 맵 legend와 서버 `default_legend`(`map_overlay_config.json`) **양쪽에 다른 색으로** 선언 → **맵 legend 색**이 나온다.
- [ ] **오버레이 — 서빙되는 바인딩(F1 `17f65bd`)** 🔴: `map_overlay_config.json`의 `table_bindings`에 **관례 밖 좌표 컬럼**(`dt_log`의 `tx`/`ty`)과 **대문자/한글/숫자 시작 테이블명**을 선언 → 맵 에디터에서 그 테이블을 **선언만으로** 로드·오버레이할 수 있어야 한다(클라가 별도 유도를 하지 않는다). 드롭다운이 선언된 컬럼으로 **미리 선택**되는지 확인. 종전에는 서버만 존중하고 클라가 리터럴 소문자 `x`/`y`를 요구해 "설정이 안 먹는" 상태였다.
- [ ] **오버레이 — 추측 바인딩 거부(F2 `17f65bd`)** 🔴: 값 컬럼 후보(`value_column_candidates`)에 **하나도 맞지 않는** 맵 테이블을 준비 → `GET /api/maps/paint-rules?table=<t>`의 `binding.source`가 **`fallback_guess`**인지 확인 → ⓐ **로드** 경로는 미리 선택하되 **추측 경고**를 낸다 ⓑ **오버레이** 경로는 **거부**한다(추측 컬럼을 칠하면 미끼 셀). 같은 상태에서 `GET /api/maps/overlay`는 `source_missing`으로 답해야 하고 **셀을 하나도 내려보내면 안 된다**.
- [ ] **오버레이 — 행은 있는데 셀 0개**: 소스 맵에 행은 있으나 격자 밖/값 없음으로 그릴 셀이 0개인 상황 → **초록 성공 토스트가 아니라 원인을 이름 붙인 경고**가 떠야 한다.
- [ ] **오버레이 — 좌표 정확성** ⚠️: 회전 90/270 + **비등방 칩**(chip_x ≠ chip_y) + **bbox ≠ 0인 실데이터**(29×25, 27×21 등)로 확인할 것. 40×40(`minC=0`)은 결함이 원리적으로 발현하지 않는 구간이라 통과해도 아무 의미가 없다(과거 2회 이 사각지대에서 "해소" 오판정). 오라클은 앱의 변환 함수를 쓰지 말고 독립 계산으로.
- [ ] **오버레이 — 규격 변경 추종**: 오버레이가 떠 있는 상태에서 회전·면반전·start 좌표 **및 물리값(`phys_chip_*`/`phys_offset_*`)** 변경 → 마커가 메인 맵과 **같은 칸에서 함께** 이동(`syncOverlayGeometry`). ⚠️ **판정은 "오버레이가 움직였는가"가 아니라 "메인 맵과 같은 칸에 있는가"다** — invertY·START는 `(c,r)↔물리` 사상에 개입하지 않으므로 **양쪽 다 안 움직이는 것이 정답**이다(구 설계에서는 이 두 축에서 오버레이만 움직였고, 그것이 사용자가 본 어긋남의 한 갈래였다).
- [ ] **오버레이 — 실패 표면화**: 존재하지 않는 소스 맵 추가 → 목록에 **실패 행으로 남고** 사유 표시(조용히 사라지지 않음). 규격 조회를 5xx로 막아 `meta_unavailable`이 뜨고 **마커가 0개**인지 확인("확인 못 함"이지 "미등록"이 아니다 — 폴백해서 그리면 결함). *(구 `align_unconfirmed` 점검 항목은 선언 probe 삭제로 2026-07-27 폐기)*
- [ ] **오버레이 — 기준 변경 시 해제**: 오버레이를 띄운 채 ⓐ 다른 맵 로드 ⓑ **다른 테이블로 전환** ⓒ 프레임 진입 → 세 경우 모두 오버레이가 사라진다. 특히 ⓑ에서 목록이 비었는지 확인 — 남아 있으면 `가져오기`로 **이전 테이블 값이 새 테이블에 써진다**(`251dbfd`가 닫은 경로).
- [ ] **오버레이 — 캔버스 측정 함정**: 비표시(백그라운드) 창에서는 `requestAnimationFrame`이 멈춰 캔버스가 얼어붙는다. "마커 0개"를 결함으로 판정하기 전에 **탭을 앞으로 꺼내고 명시적 재렌더를 유발**할 것. `phys-*` 입력은 재렌더 예약 목록에 없어 값만 바꾸면 화면이 낡은 채로 남는다.
- [ ] **전사 계획 — 기본 흐름(ZONE)**: `bonding_map` 로드 → 사이드바에 stage가 **자동 유도**되어 표시(선택 UI 없음) → DOE 값 행 펼침 → **STACK 숫자 하나 + 구역 셋(1H/MID/TOP) 자재 입력**(FROM/TO·구간 행·순서 개념 없음) → ⚡ Push 후 재로드 시 유지. `dt_map`은 STACK=1·MID만인 퇴화형이 **조용히 통과**해야 한다.
- [ ] **전사 계획 — 개명 생존(ZONE)**: DOE 값 이름을 바꿔도 층 구조(STACK·구역 자재)가 같은 행에 그대로 붙어 온다 — zone 모델에는 값을 이름으로 가리키는 참조가 없다(구간 모델의 `seq`·`values[]` 폐기).
- [ ] **전사 계획 — replace 권한(C1 회귀)** 🔴: `map_split_registry` **GET만** 500으로 1회 막았다가 **복구**시킨 뒤 편집 → 서버 행이 삭제·덮어쓰기되지 않아야 한다. 지속 실패만 시험하면 **회복 분기를 한 번도 실행하지 않으므로 이 항목은 검증되지 않은 것**이다. 절단 응답(`total > rows.length`)·맵 전환 중 늦은 응답도 같은 방식으로 확인.
- [ ] **전사 계획 — 동시 편집 거부(M2.6 신설)**: 두 세션에서 같은 맵을 열고 A가 저장 → B가 저장 시도 → **upsert로 강등되지 않고 거부**되며 리로드 전까지 그 맵의 쓰기가 막힌다. 강등되면 B의 낡은 층 구조가 A의 것을 덮는다.
- [ ] **전사 계획 — 읽을 수 없는 STACK(V5)**: `stack` 컬럼에 `0x10` 같은 값이 저장된 상태로 로드 → 화면에 **원문 그대로** 표시되고 V5 사유가 뜬다. **재저장해도 값이 `16`이나 빈칸으로 바뀌지 않아야 한다**(정규화기가 값을 고쳐 저장하면 화면에는 아무 잘못도 안 보인다).
- [ ] **전사 계획 — 자재 토큰(ZONE 문법)**: 진짜 malformed 토큰(`ABC_`, `_01`, `_`)은 **조회 요청 자체가 나가지 않고** `미상`으로 표시된다(숫자 `0`이 뜨면 실패 — "조회 못 함"과 "잔여 0"은 다르다). 반면 분리자 없는 `MID1`은 해석 실패가 **아니라 로트 전체 토큰**이다 — `scope=lot`으로 조회되고 슬롯 전개(by_slot)가 뜬다.
- [ ] **전사 계획 — 초과 배정 경고가 죽지 않는가** 🔴: 한 자재에 두 구간이 각각 요구를 걸어 **합계만 초과**하게 만든다(개별로는 부족하지 않게). `validate`가 `status: ok` + 경고 0건을 내면 실패 — 집계 게이트가 라벨 가짓수를 세고 있다는 뜻이다.
- [ ] **전사 계획 — degraded 표기**: 역할 바인딩을 하나 끊고 자재 요약 조회 → `remaining`이 숫자가 아니라 **미상**으로 표시되고 경고가 뜬다. **초록/정상으로 뒤집히면 실패.**
- [ ] **전사 계획 — STACK 0 마커(U9, `2baf9ff`)**: 값의 STACK에 `0` 입력 → 입력이 오류(빨강)로 칠해지지 않고 구역 셀 셋이 **해당 없음**으로 잠기며, 자재 롤업 표에 그 값의 행이 **아예 없다**(「사용 0」으로 존재하면 실패). 구역에 자재가 남은 채 0을 넣으면 그 행에는 **V6 메시지 하나만** 뜬다(V4·V5 동반 금지). 엑셀 복사/붙여넣기 왕복에서 `0`이 적은 그대로 돌아온다. **빈칸은 마커가 아니다** — 여전히 V5.
- [ ] **전사 계획 — ↻ 가용 피드백(U8, `2baf9ff`)**: BIN 축 미선언 등으로 결과가 전부 `미상`인 상태에서 [↻ 가용] 클릭 → 숫자는 그대로여도 **토스트가 조회 완료 사실과 지배적 미상 사유**를 말한다(아무 반응 없이 같은 화면이면 회귀 — "버튼이 죽어 보임"이 원 결함). 사유는 각 `미상` 셀 툴팁에도 남는다.
- [ ] **맵 Push — 적재 대조 게이트(H2, `6db517d`)** 🔴: 메타 미등록 맵을 기본 프레임으로 열어 일부 셀이 격자 범위·원 밖에 놓인 상태에서 ⚡ Push → **confirm 창이 뜨기 전에 거부**되고, 메시지에 "값 있는 셀 N개 중 M개 삭제 예정" 수치가 명시된다. 거부 시 서버 PUT **0건**(DB 행 수 불변). 화면과 페이로드가 동수인 정상 맵(사용자가 지운 셀 포함)은 무마찰 통과.
- [ ] **맵 Push — 로그형 대상 게이트(Gate 4, `deed6d2`)** 🔴: 로그형 테이블(dt_log처럼 맵 계약 밖 데이터 컬럼을 가진 테이블 — `map_push_ok` 미선언)을 맵으로 열고 ⚡ Push → **어떤 다이얼로그도 뜨기 전에 거부**되고, 메시지에 **파괴될 컬럼명이 명시**된다(dt_id·eventtime·장비 컬럼 등). 거부 시 서버 쓰기 **0건**(DB 행 수·값 불변). 맵 **조회**(로드·오버레이 소스)는 계속 정상 동작해야 한다 — 게이트는 Push에만 걸린다. 합성 bk 테이블(bonding_map의 pkg_id)은 로그형으로 오판되지 않고 무마찰 통과.
- [ ] **맵 Push — `map_push_ok` 선언 = 소실 confirm 1회(Gate 4, `deed6d2`)**: 로그형 테이블의 table_config에 `map_push_ok: true`(JSON boolean) 선언 후 Push → 차단 대신 **소실될 컬럼명을 명시한 확인창 1회**가 뜨고, 취소하면 쓰기 0건, 승인하면 진행된다. 선언 값을 문자열 `"true"`/`"false"`로 바꾸면 **여전히 차단**되어야 한다(오타가 파괴를 해제하면 회귀 — 서버 `is True` 판정). 맵 계약 안에 다 들어오는 깨끗한 테이블에 선언해도 **추가 confirm이 생기지 않는다**(inert).
- [ ] **replace_map — 무음 no-op 폐기(U6, `deed6d2`)** 🔴: `map_key_columns` 미선언(그리고 페이로드에서 범위 파생 불가) 테이블에 `replace_map` 요청 → **200이 아니라 400 + 사유**로 거부된다(종전에는 아무것도 안 지우면서 200 — 행이 조용히 누적). 정상 Push의 응답에는 `scope: {filters, deleted, inserted}`가 실려 실제 purge 필터·건수와 일치해야 한다. 명시적 `scope` 필드 + 빈 `updates`는 그 범위 전량 소거로 동작하고 `inserted: 0`이 정직하게 내려온다. 셀 없는 순수 소거 후에도 그리드 행 수 표시가 낡지 않아야 한다(count 캐시 무효화 — 순수 wipe 경로).
- [ ] **메타 없는 맵 — 기본 선택으로 Push 가능(5b `0052d76`)**: `wafer_map_metadata`가 없는 맵 로드 → 좌표계 모달에서 **📐 표준(기본)** 선택 → 데이터 전체가 사각 bbox 격자에 그려지고(마스크로 빠지는 모서리 셀 없음), 편집 없이 ⚡ Push → **적재 대조 게이트에 걸리지 않고** 화면 셀 수 그대로 confirm·적재된다(로드 N건 = Push N건). 종전에는 원 마스크가 살아 있어 기본 선택이 전량 거부됐다(1293→379 거부 회귀). 원형 규격이 필요하면 ⚙️ 좌측 패널 선택이 여전히 동작. Push 후 재로드 → 모달 없이 열림(합성 규격이 메타로 등록됨).
- [ ] 🎯 **읽을 수 없는 START는 잠긴 문이 아니라 질문이다(`98b48e9` · 2026-08-05)** 🔴: `wafer_map_metadata`에 **행은 있는데** `grid_start_x`가 **① 키 자체가 없는** 맵과 **② `null`인** 맵 두 벌을 만들어 각각 로드한다. 확인할 것: ① **맵이 열린다**(거절 배너로 막히면 회귀 — 운영자가 에디터를 여는 이유가 규격을 모르기 때문이다) ② **좌표계 선택 모달이 뜬다** — 규격 행이 아예 없는 맵과 **같은 모달·같은 선택지**여야 한다 ③ 모달 제목이 **`좌표계 미확정`**이다(**`맵 규격 미등록`이면 회귀** — 행은 등록돼 있다) ④ 진입 시 **`warning` 토스트 1회**가 왜 묻는지 말한다(확인창이면 회귀) ⑤ **그 행의 나머지가 화면에 섞여 들어오지 않는다** — 좌측 패널의 격자 치수·회전·면이 **그 행의 값이 아니라** 고른 좌표계의 값이어야 한다(반쯤 살린 프레임 = 아무도 선언한 적 없고 아무도 고른 적 없는 프레임). 🔴 **가장 중요한 축은 ②의 `null` 쪽이다** — `Number(null) === 0`이라 종전에는 **NaN 없이 44셀이 전부 다른 칸에 앉고 로드가 성공을 알린 뒤 ⚡ Push가 `grid_start_x: 0`을 영속화**했다. **화면이 멀쩡했으므로 토스트도 콘솔도 아무 말을 안 했다.** ⑥ 두 벌 모두에서 모달의 어느 선택으로 Push하든 **좌표 왕복이 어긋나지 않는가**(로드한 x/y = 다시 읽은 x/y).
  - ⚠️ **조회 실패와 헷갈리지 말 것** — 메타 조회가 **실패**한 맵은 여전히 **거절**이지 모달이 아니다(선언이 무엇인지 모르는 상태에서 고른 프레임을 Push하면 실재하는 선언을 덮는다). 두 경로가 하나로 합쳐졌으면 회귀다.
  - ⚠️ **알려진 침묵(총괄 판정 대기)**: 이 맵에서는 클라가 프리셋 라우팅을 부르지만 서버가 **행이 존재하므로** `meta_present` + preset `null`을 답해 **라우팅이 기본값을 대 주지 않는다.** 지금은 결함이 아니라 기록된 상태다 → [MAP_EDITOR_SPEC §5.8-bis](../spec/MAP_EDITOR_SPEC.md).
- [ ] 🎯 **고른 프레임은 골랐다고 기록된다(`b9a0ab1` · 2026-08-05)** 🔴: 위 두 벌(또는 규격 행이 아예 없는 맵)을 열어 **① 📐 표준**으로 Push → 저장된 `grid_metadata`에 **`frame_chosen_from: "data"`**가 실린다. **② ⚙️ 현재 패널**로 Push → **`"panel"`**이 실린다. **③ 진짜로 선언된 맵**(모달이 안 뜨는 맵)을 그냥 Push → **그 키가 없다**(payload가 종전과 한 바이트도 달라지면 회귀). **④ 양방향 확인이 핵심이다**: ①의 맵을 Push해 표지가 남은 상태에서 **표지 없는 다른 맵**을 이어서 열고 Push → 그 맵에 **표지가 묻어 나오면 회귀**(직전 맵의 표지가 진짜 선언을 「고른 것」으로 만든다). ⑤ 표지가 붙어도 **정렬·마스크·`inside` 판정은 하나도 안 바뀐다**(`isFrameUsable`/`geometryDeclaration` 불변 — 바뀌면 회귀). ⚠️ **서버는 아직 이 키를 읽지 않는다** — 「서버가 반응하지 않는다」는 지금 회귀가 아니다 → [MAP_EDITOR_SPEC §4-bis.3-ter](../spec/MAP_EDITOR_SPEC.md).
- [ ] 🎯 **빈 프레임 칸은 0으로 지어내지 않고 이름을 대며 거절한다(`b9a0ab1`)** 🔴: 좌측 패널의 **`START X`**(또는 `START Y`/`격자 COLS`/`격자 ROWS`) 칸을 **완전히 비운 상태**로, 좌표계 모달이 뜨는 맵을 열어 **⚙️ 현재 패널**을 고른다. 확인할 것: ① **로드가 진행되지 않고** 비어 있는 칸의 **이름을 말하는 에러 토스트**가 뜬다 ② 화면은 **취소를 눌렀을 때와 같은 자리**로 돌아간다(새 확인창·새 배너가 생기면 회귀) ③ 🔴 **그 0이 칸에 되쓰이지 않는다** — 종전에는 지어낸 `0`이 **입력칸에 되쓰여** 조작자 자신의 값처럼 보인 뒤 셀들이 그 아래 앉았다(실측 46셀). ④ 칸을 채우고 다시 로드하면 정상 동작한다. ⑤ 같은 빈 칸 상태에서 **`⚡ Push`**와 **`📐 규격만 저장`**도 지어낸 0을 보내지 않는다(셋이 같은 독법 `readGridFrameControls`를 쓴다 — 하나만 고쳐져 있으면 회귀).
- [ ] **자재 프레임 — 보기만 한 뒤로가기는 조용히(5b `0052d76`)**: 비어 있지 않은 자재 맵에 들어가 **아무 편집 없이** ← 뒤로 → 확인창 **없이** 즉시 복귀. 셀 하나 칠하거나 legend를 고친 뒤 ← 뒤로 → "저장하지 않았습니다" 확인창이 뜬다. 부모 맵이 미저장(`● 저장 안 됨`)인 상태로 자재 왕복 → 복귀 후에도 칩이 **그대로 남아 있다**(왕복이 dirty를 지우면 회귀). 프레임 진입 중 좌표계 모달에서 ❌ 취소 → 빈 격자가 아니라 **이전 화면으로 롤백** + info 토스트 1개(추가 "열기 실패" 에러 토스트가 겹치면 회귀).
- [ ] **전사 계획 — count_only 강등 = 미상이지 0이 아님(5c `1fefd12`)** 🔴: `transfer_log` 바인딩에서 x/y를 빼고(또는 좌표가 null인 로그로) 자재 요약 조회 → `sources.transfer_log`가 `connected(count_only)`, **기전사 카운트는 숫자로 유지**되되 잔여는 `미상`(+상한)으로 표시되고 코어별 분해의 used/remaining도 미상이다. **잔여가 `total − 0`짜리 맨숫자로 나오면 유령 잔여 회귀**(+101 재현으로 실증된 원 결함 — log·area_map 양 경로 모두 확인). `fail_sources`의 `val` 컬럼명을 오타로 바꾸면 fail이 전-행-count로 뛰지 않고 **0 + `connected(column_unresolved:val)`**로 강등된다.
- [ ] **전사 계획 — self-frame fail도 count_only = 미상이지 틀린 숫자가 아님(`deed6d2`)** 🔴: `origin_log`가 connected인 상태에서 `frame: "self"`인 fail 원천을 x/y 없이(또는 좌표가 null인 원천으로) 바인딩하고 자재 요약 조회 → 그 원천 status가 `connected(count_only)`, **fail 카운트는 `fail_breakdown`에 숫자로 유지**되되 잔여는 `미상`(+상한)이고 코어별 분해의 fail·remaining도 미상(used는 숫자 유지)이다. **잔여가 맨숫자로 나오면 유령 잔여 회귀**(원 결함 재현: 256/256 칩이 'fail'인데 remaining 209가 `reliable: true`로 정상 표시). `origin_log`를 끊은 폴백 경로에서는 같은 원천이 강등 없이 count 감산으로 동작해야 한다(폴백은 감산이 정확 — 과잉 강등도 회귀).
- [ ] **전사 계획 — 선언된 미추적 소비(7c `ab6ac02`)** 🔴: stage의 `source.transfer_log`를 **정확히 문자열 `"none"`**으로 선언하고 자재 요약 조회 → `sources.transfer_log`가 **`connected(untracked)`**이고 `source_degraded` 경고는 **뜨지 않는다**(강등이 아님). `transferred`는 **`null`**(0이면 실패 — "한 칩도 안 썼다"로 읽힌다), `remaining`은 `null` + `remaining_upper_bound`(= 총 − fail) + 경고 `transfer_untracked`. `?bins=`의 각 항목도 `transfer_untracked: true` + 상한, `by_core`의 used/remaining은 **양 경로 모두 null**. ⚠️ **어휘 엄격성 회귀 시험**: 같은 자리를 JSON `null` / `"None"` / `"NONE"`으로 바꾸면 **전부 `missing`**이어야 한다(하나라도 untracked로 통과하면 오타가 깨진 바인딩을 자신만만한 숫자로 바꾼다). 🔴 **[2026-08-04 정정] 이 목록에서 「키 삭제」를 뺐습니다** — 키를 지우면 이제 `missing`이 아니라 `not_declared`이고, 종전 이 줄은 **출하된 동작을 실패로 판정하라고 지시하고 있었습니다.** 키 삭제의 점검은 아래 항목입니다.

- [ ] **전사 계획 — 미선언 보조 역할은 고장이 아니다(`2c2a777`+`101311f`)** 🔴: stage config에서 `transfer_log`·`origin_log`·`fail_sources`·`process_history` **키를 통째로 지우고** 자재 요약 조회 → 각 `sources.<역할>`이 **`not_declared`**, `source_degraded` 경고 **없음**, `remaining`은 **숫자**, `remaining_reliable`은 **`true`**, `transferred`는 **`null`**(가짜 0 금지), 응답에 **`inactive_subtractions`**가 서버 어휘 그대로 실린다.
  - 🔴 **`validate`도 같은 필드를 실어야 한다** — `POST /api/transfer-plan/validate`가 `status: "ok"`를 돌려주면서 `inactive_subtractions`가 **없으면 회귀다**. 판정을 내는 라우트가 정확히 사고가 나는 자리이고, 실제로 그 필드가 요약에만 달려 출하될 뻔했다(QA B1).
  - 🔴 **화면이 그것을 말하는가** — 가용·잔여 칸에 **`*`**가 붙고 ② 각주에 빠진 감산의 **이름**이 인쇄되는가. 표시가 없으면 감산 0회짜리 `8`이 완전 순량 `8`과 화면에서 **바이트 단위로 같다**(실제로 그렇게 출하될 뻔했다 — QA B2). ⚠️ **`≤`가 아니라 `*`**여야 한다(둘은 동시에 참일 수 있어 `≤12*`로 병기된다). ⚠️ 표시가 본문보다 **작으면 회귀**다 — 읽히지 않는 공시는 공시가 아니다.
  - 🔴 **가드 쪽 회귀 시험**: 같은 키를 **남겨 두고 값만 깨뜨리면**(오타 테이블명·`null`) 종전 강등이 **전부 그대로** 나와야 한다. 판정은 진리값이 아니라 **키 존재**다 — 이것이 무너지면 「사이트가 안 쓴다」와 「사이트가 잘못 적었다」가 다시 하나로 접힌다.
  - 🔴 **`total_chips`를 지우면 여전히 `missing`**이어야 한다(분모는 예외). 숫자가 나오면 회귀다.
  - ⚠️ **전 역할을 선언한 환경의 응답은 완화 전과 바이트 단위로 동일**해야 한다(목록이 비면 필드 자체가 없다).
- [ ] **전사 계획 — 캐노니컬 키 바인드(7b `ab6ac02`)** 🔴: `number` 선언 slot 컬럼을 가진 풀에서, 자재 토큰을 **패딩된 형태**(`LOT_01`)로 주고 조회 → **패딩 없는 `LOT_1`과 같은 수**가 나와야 한다(0이나 `미상`이면 회귀 — 운영에서 실제로 가용이 0으로 보이던 결함). 같은 축으로 ⓐ `' 1 '`(공백) ⓑ Float 컬럼의 `1.0` 왕복 ⓒ `map_id` 조합(메타 조회가 실제로 히트하는지 — `align_unavailable`로 떨어지면 실패)까지 확인. **반대 방향도 시험할 것**: `string` 선언 컬럼에서는 `'01'`과 `'1'`이 **서로 다른 키로 남아야** 한다(패딩이 유의미한 사이트를 뭉개면 회귀). 읽을 수 없는 값(`'A1'`)은 지어낸 키가 아니라 원문으로 조회돼 정직하게 빗나간다.
- [ ] **전사 계획 — 이동 허브**: 자재 행 클릭 → 해당 자재 맵으로 이동, 브레드크럼·뒤로가기로 복귀 후 그 자재만 재조회.
- [ ] **브레드크럼 좁은 폭 생존(U7, `a98dc72`)**: 자재 프레임에 들어가 브레드크럼 바를 띄운 채 창 폭을 좁힌다 → 긴 crumb가 **말줄임(…)** 되고, ← 뒤로 버튼은 찌그러지지 않으며, 힌트 문구는 제 줄로 내려간다(바가 가로로 넘치거나 민짜 텍스트로 보이면 `.map-breadcrumb`/`.bc-*` 룰 소실 회귀 — `b35bc9f` CSS 재작성이 실제로 떨궜던 것).
- [ ] **없는 풀 클릭 = 빈 프레임(LOAD 동등성, `280ebf0`)**: 아직 맵이 없는 dt_map 풀(분해 안 되는 원문 ID 포함) 행 클릭 → 에러 토스트가 아니라 **빈 격자 프레임**으로 이동하고, ⚡ Push하면 그 키가 생성된다. 단 목록의 존재 표시는 여전히 `미상`/없음을 유지해야 한다(라우팅은 추측해도 **존재 주장은 추측하지 않는다**).
- [ ] **같은 테이블 연속 빈 맵 로드 = 시드 한 행(U6-1, `95bf072`)** 🔴: legend가 여러 값인 맵을 로드한 뒤 **테이블 전환 없이** 같은 테이블에서 레지스트리 행이 없는 빈 키를 로드 → legend가 **정확히 VALUE 1 한 행**으로 리셋된다(이전 맵의 값들이 남아 있으면 legend 유출 회귀 — 그 상태로 Push하면 이전 맵의 계획이 새 키에 써진다). 반대로 레지스트리 **조회를 5xx로 막고** 로드하면 행이 **보존**되어야 한다(읽기 실패는 "비어 있음"이 아니다).
- [ ] **선언 legend 색 우선(U6, `95bf072`)**: `map_overlay_config.json`의 `default_legend`에 `E1` 행을 색·설명과 함께 선언하고 ⚡ Auto-Paint E1/E2 → E1이 **선언된 색·설명**으로 legend에 추가된다(고정 hex `#8b5cf6`가 아니라). 선언 없는 값(E2)은 팔레트 규칙으로 미사용 색을 받는다. 빈 맵을 열 때의 초기 legend도 선언 행 그대로다(미선언 서버는 VALUE 1 한 행).
- [ ] **페인팅 새로고침 생존(`b35bc9f`+H1 `6db517d`)**: ⚠️ **서버에 이미 행이 있는(비어 있지 않은) 맵에서** 검증할 것 — H1 이전에는 로드 경로가 서버 상태를 초안에 먼저 되써 **비어 있지 않은 맵에서만 전멸**했다(빈 맵 검증은 이 회귀를 못 잡는다). 드래그로 수백 셀 페인팅(클릭 편집만으론 불충분 — 드래그·fill·paste 경로 검증) → 1초쯤 기다렸다 새로고침 → **그림이 돌아오고** 「복구했습니다」 토스트와 함께 패널 헤더에 `● 저장 안 됨 · [⚡ Push]로 저장` 칩이 떠 있다(복구된 편집은 여전히 미저장). Push 성공 후 새로고침 → 칩이 사라지고(초안 삭제) **유령 「복구」 토스트가 뜨지 않는다**(복구 = 화면이 실제로 바뀐 경우만). 다른 세션이 그 사이 저장했다면 서버본이 뜨고 초안은 **조용히 버려지지 않고** 토스트로 드러난다.
- [ ] **새로고침이 마지막 맵을 다시 연다(`280ebf0`)**: 맵 로드 → 새로고침 → 초기 화면이 아니라 **같은 테이블·같은 맵**이 다시 열린다(메타 입력 복원 포함). 자재 프레임에 들어간 채 새로고침 → 프레임이 아니라 **루트 맵**으로 복귀. 테이블이 사라진 뒤엔 조용히 초기 화면(에러 다이얼로그 금지). 좌표계가 확정되지 않은 맵은 복원 시에도 좌표계 선택 모달이 다시 뜨는 것이 **정답**(조용히 추측하면 회귀). ⚠️ **「좌표계가 확정되지 않은」은 `98b48e9`에서 넓어졌다** — 규격 행이 없는 맵만이 아니라 **행이 있어도 START X,Y를 읽을 수 없는 맵**이 포함된다.
- [ ] **DOE 입력 즉응(`280ebf0`)**: DOE 값 행의 STACK·자재 입력을 **첫 클릭**에 커서가 잡히고 즉시 타이핑된다(두 번 클릭 필요하거나 ~0.3초 배경 램프가 보이면 회귀 — 행 선택이 목록 innerHTML 재빌드나 전체 격자 카운트 스캔을 유발하고 있다는 뜻).
- [ ] **오버레이 블록 스타일(`280ebf0` 회귀 방지)**: 좌측 「겹치기」 오버레이 블록이 로드 패널과 같은 스타일로 렌더된다(민짜 HTML로 보이면 `.overlay-box`/`.ov-*` 룰 소실 회귀 — `b35bc9f`의 CSS 재작성이 실제로 떨궜던 것).
- [ ] **전역 토스트**(전 페이지): 에러 토스트 4개를 띄운 뒤 성공 토스트 1개 → **새 토스트가 즉시 사라지지 않고** 가장 오래된 에러가 밀려난다. 토스트를 띄운 채 탭을 30초 이상 백그라운드로 두었다 복귀 → **만료된 토스트가 즉시 정리**된다(누적 없음). 같은 `dedupeKey`의 비-에러 알림 반복 → `… · N건`으로 합쳐진다. 에러는 **합쳐지지 않는다**.
- [ ] **토스트 위치 = 하단 중앙 배너(U3, `a98dc72`)**: 토스트가 **하단 중앙**에 배너로 뜨고, 등장·퇴장이 **opacity만**이다(위로 떠오르는 rise 애니메이션이 보이면 회귀). 우하단에 뜨거나 자재 패널 우하단을 가리면 구 배치 회귀(`--toast-inset-right` 워크어라운드는 삭제됨 — 참조 0 확인 후 제거).

### 2.10 어드민 대시보드 (5탭 IA)

> 🔒 **선행: §2.16을 먼저 통과시킬 것.** 2026-07-27부터 이 절의 모든 화면은 토큰 게이트 뒤에 있다 — 게이트가 막고 있는 빈 표를 "렌더 결함"으로 오진하기 쉽다.

- [ ] **탭 전환**: Overview/File/Chain/AutoUpdate/Enrichment 5탭 모두 렌더 + 콘솔 에러 없음. 해시 라우팅(`#file` 등) 직접 진입 동작, 구 별칭(`#outbox`)이 Chain 탭으로 리다이렉트.
- [ ] **Overview**: 4카드에 헬스 상태·핵심 지표 표시, 최근 이벤트 목록, 카드 클릭 → 해당 탭 딥링크 이동. 파이프라인 헬스 스트립이 탭 전환에도 유지.
- [ ] **Outbox 재시도**(Chain 탭): 실패 outbox 이벤트 단건 재시도 → 상태 전환. "전체 재시도" 동작. 이벤트 진단 → Edit Mapper 딥링크로 에디터 뷰 진입.
- [ ] **코드 에디터(공용 뷰)**: 파일 피커에서 파서 스크립트 열기 → Monaco 편집 → 저장 → 다음 인제션에 반영. `#editor=<path>` 딥링크 직접 진입 동작. dirty 상태에서 다른 파일 선택 시 confirm. (오프라인 등 Monaco CDN 실패 시 인라인 에디터 폴백.)
- [ ] **Config 리로드**: `table_config.json` 수정 → Reload Configs → 웹서버·워커 캐시 리로드(SYSTEM_RELOAD), 신규 테이블 물리 CREATE + 워크스페이스 감시 시작(이슈 #7 해소 확인).

### 2.11 ⚰️ ~~온톨로지 그래프 (승격·뷰어·추적)~~ — **은퇴 · 돌리지 마십시오** (2026-08-14 `2ec78b9`)

> 🔴 **아래 절차는 전부 실패합니다** — 저장소가 DROP되고 라우트가 410입니다. 이 절 대신 **§1.9의 「은퇴가 정직하게 보이는가」 다섯 항목**을 돌리십시오.

<details>
<summary>⚪ 이하 원문(역사 기록)</summary>

#### ~~2.11 온톨로지 그래프 (승격·뷰어·추적)~~

- [ ] 🎯 **자동 승격**: 매핑 대상 테이블 셀 교정 → 재조회 없이 graph_nodes/edges에 반영(워커 `[GraphLatency]` 로그 lag 확인, 실측 기대 ~수백 ms). 교정값 엣지는 provenance=user.
- [ ] **수동 백필**: 메인 툴바 그래프 동기화 버튼(또는 POST `/api/graph/sync`) → 성공 응답 + 테이블 노드/엣지 수 stats 반영.
- [ ] **뷰어 — 탐색**: `/graph.html` 진입 → stats 카운트 카드 표시 → 검색창에 identity 일부 입력 → 자동완성 → 선택 → k-hop 동심원 서브그래프 렌더. 팬·줌 동작, **노드 더블클릭 → 재중심 탐색**, 노드 캡 초과 시 truncated 배지.
- [ ] **뷰어 — Connections 테이블**: 노드 **단일 클릭** → 우측 패널에 선택 노드 정보 + Connections 테이블(방향·엣지 type·상대 노드) 표시, 캔버스 중심은 유지. 비중심 노드는 "서브그래프 단면" 배지 → 전체 이웃 보강 후 배지 제거. 이웃 80행 초과 시 "더 보기"로 증분 렌더(프리징 없음).
- [ ] **뷰어 — 행 클릭 시드 연동**: Connections 테이블 행 클릭 → 해당 노드 중심 재조회 + URL `?label=&identity=` 갱신 + 검색바(label·identity) 반영. 브라우저 뒤로가기 → 이전 중심(URL·검색바·그래프) 복원. 패널 접기(`»`) 토글 후 노드 클릭 시 자동 펼침.
- [ ] **뷰어 — user 강조**: 사람이 교정한 값에서 유래한 엣지가 강조색(`--overwrite`)으로 구분 표시(Connections 테이블 행에도 동일 강조).
- [ ] **뷰어 — 라벨 노드 리스트**: stats 라벨 카드 클릭 → 그 라벨의 노드 목록(identity 오름차순, 로드수/총수 헤더) 표시, 200행 초과 시 "더 보기" 증분 로드. 행 클릭 → 해당 노드 중심 탐색, back → Stats 복귀.
- [ ] **추적 리포트**: 메인 그리드에서 매핑 대상 행 1~여러 개 선택 → 「🕸️ 추적」 → 새 탭 trace.html에 시드 칩 + 라벨별 그룹 테이블 + 타임라인 렌더. depth 변경 → 즉시 재실행, 시간 범위 입력 → 재실행 버튼 동작.
- [ ] **추적 에지 — missing seeds**: 그래프에 없는 시드 포함 시 missing 구분 표시(전체 실패 아님). 시드 21개 이상 선택 시 상한 20 토스트.
- [ ] **크로스링크**: 추적 리포트 노드 → 뷰어(`?label=&identity=`) 이동, 뷰어 → 추적 리포트 역방향 이동.
- [ ] ⚰️ **[2026-08-14] 이 항목은 이제 「항상 숨는다」가 정답입니다** — 판정 라우트가 410이라 어느 테이블에서도 안 뜹니다. **진입점 자동 표시**: 매핑 없는 테이블에서는 「🕸️ 추적」 버튼 숨김, 매핑 대상 테이블 전환 시 노출.

</details>

### 2.12 듀얼 테마

- [ ] **토글**: 메인 툴바 테마 버튼 → 라이트↔다크 전환, AG-Grid 포함 전 영역 재도색(그리드 재생성/데이터 소실 없음).
- [ ] **유지/전파**: 전환 후 새로고침·타 페이지(enrichment 등) 이동 시 테마 유지(localStorage). 첫 로드 시 흰 화면 깜빡임(FOUC) 없음.
- [ ] **전 페이지 렌더**: admin/map_editor/enrichment 각 페이지가 양 테마에서 가독성 유지 — 각 페이지 헤더의 자체 토글 버튼(`data-theme-toggle`, 4페이지 모두 존재)으로 직접 전환하며 확인.

### 2.13 WS 실시간 반영

- [ ] 🎯 **다중 클라이언트 반영**: 브라우저 창 2개에서 같은 테이블 열기 → A창 편집 → B창에 체감 즉시(100ms 수준) 델타 반영 + 변경 셀 플래시. 전체 리프레시(스크롤 위치 소실) 아님.
- [ ] **행 생성/삭제 반영**: A창 행 추가/삭제 → B창 그리드에 행 추가/제거 + 총계 갱신.
- [ ] **재연결 에지**: 서버 재시작 → 클라이언트가 백오프 재연결 → 재연결 후 편집·수신 정상(수동 새로고침 불필요).
- [ ] **인제션 브로드캐스트**: 파일 드롭 → 열려 있는 모든 창에 진행/완료 토스트 + 그리드 갱신.

**소켓이 무엇에도 걸려 있지 않은가 (2026-08-04 `2b90009`+`4132704`+`21da55e`)** — 사용자 신고의 증상은 「실패한 `/ws`」가 아니라 **`/ws` 요청 자체가 없었다**였다.

- [ ] 🎯 **소켓이 REST보다 먼저 나간다**: 개발자도구 Network를 열고 페이지 로드 → **`/ws`가 `/tables` 등 REST 호출보다 먼저** 뜬다. 🔴 **「없음」이 이 항목이 잡는 결함이다** — 실패한 요청이 아니라 **요청이 아예 없는 것**을 본다.
- [ ] 🎯 **응답 없는 경로에서 8초 안에 포기하고 재시도한다**: 백엔드로 가는 경로를 블랙홀로 만든 뒤(방화벽 DROP 등) → **8초 안에** 배지가 `WS: 응답 없음 1회`로 바뀌고 백오프 재시도가 이어진다. ⚠️ **끊긴 것(RST)이 아니라 삼켜지는 것**이라야 이 경로를 탄다 — 거절되면 `WS: DISCONNECTED`가 정상이다.
- [ ] 🎯 **배지가 세 상태를 구별한다**: ① `WS: Connecting`(= **아무도 배지를 쓴 적이 없다** — `init()`이 `initWebSocket`에 닿지 못했다는 뜻이고 그 자체가 결함 신호) ② `WS: 연결 시도 N`(만들었고 협상 중) ③ `WS: 응답 없음 N회`(경로가 삼킴). 🔴 **셋 중 둘이 같은 글자면 회귀다.**
- [ ] **정리가 재진입하지 않는다**: 감시견이 발화한 뒤 재연결 사다리가 **한 칸만** 올라간다(콘솔에 같은 시도 번호가 두 번 찍히면 핸들러를 `null`로 만들기 전에 `close()`한 것 = 회귀).
- [ ] **목록이 두 번 로드되지 않는다**: 소켓이 먼저 뜨면 `onopen`의 부트스트랩이 `init()`의 `loadTables()`와 겹친다 → **스키마 로드·그리드 재생성이 각 1회**인지(걸쇠 `tablesLoadInFlight`가 같은 프라미스를 공유해야 하고, **버리면** 목록 없이 진행한다).

### 2.14 데스크톱 래퍼

- [ ] **기동**: `python run_decoupled_app.py` → QtWebEngine 셸에 메인 그리드 로드(`?client=desktop`).
- [ ] **OS 드래그앤드롭**: 파일을 셸 창에 드롭 → 현재 테이블로 업로드·인제션 완료.
- [ ] **네이티브 다운로드**: CSV export → OS 파일 저장 다이얼로그 표시·저장.
- [ ] **다운로드 배포**: 웹에서 GET `/api/download/client` → 셸 패키지 다운로드.

### 2.15 운영 감시 🎯

> ⚠️ **아래 정지·종료 항목은 격리 환경에서 하십시오** — `devenv.py up`(:8081) + `ASSY_API_PORT=8081`. 운영 스택에서 워커를 죽여 보는 것은 실데이터 유입을 끊는 행위입니다.

- [ ] **헬스 기본**: `curl -i http://localhost:8080/health` → **200 + `Content-Type: application/json`**. 본문 `status: ok`, `checks.workers`에 워커 4종이 모두 있고 전부 `ok`.
- [ ] **catch-all과 구분**: 아무 오타 경로(`/healthz` 등) → **HTML 200**이 온다. `/health`만 JSON인지 확인(감시 대상 경로를 틀리면 죽은 서버가 살아 보인다).
- [ ] 🎯 **죽으면 되살아난다**: 워커 프로세스 하나를 강제 종료 → 로그에 재시작 줄 + `supervisor_status.json`의 `restarts` 증가 → 수십 초 내 `/health` 다시 `ok`.
- [ ] 🎯 **살아 있는데 멈춘 것을 잡는다**: 워커를 **정지(suspend)**시킨다(kill 아님) → **약 1분 뒤**(마지막 박동 기준 60초) `/health`가 **503**, 해당 워커 `status: wedged`. 재개하면 곧(초 단위) `ok`, pid 불변. *(pid만 보는 감시로는 절대 안 잡히는 케이스 — 이 항목이 이 절의 핵심이다)*
- [ ] 🎯 **박동하는데 일이 안 되는 것을 잡는다**(`stalled`): 인제션 작업을 claim한 상태에서 **작업만** 멈춘다(워커 루프는 계속 돌게 둘 것) → **약 5분 뒤**(300초) 해당 워커 `status: stalled` + 503. ⚠️ **`wedged` 시험으로 이 항목을 대신할 수 없다** — 임계도 조건도 다르고, 실제 사고는 워처의 3초 재시도 폴러가 계속 박동하는 동안 인제션이 멈춘 형태였다. 또 더 구체적인 판정을 덮지 않는지 확인: `down`/`wedged`인 워커는 `stalled`로 바뀌면 안 된다.
- [ ] **박동 pid 위조 방지**(`foreign_beat`): 같은 역할 이름으로 다른 프로세스가 박동 파일을 쓰게 한 뒤 → 감시자가 띄운 pid와 불일치하므로 `ok`가 아니라 `foreign_beat`가 뜬다(유령 프로세스가 정체를 가리지 못한다).
- [ ] **영구 실패는 조용히 넘어가지 않는다**: 자식이 즉사하도록 만들면(예: 잘못된 config) 5회 재시작 후 **`FAILED` 배너 로그** + `/health` 503이 **계속** 유지된다(무한 재시작 금지).

**중복 기동 거절 (2026-08-04 `06b7761`)** — 재시도로 고칠 수 없는 실패는 예산을 태우기 전에 이름을 얻어야 한다.

- [ ] 🎯 **스택이 떠 있는 상태에서 런처를 또 돌린다** → **1초 안에 거절**하고 **아무것도 기동하지 않는다.** 배너가 포트를 쥔 **PID와 프로세스 이름**을 대고 `taskkill /PID <pid> /T /F`를 준다. 🔴 **이미 도는 스택이 멀쩡한지 확인**하는 것까지가 이 항목이다(가드가 남의 프로세스를 건드리면 회귀).
- [ ] **질문만 하는 형태**: `python run_decoupled_app.py --preflight-only` → 포트가 비었으면 **`Preflight OK: port 8080 is free.`**(⚠️ **[2026-08-14 정정] 종전 「ports 8080 and 8090 are free.」는 그래프 워커 은퇴로 거짓이 됐다** — 프로브 대상이 하나다) + **exit 0**, 물려 있으면 거절 배너 + **exit 1**.

**스키마 드리프트 부팅 점검 (2026-08-05 `f6406b1` · `server/schema_drift.py`)** — 「마이그레이션이 돌아야 한다」는 배포 사실을 **아무도 안 나르고 있었다.** 개발·테스트 박스에서는 절대 안 보이고 **오직 운영 화면에서만** 드러난다.

- [ ] 🎯 **드리프트난 DB에서 배너가 뜨고, 그래도 기동한다**: 매핑된 시스템 테이블 하나에서 컬럼을 지운 DB로 `--preflight-only` → **`TABLE-DOWN` 배너**가 테이블·컬럼·**「이 컬럼을 읽지 않는 코드까지 포함해 그 테이블 전체가 죽는다」**를 말하고, 평결이 **어느 마이그레이션을 돌려라**까지 간다. 이어서 실제 기동 → 🔴 **거절하지 않고 뜬다.** **막으면 회귀다** — 컬럼 하나가 무인 재기동에 스택 전체를 계속 죽여 놓을 권한을 갖게 된다.
- [ ] 🎯 **종료 코드는 포트만 본다**: 위 드리프트 상태에서 `--preflight-only`의 **exit이 0**이다(포트가 비었다면). **1이 나오면 회귀** — 드리프트가 재기동을 거절로 바꾸면 안 된다. 반대로 포트를 물린 채 돌리면 드리프트와 무관하게 **exit 1**.
- [ ] 🎯 **평결이 트리에서 유도된다**: `server/migrations/`에 `ADD COLUMN`이 실재하는 컬럼을 지우고 점검 → **「기록된 마이그레이션 없음」이 아니라 그 파일 이름**이 나온다. 🔴 **`MIGRATION_OWNER` 딕트에 손으로 적혀 있는지와 무관해야 한다** — 손으로 적은 표가 낡아 **실제로 테이블을 죽인 컬럼 둘이 「기록 없음」으로 나온 것**이 이 수리의 계기다.
- [ ] 🎯 **동적 테이블이 점검 범위에 있다**: 배너의 점검 대상 수가 **시스템 테이블만이 아니다**(config 선언 테이블 포함). 🔴 **운영자 화면이 전부 얹혀 있는 쪽이 빠지면** 이 점검은 26개 중 12개만 보고 나머지를 건강하다고 답한다 — 그것이 원 결함이다.
- [ ] 🎯 **[2026-08-13 `eb700e5`] 자기 기동이 고치는 컬럼은 「할 일 없음」으로 나온다**: **config로 선언한 동적 테이블**에 컬럼을 하나 더 선언하고 마이그레이션 없이 `--preflight-only` → 심각도가 **`SELF-HEALING`**이고 문구가 **「할 일 없음, 마이그레이션을 쓰지 마라」**를 말한다. 🔴 **`TABLE-DOWN`이 나오면 회귀다** — 제품 소유자가 그 말을 믿고 조치·재기동한 뒤 항목이 사라진 것을 발견한 것이 이 수리의 계기다. 이어서 실제 기동 → **컬럼이 생기고 다음 점검에서 사라진다.**
- [ ] 🔴 **강등이지 은닉이 아니다**: 위 항목에서 **테이블·컬럼·수동 `ALTER`·에스컬레이션 경로가 그대로 인쇄**되는지 확인. 안 보이면 회귀다 — **재기동 뒤 두 번째로 보이는 것**이 「그 `ALTER`가 실패 중」의 유일한 신호다. 그리고 드리프트가 이것뿐이면 **빨간 블록이 아예 안 열린다**(헤드라인 카운트에서 빠진다).
- [ ] 🔴 **시스템 테이블은 강등되지 않는다**: `database/models.py`에 ORM 클래스로 선언된 **시스템** 테이블에서 컬럼을 지우고 점검 → 여전히 **`TABLE-DOWN`**이다(어떤 부팅 경로도 그것을 `ALTER`하지 않는다 — 2026-08-05 사고의 모양). **`SELF-HEALING`으로 나오면 즉시 결함.**
- [ ] ⚠️ **대소문자가 어긋난 컬럼은 강등되지 않지만 «고쳐지지도 않는다»**: 선언 `Foo` / 저장 `foo` → 매 부팅 보고되고 수리기는 **영구히 건너뛴다**(실패 로그조차 없다). 이 변경이 만든 결함이 아니라 **이번에 보이게 된 것**이고, 배너가 그것을 `SELF-HEALING`으로 부르면 회귀다.
- [ ] ⚠️ **타입 불일치는 이 점검의 능력 밖이다** — 컬럼 타입만 바꿔 놓고 초록이 나오는 것은 **정상**이다(고정 테스트 있음). 「타입도 잡히겠지」로 이 축을 점검하지 마라.
- [ ] **두 자리에서 발화한다**: 런처(`--preflight-only` 포함)와 **웹서버 기동 로그** 양쪽에 배너가 있다. 웹서버 쪽은 자기 outbox 마이그레이션 **뒤**여야 한다(고쳐지려는 DB를 고장으로 읽지 않도록).
- [ ] **배너에 접속 비밀번호가 없다**: DB URL을 찍는 줄에 자격증명이 노출되지 않는다.
- [ ] **점검이 환경을 오염시키지 않는다**: 점검 후 `TESTING`이 남아 있지 않다. 🔴 **런처는 `os.environ.copy()`를 자식 다섯에 물려주므로**, 새면 웹서버가 자기 부팅 DDL을 거부하고 워커가 전부 일을 건너뛴다(관측: 기동 직후 워커 로그가 조용하고 DDL이 안 돈다).
- [ ] ⚠️ **`/health`로 이 축을 점검하지 마라** — 드리프트난 스택은 `/health`가 **정상 200**을 답한다. 관측 지점은 배너뿐이다([DEPLOY_SETUP §6.1](../guide/DEPLOY_SETUP.md) · [ROLLBACK_PROCEDURE §6](../guide/ROLLBACK_PROCEDURE.md)).

**인자 관문 (2026-08-04 `63b17f7` · `server/launcher_args.py`)** — 🔴 **종전 이 자리는 *「`--help`가 없고 오타는 조용히 무시되므로 철자를 확인할 것」*이라고 적고 있었고, 그 문장은 이제 거짓이다.** 그대로 두면 점검자에게 **고쳐진 결함을 통과시키라고** 지시하는 셈이다.

- [ ] 🎯 **오타는 거절이고, 아무것도 뜨지 않는다**: `python run_decoupled_app.py --server_only`(밑줄) → 거절 배너 + **exit 2**, **자식 0개**. 배너가 `이것을 쓰려던 것입니까? / did you mean:  --server-only`로 **가장 가까운 철자를 제안**하되 **자동 교정하지 않는다**. 🔴 **이미 도는 스택을 건드리지 않는다**는 문장(`Nothing was started. Nothing that is already running was touched.`)까지 확인.
- [ ] **거절이 `--help`보다 앞이다**: `--help --oops` → 도움말이 아니라 **거절**. (도움말만 찍고 끝나면 오타가 다시 조용해진다.)
- [ ] **`--help`가 있다**: `python run_decoupled_app.py --help` → 플래그 6개(`--server-only`·`--no-client`·`--reload`·`--preflight-only`·`--help`·`-h`)가 한 줄씩 + **exit 0**, stdout으로 나간다(사고가 아니므로 로그가 아니다).
- [ ] **기존 철자가 그대로다**: `--no-client`·`--server-only` 동의어, **순서 무관**, 조합 가능. 🔴 **운영자의 손이 기억하는 명령이 바뀌면 회귀다.**
- [ ] **배너가 한국어 콘솔에서 안 깨진다**: cp949라 `―`(U+2015)만 쓴다 — `—`가 섞이면 **줄 전체가 사라져** 거절이 무동작과 같아진다.
- [ ] 🎯 **가드는 열려 실패해야 한다**: 프로브가 예외를 내는 상황(예: psutil 부재)에서 런처가 **거절하지 않고 경고만 남기고 기동**하는지. 🔴 **가드가 시스템이 안 뜨는 이유가 되면 회귀다.**
- [ ] 🎯 **감시자도 같은 판정을 한다**: 포트를 다른 프로세스에 물린 채 자식 하나를 예산 소진까지 죽게 만들면 → **동료 규칙보다 먼저** 포트 프로브가 돌아 상태 파일의 `terminal_verdict`가 **`port_conflict`**가 된다(`broken_child`도 `RETRYING_CORRELATED`도 아니다). 문구가 *"retrying cannot take a port away from the process that owns it"*를 말하는지 확인.
- [ ] **포트 안 잡는 자식은 프로브 대상이 아니다**: `ports`를 선언하지 않은 자식이 영구 실패하면 평결이 **`broken_child`**여야 한다(프로브가 아예 호출되지 않는다 — 매 재시작마다 찌르면 감시가 곧 부하다).
- [ ] 🎯 **자식의 죽는 이유가 파일에 남는다**: 자식이 bind 에러로 죽게 만든 뒤 데이터 루트의 `server_stdout.log`(또는 해당 `*_stdout.log`)에 `=== <name> started <시각> pid=<pid> cmd=<...> ===` 헤더와 **그 에러**가 있는지. 🔴 **한글 로그가 깨지지 않아야 한다** — 로그 펌프는 **바이트를 그대로** 통과시키므로 자식이 cp949로 찍어도 그대로 남는다(디코딩하면 그 줄이 사라진다). 보관은 자식당 **20 MB + `.1` 백업 하나**.

**두 스택 모두에서 받는가 (2026-08-04)** — 이름 해석 하나 때문에 WebSocket이 영구 CONNECTING에 걸린 사고의 회귀 점검. 🔴 **HTTP만 확인하면 절대 못 잡는다**: 브라우저가 IPv4로 폴백해 페이지는 멀쩡히 뜨고 **WS만** 멈춘다.

- [ ] 🎯 **리스너가 양쪽에 있다**: `netstat -ano | findstr :8080` → **`0.0.0.0:8080`과 `[::]:8080`이 둘 다** LISTENING. 🔴 **한쪽만 있으면 그 자체가 결함이다** — `0.0.0.0`만이면 `localhost` 접속이 깨지고, `[::]`만이면 IPv4 클라이언트가 전부 깨진다(후자가 더 나쁘다).
- [ ] 🎯 **`localhost`로 WS가 붙는다**: 브라우저를 `http://localhost:8080`으로 열고 개발자도구 Network → WS가 **101 Switching Protocols**. ⚠️ **페이지가 떴다는 것은 증거가 아니다.** Windows에서 `localhost`는 `::1`을 먼저 고르므로 이 항목이 IPv6 경로의 유일한 실사용 점검이다.
- [ ] **IPv4도 그대로 받는다**: `http://127.0.0.1:8080`과 **사내망 IP** 양쪽에서도 WS가 101. 부주의한 듀얼스택 수리는 IPv6를 얻고 **IPv4를 잃는다** — 그러면 운영자는 사용자 신고로만 알게 된다.
- [ ] **운영자가 실제 주소를 읽는다**: 런처 콘솔/`launcher.log`의 `API 리슨 주소: [::] + 0.0.0.0 : 포트 8080`. ⚠️ uvicorn 자신의 `Uvicorn running on http://:8080`은 **듣고 있는 주소를 하나도 대지 못한다** — 판정은 런처 줄로 한다.
- [ ] **좁히는 레버는 그대로다**: `ASSY_API_HOST=127.0.0.1`로 기동하면 `netstat`에 **`127.0.0.1:8080` 하나만** 뜬다(IPv6 리스너 없음). 🔴 **명시 지정이 넓어지면 회귀다.**
- [ ] **적체는 나이로 본다**: 대형 파일(수만 행) 적재 중 `/health`가 `ok`를 유지하는지. 건수가 많다는 이유만으로 경보가 뜨면 회귀다.
- [ ] **격리 워처 관문**: `DATABASE_URL`을 운영으로 둔 채 `devenv.py watcher-up` → **REFUSED로 기동 거부**(워처 프로세스가 뜨지 않음). 로그 파일이 새로 생기지 않는 것까지 확인.
- [ ] **격리 로그 누수 없음**: 격리 스택을 돌린 전후로 `server/*.log` 5종의 크기·mtime이 불변인지.
- [ ] **config 백업이 살아 있다**(C3, 2026-07-28): `backup_config.py check` → `ok`. `/health`의 `checks.config_backup.status`도 `ok`이고 `problems`에 백업 줄이 없다.
- [ ] 🎯 **멈춘 백업이 보인다**: 최신 스냅샷을 잠시 다른 이름으로 옮긴다 → `/health`가 **`degraded`(HTTP는 200 유지)** + `problems`에 `config backup: ...` 한 줄. 되돌리면 사라진다(캐시 60초). ⚠️ **503이 되면 회귀다** — 백업 부재로 멀쩡한 스택을 재기동시키면 안 된다.
- [ ] 🎯 **복원이 실제로 된다**(격리 환경에서만): 스냅샷을 뜬 뒤 `transfer_plan_config.json`을 깨뜨리고 → `restore <파일> --yes` → `GET /api/transfer-plan/stages`의 `target_map.table`이 **되돌아오는지**. 실측 0.17초. *(파일이 바뀐 것은 증거가 아니다 — 도메인 응답으로 판정한다)*
- [ ] **연속 저장이 버려지지 않는지**(2026-07-29 H2로 해소된 함정의 회귀 점검): `table_config.json`을 고친 직후(1초 이내) 곧바로 복원한 뒤, **`information_schema`의 물리 컬럼이 최종 디스크 선언과 일치**하는지 확인. 예전에는 두 번째 쓰기가 통째로 버려져 파일은 옳은데 시스템이 옛 선언을 서빙했다. 반영은 **마지막 쓰기 후 약 1초**이므로 즉시 확인하지 말고 1초 기다린다.
- [ ] **저장 방식 무관**(#9/H3): 제자리 저장 · 같은 폴더 temp+rename · **다른 폴더 temp+rename** 세 가지 모두에서 ALTER가 반영되는지. 세 번째는 `moved` 이벤트가 아예 없어 예전에는 무음 누락이었다.
- [ ] **BOM 붙은 config로 재기동**(H1): PowerShell `Set-Content -Encoding utf8`(UTF-8 BOM) 또는 `>` 리다이렉트(UTF-16)로 저장한 `table_config.json`으로 웹서버가 **정상 기동**하는지. 예전에는 이 상태로 영영 안 떴다.
- [ ] **설치 스크립트 안전성**: `install_product_tables.py`(인자 없음) → **아무것도 쓰지 않고** 할 일만 출력. `--apply` 후 현장 항목의 키 순서·들여쓰기가 그대로인지.

### 2.16 접근 통제 🎯 — 2026-07-27 신설 (`90e284f`)

> 🚨 **전 항목을 사내망 평문 HTTP 주소(`http://<사내IP>:8080`)에서 점검한다.** `localhost`/`127.0.0.1`에서 통과한 것은 **아무것도 증명하지 않는다** — 공격면도 사용자도 그 주소에 있지 않다. 이 절이 닫는 결함 중 하나는 실제로 라이브에서 열려 있었고, 로컬에서는 보이지 않았다.
> **순서가 있다.** 번들 확인(첫 항목) → 미설정 상태 → 설정 상태. 번들 확인을 건너뛰고 토큰을 켜면 어드민에서 잠기고, 되돌리려면 보안 조치를 취소해야 한다.

**A. 토큰을 켜기 전에**

- [ ] 🎯 **번들 선행 확인**: `grep -c X-Admin-Token client2/dist/assets/admin-*.js` → **1 이상**. **0이면 여기서 멈추고** `cd client2 && npm run build` 후 `dist/` 커밋. 0인 채로 토큰을 켜면 어드민 페이지가 401만 받고 **프롬프트조차 뜨지 않는다**(서버가 서빙하는 것은 소스가 아니라 번들이다).
- [ ] 🎯 **traversal은 404다**(토큰 설정 여부와 무관 — **인증 없이** 확인할 것):
  ```bash
  # 🚨 --path-as-is 가 없으면 curl이 클라이언트에서 ../를 접어 버린다.
  #    그 경우 서버에는 traversal이 도착조차 하지 않고, 404를 보고 "닫혔다"고 오판한다.
  H=http://<사내IP>:8080
  curl -si --path-as-is "$H/../../server/config/table_config.json"  | head -1   # 404
  curl -si --path-as-is "$H/../../../../../../Windows/win.ini"      | head -1   # 404
  curl -si --path-as-is "$H/../../server/admin_auth.py"             | head -1   # 404
  curl -si --path-as-is "$H/%2e%2e%2f%2e%2e%2fserver/admin_auth.py" | head -1   # 404 (인코딩 변형)
  curl -si "$H/index.html"                                          | head -1   # 200 (정상 서빙은 살아 있어야 한다)
  ```
  ⚠️ **상태코드만 보지 말고 본문을 볼 것.** 200에 SPA HTML이 오는 것은 catch-all의 정상 동작이고, **파일 내용이 오면 실패**다. 위 4종 외에 `..%5c`(백슬래시)·절대경로 `/C:/Windows/win.ini`·드라이브 상대 `C:server/admin_auth.py`도 던진다 — **문자 denylist로 막은 구현이라면 바로 여기서 갈린다.**
  ⚠️ **403이 와도 회귀다.** 탈출이 파싱됐다는 사실조차 확인해 주면 안 된다.
  > 브라우저 주소창으로는 이 점검을 할 수 없다(브라우저도 `../`를 접는다). `curl --path-as-is` 또는 raw 소켓으로만 가능하다.

**B. 토큰 미설정 상태 (`ASSY_ADMIN_TOKEN` 없이 기동)**

- [ ] **배너가 상태를 말한다**: 기동 로그 첫머리에 `[admin-auth] ... is NOT set`이 **WARNING**으로, 무엇이 꺼졌고 어떤 변수를 설정해야 하는지 담겨 있다.
- [ ] 🎯 **위험한 셋만 막힌다**(2026-07-31 — 종전 「둘」에 하나 추가): 어드민 코드 에디터 저장(`POST /admin/scripts/code`) · AutoUpdate Run Now · **소급 실행(`POST /admin/retroactive/{op}/run`)** → **503**, 본문에 "환경변수를 설정하고 재시작하라"는 문장. **그 문장이 화면 토스트로 보이는지** 확인(삼키면 "저장 중 오류"만 남아 503 분기의 존재 이유가 사라진다).
- [ ] **나머지는 열려 있다**: 5탭 전부 정상 렌더 + 토큰 프롬프트가 **뜨지 않음**. (첫 재기동에 운영자가 어드민 전체에서 잠기지 않게 한 의도된 상태다.)

**C. 토큰 설정 상태 (스택 전체 재기동 후)**

- [ ] **배너 `INFO`**: `[admin-auth] ... is set`.
- [ ] 🎯 **헤더 없이는 안 된다**: `curl -si http://<사내IP>:8080/admin/chain/rules | head -1` → **401**, 응답에 `WWW-Authenticate: X-Admin-Token`. 틀린 토큰 → **403** + 같은 헤더. 올바른 토큰(`-H "X-Admin-Token: <값>"`) → 200.
- [ ] **`/health`는 계속 무인증**: 헤더 없이 `curl -i .../health` → **JSON 200**. 401이 오면 회귀다(잠그면 감시가 무의미해진다).
- [ ] 🎯 **비-ASCII 토큰은 잠그지 않고 거부된다**: `ASSY_ADMIN_TOKEN=관리자토큰` 으로 기동 → 배너가 **`ERROR`**, 그리고 상태는 **미설정과 동일**(strict 3개 503, 나머지 열림). **"is set"이라고 안심시켜 놓고 올바른 토큰에 403을 돌려주면 실패** — 이게 복구 불능 상태를 만드는 경로다.
- [ ] 🎯 **워커가 토큰을 못 받으면 조용히 멈춘다**: 워커를 런처 밖에서 **변수 없는 셸**로 띄우고 파일 드롭 → 워커 로그에 `API notification failed: ... -> 401`이 쌓이고 **그리드가 갱신되지 않는다**. 런처(`run_decoupled_app.py`)로 정상 기동하면 워커가 환경을 상속해 별도 설정 없이 동작.
- [ ] **어드민 프롬프트 1회**: 어드민 페이지 최초 진입 → 프롬프트 1회 → 붙여넣기 → 5탭 정상. 새로고침해도 다시 묻지 않음(`localStorage`).
- [ ] 🎯 **정상 토큰이 파괴되지 않는다**(가장 비싸게 산 항목): 격리 서버(`devenv.py up`)에서 **라이브 트리로 쓰기**를 시도해 `_resolve_admin_script_path`의 **격리 403**을 유발 → 토큰 프롬프트가 **뜨면 안 된다**(그 403에는 `WWW-Authenticate`가 없다). 뜬 뒤 아무거나 입력하면 **멀쩡한 토큰이 덮어써진다.**
- [ ] **동시 401 → 프롬프트 1회**: 토큰을 지우고 Overview 진입(동시 요청 다수) → 모달이 **하나만** 뜬다. 두 번째 모달이 **올바른 토큰을 두고** "거부되었습니다"라고 말하면 세대 카운터 회귀.
- [ ] **취소가 토큰을 지우지 않는다**: 프롬프트에서 취소(Esc) → 토스트 안내 후 **더 묻지 않음**. 30초 갱신 타이머가 모달을 반복해 띄우면 실패. 저장돼 있던 토큰이 빈 문자열로 덮어써져도 실패.
**D. 내부 통지 진단 (2026-07-30 `23a346d`)** — 이 넷은 **실패했을 때 무엇을 봐야 하는지**를 점검한다. 원 사고에서 세 시간이 든 판별이다.

- [ ] 🎯 **4xx가 누가 거절했는지 말한다**: 워커를 **변수 없는 셸**로 띄우고 파일 드롭 → 워커 로그의 통지 실패 줄에 **`admin-gate=yes token-fingerprint=none`** + "이 프로세스에 변수가 없다"는 REMEDY가 함께 나온다. 이어서 **다른 토큰**을 든 셸로 띄우면 `admin-gate=yes` + **403** + "서버가 다른 토큰을 쥐고 있다, 지문을 배너와 대조하고 **트리 전체**를 한 셸에서 재기동하라". 숫자만 있고 진단이 없으면 회귀.
- [ ] 🎯 **`admin-gate=no`는 우리가 아니다**: `/internal/events/*`를 가로채는 것(프록시·다른 프로세스)을 앞에 두고 통지 → 로그가 **`admin-gate=no`** + *"NOT AN ADMIN-TOKEN FAILURE"* + 본 헤더 에코. 🔴 이 상태에서 **토큰을 고치라고 안내하면 회귀**다 — 실제 사고에서 그 오안내가 진단을 몇 시간 늦췄다. 판정 근거는 `WWW-Authenticate: X-Admin-Token`의 **정확 일치**이므로, 프록시가 `WWW-Authenticate: Basic realm=…`을 붙여도 `no`로 읽혀야 한다.
- [ ] **기동 로그가 프록시를 먼저 말한다**: 데몬들(`run_watcher`·`chain_ingestion_worker` — ⚰️ **[2026-08-14] `graph_sync_worker` 은퇴**) 기동 로그에 `[internal-events] http://127.0.0.1:8080/health -> 200, direct (proxy bypassed). proxy-env=…`가 **정상일 때도** 찍힌다. **연결 거부는 `INFO`**(기동 순서상 정상 — 여기에 경고를 울리면 아무도 안 읽는다).
- [ ] 🎯 **아픈 스택을 프록시로 고발하지 않는다** (2026-08-04): `/health`가 **503**을 돌려주는 상태를 만든다(체크 하나만 실패해도 그렇게 된다 — `health.HTTP_UNHEALTHY`). 데몬 기동 로그가 **`WARNING`** + `answered by THIS application reporting status='…'` + `Problems:` 목록으로 나와야 한다. 🔴 **여기서 프록시 장문(`ERROR`)이 뜨면 회귀다** — 2026-07-31에 실제 원인이 **중복 런처**였는데 체인 워커와 그래프 싱크 워커가 나란히 이 장문을 찍어 진단을 오도했다. 판별자는 상태코드가 아니라 응답 **BODY**이고(`internal_event_client.own_health_payload` — `status` 키 + **dict인** `checks`가 함께 있어야 우리 것), 프록시의 HTML 에러 페이지는 그 둘을 동시에 만족시킬 수 없다.
- [ ] **그래도 앞단 탐지는 살아 있다**: `/health`에 **우리 모양이 아닌 body**로 비-200을 내는 것을 앞에 두면 여전히 **`ERROR`** + `/health carries NO admin gate …` + `answered by '<이름>'`이 나와야 한다(방아쇠만 좁힌 것이지 탐지를 없앤 게 아니다 — 이 사이트의 사내 프록시는 여전히 `127.0.0.1`에 `<local>`을 안 먹인다).
- [ ] **발신자가 자기 세션을 만들지 않는다**: `conda run -n assy_manager pytest server/tests/test_admin_auth.py -k "own_client or trust_the_environment"` → 통과. 새 워커가 `requests.post(`를 직접 쓰면 **여기서 빨개져야** 한다(같은 결함이 발신자별로 세 번 재발한 자리라, 규칙이 아니라 테스트로 못박혀 있다). ⚠️ **`NO_PROXY` 환경변수를 이 문제의 처방으로 쓰지 마라** — 그 트리의 모든 자식이 프록시를 못 타게 되어 자동 업데이트가 죽는다([DEPLOY_SETUP §1-5](../guide/DEPLOY_SETUP.md)).

**E. 그 밖**

- [ ] **맨 `fetch` 잔존 없음**: `client2/src/`에서 `adminFetch`를 거치지 않고 `/admin/` 경로를 직접 부르는 곳이 **0건**이어야 한다.
  ```bash
  grep -rn 'fetch(`${API_BASE}/admin/' client2/src/     # 0건
  ```
  남은 호출부는 **미설정 서버에서 멀쩡히 동작하다가 운영에서만** 401이 난다 — 개발 환경에서 절대 안 잡히는 부류다.
- [ ] **라우트 커버리지 회귀**: `pytest server/tests/test_admin_auth.py` 통과.
- [ ] ⚠️ **열거가 못 잡는 축은 사람이 본다**: `grep -rn '@app.websocket\|app.mount' server/main.py` → `/admin` 접두 라우트가 새로 생겼는지 눈으로 확인. `route.methods`가 `None`이라 **위 테스트는 이것을 통과시킨다**.

*이 문서는 기능 병합 시마다 doc-keeper가 갱신한다 — [CONTRIBUTING](../process/CONTRIBUTING.md) · 소유 매핑: [DOC_OWNERSHIP](../process/DOC_OWNERSHIP.md).*
