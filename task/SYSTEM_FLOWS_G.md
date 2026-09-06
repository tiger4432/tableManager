# 2차 실측 — 다섯 흐름 (⑨ · ⑭ · ⑮ · ⑰ · ㉒)

> **대상:** `docs/architecture/SYSTEM_FLOWS.md` §2 의 ⑨ Enrichment Queue · ⑭ 범용 맵 오버레이 ·
> ⑮ 전사 계획(본딩/DT) · ⑰ 어드민 대시보드(생애주기 5탭) · ㉒ 데스크톱 래퍼·듀얼 테마
> **칸 정의는 §1 · 채우는 규칙은 §3 · 체크리스트 추출은 §4 를 그대로 따랐다.**
> ⛔ 이 파일은 실측 원본이다. `SYSTEM_FLOWS.md` 병합은 총괄이 한다.

---

## 0. 🔴 측정 환경 선언 — 「어느 상태에서 쟀나」 (**세션 중에 «바뀌었다»**)

지시서가 「map2 를 건드리는 것을 재기 전에 NUL 바이트가 고쳐졌는지 확인하고, **어느 상태에서
쟀는지 밝히라**」고 요구했다. 🔴 **답이 하나가 아니다 — 이 세션 «도중»에 고쳐졌다.**

```
착수 시점  HEAD 72f5b752
  client2/src/map2/main.js   156,321 바이트 · 2,610줄 · NUL 1 — 오프셋 28521 (479행)
  그 자리                     const signature = options.map(o => o.value).join('\x00');
  rg 동작                     디렉터리 훑기에서 «목록에 안 뜸» (경고 없이 조용히 빠짐)

세션 중    78a88e7f  feat(walk): the form's five arguments reach the wire …  (09-06 10:40:53)
           -> 이 커밋이 map2/main.js 를 건드렸다

측정 종료 시점 (재검)
  client2/src/map2/main.js   159,298 바이트 · 2,615줄 · NUL «0»
  rg 동작                     rg -l "me2" client2/src/map2/  ->  main.js 가 «목록에 뜬다» ✅
```
🟢 **그러므로 map2/main.js 는 «고쳐졌다».** 다만 **내 ⑭·⑮ 측정은 전부 `grep -a`/`Read` 로 했고,
그 둘은 «양쪽 상태에서 같은 답»을 준다** — 그래서 상태가 바뀐 것이 측정을 무효화하지 않는다.

### 🔴 그런데 재검이 «더 중요한 것»을 찾았다 — 문제는 «한 파일»이 아니었다

착수 시점에 나도, 1차 실측도, 지시서도 **`map2/main.js` 하나만** 이야기했다.
`client2/src` **전수 NUL 스캔**(파이썬, 도구 무관)이 셋을 낸다:

| 파일 | NUL | 오프셋 | 행 | 줄 수 | 상태 |
|---|---|---|---|---|---|
| ~~`client2/src/map2/main.js`~~ | ~~1~~ | ~~28521~~ | ~~479~~ | 2,615 | 🟢 **오늘 고쳐짐** (`78a88e7f`) |
| 🔴 `client2/src/enrichment.js` | **1** | 57146 | **1156** | 1,279 | **남아 있다** |
| 🔴 `client2/src/map2/authoring.js` | **1** | 18827 | **385** | 395 | **남아 있다** |
| `client2/src/assets/hero.png` | 77 | 8 | — | — | 정상 (진짜 바이너리) |

```
🔴 부류로 판정하면: 「NUL 때문에 검색이 눈머는 파일」이 «셋»이었고 «하나»가 고쳐졌다.
   나머지 둘은 «하필» 이번 라운드가 판정한 두 자리다:
     enrichment.js       ⑨ 의 워크리스트 본체 (1,279줄)  <- 은퇴 판정을 받은 그 모듈
     map2/authoring.js   1차 실측이 「871줄이 도달 불가」로 판정한 그 사슬의 머리
```
⚠️ **그래서 이 둘에 대한 «과거의 rg 기반 0»은 전부 재측정 대상이다.**
다행히 이번 라운드의 판정 둘은 **영향받지 않는다** — 근거가 «그 파일 안»이 아니라 «밖»에 있기 때문이다:
```
enrichment.js 가 «안 빌드된다»    근거 = vite.config.js(밖) · dist 목록(밖) · 다른 파일의 import 문(밖)
authoring.js 를 «아무도 import 안 한다»   근거 = 다른 파일들의 import 문(밖)
=> 둘 다 «그 파일을 읽어야» 답하는 물음이 아니다. 그래서 NUL 과 무관하게 참이다
```
🔴 **하지만 「그 파일 «안»에 무엇이 있나」를 rg 로 물은 과거 측정은 전부 신뢰할 수 없다.**

📎 **이 항목의 교훈은 흐름이 아니라 «감사 방법»이다** — 1차 실측이 이 사각을 발견하고
   `map2/main.js` 를 이름으로 지목했고, 수리도 그 이름으로 왔다. **낱개로 고쳐서 부류가 남았다.**
   판별식은 「이 파일이 고쳐졌나」가 아니라 **「NUL 을 가진 파일이 몇 개인가」**여야 했다.

⚠️ **이번 측정의 도구 규율:** map2·enrichment 관련 계수는 **전부 `grep -a` 또는 `Read`** 로 냈다.
`Grep` 도구(ripgrep 기반)는 그 경로에 한 번도 쓰지 않았다.

---

## ⑭ 범용 맵 오버레이 (맵 인프라)

**한 줄:** 이 흐름은 **모듈로는 이 저장소에서 가장 많이 소비되는 것**이고 —
**HTTP 표면으로는 완전히 죽어 있다.** 그리고 스펙 §5.2 의 「소비자」 표가 그 둘을 한 칸에 적어서,
**죽은 절반이 살아 있는 절반의 이름으로 보고돼 왔다.**

```
map_overlay.py   2,744줄 · 서버 «비시험» importer 14
                 alignment_view_service · bonding_plan · config_resolve_report · dt_frame_transform ·
                 dt_map_derivation · frame_confirmation · main · map_alignment · map_meta_registrar ·
                 map_preset_routing · mappers/{core_alignment, dt_alignment_metadata,
                 dt_inventory_metadata, dt_standard_map}
                 -> 「범용 맵 인프라」는 «과장이 아니다». 서버의 좌표 변환 구현은 실제로 하나다
GET /api/maps/overlay
                 -> 🔴 클라 소비자 «0» (client2 전량 `grep -a`: src·dist·*.html 히트 0)
```

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| O-1 | `map_editor.js::fetchPaintRules` | `GET /api/maps/paint-rules` | `switchTable` 이 `await` (테이블 전환마다) | HTTP GET 쿼리 | `` `/api/maps/paint-rules?table=${encodeURIComponent(t)}` `` — 파라미터는 **`table` 하나**. 서버 시그니처도 `table: Optional[str]` **하나** → 🟢 **어긋남 없음** | 응답 4키 중 **4키 전부 읽는다**: `rules`(→`paintLockConfig`) · `value_column_candidates`(→`overlayContract`) · `default_legend`(→ 같은 캐시) · `binding`(→`servedBindingCache`). `table` 에코만 안 읽음 | 🔊 **세 갈래로 «정확히» 가른다** — 404/405 → `{...NO_PAINT_LOCK, source:'unsupported'}`(조용, 그것이 정답) · 그 외 실패 → `degrade()` 가 **직전 잠금 유지** + `source:'stale'` + 툴바 칩 `⚠ 잠금 규칙 미확인`(사라지지 않는다) + `console.log`. 토스트는 **일부러 뺐다**(주석이 사유 명시) | ✅ |
| O-2 | `map_editor.js::fetchServedBinding` | 같은 라우트 | 오버레이 소스 테이블의 바인딩이 필요할 때 (소스는 `selectedTable` 이 아니라 O-1 에 못 얹힌다) | HTTP GET 쿼리 | 같은 URL. 🔴 **응답의 `rules` 를 «일부러» 버린다** — 주석 명시(「locks belong to the selected table only」) | 1 (`servedBindingCache`). 성공만 캐시하고 실패는 캐시하지 않는다 | 🔊 `throw new Error('HTTP N')` → 호출자가 오버레이 행을 실패로 남긴다 | ✅ |
| O-3 | `map_editor.js::addOverlayLayer` | `GET /tables/{sourceTable}/data` | **호출처 3** — 세션 복원(`:11068`) · 사용자 추가(`:11096`) · 타깃 지정 추가(`:11141`) | HTTP GET 쿼리 | `` `/tables/${sourceTable}/data?limit=${OVERLAY_CELL_LIMIT+1}&defer_total=true&filters=${enc(JSON.stringify(filters))}` `` — 🔴 **`total` 을 안 쓴다**(`defer_total=true`), 절단은 `rows.length > 2000` 으로 판정 | 1 | 🔊 `fail('${sourceTable}: 셀 조회 실패 · …', 'error')` — 행으로 남고 `↻` 재시도 버튼 유지 | ✅ |
| O-4 | 같은 호출 | `fetchGridMetaFor(source)` · `fetchGridMetaFor(target)` | 같은 클릭, `Promise.allSettled` 로 **병렬** | HTTP GET 쿼리 ×2 | 셋을 `allSettled` 로 «따로» 잡는다 — 주석 명시(「셀 실패와 규격 실패는 다른 사유. 한 catch 로 접으면 규격 실패가 셀 실패로 보고된다」) | 2 | 🔊 소스 규격 조회 실패는 **identity 로 안 떨어진다** — `fail(...)` 로 행을 남긴다(「무보정·규격 미등록」이라는 **거짓 사유**를 안 낸다) | ✅ |
| O-5 | `map_editor.js` 치수 관문 | `align_unavailable` | ④ 프레임 확정 직후 (`:10528` `frameDimError`) | 함수 반환 | `srcDimErr \|\| seatDimErr` → `1~100` 정수 밖이면 거절. 🔴 **이것이 «취소 수단 없는 동기 루프 104만 칸»을 막는 유일한 것** — 셀 수는 `OVERLAY_CELL_LIMIT` 이 막지만 **치수는 이 한 줄뿐**이다 | 2 자리 | 🔊 `align_unavailable` 행 + 사유 | ✅ **스펙 §5.1 의 서술과 코드가 일치** |
| O-6 | `map_editor.js::syncOverlayGeometry` | 오버레이 레이어 재투영 | **호출처 2** — `:3481` · `:8201` (`currentGeomSignature` 변화 시) | 클라 메모리 | `rawCells`(소스 원본 좌표) + `frame` 동반 보관 → 원본에서 다시 투영 | 1 | 🔇 조용 (재투영은 항등일 때가 정상) | ✅ |
| O-7 | `map_editor.js::importOverlayToGrid` | `gridData` | **호출처 1** — `:11063` 액션 디스패치 (`act === 'import'`) | 클라 메모리 | 오버레이 → `gridData`. **서버 쓰기 0** · 페인트 잠금 존중 · 격자 밖 셀 제외 | 1 | — | ✅ **`frontend.md`·스펙의 「유일한 의도적 교차」 서술 정확** |
| O-8 | `map_editor.js::applyRoutedPreset` | `GET /api/maps/preset-routing` | 맵 «첫 열기» | HTTP GET 쿼리 | `` `?table=${enc(t)}&map_key=${enc(k)}` `` — 서버 시그니처 `(table: str, map_key: str, db)` → 🟢 **어긋남 없음**. `t`·`k` 중 하나라도 비면 **요청을 만들지 않는다** | 1 | 🔇 **의도된 조용** — 실패도 `no routing` 도 `console.info` 뿐. 사유 명시(「라우팅의 부재 = 기존 동작(패널 그대로) = 강등할 것이 없다」) | ✅ |
| O-9 | `GET /api/maps/overlay` | **(없음)** | — | HTTP | `map_overlay.get_overlay(db, config, target_table, target_key, src_list, cell_cap)`. 🔴 시그니처에 **`eqp` 가 살아 있고 그 docstring 이 「폐기됨(no-op)」이라고 자기 입으로 적었다** — 「기존 호출자가 깨지지 않도록 시그니처만 남겨두었다」 | 🔴 **클라 소비자 0**(`grep -a`: `client2/src`·`client2/dist`·`client2/*.html` 전량 히트 0). `get_overlay`·`parse_sources` 의 비시험 호출자도 **이 라우트 하나**뿐 | 🔇 완전 무음 | ⚰️ **HTTP 표면만. 모듈은 살아 있다** |
| O-10 | `map_overlay.resolve_valid_die_basis` | — | — | 함수 | `(meta, resolver=None, table)` → `{basis, source, reason}`. `resolver is None` 이면 **`SOURCE_REFUSED` + 「참조를 풀 해석기가 주어지지 않았다」** | 🔴 **운영 호출자 0.** 히트 16 전건 분해: 주석 2(`map_alignment:631·950`) · docstring 1(`map_overlay:1167`) · def 1 · **시험 12**(`test_valid_die_ref` 11 · `test_map_overlay` 1) | 🔇 조용 | ⚰️ — **아래 §⑭-A 참조. 기능은 안 깨졌다** |
| O-11 | `map_overlay.resolve_valid_die_set` | — | — | 함수 | `(db, cfg, target_table, target_key, …)` | 🔴 **운영 호출자 0** — 히트 10 중 주석 2(`main.py:4680`·`map_alignment:5122`) · docstring 2 · def 1 · **시험 5**. `main.py:4680` 이 그 사유를 적어 뒀다: 「서버가 스스로 유효 다이를 판정해야 하는 **phase 2/3** 에서 그대로 쓴다」 | 🔇 조용 | ⚰️ **선언된 미래용 — 「퍼뜨리기」 쪽**(§⑭-B) |
| O-12 | `map_overlay.origin_box` | `dt_frame_transform` · `map_alignment` | 정렬 계산 | 함수 인자 | `origin_box(meta, die_mask)` — 마스크는 `die_mask_from_reference(basis_meta, basis_cells)` 가 만든다 | **운영 호출자 2 자리 · 3 호출**(`dt_frame_transform:57·58` · `map_alignment:744`) | 🔊 마스크 0칸이면 원 상자로 폴백 | ✅ |

