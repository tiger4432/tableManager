# QA 적대적 검수 — M2-v2 「계획 = 그 맵 자체」 재설계 (서버+클라 합본)

> **검수:** qa-reviewer / 2026-07-26 · 대상: 미커밋 워킹트리(`8e34804` 위) · 코드 무수정
> **스위트 재실행:** `405 passed / 1 failed(test_map_presets_api — allowed)` — **주장 그대로 재현됨**

---

## 1. 판정

# 🔴 NO-GO (병합 차단 2건)

**근거 한 줄:** 오버레이 유도 변환이 **웨이퍼 바운딩박스를 무시**해 라이브 24쌍 중 **12쌍이 4셀 어긋난 좌표를 `status: ok`로 반환**하며(그중 10쌍은 변경 전 *명시 실패*였다 — 핵심가치 #3 정면 위배), 클라의 `pruneScoped`가 **빈 keep으로도 무조건 실행**되어 GET 1회 실패만으로 열린 맵의 서버 DOE 전량이 조용히 삭제된다.

두 건 모두 **국소 수정으로 해소 가능**하다(§5). 나머지 발견은 전부 후속 백로그이며, 재설계 자체의 방향·모델·계약은 건전하다.

---

## 2. 확인된 결함

### 🔴 B1 [차단·심각도 높음] 유도 변환이 웨이퍼 바운딩박스를 무시 — 라이브 12쌍이 조용히 4셀 어긋남
`server/map_overlay.py:225-234` (`make_frame_transform.to_target`)

**사실 관계.** 클라가 셀에 저장하는 x/y는 **바운딩박스 상대 시각좌표**다:
`client2/src/map_editor.js:1049-1060` — `xv = c - box.minC + startX`, `yv = r - box.minR + startY` (역변환 `getCellFromVisualCoords`, `map_editor.js:982-994`도 동일). `box`는 `getWaferBoundingBox`(`map_editor.js:999`)가 **phys 파라미터**(`phys_wafer_dia`/`phys_chip_x·y`/`phys_offset_x·y`/`phys_edge_margin`)로 실제 웨이퍼 원을 잘라 계산한 것이다.

서버는 그 항을 통째로 뺐다:
```python
c = int(x) - s_ox          # 참값은  x - s_ox + minC_src
...
return c + t_ox, r + t_oy  # 참값은  c - minC_dst + t_ox
```
**두 항은 합성 선형부의 계수가 +1일 때만 상쇄된다.** 거울(면 반전·180/270 조합)이 끼면 상쇄 대신 **가산**되어 `2·minC` 만큼 어긋난다.

**라이브 실측 (161건 메타, 물리치수 동일 쌍 전수).** 클라 파이프라인을 파이썬으로 그대로 복제해 정답을 만들고 대조했다. 정답 하네스는 ①자기 자신 쌍이 항등임 ②구현자 보고 §5-2-bis의 실측치(`test/QQ→bonding_map/QQ`의 `(1,1)→(-10,-12)`, `(5,7)→(-6,-6)`, `(12,3)→(1,-10)`)를 정확히 재현함 — 두 가지로 교차 검증했다.

```
derived 쌍 24건 중  정확 12  ·  조용한 오답 12   (전부 status: ok)

bonding_map/AAA (rot270,back)   -> bonding_map/aa123_a (rot0,back)     전 셀 (+4, 0)
bonding_map/EXP1 (rot0,front)   -> bonding_map/aa123_a (rot0,back)     전 셀 (+4, 0)
bonding_map/QQ  (rot270,back)   -> bonding_map/aa123_a (rot0,back)     전 셀 (+4, 0)
sample_map/aa123_a(rot270,front)-> bonding_map/EXP1    (rot0,front)    전 셀 (+4, 0)
bonding_map/aa123_a(rot0,back)  -> bonding_map/AAA     (rot270,back)   전 셀 (0, +4)
sample_map/base (rot0,front)    -> sample_map/aa123_a  (rot270,front)  전 셀 (0, +4)
… (총 12쌍, 29x25·27x21 규격 전부. 40x40 맵은 minC=0이라 무영향 —
   클라 라이브검증 V20이 `eds_fail_map→core_defect_map`(40x40)만 봐서 통과한 이유다)
```

**변경 전/후 대조 — 이것이 차단 사유다.** `git show HEAD:server/map_overlay.py`를 별도 모듈로 올려 같은 쌍을 돌렸다:

| OLD → NEW | 건수 |
|---|---|
| `align_unavailable`(명시 실패) → **SILENT-WRONG** | **10** |
| `align_unavailable` → CORRECT | 8 |
| SILENT-WRONG → CORRECT | 2 |
| SILENT-WRONG → SILENT-WRONG | 2 |
| CORRECT → SILENT-WRONG (순수 회귀) | **0** |

순수 회귀는 0이고 커버리지는 늘었다. 그러나 **"소리 나는 실패" 10건이 "조용한 오답"으로 바뀌었다.** 이는 구 QA B3 가드가 정확히 막으려던 거래이며, SYSTEM_OVERVIEW §1 핵심가치 #3(*"빠르지만 가끔 조용히 안 맞음"은 "느리지만 항상 맞음"보다 나쁘다*)의 정면 위배다.

**실패 시나리오 (데이터 오염까지 간다).**
1. 사용자가 `bonding_map/aa123_a`를 연다.
2. 오버레이 블록에서 `bonding_map:AAA`를 겹친다 → `status: ok`, 칩 `정렬됨 270°`. 화면상 아무 이상 없음.
3. 오버레이 행의 `[↓ 가져오기]`(`map_editor.js:3973 importOverlayToGrid`)를 누른다 → **4열 어긋난 셀이 `gridData`에 들어간다.**
4. `[⚡ Push]` → `replace_map: true`로 **실운영 `bonding_map/aa123_a`가 4열 밀린 맵으로 통째로 교체된다.**
   `importOverlayToGrid`의 격자 밖 필터가 오른쪽 4열을 조용히 버리므로 셀 수도 줄어 있다.
   가드는 전부 통과한다 — 정체성 일치, 값 잠금 정상, 확인창은 "이 맵 키를 덮어씁니다"만 묻는다.

**신규 테스트가 이 결함을 구조적으로 잡을 수 없다.** `server/tests/test_map_overlay.py:579 test_all_four_axes_compose_without_silent_error`(1024쌍)가 검사하는 것은 **단사 · 타깃 범위 내 · 왕복 항등**뿐인데, 셋 다 *같은 함수를 정·역으로 쓴 자기 대조*라 **균일 오프셋 오류에 전부 참**이다. `back(fwd(x,y)) == (x,y)`는 정의상 성립한다. 픽스처(`_meta_of`)는 phys 파라미터가 없어 마스크가 개입할 여지도 없다. 즉 "전수 대조 1024쌍"은 **독립 정답과 한 번도 대조하지 않았다.**

**권장 조치 (택1, ①이 정본).**
① 서버가 `grid_metadata`의 phys 파라미터로 바운딩박스를 계산(`isCellInsideWaferFast` 복제, ~25줄)해 `c = x - s_ox + minC_src` / `x = c - minC_dst + t_ox`로 고친다. 회귀는 **클라 규약을 독립 구현한 정답과 대조**해야 한다(자기 왕복 금지). 검증 하네스는 아래 스크래치패드에 그대로 있다 — 이식하면 된다.
② 즉시 병합이 필요하면, 합성 선형부에 거울이 포함되고 두 맵 중 하나라도 `minC/minR ≠ 0`이면 **`align_unavailable`로 되돌린다**(구 가드의 정확한 일반화). 조용한 오답보다 낫다.

> 정답 하네스: `…/scratchpad/q2_truth.py`(클라 파이프라인 복제 + 자기항등 sanity), `q3_sweep.py`(라이브 전수), `q4_oldnew.py`(구/신 대조).

---

### 🔴 B2 [차단·심각도 높음] `pruneScoped`가 빈 keep으로도 실행 — GET 1회 실패로 서버 DOE 전량 삭제
`client2/src/transfer_plan.js:954-955` (호출) · `:969-993` (본체) · `:1058-1061`·`:1103-1106` (촉발 조건)

```js
if (doeUpdates.length > 0) await putUpdates(DOE_TABLE, doeUpdates);
if (srcUpdates.length > 0) await putUpdates(DOE_SOURCE_TABLE, srcUpdates);
...
await pruneScoped(DOE_TABLE,        'doe_key',    new Set(doeUpdates.map(...)));   // ← 길이 가드 없음
await pruneScoped(DOE_SOURCE_TABLE, 'source_key', new Set(srcUpdates.map(...)));
```
업서트는 `length > 0` 가드를 받는데 **prune은 받지 않는다.** `pruneScoped`는 `(ref_table, map_key)` 범위 안에서 `keep`에 없는 행을 `batch_delete` 하므로, **`keep`이 비면 그 맵의 계획 전체가 삭제**된다. 절단 가드(`data.total > rows.length`)는 있지만 **공집합 가드는 없고**, 자기 catch(`:992`)는 완전히 비어 있어 삭제 사실조차 남지 않는다.

**실패 시나리오 A (네트워크 1회 실패 → 영구 손실).**
1. `bonding_map/AAA`에 서버 DOE 3구간 + 자재 5매가 저장돼 있다.
2. 맵을 연다 → `loadDoeFromServer()`가 일시 실패(500/타임아웃) → `catch`는 `console.warn`만(`:1058`) → `S.doe`가 빈 채로 남는다. **화면에도 토스트에도 아무 신호가 없다.**
3. 사용자가 legend 값 하나를 삭제하거나 색을 바꾼다 → `scheduleSave()` → 1.2s 후 `saveDoeToServer()`.
4. `doeUpdates = []`(밴드가 없으니) → `pruneScoped(…, ∅)` → **`map_doe` 3행 + `map_doe_source` 5행 전량 삭제.** 조용히.

**실패 시나리오 B (다중 브라우저).** `:1103` `if (!hadDraft && …)` — **오래된 localStorage 초안이 있으면 서버 로드를 아예 건너뛴다.** 브라우저 A가 어제 초안(밴드 0개)을 들고 있으면, 오늘 브라우저 B에서 저장한 계획을 A의 다음 편집 한 번이 지운다.

**권장 조치.** ① `doeUpdates.length === 0`이면 prune 금지. ② `S.doeLoadedFromServer` 플래그를 두고 서버 로드가 실패했으면 prune 금지(“모른다”와 “없다”를 구분). ③ `pruneScoped`의 빈 catch를 토스트까지 올린다. ④ 초안 우선 규칙에 서버 `eventtime` 비교를 넣는다.

---

### 🟠 M1 [심각도 중] 토스트 상한 — 에러 4건이 떠 있으면 **새 성공/정보 토스트가 즉시 파괴**된다
`client2/src/utils.js:71-76` (+ 삽입 `:149-150`)

```js
toastItems.push(item);
sweepToasts();   // ← 여기서 방금 넣은 것이 첫 번째 '비-에러'로 걸린다
...
for (let i = 0; i < toastItems.length && overflow > 0; i++) {
  if (toastItems[i].type !== 'error') { removeToast(toastItems[i]); i--; overflow--; }
}
```
`[err,err,err,err]` 상태에서 성공 토스트를 올리면 배열은 `[err×4, success]`가 되고, 인덱스 0부터 훑는 퇴거 루프에서 **유일한 비-에러 = 방금 넣은 그것**이 제거된다. 에러 TTL은 15초이고 새 에러마다 갱신되므로 창은 쉽게 유지된다.

**실패 시나리오.** admin 화면에서 인제션 오류가 연달아 뜨는 동안(`admin.js:701`, `2083/2109/2139`, `websocket.js:89`) 사용자가 코드를 저장한다 → `admin.js:2339` "정상 저장 및 핫 리로드되었습니다" 토스트가 **화면에 1프레임도 나오지 않는다.** 사용자는 저장이 안 된 것으로 판단한다. 이번 배치가 없애려던 "조용한 알림 소실"이 반대 방향에서 재발한 것이다.

**권장 조치.** 퇴거 후보에서 **방금 삽입한 항목을 제외**한다(`toastItems.slice(0, -1)` 대상으로 스캔). `sticky`도 퇴거에서 보호되지 않으니(`:72`) 함께 정리 권장(현재 호출부 없음).

> 나머지 토스트 주장(a·c·d·e·f)은 전부 **확인됨**: 만료시각 정본(`utils.js:64-68`, 타이머는 힌트일 뿐 `:82-87`), `visibilitychange`+`focus` 훅이 모듈 최상위에 **정확히 1회** 등록(`:91-96`), 에러 집계 제외(`:120`), `textContent` 전환(`:102-104` — 구 admin 구현은 `innerHTML`이었으므로 실질 보안 개선), TTL 15/9/5s(`:30`).
> `admin.js` 중복 구현 삭제 회귀 **없음**: 잔여 24개 호출부 전부 `admin.js:9`의 import로 해소, 미정의 심볼 0, CSS(`tokens.css:207-262`, `.toast.hide` 포함)가 6개 진입점 전부에 도달하며 `dist`도 동기 상태.

---

### 🟠 M2 [심각도 중] 페인트 잠금이 네트워크 1회 실패로 **조용히 전면 해제**된다
`client2/src/map_editor.js:89`·`:98`

```js
catch (e) { paintLockConfig = { ...NO_PAINT_LOCK, source: 'unsupported' }; }
```
`GET /api/maps/paint-rules` 한 번 실패하면 8개 강제 지점(`:645, 1794, 2353, 2781, 3154, 3183, 3204, 3999`)이 전부 무력화된다. `paintLockConfig.source`는 **어디에서도 읽히지 않아** UI 신호가 0이고, `fetchPaintRules`는 fire-and-forget(`:743`,`:3625`)이라 테이블을 다시 바꾸기 전까지 세션 내내 꺼진 채다.

**실패 시나리오.** 잠금 값 `F`(불량 칩)가 보호돼야 할 실맵에서, 사용자는 아무 경고 없이 F 셀을 덮어 칠하고 Push한다. §4의 오버레이 가져오기 규율 ②(잠금 존중)도 같이 무력화된다. **fail-open이 조용하다** — 최소한 배지·토스트로 표면화하거나, 404(미지원)와 네트워크 오류를 구분해 후자는 fail-closed로 가야 한다.

---

### 🟡 M3 [심각도 중] `doe_value` 재키잉 위험이 `stack_band`와 동일한데 방치 — **라이브 실증**
`server/config/table_config.json` (`map_doe.composite_key_source`) · `server/database/crud.py:1576-1591`

보고서 §3-3의 논증(“키 컬럼이 바뀌면 re-key → 자식 고아”)은 **`doe_value`에도 그대로 적용된다.** `doe_value`는 사용자가 legend에서 언제든 고치는 자유 텍스트다. 라이브 DB에 `qa_v2_` 시드로 실증했다:

```
STEP 2  stack_band 라벨 전면 교체        → bk 불변, 자식 자재 그대로 ✅ (설계대로 동작)
        (라벨에 '|' 포함(`2-11|extra`)도 안전 ✅)
STEP 3  doe_value 'A' → 'B' (band 1)     → bk가 …|A|1 → …|B|1 로 re-key
        자식 map_doe_source(…|A|1|…)는 그대로 남아 고아
        validate → source_unresolved 발화
```
클라 정상 동선에서는 `pruneScoped`가 구 행을 치워 은폐되지만, ①prune이 실패하면(빈 catch) 고아가 영구 잔존하고 ②admin 데이터 그리드에서 `map_doe.doe_value`를 직접 고치면 즉시 영구 고아가 된다. `crud.py:1584-1591`의 **Silent Merge & Overwrite**(bk 충돌 시 조용히 병합·삭제)까지 겹치면 값 충돌이 무성한 데이터 손실이 된다.

**권장 조치.** 후속 배치에서 `doe_value`도 키에서 빼고 불변 서수(`doe_seq`)로 정체성을 옮기거나, 최소한 값 개명 시 자식 re-key를 원자적으로 수행하는 경로를 만든다. **이번 병합의 차단 사유는 아니다**(클라 happy path는 동작).

---

### 🟡 M4 [심각도 중] identity 지름길이 **물리 격자 치수를 안 본다** — 보고서 주장과 반대
`server/map_overlay.py:173-182` (`frame_axes`) · `:270-274`

`frame_axes`는 `(회전, 면, y반전, start_x, start_y)`만 담고 **`cols/rows`가 없다.** 네 축이 같고 규격만 다른 두 맵은 지름길을 타서 `make_frame_transform`의 명시 실패(`:208-211`)를 **완전히 우회**한다. 실측:

```
a = 40x40 rot0 front (1,1)   b = 29x25 rot0 front (1,1)
frame_axes 동일 → origin: identity, 변환 없음, status: ok
make_frame_transform이었다면 → ValueError "physical grid dims differ: 40x40 vs 29x25"
```
라이브 축 분포에서 `(0,'front',False,1,1)`에 80건이 몰려 있고 그 안에 40x40·20x20·23x23이 섞여 있으므로 **실제 발화 가능**하다(40x40 맵을 20x20 맵 위에 겹치면 절반 이상이 격자 밖으로 나가 조용히 버려진다).

보고서 §1-3의 *"물리 치수가 서로 다른 두 맵은 여전히 `align_unavailable`로 명시 실패한다"* 는 **derived 경로에서만 참**이다. 구코드도 동일했으므로 회귀는 아니나 **주장이 틀렸다.** 조치: `frame_axes`에 `(cols, rows)`를 넣으면 한 줄로 닫힌다.

---

### 🟡 M5 [심각도 중] `saveDoeToServer` 서버 업서트 실패가 조용하다 — 자체 신고 결함의 **미수복 형제**
`client2/src/transfer_plan.js:957-964`

구현자는 “1차 저장소의 catch는 사용자에게 보이는 신호까지 올린다”는 교훈을 세우고 `saveDraft`(`:262-268`)에는 토스트를 붙였다. **그러나 형제인 서버 업서트에는 붙이지 않았다** — `missingTable`이 아닌 모든 실패(500·네트워크·인증)는 `console.warn`으로 끝난다. 게다가 헤더 표시(`:383-385`)가 로컬 초안의 `S.savedAt`을 우선하므로 **"자동 저장 HH:MM"이 계속 떠 있다.** 재시도도 없다(다음 편집 때까지 방치).

같은 계열의 조용한 실패 3건을 함께 올린다(전부 후속):
- `map_editor.js:1995-1998` — split registry(legend) 서버 저장 실패가 반환값만 `false`, 호출부(`:2004`)가 버림 → 팀 공유 legend가 갱신 안 됨.
- `map_editor.js:2328-2329` — 스키마 조회 실패 시 `[]`를 **캐시에 박고 무효화하지 않는다** → 그 세션 내내 해당 자재 맵이 "맵 없음"으로 오표시.
- `map_editor.js:2959-2961` — `wafer_map_metadata` Push의 `metaRes.status`를 **검사하지 않는다** → 500이어도 catch에 안 걸리고 본 Push는 "적재 완료"를 알린다. **회전/면 규격이 저장 안 된 채 성공으로 보인다** (B1과 결합하면 다음 오버레이가 틀린 메타로 계산된다).

---

### 🟡 M6 [심각도 낮음] 클라의 `Math.round` 배분이 서버의 “올림 배분” 안전 규율을 무효화
`client2/src/transfer_plan.js:929` vs `server/transfer_plan.py:1300-1302`

서버는 `share = ceil(qty_total / 매수)`로 **부족을 과소평가하지 않게** 계산하지만, 행에 `qty`가 있으면 그것이 우선한다(`:1302`). 클라는 **항상** `qty = Math.round(need / materials.length)`를 써 넣으므로 서버의 올림은 **한 번도 적용되지 않는다.**
예: `qty_total=100`, 자재 3매 → 서버 의도 34×3=102, 클라 실제 33×3=99. 매당 가용이 정확히 33이면 실제로는 1칩 부족인데 `qty_shortage`가 발화하지 않는다. 현재 검증 UI가 보류(H1/H3)라 사용자 영향은 없다 — **후속**.

---

### 🟡 M7 [심각도 낮음] 보고서의 config 적용 주장이 라이브와 불일치
`server/config/map_overlay_config.json`

보고서 §2·§3-5·§4-1이 *"`bonding_map`/`test`/`sample_map`/`transfer_plan_map`의 `table_bindings` 선언 제거 — 적용 완료"* 라고 하나, 라이브 config에는 **네 개가 전부 남아 있다**. 파일 안의 `__derived_note`가 "제거했다"고 단언하고 있어 더 혼란스럽다(보드 §현재 초점 1번 "오버레이 바인딩 복구(구코드 호환)"로 미루어 총괄이 의도적으로 되돌린 것으로 보이나, 그렇다면 주석이 거짓이다).

결과: **`derive_table_binding` 유도 경로가 주요 맵 테이블에서 실제로는 한 번도 타지 않는다**(선언 우선). 다만 유도 결과를 직접 대조한 결과 **선언과 100% 일치**했으므로 기능 위험은 없다.

```
bonding_map / test / sample_map / dt_map / core_defect_map / eds_fail_map / transfer_plan_map
  → 선언 == 유도 (7/7 일치)
dt_log / bonding_log → 유도 None(관례 밖 컬럼명) → 선언 경로 유지 ✅ 설계대로
```
조치: `__derived_note` 문구를 실제 상태에 맞추고, 보고서 §4-1의 "적용 완료"를 정정. 구코드 호환이 끝나는 재기동 후 선언을 실제로 제거해 유도 경로를 1회 실증할 것.

---

### ⚪ L1 [정보] 죽은 배선 6종
`map_editor.js:240, 242, 258-261` — controller에 주입한 `getCounts`·`addLegendRow`·`listOverlays`·`removeOverlay`·`toggleOverlay`·`clearOverlays`를 `transfer_plan.js`가 한 번도 호출하지 않는다. 크래시는 없으나 "＋ DOE" 등의 의도된 소비자가 없다.

---

## 3. 반증 시도했으나 **안전한** 항목

| # | 가설 | 반증 근거 |
|---|---|---|
| S1 | 밴드 라벨 수정이 자재 묶음을 고아로 만든다 | **라이브 실증 안전** — `stack_band` 전면 교체 후에도 bk 불변·자식 2행 유지. `\|` 포함 라벨(`2-11\|extra`)도 안전. `band_seq` 정수 정체성 설계는 **의도대로 작동한다** |
| S2 | 클라가 밴드 삭제 후 재번호해 자식을 고아로 만든다 | 안전 — `nextBandSeq`(`transfer_plan.js:200-202`)가 `max+1`이고 삭제는 `splice`만(`:582-584`), 재번호 코드 없음 |
| S3 | 오버레이 추가/제거가 편집 중 맵을 변조한다 | 안전 — `addOverlayLayer`(`map_editor.js:3796-3886`)/`removeOverlayLayer`(`:3888`)가 `selectedTable`·`gridData`·`legend`·규격을 **읽기만** 한다. `switchTable`/`renderMetadataInputs` 미호출, DOM도 `#overlay-src-table`로 분리 |
| S4 | 오버레이 가져오기가 legend를 서버 registry에 오염시킨다 | 안전 — `ensureLegendValues`(`:4030-4046`)가 `saveLegendToStorage()`(로컬)만 부르고 `persistLegend`(=서버 디바운스, `:2008`)를 **의도적으로 우회**. Push 성공 시점에만 서버 기록. 이전 배치의 registry 오염 전례는 재발하지 않는다 |
| S5 | 가드 제거로 `replace_map` 전량 삭제를 막을 수 없다 | 안전 — 최종 방어선인 Clean Replace 확인이 **대상 테이블 + 대상 맵 키를 명시**한 채 존치(`:2915-2925`). `replace_map:true`를 쓰는 코드 경로는 `pushMapData` **1곳뿐**(`:2967`). 정체성 불일치 시 `:2797`의 2차 확인이 추가로 뜬다. 우회 시도(키 변경 후 Push / 오버레이 가져오기 직후 Push / 테이블 전환 후 Push)를 모두 구성했으나 전부 최종 확인창에 걸린다 |
| S6 | 클라가 `origin: derived + rotation 0`을 "보정 없음"으로 오표시한다 | 안전 — `map_editor.js:3955-3960`이 **`origin`으로만** 분기하고 각도는 `rot`가 있을 때만 병기. `alignApplied`도 `origin !== 'identity'`(`:3869`) |
| S7 | `knobsToObject` 계열 미정의 심볼이 더 있다 | 안전 — `transfer_plan.js`/`map_editor.js` 전 식별자를 선언 집합과 diff한 결과 **미정의 호출 0건**. 크로스 모듈 계약(export 4종, controller 11종)도 전부 실재. `node --check` 5개 파일 통과 |
| S8 | 확장성 위반(풀스캔·전량 로드) | 안전 — DOE/자재는 `(ref_table, map_key)` equality(`transfer_plan.py:1161-1164`), 페인팅 분포는 group-by만(`:1112-1113`), 캡 `MAX_DOE_PER_PLAN`/`MAX_PLAN_VALUES`/`MAX_OVERLAY_CELLS` 존치. 구 `doe_key LIKE '<plan_id>\|%'` 접두 스캔 제거 확인 |
| S9 | v2 API가 라이브에서 죽는다 | 안전 — 실 PG 함수 직접 호출로 확인: `plan_store {doe: connected, doe_source: connected}`, `validate(bonding_map, aa123_a)` → `stage: bonding`, `map_status: connected`, `painted {1:137, 2:11, F:39}`; `validate(test, AAA)` → 200 + `stage: null` + `stage_unknown` + `unverified`(404 아님). 계약대로 |

---

## 4. 런타임 검증 필요 (재기동 후)

1. **B1 수정 후** — `bonding_map/AAA → bonding_map/aa123_a` 오버레이의 셀 좌표를 화면에서 육안 대조(맵 상 같은 칩이 같은 자리인지). 코드만으로는 클라 캔버스 렌더까지 단정 불가.
2. **인덱스 미생성** — `idx_map_doe_ref_map` · `idx_map_doe_source_ref_map` · `idx_map_source_region_ref_map_src` 전부 `pg_indexes`에 **없다**. `setup_transfer_plan_indexes.py`를 실행하고 `pg_indexes`로 물리 확인할 것(스크립트 `[ok]`만 믿지 말 것). 현재 0행이라 성능 영향은 없다.
3. `map_source_region` 물리 테이블 **미존재**(E5 휴면 — 설계대로이나 인덱스 스크립트가 skip하는지 확인).
4. `grid_y_invert = true` 맵은 라이브에 **0건**(161건 전부 false)이라 y반전 축은 실증 불가. 첫 `true` 맵 생성 시점이 유일한 검증 기회 — **B1의 바운딩박스 오류는 y반전 단독 차이에서도 `2·minR` 만큼 발생**하므로 B1 수정 전에 `true` 맵을 만들지 말 것.
5. 토스트 M1 — 에러 4건 상태에서 성공 토스트 투하 육안 확인.
6. HTTP 레이어 전체(`/api/transfer-plan/validate?ref_table=&map_key=`, `/source-summary`)는 재기동 후에야 신 코드로 응답한다. 서버 보고서 §5-4 체크리스트 1~6 그대로 수행 권장.

---

## 5. 병합 차단 vs 후속 백로그

### 병합 차단 (이것만 고치면 GO)
| # | 조치 | 규모 |
|---|---|---|
| **B1** | `make_frame_transform`에 웨이퍼 바운딩박스 항 편입(또는 거울 포함 조합 명시 거절로 임시 복원) + **독립 정답 대조** 회귀 추가 | 서버 ~30줄 + 테스트 1건 |
| **B2** | `pruneScoped` 공집합 가드 + 서버 로드 실패 시 prune 금지 + 빈 catch 표면화 | 클라 ~10줄 |

### 후속 백로그 (병합 후 별도 배치)
M1 토스트 퇴거 순서 · M2 페인트 잠금 fail-open 표면화 · M3 `doe_value` 재키잉 · M4 `frame_axes`에 격자 치수 추가 · M5 조용한 저장 실패 4곳 · M6 배분 반올림/올림 불일치 · M7 config 주석·보고서 정정 · L1 죽은 배선 · (기존) E2 `from_overlay` 이전처, E3 온톨로지, E4 `total_layers` 소속, 7-b의 `alert` 강등 일습

---

## 6. 문서 정합

| 대상 | 판정 |
|---|---|
| `CONFIG_GUIDE.md` §S6·§5.8 | ✅ v2 반영 정확(`plan_store.{doe,doe_source}`, stage 유도, band_seq 논거). 다만 `align_unavailable` 절에 **`unresolvable` 폐지·`origin: derived + rotation 0` 의미**가 빠져 있다 — 클라 계약의 핵심인데 서버 보고서 §0-4에만 있고 리빙 문서에 없다 |
| 서버 보고서 §1-3 "물리 치수 다르면 명시 실패" | ❌ **과장** — identity 지름길에서 미검사(M4) |
| 서버 보고서 §1-7 "전수 대조 1024쌍" | ⚠️ **과장** — 자기 왕복 대조라 균일 오프셋 오류에 무력. "구현을 되풀이하지 않는 불변식"이라 썼으나 실제로는 **독립 정답이 없다** |
| 서버 보고서 §2·§3-5·§4-1 "config 적용 완료" | ❌ **라이브와 불일치**(M7) |
| 클라 보고서 V20 "오버레이 가져오기 PASS" | ⚠️ 40x40 맵(minC=0)만 검증해 B1을 통과시켰다. 29x25 맵으로 재검증 필요 |
| 클라 보고서 §10 교훈 "1차 저장소 catch는 사용자에게 보이는 신호까지" | ⚠️ 초안에만 적용, 서버 업서트에는 미적용(M5) — 교훈과 코드가 어긋난다 |
| `docs/architecture/CODE_MAP.md` | 미갱신(신규 `make_frame_transform`·`derive_table_binding`·`stage_of_table`·`_painted_values` 부재). doc-keeper 트리거 누적 17건에 합류 |
| `PROJECT_STATUS.md` §현재 초점 1 | 대체로 정합. "서버 진행: 남은 좌표축" 행은 완료로 갱신 필요 |

---

## 7. 라이브 정리 목록 (삭제는 총괄)

QA 시드는 전부 `qa_v2_` 접두이며 **맵 셀·`wafer_map_metadata`는 무접촉**이다.

```sql
DELETE FROM map_doe_source WHERE map_key = 'qa_v2_BAND1';   -- 2행
DELETE FROM map_doe        WHERE map_key = 'qa_v2_BAND1';   -- 2행
-- 잔존 bk: bonding_map|qa_v2_BAND1|A|2 , bonding_map|qa_v2_BAND1|B|1
--          bonding_map|qa_v2_BAND1|A|1|qa_v2_TAPE-X|01 , …|A|2|qa_v2_TAPE-Y|02
```
(`updated_by = 'qa_v2'`로도 식별 가능. 감사 로그에도 같은 주체로 남아 있다.)

---

## 8. 교훈 제안 (`agent_workspace/memory/qa-reviewer.md` — 총괄 검수 후 반영)

- **함정**: 좌표 변환 검수에서 **단사·범위·왕복 항등**만 확인하면 통과 도장을 찍게 된다. 세 불변식은 *같은 함수를 정·역으로 쓴 자기 대조*라 **균일 오프셋 오류에 전부 참**이며, 조용한 오답의 가장 흔한 형태가 정확히 그것이다.
  **올바른 방법**: 변환 검수는 **소비자 쪽 규약을 독립 구현한 정답**과 대조한다(본 건: 클라 `getVisualCoords`/`getCellFromVisualCoords`를 파이썬으로 복제). 정답 하네스 자체는 ①자기 자신 쌍이 항등 ②구현자가 보고한 실측치 재현 — 두 가지로 먼저 검증한 뒤 쓴다.
- **함정**: "가드를 제거하고 근본 수정했다"는 보고는 **커버리지 증가**로 보이지만, 실제로는 *명시 실패 → 조용한 오답* 전환일 수 있다. 신코드만 보면 어느 쪽인지 알 수 없다.
  **올바른 방법**: `git show HEAD:<파일>`을 **별도 모듈로 올려 구/신을 같은 입력에 돌리고**, 판정을 `CORRECT / SILENT-WRONG / LOUD-FAIL` 3분류로 **전이 행렬**을 만든다. `LOUD-FAIL → SILENT-WRONG` 칸이 비어 있지 않으면 커버리지가 늘었어도 차단이다.
- **함정**: 라이브 실증이 "PASS"라도 **결함이 발현하지 않는 데이터**로만 돌렸을 수 있다(본 건: 40x40 맵은 웨이퍼 마스크가 격자를 안 잘라 `minC=0`이라 오류가 0이었고, 29x25 맵에서만 4셀 어긋났다).
  **올바른 방법**: 구현자의 라이브 검증 케이스가 **파라미터 공간의 어디에 있는지** 먼저 확인하고, 결함이 발현할 수 있는 구간의 케이스를 직접 고른다. 라이브 메타를 그룹별로 세어 "검증된 그룹 / 미검증 그룹"을 나눈다.
- **함정**: 삭제(prune/cleanup) 코드는 업서트와 붙어 있어 같은 가드를 받는 것처럼 보이지만, **길이 가드가 업서트에만 걸려 있고 삭제에는 없는** 패턴이 자주 나온다. `keep` 집합이 비면 "전부 지워라"가 된다.
  **올바른 방법**: diff 기반 삭제를 보면 항상 **"이 집합이 비었을 때 무엇이 지워지는가"** 를 먼저 묻고, 그 집합을 만든 조회가 실패했을 때 어떤 값이 되는지 역추적한다(“없다”와 “모른다”의 구분).
- **함정**: 자체 신고 결함("이 catch가 기능을 조용히 죽였다")을 보고받으면 그 한 곳이 고쳐진 것만 확인하고 넘어가게 된다.
  **올바른 방법**: 같은 파일의 **형제 경로**(같은 데이터를 다른 저장소에 쓰는 코드)를 먼저 본다. 본 건은 `saveDraft`에는 토스트가 붙었는데 바로 아래 `saveDoeToServer`에는 안 붙었다 — 교훈을 세운 사람이 자기 교훈을 옆 함수에 적용하지 않은 전형이다.