### ⑭-A 핵심 발견 — 「**스펙이 계약이라 이름 붙인 심볼에 운영 호출자가 «0» 이다. 그런데 기능은 돈다**」

`MAP_EDITOR_SPEC §5.7` 이 **두 구현을 잇는 계약**으로 이 쌍을 명시한다:

```
스펙 §5.7 원문   「같은 판정식으로 갈린다 —
                 클라 validDieBasis() === 'ref'  ↔  서버 resolve_valid_die_basis(...)["source"] == SOURCE_REF」
실측             서버 쪽 그 함수의 «운영 호출자» = 0 (시험 12 · 주석 2 · docstring 1 · def 1)
운영이 실제로 도는 길   map_alignment:744
                 mask = map_overlay.die_mask_from_reference(basis_meta, basis_cells)
                 src_box = map_overlay.origin_box(base, mask)
                 -> «결과»(마스크에서 나온 원점 상자)는 «얻는다». 다만 계약 심볼을 «경유하지 않는다»
```

🔴 **이것은 「반쪽」의 «세 번째» 방향이다.** 1차 실측이 둘을 봤다 — 쓰는 쪽이 살고 읽는 쪽이 죽은 것(통지),
읽는 쪽이 살고 쓰는 쪽이 못 닿는 것(⑩ 거절). 여기는 **양쪽이 다 살아 있는데 «지정된 이음매»를 안 지난다.**
```
그래서 위험이 「지금 틀린 답」이 아니라 「나중에 갈라진다」이다:
  · 계약 심볼은 시험 12개가 «촘촘히» 채점한다 -> 고쳐도 초록
  · 운영 경로는 그 심볼을 «안 부른다»        -> 고쳐도 안 바뀐다
  => 시험이 지키는 것과 운영이 도는 것이 «다른 코드»다. 오늘 같은 답을 내는 것은 «우연»이다
```
📎 이것이 기억의 「같은 모양을 두 번 그리면 자리 이동을 못 본다」와 같은 부류이고,
   `contracts/map_seam` 이 **클라↔서버**를 채점하는 것과 **다른 축**이다(그쪽은 두 언어, 이쪽은 한 파일 안).

### ⑭-B 「소비자 0」이 «두 뜻»인 자리 — 셋을 갈랐다 (§6 판별식: 「없으면 무엇을 말할 수 없게 되나」)

| 심볼 | 없으면 못 말하게 되는 것 | 판정 |
|---|---|---|
| `GET /api/maps/overlay` 의 **`eqp`** | **없다.** docstring 이 스스로 「폐기됨(no-op)」이라 적었고 분기가 남아 있지 않다 | 🗑️ **빼기** — 다만 「제거는 총괄 승인 사항」이라 코드가 이미 적어 뒀다 |
| `GET /api/maps/overlay` **라우트** | **「임의의 맵을 임의의 맵 위에」를 «HTTP 로» 물을 자리.** 지금 그 능력은 `map_editor.js` 안에만 있고, map2·계획·어드민 어디서도 못 묻는다 | 📡 **퍼뜨리기** — 엔진은 살아 있고 표면만 없다 |
| `resolve_valid_die_set` / `resolve_valid_die_basis` | **「이 다이가 유효한가」를 서버가 스스로 답하는 것.** phase 2/3 의 전제이고, 없으면 판정이 영원히 클라에만 산다 | 📡 **퍼뜨리기** — 다만 O-10 은 «지금 배선»이 빠진 것이고 O-11 은 «아직 안 온 라운드»다. **둘을 같은 칸에 적으면 안 된다** |

### ⑭ 양끝이 다 있는데 아무것도 잇지 않는 이음매 (넷)

| # | 이음매 | 양끝 | 가운데 |
|---|---|---|---|
| 1 | 오버레이 엔진 ↔ 아무 화면 | `get_overlay` + `parse_sources` + `MAX_OVERLAY_CELLS` 상한·`truncated` 표기까지 완비 | **클라 소비자 0.** 유일한 비시험 호출자가 그 라우트 자신 |
| 2 | 계약 심볼 `resolve_valid_die_basis` ↔ 운영 경로 | 함수·시험 12·스펙 §5.7 의 명시 계약 | 운영은 `die_mask_from_reference`+`origin_box` 로 «우회»한다 |
| 3 | `resolve_valid_die_set` ↔ 노출 | 함수 완성 · `main.py:4680` 이 「phase 2/3 에서 그대로 쓴다」 | 라우트 0 · 호출자 0 |
| 4 | 절단 상한 둘 | 클라 `OVERLAY_CELL_LIMIT = 2000` · 서버 `MAX_OVERLAY_CELLS = 20_000` | **10배 차이인데 만나는 자리가 없다** — 클라가 그 라우트를 안 부르므로 두 수가 서로를 모른다 |

### ⑭ 에서 나온 문서 정정

| 자리 | 적혀 있는 것 | 실측 |
|---|---|---|
| 🔴 `MAP_EDITOR_SPEC §5.2` 「현재 소비자」 표 | 5행: `GET /api/maps/overlay` · `bonding_plan.py` · `transfer_plan.py` · `GET /api/maps/paint-rules` · `tests/test_map_overlay.py` | ⚠️ **표가 「라우트의 소비자」와 「모듈의 소비자」를 한 칸에 섞는다.** 라우트를 실제로 «부르는» 것은 **시험 하나**뿐이고, `bonding_plan`·`transfer_plan` 은 **모듈** 소비자다. 1차 실측이 §5-⑨ 에서 같은 지적을 했는데(「오해를 부른다」) **표 자체는 아직 그대로다.** 그리고 이번에 하나 더: 이 표는 `map_overlay` 의 «비시험 importer 14» 중 **둘만** 싣는다 — 나머지 12(매퍼 4 포함)가 빠져 있어 「이 모듈을 고치면 무엇이 움직이나」를 이 표로 답할 수 없다 |
| ✅ `MAP_EDITOR_SPEC §5.1` 치수 정의역 관문 | 「`1~100` 정수 밖이면 `align_unavailable`. 셀 수는 상한이 막지만 **치수는 아무도 안 막는다**」 | **정확하다.** `map_editor.js:10528` `frameDimError(srcResolved) \|\| frameDimError(seatFrame)` 로 실재 |
| ✅ `MAP_EDITOR_SPEC §5.5` 페인트 잠금 fail-open 금지 | 「404/405만 «없다», 그 외는 «확인 못 했다» → 직전 값 유지 + 칩」 | **정확하다.** `fetchPaintRules` 의 `degrade()` 가 그대로 구현 |
| ⚠️ `MAP_EDITOR_SPEC §5.5` C4 「콜드 스타트 fail-open」 | 열린 항목으로 등재 | **여전히 열려 있다** — `paintLockConfig` 초기값이 잠금 없음이라 첫 조회 실패 시 잠기지 않은 채 시작하는 구조가 그대로다 |

### ⑭ 에서 목록이 놓친 흐름

- **① 「이 맵을 «어떤 규격»으로 열까」는 오버레이가 아니다.** `GET /api/maps/preset-routing`
  (+ `map_preset_routing.py` **536줄**)은 **첫 열기의 기본값**을 정한다 — 트리거가 다르고(맵 첫 열기 ≠
  오버레이 추가), 목적지가 다르고(패널 규격 ≠ 캔버스 마커), 해석 순서도 자기 것이다
  (①제품코드 조회 표 → ②텍스트 패턴 규칙 → ③없음). 오버레이 인프라 밑에 접혀 있으나 **다른 물음**이다.
  🔴 그리고 이 흐름의 「끊기면」은 **의도적으로 조용**하다(`console.info` 뿐) — 사유는 코드가 적었다:
  「라우팅의 부재 = 기존 동작 = 강등할 것이 없다」. 다만 그 결과 **선언이 있는데 빗나가는 것**과
  **선언이 없는 것**이 화면에서 같아 보인다. `lookup{declared,status,product_code}` 가 그 둘을
  가르라고 서버가 실어 보내는데 클라는 `console.info` 문자열에만 넣는다.
- **② `GET /api/maps/paint-rules` 는 «세 물음»에 답한다.** 라우트를 세면 하나인데 흐름은 셋이다:
  ```
  ① 이 표의 어느 셀이 «잠겼나»          -> paintLockConfig  (테이블 의존)
  ② 이 사이트의 «맵 기본값»은 무엇인가   -> value_column_candidates · default_legend (테이블 «무관»)
  ③ 이 표의 «좌표 바인딩»은 무엇인가     -> binding          (테이블 의존)
  ```
  🔴 **셋의 «청중»과 «신선도 규율»이 다르다** — ①은 편집 관문이라 실패 시 직전 값을 쥐고,
  ②는 사이트 상수라 한 번 받으면 되고, ③은 소스 테이블마다 따로 받는다(`fetchServedBinding` 이
  **같은 라우트를 다시** 부르는 이유가 그것이다 — O-2). 그래서 한 화면 로드에 이 라우트가
  **테이블 수만큼 반복**된다. 기억의 「하나의 라우트가 하나의 질문이 아니다」가 그대로 걸리는 자리.

---

## ⑮ 전사 계획 (본딩/DT)

**한 줄:** 계획을 **쓰는** 길과 **읽는** 길은 이어져 있다. **판정하는 길만 «양끝이 다 지어진 채»
끊겨 있고** — 클라 쪽 끝이 `__held_` 라는 이름으로 **자기가 안 붙었다고 적어 두었다.**
그리고 그 보류의 «사유»가 **낡았다**: 기다리던 서버 계약은 이미 확정됐다.

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| T-1 | `transfer_plan.js::fetchStages` | `GET /api/transfer-plan/stages` | `ensureStages()` — 최초 1회만(`stagesPromise` 래치) | HTTP GET | **파라미터 없음** (서버도 인자 0 — 「선언 해석만, 행 조회 없음」). 응답은 배열 또는 `{stages:[…]}` 둘 다 받는다 | 1 → `S.stages`. **추가 소비자 1**: `map_editor.js` 가 `stageTargetTables()` 로 초기 테이블 선택에 씀(`:1207` 주석이 사유 명시 — builtin 표 이름 목록을 대체) | 🔊 **세 갈래** — 404/405 → `unsupported`(빈 목록이 «정답») · 그 외 → `console.warn` + **직전 선언 유지**, 다음 맵 전환에 재시도. 🔴 **builtin 목록으로 절대 안 돌아간다**(주석 명시) | ✅ |
| T-2 | `transfer_plan.js::getPoolSummary` | `GET /api/transfer-plan/source-summary` | 자재 풀 요약이 필요할 때 (`S.summaries` 캐시 미스) | HTTP GET 쿼리 | `URLSearchParams{stage, lot, scope∈{lot,slot}, bins}` + `scope!=='lot'` 일 때만 `slot`. 🟢 **서버의 `scope=lot` + `slot` 동시 지정 400 규율을 클라가 «구조적으로» 못 어긴다** — 조건이 파라미터 설정 자체를 가른다 | 1 → `entry.data` | 🔊 `isPlainNotFound` → `unsupported`, 그 외 → `entry.status='error'` + `body.detail` 을 **서버 문장 그대로** | ✅ |
| T-3 | `transfer_plan.js` | **서버 쓰기** | — | — | 🔴 **fetch 3건 전부 GET.** `method:'PUT'`/`'POST'` 히트 **0** | — | — | ✅ **`frontend.md §5.1` 「쓰기 소유권」 서술 정확** |
| T-4 | `map_editor.js::saveLegendToServer` | `PUT /tables/map_split_registry/data/updates` | `pushMapData` 안의 `await` — 호출처 1 | HTTP PUT | 계획의 **유일한 쓰기 경로**. (1차 실측 §5-⑨ 가 이미 잰 행 — 관문 거절 넷이 🔇 조용한 것도 그대로) | 1 | ⚠️ 1차 실측 참조 | ⚠️ |
| T-5 | `map_split_registry` | `transfer_plan.validate_plan` | **(없음)** | — | `validate_plan(db, config, ref_table, map_key)` — 경고 4종을 낸다: 수량 부족 · 구간 구조 결함(`layer_range_invalid`) · DOE 값-맵 정합 · 소스 fail | 🔴 **라우트 1 · 클라 «0»** (아래 T-6) | 🔇 | 🔴 |
| T-6 | `GET /api/transfer-plan/validate` | `transfer_plan.js::__held_refreshValidate` | **(없음 — 그 함수를 부르는 곳이 0)** | HTTP GET 쿼리 | 🔴 **파라미터가 «어긋난다»**: 클라가 짓는 것은 `?plan_id=${planId}` · 서버 시그니처는 **`(ref_table: str, map_key: str, db)`** — 필수 둘이 안 실리고 `plan_id` 는 받는 칸이 없다 → **불렸다면 422** | 🔴 **0.** `__held_refreshValidate` 는 히트 **1**(자기 def) · `// eslint-disable-next-line no-unused-vars` 가 붙어 있다. **출하본에도 없다**: `dist/assets/` 에서 `transfer-plan/validate` = **0**(`stages` 1 · `source-summary` 1) — 번들러가 흔들어 떨어뜨렸다 | 🔇 완전 무음 | ⚰️ **의도된 보류 · 다만 사유가 낡았다(§⑮-A)** |
| T-7 | `admin.js` | `GET /admin/transfer-plan/dry-run` | 어드민에서 (`admin.js:2168` `adminFetch`) | HTTP GET | 역할마다 넷: 이름 붙은 거절 «사유» · 해석된 «실제 컬럼명» · 그 컬럼이 «선언/유도» 중 어디서 왔나 · 「틀린 선언을 지우면 무엇이 유도되는지」 | **1 · 살아 있다** — `admin.js:39` 가 `plan_dry_run.js` 의 `planDryRunView` 를 import | 🔊 | ✅ **과거의 「소비자 0」이 «닫힌» 자리**(`plan_dry_run.js` 머리말이 그 이력을 적어 뒀다) |
| T-8 | `GET /api/bonding-plan/core-summary` | **(없음)** | — | HTTP GET 쿼리 | `(lot, slot, region?, db)` — `region` 은 URL 인코딩 JSON `{"rects":[{x1,y1,x2,y2}]}`. docstring: 「본딩 실험계획 **Info 창**용 코어 (lot, slot) 집계 요약」 | 🔴 **클라 소비자 «0»** — `client2/` 전량(`src`+`dist`+`*.html`) `grep -a` 히트 **0**. 전체 히트 10 분해: 라우트 def 1 · 주석 3(`bonding_plan.py:8` 「경계 계약 — 총괄 고정」 · `setup_bonding_plan_indexes.py:3` · `transfer_plan.py:88`) · 로그 1 · **시험 5**(`test_bonding_plan` 3 · `test_availability_relaxation` 2) | 🔇 완전 무음 | ⚰️ **§⑮-B** |
| T-9 | `transfer_plan.py` 규모 상한 넷 | `validate_plan` | — | 모듈 상수 | `MAX_DOE_PER_PLAN=500`(주석: 「**validate 가 다루는** DOE 정의 상한」) · `MAX_BANDS_PER_PLAN=2000` · `MAX_DEMANDS_PER_PLAN=5000` · `MAX_SOURCES_PER_PLAN=200` | 🔴 넷 다 **`validate_plan` 을 지키는 가드**이고 그 함수는 T-6 에 의해 도달 불가 | 🔇 | ⚰️ **「가드는 도달 가능해지는 날 틀린다」의 반대편** — 도달 «불가»라 오늘 재본 적이 없다 |
| T-10 | `bonding_plan.py` | `transfer_plan.py` | import | 함수 | `from bonding_plan import STATUS_NOT_DECLARED, finite_point, role_is_declared` (`:128`) + `_resolve_model_columns` (`:365-368`, 함수 안 지연 import) | **비시험 소비자 2** (`main.py` 라우트 · `transfer_plan`) | — | ✅ **모듈은 살아 있다** |

### ⑮-A 핵심 발견 — 「**보류의 «사유»가 낡았다. 기다리던 계약은 이미 왔다**」

`transfer_plan.js:1877` 의 보류 함수가 자기 이유를 적어 두었다:

```js
// eslint-disable-next-line no-unused-vars
async function __held_refreshValidate(planId) {
  // GET /api/transfer-plan/validate?plan_id=... — 서버가 ref_table+map_key 파라미터로
  // 이전하는 중이라 재연결은 «서버 계약 확정 후»에 한다.
  const params = new URLSearchParams({ plan_id: planId });
```
그런데 **서버는 이전을 끝냈고, 그 사실을 자기 docstring 에 적어 두었다** (`main.py:4785`):
```
@app.get("/api/transfer-plan/validate")
def validate_transfer_plan(ref_table: str, map_key: str, db):
    「[v2 계획 모델] 계획 정체성은 «지금 열어 편집 중인 맵»(ref_table, map_key)이다.
     구 `plan_id` 파라미터는 «폐기» — 계획 헤더 테이블도 계획 맵 사본도 존재하지 않는다.」
```
```
🔴 즉 «양쪽이 서로를 기다리고 있지 않다» — 한쪽은 도착했고 다른 쪽만 그것을 모른다.
   그리고 이 낡음은 «조용하다»: 보류 함수는 호출자가 0 이라 422 를 낼 기회조차 없고,
   번들에서 흔들려 떨어져 출하본에는 존재하지도 않는다
```
⚠️ **이 항목을 「결함」으로만 읽으면 안 된다.** 보류는 **선언된 것**이다 —
`transfer_plan.js:1791-1802` 의 `§보류 구역` 머리말이 「사용자 지시로 이번 범위에서 **미연결**」이라
적고 보류 항목 일곱을 이름으로 나열한다(수량 부족 판정 · 교차 초과배정 · **validate 연동** ·
신뢰 어휘 4단 배지 · STACK 커버리지 스트립 · 검증 스킵 배너 · by_core 분해표).
🔴 **발견은 「보류했다」가 아니라 「보류의 «해제 조건»이 충족됐는데 아무도 안 본다」이다.**

보류 구역 실측 — **완전히 닫힌 죽은 섬**이다(각 함수의 전체 히트 수 = 자기 정의 + 서로 간 호출뿐):
```
__held_normalizeSources        2   (def + __held_remainingReliability 가 부름)
__held_classifySourceStatus    2   (def + 같은 곳)
__held_remainingReliability    1   (def 만)
__held_normalizeWarning        1   (def 만)
__held_refreshValidate         1   (def 만)
__held_fmtChips                1   (def 만)
=> 밖에서 들어오는 화살표 «0». 그 머리말도 같은 말을 한다: 「현재 어떤 렌더러도 이들을 호출하지 않는다」
```

### ⑮-B 두 번째 발견 — 「**Info 창을 위해 지은 라우트에 Info 창이 없다**」

```
GET /api/bonding-plan/core-summary
  docstring        「본딩 실험계획 «Info 창»용 코어 (lot, slot) 집계 요약」
  경계 계약        bonding_plan.py:8  「[경계 계약 — 총괄 고정] 응답 형태는 지시서 …」
  전용 인덱스      server/scripts/setup_bonding_plan_indexes.py
                   그 머리말: 「core-summary 집계는 (lot, slot) 동치 필터가 전 쿼리의 진입점이다 —
                              «1,000만 행» 규모에서 …」
  클라 소비자      🔴 0
```
🔴 **규모를 위해 «전용 인덱스 설치 스크립트»까지 지은 라우트인데 그 수를 볼 화면이 없다.**
이것은 ⑭ 의 오버레이 라우트와 **같은 모양이되 더 비싸다** — 오버레이는 엔진이 다른 소비자로
살아 있지만, `get_core_summary` 는 **이 라우트 말고 부르는 곳이 없다**(`bonding_plan` 의 다른
심볼 셋만 `transfer_plan` 이 쓴다).

### ⑮ 양끝이 다 있는데 아무것도 잇지 않는 이음매 (넷)

| # | 이음매 | 양끝 | 가운데 |
|---|---|---|---|
| 1 | `validate_plan` 경고 4종 ↔ 화면 | 서버가 판정하고 상한 넷으로 규모까지 지킨다 · 클라에 렌더러 뼈대(`__held_*` 여섯)가 «있다» | 부르는 코드 0 · 파라미터도 어긋남 · 출하본에 없음 |
| 2 | `core-summary` ↔ Info 창 | 라우트 · 경계 계약 · 전용 인덱스 스크립트 · 시험 5 | **Info 창이 없다** |
| 3 | 계획 «쓰기» ↔ 계획 «판정» | 쓰기는 `map_split_registry` 로 간다 · 판정도 같은 표를 읽는다 | 판정을 촉발하는 것이 없다 — 같은 표를 보면서 만나지 않는다 |
| 4 | 계획 «편집 화면» ↔ 계획 «진단» | 편집은 맵 에디터 사이드바 · 진단(`dry-run`)은 **어드민** | 이어져는 있으나 **다른 화면**이다(§⑮ 놓친 흐름 ①) |

### ⑮ 에서 나온 문서 정정

| 자리 | 적혀 있는 것 | 실측 |
|---|---|---|
| 🔴 `client2/src/transfer_plan.js:1878-1879` 주석 | 「서버가 `ref_table`+`map_key` 파라미터로 **이전하는 중**이라 재연결은 서버 계약 확정 후에 한다」 | **낡았다.** 이전은 끝났다 — `main.py:4786` 시그니처가 `(ref_table, map_key)` 이고 docstring 이 「구 `plan_id` 파라미터는 폐기」라고 «완료형»으로 적는다 |
| ✅ `frontend.md §5.1` | 「`transfer_plan.js` 는 서버에 쓰지 않는다 — fetch 3건 전부 GET」 | **정확하다.** `method:'PUT'\|'POST'` 히트 0 으로 재확인 |
| ✅ `MAP_EDITOR_SPEC §5.2` A2 해소 | 「`bonding_plan` 의 자체 정렬 구현은 삭제됐고 가용량 산출도 `map_overlay` 경유」 | **정확하다.** `bonding_plan.py` 안 `map_overlay` 지연 import 4자리(`:231·516·539·800`) |

### ⑮ 에서 목록이 놓친 흐름

- **① 계획의 «진단»은 계획의 «화면»에 없다.** 편집은 맵 에디터 사이드바(`transfer_plan.js`)인데,
  「내 선언이 왜 거절되나」는 **어드민**(`admin.js` → `plan_dry_run.js` → `/admin/transfer-plan/dry-run`)이다.
  게다가 그 라우트는 **어드민 토큰 게이트 뒤**다. 🔴 **계획을 짜는 사람과 계획을 고칠 수 있는 사람이
  «다른 화면·다른 권한»에 있다** — 이건 배선 결함이 아니라 «청중이 갈린» 별도 흐름이다.
- **② `stages` 는 계획 UI 만의 것이 아니다.** `map_editor.js:1207` 이 `stageTargetTables()` 로
  **초기 테이블 선택**에 쓴다. 즉 이 라우트는 「어느 stage 가 있나」와 「맵 에디터가 처음 무엇을 열까」
  **두 질문**에 답한다. 라우트를 세면 하나지만 흐름은 둘이다.

---

## ⑨ Enrichment Queue (결손 탐지 → 워크리스트 → 보정 → 표)

**한 줄:** **「몇 건인가」는 살아 있고 「어느 건인가」는 닿을 수 없다.** 워크리스트 화면이 없는 것은
**소유자 판정**이라 발견이 아니다 — 발견은 **그 판정이 지목한 «대체 자리»가 그 능력을 못 받았다**는 것이다.

> 🟢 **먼저 닫고 간다 (§2-bis 와 같은 자리).** `client2/vite.config.js:22-26` 이 자기 입으로 적었다:
> 「`enrichment` was here until 2026-08-11. The queue page was **retired from navigation by
> product-owner ruling** (`5116f67` took its links; this takes the page), because **correction
> happens in the grid with the sidebar 참조뷰 beside it.** Building an entry nobody can reach is
> how a retired screen keeps looking shipped.」
> 🔴 **그러므로 「워크리스트 페이지가 없다」는 «발견이 아니다».** 이 문단이 그 재측정을 끝낸다.
> ⚠️ 다만 판정이 «닫는 것»과 «안 닫는 것»이 다르다 — 판정은 **보정을 그리드로 옮겼다.**
> 그래서 판별식이 이렇게 바뀐다: 「워크리스트가 있나」 ❌ → **「그리드가 큐로 좁혀지나」 ✅**

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| E-1 | `enrichment_config.load_enrichment_chain_rules()` | 체인 워커 규칙 목록 | **워커 기동 + `SYSTEM_RELOAD`** (⑦ C-7 과 같은 자리) | 함수 반환 → dict 병합 | 합성 규칙이 일반 체인 규칙에 `+` 된다. 디스패치 키는 `rule["mapper_module"]` = `"enrichment_mapper"`(`enrichment_config.py:739`). `logger.info("[Enrichment] Synthesized N dedup chain rule(s)")` **실제로 찍힌다** | 디스패치 3 (`chain_ingestion_worker:698·1169` · `chain_replay:340`) | 🔊 `logger.error("[Enrichment] Failed to synthesize enrichment chain rules")` → **워커 로그 파일** | ✅ |
| E-2 | `chain_ingestion_worker:1012` | `enrichment_candidates.AutoConfirmCollector.flush(db)` | `crud.apply_batch_updates` 커밋 **직후**, 같은 루프 | 함수 인자 | `if ac.active:` → collect → flush. **기본 OFF** — `DEFAULT_ENABLED=False` + 전역 킬스위치 + 규칙별 노브 **셋 다** 필요. 쓰면 `source_name="enrichment_auto_confirm"`(SOURCE_PRIORITY 미등재 → **99**) | 1 | 🔊 `logger.error("[Enrichment ①] Auto-confirm failed for '{t}' (chain write unaffected)")`. ⚠️ 그 `except` 가 **오염된 세션은 못 막는다**(모듈이 스스로 적어 둠) | ✅ (기본 꺼짐) |
| E-3 | `admin.js::fetchEnrichmentStatus` | `GET /tables/{derived}/data` | **호출처 3 · 그중 산 것 2** — Enrichment 탭 열기(`:965`) · Overview 로더(`:3347`) · ~~헬스 스트립(`:4668`)~~ | HTTP GET 쿼리 | 규칙마다 `` `?skip=0&limit=1&<queueQuery(rule)>` `` → `enrichment_queue=<name>&enrichment_queue_scope=queue`. 🔴 **클라 소스에 `enrichment_queue` 리터럴이 없다** — `queueQuery` 가 **서버 응답의 `p.param`/`p.scope_param` 을 읽어 조립**한다(철자의 저자가 서버 하나) | 1 (`admin.js:4515`) · 응답에서 **`cr.total` 만** 읽는다 | 🔇 `catch (e) { /* missing = null */ }` — **콘솔도 안 찍는다**. 카드엔 「상태 조회 실패」 | ✅ |
| E-4 | 「결손 N건」 | **행 목록** | — | — | 🔴 큐 술어를 **행 목록으로** 태우는 유일한 모듈 `client2/src/enrichment.js`(**1,278줄**)가 ⓐ vite 엔트리 **아님**(실측: 엔트리 **6** — main·admin·map_editor·map_editor2·rnd_board·walk) ⓑ 이를 import 하는 모듈 **0**(히트 3은 전부 **주석**) ⓒ `dist/assets/` 에 enrichment 번들 **0** | **0** | 🔇 | ⚰️ **의도된 묘비 (소유자 판정)** |
| E-5 | 판정이 지목한 대체 자리 — **메인 그리드** | `enrichment_queue` 좁힘 | — | — | 🔴 **`client2/src/narrowing.js` 에 `enrichment_queue` 가 «0건».** 그리고 그 철자를 **전선에 싣는 산 코드가 client2 전량에 0**(유일 히트는 죽은 `enrichment.js:379` 의 주석) | **0** | 🔇 **완전 무음** | 🔴 **끊김 — ⑨ 의 핵심** |
| E-6 | `enrichment_reference_view.js::showReferenceView` | `GET /enrichment/rules/{name}/references/{index}` | 사이드바 참조 탭 클릭(`main.js:579`) · 행 선택(`grid.js:1133`) | HTTP GET 쿼리 | `?params=${enc(JSON.stringify(params))}`, `params = Object.fromEntries(decision_key.map(c => [c, valueOf(row,c)]))`. 서버 `(rule_name, index, params=None, db)` — 🟢 **보내는 것과 받는 것이 정확히 일치**. 판단키가 비면 **요청 자체를 안 보낸다**(`:485`) | **4 모듈** (`api.js` · `grid.js` ×2 · `main.js` ×5) | 🔊 `'참조뷰 요청에 실패했습니다.'` 또는 서버 `detail` 그대로 | ✅ **판정의 「사이드바 참조뷰」 절반은 실제로 이식됐다** |
| E-7 | `admin.js::runAutoConfirmDryRun` | `GET /admin/enrichment/auto-confirm/dry-run` | 사람 클릭 (자동 실행 없음) | HTTP GET 쿼리 | `?rule=<rule>` — 🔴 **`limit` 을 안 보낸다.** 서버는 `limit: int = 200`(max 2000) | 1 | 🔊 `console.error` + 화면 `CHROME.MEASURE_FAILED` | ⚠️ **§⑨-B** |
| E-8 | `admin.js` 소급 | `retroactive.OPERATIONS["enrichment_backfill"]` · `["enrichment_confirm"]` → `enrichment_backfill.run_backfill` → `crud.apply_batch_updates` | 사람이 소급 줄 펼침 → count → 확인 → run (**2클릭**) | count=GET 쿼리 · run=POST 바디 | `GET /admin/retroactive/{op}/count?rule=<name>` · `POST /admin/retroactive/{op}/run` 바디 `{"params":{"rule":"<name>"}}`. 🔴 **클라가 파라미터 «이름»을 안 적는다** — `retroParamEntries` 가 서버의 `_p("rule", …)` 선언(`retroactive.py:703·715`)에서 받아 조립 | 2 (`retroactive.count`·`.run` 디스패치). `OPERATIONS` dict 리터럴 2는 **등록**이라 뺀다 | 🔊 `showToast(failureText,'error',{ttl:12000})` + 줄에 사유. 503 은 `adminFetch` 가 이미 띄우므로 **중복 억제** | ✅ **보정이 표에 닿는 «유일한 산 경로»** |
| E-9 | `@app.get("/enrichment")` · `/enrichment.html` (`main.py:6279-6280`) | `serve_enrichment_page` | 북마크·직접 URL | HTTP | 들여쓰기의 조건은 `if os.path.exists(client2_dist_path)`(`:6214`) — dist 가 있으므로 **라우트는 등록된다**. 그러나 `dist/enrichment.html` 도 `client2/enrichment.html` 도 **둘 다 없고** 구울 엔트리도 없다 → **항상 404** | 0 (산 링크 없음) | 🔊 404 `"Enrichment 페이지 폐지됨 · 참조뷰 → 메인 화면 이력 사이드바 탭"` | ⚰️ **의도된 묘비 — 거절문이 대체 자리를 «이름으로» 댄다** |

### ⑨-A 핵심 발견 — 「**판정은 보정을 그리드로 옮겼는데, 그리드가 큐를 «모른다»**」

```
소유자 판정 (vite.config.js:22-26)   「correction happens in the grid with the sidebar 참조뷰 beside it」
                                    -> 대체 자리는 «메인 그리드» + «사이드바 참조뷰» 둘이다
이식된 절반                          참조뷰 ✅  (E-6. 4모듈이 소비 · 판단키 없으면 요청도 안 보냄)
이식 안 된 절반                      그리드 좁힘 🔴
실측
  서버      /tables/{t}/data 가 enrichment_queue·enrichment_queue_scope 를 «받는다»(main.py:1580)
            /tables/{t}/data/count 도 «받는다»(main.py:2009-2010)
  클라      narrowing.js 의 enrichment_queue = «0»
            그 철자를 전선에 싣는 산 코드 = «0» (유일 히트가 죽은 enrichment.js 의 주석)
=> 운영자는 「결손 12건」을 «보고», 그 12건을 그리드에 «띄울 수 없다»
```
🔴 **이것이 「반쪽」이다 — 그리고 조용한 쪽이 «판정을 실행한 쪽»이다.**
판정은 옳았고(중복 화면을 없앴다), 이행이 **절반에서 멈췄다.** 그리고 멈춘 절반은
「페이지가 없다」와 달리 **어디에도 안 적혀 있다** — vite 주석은 「그리드에서 한다」를
«이미 그렇다»는 어조로 적는다.

⚠️ **한 번 틀렸다가 잡은 자리 (기록으로 남긴다).** 이 흐름을 재면서 「결손 카운트도 죽었다」고
한 번 판정했다 — `refreshEnrichmentHealth` 의 호출자가 **죽은 헬스 스트립 안**(`:4562`)이었기 때문이다.
**틀렸다.** `fetchEnrichmentStatus` 는 호출처가 **넷**이고 그중 **둘이 살아 있다**
(`:965` 탭 열기 · `:3347` Overview). 🔴 **「이 함수의 유일한 호출자가 죽었다」를 «그 함수»가 아니라
«한 단계 위»에서 확인한 것이 오류였다.** 카운트는 산다.
📎 그리고 그 덕에 «진짜 죽은 것»의 범위가 좁혀졌다 — 헬스 스트립 카드의
`규칙 N개 · 클릭 → Enrichment 탭` 문구(`:4674`)는 **스트립 안이라 어차피 안 뜬다.**
그 문구를 「낡은 유인」으로 보고할 뻔했는데, **그것도 이미 소유자 판정이 덮은 자리**다.

### ⑨-B 「소비자 0」의 갈래 — 셋 다 다르다

| 심볼 | 없으면 못 말하게 되는 것 | 판정 |
|---|---|---|
| `keyed_queue_filters` (`enrichment_config.py:1535`, 매 응답에 실림) | **없다.** docstring 이 대는 유일한 용도(`queue_filters.total − keyed_queue_filters.total = 「판단키 없음 N건」`)를 이제 **`enrichment_queue_scope=blank_key` 가 이름으로 말한다** | 🗑️ **빼기** — 산 독자 0(서버·클라 전부, 시험만) |
| `queue_filters` (같은 자리) | **「구버전 서버와 말이 통하는 것」.** `legacyQueueQuery` 의 폴백 계약이다 | ✅ **유지** — 이 서버 상대로는 도달 불가(같은 함수가 `queue_predicate` 를 **항상** 싣는다)지만, 지우면 폴백이 못 말해진다 |
| 드라이런의 `limit` (E-7) | **「표본을 넓히는 것」.** 화면은 `truncated` 를 받아 「표본 200건까지만」을 **표시하는데** 운영자가 넓힐 수단이 없다 | 📡 **퍼뜨리기** — 절단을 «보여주면서» 그 절단을 풀 손잡이를 안 준다 |

### ⑨ 양끝이 다 있는데 아무것도 잇지 않는 이음매 (다섯)

| # | 이음매 | 양끝 | 가운데 |
|---|---|---|---|
| 1 | **큐 술어 ↔ 그리드** | 서버 4스코프 `queue_predicate_condition` · 클라 `queueQuery(rule, scope)` 가 4스코프를 전부 조립 가능 | **`narrowing.js` 가 그 인자를 안 만든다.** 비-기본 스코프를 보내는 산 호출부 **0** |
| 2 | 카운트 라우트의 큐 인자 | `main.py:2009-2010` 이 `/data/count` 에서 받음 | 보내는 클라 **0** — 어드민은 대신 `/data?limit=1` 로 스칼라를 얻는다 |
| 3 | `keyed_queue_filters` | 매 응답에 실림 | 산 독자 **0** |
| 4 | 드라이런 표본 크기 | 서버 `limit`(기본 200·최대 2000) · 화면이 `truncated` 를 **표시함** | 클라가 `limit` 을 **안 보낸다** |
| 5 | `/enrichment` 페이지 | 라우트 등록됨(가드 참) · 핸들러 존재 | HTML 도 엔트리도 없음 → 항상 404 (**의도된 묘비**) |

### ⑨ 에서 나온 문서 정정

| 자리 | 적혀 있는 것 | 실측 |
|---|---|---|
| 🔴 `CODE_MAP.md:1682`·`:2143` | `queue_filters` 소비처 **4**(`enrichment.js`·`admin.js`·`ui.js`·`_queue_condition`) → 「워크리스트·배지·어드민 카운트가 **수치가 어긋날 수 없다**」 | **산 소비처 2.** `enrichment.js` 미빌드 · **`ui.js` 에 `nrichment` 가 «0회»**(355줄, export 7 전부 비-enrichment). 보장 문장 자체는 여전히 참이나, 지금 그것이 보장하는 것은 **워크리스트가 아닌 두 수의 일치**다 |
| 🔴 `CODE_MAP.md:3752` | `ui.js` export `updateEnrichmentBadge`(~348)·`notifyEnrichmentTableEvent`(~399) + 보조 `ENRICHMENT_COUNT_TTL`·`loadEnrichmentRules`·`findEnrichmentRule` | **다섯 다 없다** (client2/src 전량 grep 0) |
| 🔴 `CODE_MAP.md:2143` | `_queue_condition` 이 `to_public_rule(rule)["queue_filters"]` 를 받아 번역 | 지금은 `enrichment_config.queue_predicate_condition` 을 **호출**한다(`enrichment_analysis.py:139-170`). `queue_filters` 를 안 읽는다. 앵커도 죽음: `_queue_condition` 80→**139** · 파일 548→**706줄** |
| ⚠️ `CODE_MAP.md:51` | vite 엔트리 **7**(index/admin/map_editor/map_editor2/graph/trace/ledger) | 현재 **6**(main·admin·map_editor·map_editor2·**rnd_board**·**walk**). `graph`·`trace`·`ledger` 소멸 · 둘 신설. `enrichment` 는 그때나 지금이나 없음 ✅ |
| ⚠️ 줄 수 드리프트 넷 | — | `enrichment_candidates.py` 613→**954** · `enrichment_config.py` 1,638→**1,654** · `enrichment_mapper.py` ~177→**310** · `enrichment.js` 1,266→**1,278** |
| ✅ `CODE_MAP.md:91` | 「`enrichment_*.py` 앵커는 정확 0 — 함수명으로 grep 하라」 | **이 경고는 맞다.** 이번 측정도 전부 심볼 grep 으로 했다 |
| 🔴 `ENRICHMENT_QUEUE_SPEC.md` 머리말 | 「참조뷰 절반만 메인 그리드 사이드바로 이식 … **§5.x 서술은 여전히 유효**」 | 이식은 ✅ 정확. **「§5.x 유효」는 거짓** — §5.1 의 「워크리스트에 뜨고, 뒤로 정렬되고, 「판단키 없음 N건」으로 이름 붙는다」는 **지금 어느 화면에서도 일어나지 않는다**(E-4·E-5) |

### ⑨ 에서 목록이 놓친 흐름

- **① 맵 정렬 규칙 채택** — `map2/api.js:74 → :194 → view_model.js:842 selectAlignmentRules`.
  물음은 「이 표를 정렬할 수 있는 규칙이 몇 개인가」이고 읽는 것은 `to_public_rule` 의 `alignment`
  **불리언 하나**뿐이다. 청중은 맵 에디터2 운영자이고 **결손과 무관**하다.
  🔴 `map_editor2` 번들에 `enrichment/rules` 문자열이 있는 이유가 이것이다 — 라우트를 세면
  ⑨ 로 보이지만 **다른 물음**이다. (⑮ 의 `stages` 와 정확히 같은 부류)
- **② 정렬 뷰 해석(서버측)** — `main.py:4369 alignment_view_service.resolve_alignment_view` →
  `alignment_view_service.py:23 load_enrichment_rules`. **같은 규칙 파일, 다른 목적지**(프레임 정렬).
- **③ 「내 config 가 먹었나」 보고서** — `config_resolve_report.py:222-277` 이
  `declaring_views`·`global_auto_confirm_enabled`·`GLOBAL_KILL_SWITCH_KEY` 를 읽는다.
  답하는 것이 결손 수가 아니라 **선언의 도달 여부**다. E-7 드라이런 버튼이 이 화면에 붙어 있다.
- **④ 결손을 «만드는» 흐름** — E-1/E-2 는 ⑨ 의 «앞»이지 ⑨ 가 아니다:
  트리거가 사람이 아니라 outbox 이벤트고, 도착지가 워크리스트가 아니라 **파생 표**다.

### ⑨ 못 밝힌 것

- **라이브 규칙의 내용.** `server/config/enrichment_rules.json` 은 gitignore 다. 활성 규칙 수,
  `alignment:true` 인 규칙의 유무, `auto_confirm` 노브·전역 킬스위치의 상태를 **재지 않았다** —
  이 박스에서 재도 운영의 증거가 아니다(CLAUDE.md 관문). 그래서 「결손 N건」의 N 도, E-2 가
  실제로 도는지도 **모른다**. 🔴 **알려주시면 판정되는 것 한 줄: 활성 규칙 수와 규칙별 `auto_confirm` 값.**
- **하니스 넷의 현재 통과 여부** — 실행하지 않았다(측정 전용). 다만 **넷 중 셋이
  `readFileSync(src/enrichment.js)` + `sliceBalanced` 로 함수 본문을 «잘라» 돌린다** —
  CLAUDE.md 의 **잘라쓰기 금지**에 걸리고, 게다가 **출하될 수 없는 모듈**을 채점한다.
  (`enrichment_queue_partition_harness.mjs:65` 만 `import * as SHIPPED from '../src/enrichment_queue.js'`
  로 절반은 정본 규율이다.) 🔴 **이건 ⑨ 의 결함이 아니라 «시험이 죽은 코드를 지키고 있다»는 별건이다.**

---

## ⑰ 어드민 대시보드 (생애주기 5탭)

**한 줄:** **탭은 일곱인데 그 탭들을 먹이는 기계는 «다섯»을 전제한다.** 그리고 그 어긋남이
가장 나쁘게 나오는 자리가 **새로고침 버튼**이다 — 두 탭에서 **아무것도 안 받고 「새로고침했습니다」라고 말한다.**

### ⑰-0 먼저: 「5탭」이 무엇인가 — **일곱이다**

| # | 라벨 | 버튼 id | 핸들러 | `fetchData` 갈래 |
|---|---|---|---|---|
| 1 | Overview | `tab-overview-btn` | `fetchData()` → `fetchOverview` | ✅ `tab==='overview'` |
| 2 | **Tables** | `tab-tables-btn` | `refreshTableConfig()` | 🔴 **없음** |
| 3 | File Ingestion | `tab-file-btn` | `fetchData()` | ✅ `tab==='file'` |
| 4 | Chain | `tab-chain-btn` | `fetchData()` + `refreshChainRule()` | ✅ `tab==='chain'` |
| 5 | Auto Update | `tab-autoupdate-btn` | `fetchData()` | ✅ `tab==='autoupdate'` |
| 6 | Enrichment | `tab-enrichment-btn` | `fetchData()` → `fetchEnrichmentStatus` | ✅ `tab==='enrichment'` |
| 7 | **Ontology Explorer** | `tab-ontology-btn` | `refreshOntologyExplorer()` + `refreshLedgerSources()` | 🔴 **없음** |

```
「5탭」은 «틀린 이름»이 아니라 «다른 것의 이름»이다 — fetchData 의 if/else 갈래 다섯을
정확히 묘사한다. 탭 바(tabDefs, admin.js:594-602)는 일곱이고 둘은 fetchData 를 통째로 건너뛴다
FEATURE_CHECKLIST §1.8 과 대조하면 축이 «셋 다 다르다»:
  체크리스트 해시 축   #overview #file #chain #autoupdate #enrichment #ontology  <- 여섯 (#tables 없음)
  체크리스트 표 행     Overview·File·Chain·AutoUpdate·Enrichment                 <- 다섯
  코드 TAB_ALIASES     overview tables file chain autoupdate enrichment ontology <- 일곱
🔴 Tables 탭은 체크리스트 §1.8 에 «한 글자도» 없다
```

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| D-1 | `admin.js::applyRoute` | `switchTab` | `DOMContentLoaded`(`:376`) · `hashchange`(`:396`) | 해시 문자열 | `TAB_ALIASES[key] \|\| 'overview'` — 모르는 해시는 **조용히** Overview | 1 | 🔇 오타 해시가 Overview 에 착지, 아무 말 없음 | ✅ |
| D-2 | `refreshBtn`(`:688`) | `fetchData()` | 사람 클릭 | — | 🔴 `const ok = await fetchData(); if (!ok) return;` → `messages` 사전에 **다섯 키만** → `messages[currentTab] \|\| '♻️ 목록을 새로고침했습니다.'`. **`fetchData` 의 `if/else` 는 `overview\|file\|chain\|autoupdate\|enrichment` 다섯이고 «`else` 가 없다»** → tables·ontology 는 **어느 갈래도 안 타고** `allRead=true` 로 반환 | 1 | 🔴 **완전 무음이 아니라 «거짓말»** — `markRefreshed()` 가 **새 시각**을 찍고 폴백 **성공 토스트**가 뜬다 | 🔴 **§⑰-A** |
| D-3 | `setInterval` 30s(`:379-385`) | `fetchData({silent:true})` | 타이머 | — | 가드 셋: `document.hidden` · `isInlineEditorActive\|\|isEditorDirty` · **`currentTab` 이 overview/file/chain 일 때만** | 1 | 🔇 **autoupdate·enrichment·tables·ontology 는 «영원히» 자동 갱신 없음** | ⚠️ |
| D-4 | `fetchOverview`(`:3330`) | 7 라우트 | Overview 진입 · 30s | `Promise.all` GET ×7 | `failed?page=1&limit=100` · `workspaces` · `outbox/failed?page=1&limit=3` · `chain/rules` · `mappers/list` · `auto-update/status` · `file-ingestion/active` — 전부 `.catch(()=>null)` | `renderOverview` 1 | 🔊 **넷이 다 실패해야** `throw`. 셋 실패는 카드만 표기 | ✅ |
| D-5 | `refreshLedgerSources`(`:1142`) | `GET /admin/ledger/sources` | Ontology 탭 진입 **만** | HTTP GET | 🔴 **6키 전송 / 1키 소비** — `ledger_sources_panel.js` 는 `payload.ingestion` **하나**만 읽는다. `kinds`·`unsupported_kinds`·`sources`·`config_path`·**`error`** 전부 client2 히트 0 | 1 | 🔴 **선언 파일이 깨지면 서버가 `200 + error:"JSONDecodeError…"` 를 내는데**(`ledger_admin.py:1023-1031`) 클라의 `unavailable` 경로는 **HTTP 상태로만** 갈려 200 을 정상 통과 → **빈 정상 패널**로 보인다 | 🔴 **§⑰-B** |
| D-6 | `/admin/chain/queue` 응답 | `chain_queue_panel.js` | Chain 탭 · 30s | HTTP JSON | 🔴 **13키 전송 / 11키 소비.** 안 읽히는 둘: `loop_uptime_seconds` · `mapper_reload_age_seconds`(client2 전건 0) | 1 | 🔇 서버 주석(`main.py:3915-3919`)이 **「재시작하면 풀리나」에 답하라고** 넣은 두 수가 화면에 없다 | ⚠️ |
| D-7 | `/admin/auto-update/status` 응답 | `renderAutoUpdateTable` | AutoUpdate 탭 진입 **만** | HTTP JSON | `{status, data, last_updated}` — 🔴 **`last_updated` client2 전건 0 히트** | `st.data` 만 | 🔇 「이 현황이 «언제» 것인가」가 화면에 없다 (D-3 과 겹쳐 **가장 낡을 수 있는 탭**) | ⚠️ |
| D-8 | `fetchEnrichmentStatus`(`:4501`) | `GET /enrichment/rules` | Enrichment 탭 · 15s TTL | 🔴 **bare `fetch()` — `adminFetch` 아님** | 토큰 헤더 **미첨부**. 서버(`main.py:4984`)도 **게이트 없음** — 짝이 맞는다 | 1 | 🔇 401 이 애초에 안 난다 | ⚠️ **§⑰-C** |
| D-9 | `saveScriptCode`(`:4377`) | `POST /admin/scripts/code` 🔒! | `saveCodeBtn`(`:791`) | JSON `{path, code}` | ✅ **저장 라우트가 있고 버튼이 닿는다** | 1 | 🔊 성공/실패 토스트 + `beforeunload` dirty 가드 | ✅ |
| D-10 | `adminFetch`(`:173`) | `/admin/*` 전부 | 매 호출 | `X-Admin-Token` 헤더 | `isGateRejection` = **401/403 AND `WWW-Authenticate` 가 `X-Admin-Token` 을 지목** → 1회만 재프롬프트. 503 은 `body.detail` 토스트 후 반환 | **39 호출부** | 🔊 프롬프트 1회, 취소 시 `adminTokenDeclined` | ✅ **CORS `expose_headers` 서술이 실제로 쓰인다** |
| D-11 | `runRetroactiveCount`(`:3193`) | `GET /admin/retroactive/{op}/count` | 사람 클릭 | GET 쿼리 | 쿼리는 `paramEntries` = **연산이 «선언한» 파라미터만**. 🔴 서버가 받는 `scan_limit` 은 client2 전건 **0** → 항상 서버 기본값 | 1 | 🔊 `COUNT_FAILED` + 사유 | ⚠️ |
| D-12 | `GET /admin/config/notation/preview` · `GET /admin/ledger/config/raw` · `POST /admin/ledger/dry-run` | — | — | HTTP | 게이트까지 달린 라우트 **셋** | 🔴 **client2 전건 0 히트 (셋 다)** | 🔇 | ⚰️ **§⑰-D** |
| D-13 | `GET /api/ledger/gaps` | `gap_catalogue.js` | Overview, `refreshConfigResolve` 성공 직후 | bare `fetch()` | 🔴 `name=` 을 **안 보낸다**(의도 — 주석 명시). 응답 `{mode,count,gaps}` 중 **`gaps` 하나만** 읽는다 | 1 | 🔊 503 `detail` 그대로 | ⚠️ **라우트 docstring 이 「목록은 공짜, 펼 때 센다」로 설계했는데 «펼치는 컨트롤»이 없다** |

### ⑰-A 핵심 발견 — 「**두 탭에서 새로고침이 «아무것도 안 하고 성공을 말한다»**」

```
fetchData()  admin.js:881·884·904·942·964 — if/else 갈래 «다섯». else 없음
refreshBtn   admin.js:688-700
             const ok = await fetchData();
             if (!ok) return;                       <- tables/ontology 는 ok === true
             showToast(messages[currentTab] || '♻️ 목록을 새로고침했습니다.', 'success');
                                            ^^^^^^^^ 폴백이 «성공»으로 뜬다
markRefreshed()  admin.js:426 — 시계 문자열을 «새 시각»으로 갱신
```
🔴 **운영자는 «새 시각»과 «성공 토스트»를 둘 다 보고 최신이라 믿는다. 요청은 한 건도 안 나갔다.**
이것은 「조용한 실패」보다 나쁘다 — **성공을 «적극적으로 주장»한다.**
```
그리고 이건 «세 기계가 같은 다섯을 전제»해서 생겼다:
  fetchData 의 갈래       다섯
  TAB_ERROR_MSG (:449)    다섯
  30초 폴의 화이트리스트   셋
  그런데 탭은            일곱
=> 탭을 «둘 더» 만들 때 이 셋 중 «아무도» 안 따라왔다. 그리고 그것을 알릴 자리가 없다
```
📎 이것이 「가드는 도달 가능해지는 날 틀린다」와 같은 부류다 — 갈래 다섯이 탭 다섯이던 날에는
   `else` 가 없는 것이 **옳았다.**

### ⑰-B 두 번째 — 「**깨진 선언이 «빈 정상 화면»이 된다**」

```
서버   ledger_admin.sources_view — 선언 파일 읽기가 던지면
       error = f"{exc.__class__.__name__}: {exc}"  를 세우고 «200 으로» 돌려준다
클라   refreshLedgerSources 의 unavailable 경로는 «HTTP 상태»로만 갈린다 -> 200 은 정상 통과
       그리고 ledger_sources_panel.js 는 payload.ingestion «하나»만 읽는다 — error 도 sources 도 안 읽는다
화면   「소스 없음」
```
🔴 **「없어서 0」과 「못 읽어서 0」이 «같은 픽셀»이다.** 기억의 「같아 보이는 다섯 개의 0」이
이 저장소에서 다시 나온 자리이고, **서버는 사유를 이름까지 붙여 보내 주고 있다.**

### ⑰-C 세 번째 — 「**FEATURE_CHECKLIST 의 「전부 게이트 뒤」가 거짓이다**」

체크리스트 §1.8 헤더: 「아래 탭이 부르는 `/admin/*` API는 **전부 게이트 뒤** … 토큰이 없으면
**모든 표가 비어 있고**」. 🔴 **Enrichment 탭은 안 빈다** — `/enrichment/rules` 는 `/admin/` 네임스페이스가
아니라 게이트가 없고(`main.py:4984`), 클라도 `adminFetch` 가 아니라 **bare `fetch()`** 다(`admin.js:4501`).
결손 카운트가 타는 `/tables/{t}/data` 도 마찬가지다.
⚠️ **결함이라기보다 «문서가 못 따라온 설계»로 보인다** — 다만 「토큰 없으면 전부 빈다」를
**보안 서술로** 읽으면 틀린 그림을 준다.

### ⑰-D 「소비자 0」의 갈래

| 심볼 | 없으면 못 말하게 되는 것 | 판정 |
|---|---|---|
| `GET /admin/ledger/config/raw` · `POST /admin/ledger/dry-run` · `GET /admin/config/notation/preview` | 「원장 선언 원문」 · 「이 선언을 쓰면 무엇이 나오나」 · 「내 표기 선언이 어떻게 보이나」. **Tables·Chain 은 `…/raw` 편집 패널을 이미 «둘» 돌리는데 원장만 없다** | 📡 **퍼뜨리기 — 셋이 «한 화면»이다.** 템플릿이 이미 두 벌 돈다(「근원 템플릿 + 데이터 갈아끼우기」 그대로) |
| `/api/ledger/gaps` 의 `name=` | 「이 격차가 «몇 건»인가」 — 서버 docstring 이 「목록은 공짜, 펼 때 센다」로 **UX 까지 설계**해 뒀다 | 📡 **퍼뜨리기** — 펼치는 컨트롤만 없다 |
| `/admin/chain/queue` 의 `loop_uptime_seconds`·`mapper_reload_age_seconds` | **「재시작하면 풀리나」** — 서버 주석이 그 물음을 명시 | 📡 **퍼뜨리기** — 패널이 나머지 11키를 이미 그린다 |
| `/admin/auto-update/status` 의 `last_updated` | 「이 현황이 언제 것인가」 | 📡 **퍼뜨리기** (기준 시각은 UI 상설의 ✅ 남는 것) |
| `/admin/retroactive/{op}/count` 의 `scan_limit` | 사실상 없다 — 어느 op 도 `params` 에 선언하지 않고, `truncated` 가 절단을 이미 말한다 | 🗑️ **빼기** — 축을 늘리면 사용자에게 배관을 묻는 꼴 |

### ⑰ 에서 나온 문서 정정

| 자리 | 적혀 있는 것 | 실측 |
|---|---|---|
| 🔴 `CODE_MAP §7` `admin.js` | **4,118줄** @`64b562b6` · 「파이프라인 **5탭**」 | **4,681줄** · 버튼·`tabDefs` **일곱** |
| 🔴 `CODE_MAP:959` | `require_admin_token_strict` = 「코드 실행에 닿는 **2 라우트 전용**」 | `main.py` **3** + 온톨로지 라우터 **10** = **13**. ⚠️ **같은 문서 `:688` 은 「셋」이라 적어 «자기와 모순»** — `:688` 이 맞고 `:959` 가 낡았다 |
| 🔴 `CODE_MAP:814` | 「`/admin/*` + `/internal/events/*` 4개 = **23** 라우트」 | `main.py` 의 `/admin/*` 만 **35** |
| ⚠️ 「read=일반 / write=strict」 라는 통념 | — | **축은 「코드 실행」이다.** POST 11 중 strict **3**, 비-strict **8**(`tables/config/raw` 포함 — 즉 **토큰 미설정 서버에서 선언 파일 쓰기가 열려 있다**). `admin_auth.py:237` docstring 이 그 축을 정확히 적는다 |
| 🔴 `FEATURE_CHECKLIST §1.8` 헤더 | 「전부 게이트 뒤 · 토큰 없으면 모든 표가 빈다」 | **거짓** (§⑰-C) |
| 🔴 `FEATURE_CHECKLIST §1.8` 탭 축 | 해시 여섯 · 표 행 다섯 | 정본 키 **일곱** — **`tables` 가 문서에 전무**, Ontology 도 표에 없음 |
| 🔴 `FEATURE_CHECKLIST §1.8` Enrichment 행 | 「결손 현황 + **컨베이어 딥링크**」 | **딥링크 없음.** `enrichment-tab-wrapper` 안 `<button>` **0개** · `href` **0** |
| ⚠️ `FEATURE_CHECKLIST §1.8` Overview 행 | 「상단 파이프라인 헬스 스트립 공용」 | 스트립은 `display:none`(소유자 판정 2026-09-05, **닫힘**). 체크리스트는 아직 살아 있다고 말한다 |
| ⚠️ `admin.js:254` 주석 | `AUTO_REFRESH_MS` = 「Overview/File/Chain **+ 헬스 스트립**」 | 스트립은 이 루프에 없다. 폴은 세 탭뿐 |

### ⑰ 에서 목록이 놓친 흐름

- **① 온톨로지 익스플로러 — `/admin/ontology-explorer/*` «15 라우트»(strict 10).**
  Ontology **탭 «안»**에 살지만 청중(선언 작성자)·트리거·목적지가 전부 다르다.
  🔴 **1차 실측이 이미 ⑫ 로 «따로» 쟀다** — 즉 흐름 목록에서 ⑰ 과 ⑫ 가 «같은 탭»을 나눠 갖는다.
  탭으로 세면 하나, 흐름으로 세면 둘이다.
- **② 핵심가치 계기 두 줄** — `GET /dashboard/summary`(재교정률·교정 공수, 5분 스로틀).
  Overview «안»이지만 **파이프라인 상태가 아니라 «제품 지표»**다. 청중이 다르다.
- **③ 소급 적용(retroactive)** — Overview 의 한 블록이지만 **유일한 «쓰기 촉발» 자리**이고
  strict 게이트·인라인 확인·취소·실행 등록부를 자기가 다 든다(라우트 5 + `retroactive_view.js`).
- **④ `rescope_handoff`** — `main.js` 가 쓰고 `admin.js::adoptRescopeHandoff` 가 먹는
  **그리드 → 어드민 인계**. 탭 흐름 «밖»의 횡단 이음매다.

### ⑰ 못 밝힌 것

- `/admin/mappers/list` · `/admin/chain/rules` · `/admin/outbox/failed` · `/admin/file-ingestion/logs`
  넷의 **응답 키 전량 vs 소비 키**. 라우트 «인자»는 전부 대조했고(모두 ✅ 전송) 응답 키 계수는 안 냈다.
- `ingestion_view()` 의 소스별 키 전량 vs `ledger_sources_panel` 소비 키의 정확한 차집합
  (최상위 6키 중 1키만 읽는 것은 확정).
- `retryTransaction`(`:4108`)의 `txId` **미인코딩**이 실제로 깨지는지 — `transaction_id` 형식을
  안 봤다. UUID 면 무해하다. 🔴 **결함으로 단정하지 않는다.**
- 서버를 안 띄웠으므로 전부 «정적 join» 이다. 401/503/404 경로가 실제로 그 문장을 찍는지는
  **코드 판독이지 관측이 아니다.**

---

## ㉒ 데스크톱 래퍼 · 듀얼 테마

### 🔴 먼저 — 이것은 «한 흐름이 아니라 둘»이다

```
공유하는 것이 파일·심볼·데이터 «어느 것도 없다»
  A 데스크톱 래퍼   파이썬 프로세스 기동 · 주소 해석(argv·env·파일) · HKCU · httpx
  B 듀얼 테마       브라우저 안의 localStorage · data-theme 속성 · CSS 변수
유일한 접점        셸이 {base}/?client=desktop 으로 index.html 을 «담는다»
                  그런데 그 페이지는 자기 테마를 «자기가» 초기화한다 -> 담는 관계이지 이음매가 아니다
```
🔴 **그리고 「둘이다」의 실측 근거가 하나 더 있다 — 둘이 만날 «뻔한» 자리에서 실제로 안 만난다.**
QtWebEngine 프로파일의 `localStorage` 는 운영자의 브라우저와 **별개**다. 셸에서 처음 열면
키가 없어 **항상 `light`** 로 뜬다. 그리고 OS 테마 ↔ 셸 다리도 없다(`prefers-color-scheme` **0건**).

### GROUP A — 데스크톱 래퍼

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| W-1 | `run_decoupled_app.py::main` `:333-338` | `desktop_wrapper.py` 프로세스 | **`--server-only`/`--no-client` 가 «없을» 때** (기본이 «띄운다») | subprocess argv | `[sys.executable, "<root>/client/desktop_wrapper.py"]` — 🔴 **인자가 하나도 안 붙는다.** `--server` 도 `--print-target` 도 없다 | 1 (`Supervisor(specs)`) | 🔊 `desktop_client_stdout.log` 로 tee (`process_supervisor.py:655-658`) | ✅ **저장소가 실제로 이것을 띄운다** |
| W-2 | `__main__:564` | `resolve_server_target()` | 프로세스 부팅 (HKCU·네트워크 «전에») | argv + `os.environ` + 파일 | W-1 때문에 `argv=[]`·`ASSY_SERVER` 미설정 → **3단계로 내려간다** | 1. 🔴 **저장소 전체 외부 호출자 0 · 시험 0** | 🔊 **3채널** — stderr + `QMessageBox.critical` + `exit 2` | ⚠️ |
| W-3 | `client/client_settings.json` | `_target_from_settings()` | W-2 안, argv·env 가 빌 때 | 파일 (**git 추적됨**) | `{"server_host":"127.0.0.1","server_port":8080,"current_user":"kk980"}` | 1 | 🔊 `ServerTargetError` → 위 3채널 | ⚠️ **`source` 가 «항상» `client_settings.json`** — ④ `default` 갈래는 stock 체크아웃에서 **도달 불가** |
| W-4 | `base_url()` | `HybridDesktopClient` | 해석 반환 직후 | 함수 인자 | `http://127.0.0.1:8080` → `web_url = http://127.0.0.1:8080/?client=desktop` | 2 (`self.web_url` · `_do_upload` api_url) | 🔇 QtWebEngine 이 로드 실패 페이지를 그린다. **창은 뜬다** | ✅ |
| W-5 | `web_url` 쿼리 | `state.js:141 isDesktop` | 페이지 로드 `URLSearchParams` | URL 쿼리 | `client=desktop` | 2 (`main.js:1147`·`:1173` — **둘 다 CSV 저장 경로 분기뿐**) | 🔇 저장 다이얼로그가 두 번(Qt + `showSaveFilePicker`) | ✅ |
| W-6 | `register_uri_scheme()` | **HKCU** | 프로세스 부팅, headless 아닐 때 (`:595`) | 레지스트리 키 | `HKCU\Software\Classes\assymanager` 기본값 `URL:AssyManager Protocol` · `URL Protocol=""` · `…\shell\open\command` = `"<python.exe>" "<root>\client\desktop_wrapper.py" "%1"` | 🔴 **0** — `assymanager://` 를 «만드는» 유일한 자리 `client2/src/main.js:100` 이 **블록 주석 안**(`:94-104`) | 🔇 `try/except` 가 삼키고 `print` 한 줄 | ⚰️ **§㉒-A** |
| W-7 | `DropEventFilter::eventFilter` | `runJavaScript("window.currentTable")` | **OS 드래그앤드롭** `QEvent.Drop` | Qt 이벤트 → QWebEnginePage 브리지 | 식 `window.currentTable`, **드롭당 1회**(파일당 아님) | 1 (`api.js:112` 가 `window.currentTable` 을 세운다) | 🔊 `QMessageBox.warning`「먼저 화면에서 대상을 업로드할 테이블을 선택하세요.」 | ✅ |
| W-8 | `_do_upload()` | `POST /tables/{table}/upload` (`main.py:3185`) | `_do_upload_batch` 루프, 파일당 1회 | HTTP multipart (httpx) | `?user=<getpass.getuser()>&relative_path=<rel>` — `rel` 은 **드롭한 것의 부모** 기준(`WF-001/WORK_…/voids.json`) | 1 · `relative_path` 는 `main.py:3230` 이 소비 | 🔇→🔊 예외는 `print` 로 삼키고 **배치 끝에** `_toast('❌ N개 중 M개 실패')` → `window.showToast` | ✅ |
| W-9 | `extend_no_proxy()` | httpx | 해석 직후 | 환경변수 `NO_PROXY` | 모듈 헤더가 httpx·Qt import **전에** `127.0.0.1,localhost` 를 박고, host 가 이미 있으면 변화 없음 | 1 (httpx). 🔴 **QtWebEngine 은 안 읽는다**(docstring 이 스스로 명시) | 🔇 **프록시가 먹으면 「서버가 죽었다」와 «똑같이» 보인다** | ⚠️ |
| W-10 | 데스크톱 자식 exit | `process_supervisor.py:970` | 사람이 창을 닫음 | 프로세스 exit code | `restartable=False` → `_exit_requested = True` | 1 | 🔊 `{name} exited (code {code})` + **스택 전체 종료** | ✅ |
| W-11 | `run_decoupled_app.py:351` | `_roster.json` | 기동 1회 | 파일 | `[s.heartbeat for s in specs if getattr(s,"heartbeat",None)]` = **`watcher`·`chain`·`scheduler` 셋.** 데스크톱 `ChildSpec` 은 `heartbeat=` 를 **안 준다** → 걸러진다 | 1 (`health.py:219`) | 🔊 WARNING 한 줄 | ✅ **1차 실측의 「명부 셋」 재확인** |
| W-12 | `--print-target` | stdout | **사람이 직접 타이핑** | argv → stdout | 2줄: `Server target: … (source: …)` · `NO_PROXY=…` | 🔴 **0** — 저장소에 호출자 없음(문서 3곳이 «언급»만) | — | ⚠️ |
| W-13 | `index.html:305` | `GET /api/download/client` (`main.py:626`) | 사람이 `📥 Download Desktop` 클릭 | `<a href download>` | `AssyManagerClient.exe` | 1 | 🔇 **404 JSON 이 브라우저 탭에 그대로 뜬다** — 바로 옆 버튼이 피하려고 만든 그 실패 | ⚠️ `.spec` 이 onedir(`exclude_binaries=True`)이라 **단독 exe 가 «생기지 않는다»** |
| W-14 | `main.js:368` | `GET /api/desktop/download` (`main.py:647`) | `#desktop-download-btn` 클릭 | HTTP GET | 없으면 404 `{"reason":"desktop_build_absent"}` | 1 | 🔊 showToast「데스크톱 빌드가 없습니다 · 서버에 zip 이 아직 없습니다.」 | ✅ **가드가 있는 쪽** |

### GROUP B — 듀얼 테마

| # | 출발 | 도착 | 트리거 | 나르개(IO) | 지나가는 것 (실측) | 받는 쪽 | 끊기면 | 상태 |
|---|---|---|---|---|---|---|---|---|
| H-1 | head 인라인 FOUC 스니펫 | `<html data-theme>` | **HTML 파싱 (CSS 로드 «전»)** | `localStorage['theme']` → DOM 속성 | `getItem("theme")` → `data-theme="dark"` 아니면 `"light"` | ✅ **6 / 6 엔트리 전부** | 🔇 `catch` 가 `light` 스탬프 | ✅ |
| H-2 | `tokens.css` (**308줄**) | 6 엔트리 | 페이지 로드 | CSS | `:root[data-theme=…]` 값 세트 — hex **47** + rgb **46** = **93 리터럴이 여기 «모여 있다»** | 6 (`main.js`·`admin.js` import / 나머지 넷 `<link>`) | 🔇 무스타일 | ✅ |
| H-3 | 엔트리 JS | `initTheme()` | DOM 준비 후 1회 | 함수 호출 | 토글 클릭 바인딩 + AG-Grid 클래스 동기 + **`storage` 이벤트 구독**(탭 간 동기) | 🔴 **4 / 6** — `admin.js:357` · `main.js:134` · `map_editor.js:356` · `map_editor2.js:131`. **없다: `rnd-board.html` · `walk.html`** (두 진입 모듈에 `theme` 문자열 **0건**) | 🔇 **아무것도 안 울린다** | ⚠️ **§㉒-B** |
| H-4 | 마크업 | `[data-theme-toggle]` | 사람 클릭 | DOM 속성 | `<button class="theme-toggle-btn" data-theme-toggle>` | 🔴 **4 / 6** — index·admin·map_editor·map_editor2 각 1. **rnd-board·walk «0개»** | 🔇 버튼 자체가 없다 | ⚠️ **H-3 과 «같은 두 페이지»** |
| H-5 | `toggleTheme()` | `applyTheme()` | 토글 클릭 | localStorage · DOM 속성 · CustomEvent | `setItem('theme', next)` · `setAttribute('data-theme', next)` · `CustomEvent('themechange',{detail:{theme}})` | `themechange` 구독자 **2**: `admin.js:4265`(Monaco) · `map_editor.js:3397`(캔버스 재도색) | 🔇 | ✅ |
| H-6 | `applyTheme`/`initTheme` | `syncAgGridThemeClasses()` | 토글 · 로드 | DOM 클래스 | `.ag-theme-quartz` ↔ `.ag-theme-quartz-dark` 스왑 | 🔴 **외부 호출자 0**(`theme.js` 안 두 자리뿐). 대상 노드는 `index.html:367` **하나** | 🔇 그리드만 옛 테마 | ⚠️ 토글 «경로»는 실제로 부른다 — **`export` 만 근거가 없다** |
| H-7 | **OS 테마** | (없음) | 미디어 쿼리 | CSS `@media` | 🔴 **`prefers-color-scheme` 실측 «0건»** — 유일 히트는 벤더 로고 `assets/vite.svg` | **0** | 🔇 **OS 다크 사용자가 라이트를 받는다** (`theme.js:15 DEFAULT_THEME='light'`) | 🔴 **§㉒-C** |
| H-8 | `themechange` | `rebuildThemeColorCache()` (`map_editor.js:3327`) | 테마 전환 | `getComputedStyle` → JS 캐시 | `--canvas-out-bg`·`--canvas-line`·`--canvas-wm-front` 등 **15 토큰**, 각각 hex/rgba 폴백 동반 | 2 | 🔇 폴백(라이트) 색으로 그린다 | ✅ **캔버스는 토큰을 «읽는다»** |
| H-9 | `data-theme` 속성 | `rnd_board/map_panel.js:806 _palette()` | 페인트 시점 | DOM 속성 읽기 → **하드코딩 전사 팔레트** | `ROLES.light`/`ROLES.dark` hex **14개**(`#d7dce4`·`#c22f2f`·`#1a66d0`·`#8a5a00` + 다크 대응) | 1 | 🔇 **`tokens.css` 가 바뀌어도 «여기만» 안 따라간다** | ⚠️ 전사본. 다만 「painter 는 색을 읽지 않는다」로 **선언**돼 있고, **rnd-board 는 H-3 때문에 전환 자체가 안 일어나 오늘은 안 드러난다** |
| H-10 | CSS 규칙 | 셀렉터 | 렌더 | CSS | 토큰 **진짜** 우회 **9건**: `style.css:1703 #0b1220`·`:1709 #38bdf8`·`:1710 #f59e0b` · `ontology_explorer.css:411 #c73b45`·`:501 #fff/#9d2b32`·`:301/:505/:514` rgb 그림자 | — | 🔇 **다크에서 안 뒤집힌다** | ⚠️ |

### ㉒-A 핵심 발견 (A) — 「**매 기동이 HKCU 에 쓰는데, 그것을 부를 수 있는 것이 저장소에 없다**」

```
쓰기      desktop_wrapper.py:595 — headless 가 아닌 «모든» 기동에서 register_uri_scheme()
읽기      assymanager:// 를 «내는» 유일한 자리 client2/src/main.js:100
          -> 그 줄이 :94~:104 «블록 주석 안»에 있다
해제      DeleteKey / DeleteValue 가 저장소 전체에 «0건»
=> 쓰기만 있고, 읽는 쪽도 지우는 쪽도 없다. 매 기동이 «흔적만» 남긴다
```
🔴 **이것은 「소비자 0」 중에서도 «빼기» 쪽이다** — 없애도 못 말하게 되는 것이 없고,
**남겨 두면 사용자 기계의 레지스트리를 계속 건드린다.** 되돌릴 경로가 없다는 것이 그 무게다.

### ㉒-B 핵심 발견 (B) — 「**새 두 페이지가 테마를 «읽기만» 한다**」

```
rnd-board.html · walk.html
  FOUC 스니펫    ✅ 있다        -> 로드 시점 테마로 «그려진다»
  tokens.css     ✅ <link> 로 싣는다
  initTheme()    🔴 안 부른다   (진입 모듈에 `theme` 문자열 0건)
  토글 버튼      🔴 0개
=> 결과 셋: ① 세션 내내 «못 바꾼다»  ② 다른 탭에서 바꿔도 «안 따라온다»
            (storage 리스너는 initTheme 이 거는데 그것을 안 부른다)
            ③ 아무것도 «안 울린다»
```
⚠️ **결손이 «일관돼서» 우연이 아니다** — 두 페이지 다 스니펫과 CSS 는 챙겼고 **JS 초기화만** 빠졌다.
🔴 그리고 이 둘이 **가장 새 엔트리**다(`rnd_board`·`walk`). 즉 **엔트리를 더할 때 따라오지 않는 것이
무엇인지**를 이 흐름이 말해 준다 — ⑰-A 의 「탭을 더할 때 세 기계가 안 따라왔다」와 **같은 모양**이다.
📎 재검 확인: 세션 중 착지한 `78a88e7f`(walk 라운드) **이후에도** 그대로다.

### ㉒-C 세 번째 — 「**`prefers-color-scheme` 은 «덮이는» 것이 아니라 «없다»**」

`client2/` 소스 전체 실측 **0건**(벤더 SVG 제외). 기본값은 `theme.js:15 DEFAULT_THEME='light'` 와
FOUC 스니펫의 `t === "dark" ? "dark" : "light"` **두 곳에 따로** 박혀 있다.
🔴 **OS 다크 사용자는 «선택한 적 없는» 라이트를 받고**, 그것을 바꾸려면 토글을 눌러야 하는데
그 토글이 없는 페이지가 둘이다(㉒-B). **두 결손이 곱해진다.**

### ㉒ 양끝이 다 있는데 아무것도 잇지 않는 이음매 (일곱)

| # | 이음매 | 양끝 | 가운데 | 판정 |
|---|---|---|---|---|
| 1 | `assymanager://` | `register_uri_scheme()` 가 HKCU 에 쓴다 · OS 셸이 읽을 준비 완료 | URL 을 «만드는» 코드가 주석 안 | 🗑️ **빼기** |
| 2 | `--print-target` | 헤드리스 모드 구현됨 · **문서 3곳이 절차로 지목** | 호출자 0 (사람 손뿐) | 📡 **퍼뜨리기** — 없애면 「GUI 없이 우선순위를 채점한다」가 못 말해진다 |
| 3 | `resolve_server_target` 의 주입 가능한 3인자 | 「프로세스 기동 «없이» 채점」이 **설계 목적**으로 적혀 있다 | **시험 0 · 외부 호출자 0** | 📡 **퍼뜨리기** — 계약은 옳고 **하니스가 없다** |
| 4 | `syncAgGridThemeClasses` | `export` 돼 있다 | 외부 호출자 0 | 🗑️ **빼기(export 만)** — 동작은 살아 있다 |
| 5 | `client_settings.json::current_user` | 파일에 값이 있다(`"kk980"`) | 읽는 코드 0 (`getpass.getuser()` 를 쓴다) | 🗑️ **빼기** |
| 6 | `/api/download/client` | 라우트 + 링크 | `.spec` 이 onedir 이라 단독 exe 가 안 생긴다 | 🗑️ **빼기** — 옆 버튼(zip)이 가드까지 갖고 같은 일을 한다 |
| 7 | `enrichment.js::initTheme()` | 호출이 있다 | 모듈이 안 빌드된다(⑨ E-4) | ⚰️ 그 모듈과 함께 |

### ㉒ 에서 나온 문서 정정

| 자리 | 적혀 있는 것 | 실측 |
|---|---|---|
| 🔴 `CODE_MAP:3518` | `client/desktop_wrapper.py` **514줄** | **606줄** |
| 🔴 `CODE_MAP:3518` 앵커 넷 | `DEFAULT_SERVER_HOST(~51)` · `resolve_server_target(~183)` · `HybridDesktopClient(~279)` · `register_uri_scheme(~433)` | **64 · 196 · 302 · 516** — 전부 **~90줄 밀렸다** |
| ✅ `CODE_MAP:3518` | `is_port_open` 삭제 · 거부 문구 ASCII 사유(cp949 파이프) · `client_settings.json` git 추적 | **셋 다 맞다** (`process_supervisor.py:655-658` 이 cp949 를 자기 입으로 적는다) |
| ⚠️ `CODE_MAP:3518` 우선순위 사슬 | ④ 기본값 `127.0.0.1:8080` | **stock 체크아웃에서 도달 불가** — `client_settings.json` 이 추적돼 있어 ③이 항상 이긴다. `source` 는 «항상» 그 파일 |
| 🔴 `frontend.md:32` | DevTools 「원격 디버깅 :9222」 | **opt-in 이다** — `ASSY_DEVTOOLS` 가 있을 때만(`desktop_wrapper.py:22-25`). 🔴 **이 변수는 현행 문서 어디에도 없다** |
| 🔴 `frontend.md:57` | `client/*.spec` 은 의도적으로 gitignore | `.gitignore:54` 가 `!client/AssyManagerClient.spec` 로 **되살린다** — 추적된다 |
| 🔴 `frontend.md` 엔트리 표 | 다섯 행 | 엔트리 **6** — **`walk.html` 이 표에 없다** |
| 🔴 `client2/src/theme.js:4` | 「localStorage('theme') 영속 · **4페이지 공통**」 | 엔트리 **6**, `initTheme` 호출은 **4** — 🔴 **수는 우연히 맞고 «어느 넷인지»가 틀렸다** |

### ㉒ 에서 목록이 놓친 흐름

- **① 테마가 «데스크톱 셸로 안 따라간다».** QtWebEngine 프로파일의 `localStorage` 가 브라우저와
  별개라 셸에서 처음 열면 **항상 `light`**. **A 와 B 가 만날 뻔한 유일한 자리이고 실제로는 안 만난다.**
- **② `ASSY_DEVTOOLS` → `QTWEBENGINE_REMOTE_DEBUGGING`**(`desktop_wrapper.py:22-25`).
  별개 흐름이고 **현행 문서에 0건**. 값 규칙(`1`=켜기, 1024 미만은 9222 로 폴백)이 **코드 주석에만** 산다.
- **③ 데스크톱 다운로드 입구가 «둘»** — 같은 화면(`index.html`)에 exe 링크와 zip 버튼.
  **서로 다른 산출물, 가드는 하나만**(W-13/W-14).
- **④ `_files_under` ↔ 브라우저 `webkitRelativePath` 계약** — 두 업로드 문이 «같은 루트»에서
  재도록 맞춰져 있고(`desktop_wrapper.py:393-399`) 서버 `main.py:3230` 이 소비한다.

### ㉒ 못 밝힌 것

- **운영 기계의 HKCU 실태** — 실제 등록 여부·값을 못 잰다. 저장소 사본만 봤다.
- **frozen 분기** — `settings_file_path()` 의 `sys.frozen` 갈래와 `register_uri_scheme()` 의
  frozen `cmd_str` 은 **코드로만** 확인했다(exe 빌드·실행 금지).
- **QtWebEngine 이 정말 `NO_PROXY` 를 무시하는지** — docstring 의 «주장»이고 실행으로
  확인하지 않았다. CODE_MAP 서술은 **「문서가 그렇게 적혀 있다」까지만** 확인됐다.
- **(부수, 결함으로 단정하지 않음)** `desktop_wrapper.py:454` `_toast` 의 이스케이프 —
  `message.replace("\\","\\\\").replace("'", "\'")` 에서 파이썬의 `"\'"` 는 그냥 `"'"` 라
  **두 번째 replace 가 자기 자신으로 치환**한다. 오늘 넘기는 문구가 전부 리터럴이라 **도달 불가**다.
  🔴 파일명이 메시지에 들어오는 날 JS 문자열이 깨진다 — 「가드는 도달 가능해지는 날 틀린다」 부류.

---

## 7. 2차 실측이 체크리스트에 «더하는» 것 (§4 규칙 그대로 — 발명 없음)

### ㉠ 선언된 것이 «실제로» 지나가나 — 아니오
```
🔴 전사 계획 검증이 «틀린 파라미터»로 짜여 있다 (plan_id / 서버는 ref_table+map_key) — 불렸다면 422
🔴 드라이런의 limit · 소급 count 의 scan_limit · gaps 의 name 이 «안 실림» -> 서버 기본이 항상 이김
⚠️ 오버레이 라우트의 eqp 는 «폐기됨(no-op)»이라고 서버가 자기 docstring에 적어 두고 계속 받는다
```
### ㉡ 받는 쪽이 «있나» — 아니오
```
🔴 core-summary — 「Info 창용」이라 적고 «전용 인덱스 스크립트»까지 지었는데 클라 소비자 0
🔴 결손 «목록» — 판정이 보정을 그리드로 옮겼는데 그리드에 큐 좁힘이 0
🔴 원장 선언 3종(raw · dry-run · notation preview) — 게이트까지 달고 클라 0. Tables·Chain 은 같은 패널을 이미 돌린다
🔴 validate 의 경고 4종 · 그 규모 상한 넷 — 촉발자 0
🔴 계약 심볼 resolve_valid_die_basis — 스펙이 «두 구현의 계약»이라 이름 붙였는데 운영 호출자 0
⚠️ 「재시작하면 풀리나」(loop_uptime·mapper_reload_age) · 「언제 것인가」(last_updated) — 보내는데 안 읽힌다
```
### ㉢ 끊기면 «시끄러운가» — 아니오(조용함)
```
🔴🔴 Tables·Ontology 새로고침이 «성공을 주장»한다 — 요청 0건 + 새 시각 + 성공 토스트
🔴 깨진 원장 선언이 «빈 정상 패널»이 된다 (서버는 200 + error 를 보내는데 클라가 안 읽는다)
🔴 rnd-board·walk 이 테마를 «못 바꾼다» — 버튼도 초기화도 없고 아무것도 안 울린다
🔴 OS 다크가 «조용히» 라이트로 (prefers-color-scheme 0건)
⚠️ 프록시가 QtWebEngine 을 먹으면 「서버가 죽었다」와 같은 그림
```
### ⚰️ 도달 불가 — 2차가 더한 것
```
GET /api/maps/overlay (클라 0) · GET /api/bonding-plan/core-summary (클라 0) ·
GET /api/transfer-plan/validate (호출자 0 · 파라미터 어긋남 · 번들에서 흔들려 떨어짐) ·
transfer_plan.js 의 __held_ 여섯(닫힌 죽은 섬) · 규모 상한 넷 ·
resolve_valid_die_basis · resolve_valid_die_set ·
어드민 원장 3종 · assymanager:// (HKCU 쓰기만) · /api/download/client ·
그리고 «검색이 못 보던» enrichment.js 1,279줄 + map2/authoring.js 394줄 (§0)
```

### 🔴 2차가 발견한 «부류» — 낱개가 아니라 이 셋이다

| 부류 | 사례 | 왜 부류인가 |
|---|---|---|
| **① 「N을 더할 때 기계가 안 따라온다」** | 탭 둘을 더했는데 `fetchData`·`TAB_ERROR_MSG`·폴 화이트리스트가 안 따라옴(⑰-A) · 엔트리 둘을 더했는데 `initTheme`·토글이 안 따라옴(㉒-B) | **둘 다 「다섯을 전제한 기계에 여섯째를 넣었다」**이고, 둘 다 «조용하다». 하나만 고치면 다른 하나가 남는다 |
| **② 「보류의 «사유»가 낡았다」** | `__held_refreshValidate` 가 기다리는 서버 계약은 «이미 왔다»(⑮-A) | 보류는 정당했다. **보류를 «다시 볼» 계기가 없는 것**이 부류다 |
| **③ 「낱개로 고쳐서 부류가 남았다」** | NUL 세 파일 중 «하나»만 고쳐짐(§0) | 판별식이 「이 파일이 고쳐졌나」였고 **「몇 개인가」가 아니었다** |

📎 ①과 ③은 **같은 병의 두 얼굴**이다 — 「이 사례를 고쳤나」로 물으면 옆의 형제를 못 본다.
   CLAUDE.md 의 「부류에서 판정한다, 낱개로 가져가지 않는다」가 **감사 자신에게** 걸린 자리다.
