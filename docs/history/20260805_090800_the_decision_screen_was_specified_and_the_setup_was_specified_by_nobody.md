# 판정 화면은 명세돼 있었고 설정 화면은 아무도 명세하지 않았다 — 그리고 프레임 이름이 아니라 컬럼이 원시 단위였다

> **커밋:** `74ce8b1` (2026-08-05 09:08) | **일자:** 2026-08-05 오전
> **선행:** [`20260805_074000`](./20260805_074000_a_stored_coordinate_is_bounding_box_relative_and_a_catch_turned_every_failure_into_a_plausible_wafer.md)(`cab8ed9` — 답만 할 수 있고 물을 수 없던 화면)
> **담당:** 제품 소유자(원시 단위 원칙 · 한 줄 규칙) · map 구현
> **대상:** **41파일 +8,454 / −1,826.** 신규 — `client2/src/map2/authoring.js`(394) · `brush.js`(316) · `legend.js`(161) · 하네스 `map_editor2_question_harness.mjs`(602) · `map2_authoring_harness.mjs`(569) · `server/scripts/seed_valid_die_ref_floor.py`(331) · 서버 테스트 3종(395 / 530 / 325). 수정 — `map_alignment.py`(668) · `main.js`(1,834) · `map_editor2.html`(317) · `server/main.py`(114) · `bonding_plan.py`(131) 등 + dist
> **스위트:** 커밋 메시지 기준 **41 하네스 중 게이트 37 전부 초록, 기지의 빨강 4 불변, `KNOWN_RED` 추가 없음.** `KNOWN_RED`가 4개인 것은 `check_harnesses.mjs`에서 확인되고 이 커밋은 `FLOORS`만 건드린다. **하네스 총수와 초록 여부를 기록한 산출물은 diff에 없다.**

## 배경 — 미스 하나가 세 번 반복됐다

Map Editor 2는 정렬 질문에 **답할 수 있었고 물을 수 없었다.** API가 이미 받고 있던
파라미터 셋에 화면 컨트롤이 없었다 — **대상 테이블 · 어느 좌표 컬럼을 읽을지 ·
기준 바닥.**

> **판정 화면은 명세돼 있었고 설정 화면은 아무도 명세하지 않았다.**

## 프레임 이름이 아니라 컬럼이다 — 원시 단위에서 시작한다

제품 소유자의 상시 원칙: **가장 원시적인 단위에서 일하고, 그 위에 단일 상태 함수를
세우고, config로 몰고, 프리셋 지름길은 마지막에 붙인다.**

그래서 선택기는 `core_frame` / `dt_frame`을 고르는 picker가 아니라, **테이블의
실제 스키마에서 읽은 x / y / value 컬럼**이다. 그 이름들은 애초에 **「내가 어느
x/y 쌍을 읽고 있나」의 별칭**이었을 뿐이다.

```python
    types = (crud.TABLE_CONFIG.get(src_table) or {}).get("column_types") or {}
    numeric = sorted(c for c, t in types.items()
                     if str(t).strip().lower() in ("number", "int", "integer", "float",
                                                   "numeric", "double"))
    return {"table": src_table, "numeric_columns": numeric,
            "declared_binding": map_overlay.resolve_binding_info(cfg, src_table)}
```

**`*_x` / `*_y` 이름 짝짓기를 하지 않는다** — 짝짓기는 운영자에게 남긴다.
그 결과 **하드코딩된 어휘가 사라지고 일반화된다**: 좌표 쌍을 가진 테이블이라면
그것을 위한 선언이 없어도 정렬 대상이 된다.

## 프리셋 층은 발명하지 않았다 — 이미 있었다

`map_overlay_config.json → table_bindings.<t>.columns`가 `source: declared |
derived | fallback_guess`와 함께 서빙되고 있었고, **`fallback_guess`가 이미
「이건 추측이다」 표시이자 쓰기 차단**이다. 클라는 그 어휘를 **그대로** 소비한다.

## 워크리스트 — 화면에 없던 또 하나

`GET /api/maps/alignment/worklist`가 결정 단위를 상태·검색·정렬과 함께 준다
(정렬과 검색은 서버에서). 검증하려고 어차피 만들어야 하는 **테이블 카탈로그**를
같이 싣는다.

| | 크기 |
|---|---|
| 단위 1건(워크리스트) | **242 B** |
| 그 단위 하나의 view | **6.3 KB** |

**인덱스가 인덱스 대상보다 26배 가볍다.** 그리고 **페이로드에 프레임 필드 이름이
하나도 안 나오고, 그것을 단언하는 테스트가 있다**(`test_the_worklist_never_names_a_frame_field`).

## 진짜 바닥 하나

`seed_valid_die_ref_floor.py`가 실제 단위의 선언 규격과 **바이트 단위로 맞는**
88다이 비대칭 발자국을 심는다. 비대칭은 손으로 확인하지 않고 **채점기 자신의
변환을 통해** 검증한다 — 최악 후보가 88 중 20 회수 가능, 눈먼 것 0.

`verify_discrimination`은 **항등이 아닌 7개 프레임 중 하나라도 발자국을 자기
자신으로 되돌리면 쓰기를 거절한다.** 변이 확인: 평범한 원은 7개 전부 0점이므로
가드가 살아 있다.

## 읽어서가 아니라 굴려서 찾은 결함 넷 — 그중 하나는 diff가 뒷받침하지 않는다

### ① `onConfirm`이 레코드형 함수를 위치 인자로 불렀다

```js
// 이전
Promise.resolve(api.confirmFrame(session.decision, vm.selectedCandidateId, sourceIds))
```

`api.confirmFrame(record, signal)`은 이미 레코드를 받고 있었다. 그래서 **사슬의
유일한 쓰기의 모든 필드가 `undefined`였다.** 빈 몸통을 POST하고 있었고,
**읽어서 하는 어떤 리뷰도 통과했을 것이다.**

이후에는 `rule`·`decisionKey`·`mapTable`·`columns`·`frame`·`sources`를 이름으로
싣는다. 하네스가 `G17 the write is given a record` / `G18 naming the rule`로 박았다.

### ② 문서 레벨 Enter 핸들러가 아무 드롭다운 안에서나 그 쓰기를 발사했다

```js
// 이전
if (e.key === 'Enter' && el.confirmBtn && !el.confirmBtn.disabled) onConfirm();
```

**id 검사가 아니라 허용 목록으로** 고쳤다 — id 검사는 오늘의 마크업만 보호한다.

```js
  function takesEnter(target) {
    if (!target) return false;
    if (el.confirmBtn && target === el.confirmBtn) return false;
    if (typeof target.closest === 'function' && el.confirmBtn
        && target.closest('#me2-confirm-btn')) return false;
    const tag = String(target.tagName || '').toUpperCase();
    return !(tag === 'BODY' || tag === 'HTML' || tag === '#DOCUMENT' || tag === '');
  }
```

### ③ `Number(null) === 0`이 또 나왔다 — 이 프로젝트에서 **세 번째**다

응답이 총계를 안 보냈는데 화면에 개수가 떴다.

```js
    const value = Number.isFinite(Number(count)) && count !== null ? `${count}건` : UNKNOWN;
```

### ④ ⚠️ 「클라가 `val_col`을 보내는데 라우트 철자는 `value_col`」 — diff가 이것을 뒷받침하지 않는다

`74ce8b1`과 그 부모 양쪽에서 `client2/` 전체에 **`val_col`이라는 문자열이
없다.** 이 커밋 전체에서 `val_col`이 나오는 곳은 **서버 파이썬의 지역
변수**(`_cells_of`)뿐이다. 전선 철자는 `api.js`의 **추가된 줄로만** 나타난다:

```js
      if (r.xCol) q.x_col = String(r.xCol);
      if (r.yCol) q.y_col = String(r.yCol);
      if (r.valCol) q.value_col = String(r.valCol);
```

즉 대응하는 `-`줄이 없다. **커밋된 트리에서 그 오철자가 있었던 흔적은 확인되지
않는다** — 증상(모든 실행이 점유 전용이고, 오류 없고, 8자 동점이 정상처럼 보임)은
`5120e35`가 별도로 실측한다.

## 화면은 한 줄, 나머지는 콘솔이 진다

제품 소유자 규칙: **경고는 콘솔로, 화면 문자열은 한 줄을 넘지 않는다.** 대상은
관리자이고 그들은 문서를 읽으므로 — **설명은 문서에, 진단은 콘솔에, 화면에는
판단을 바꾸는 것만.** 판정 사유는 **부재가 아니라 복귀 조건이 적힌 기록된 결정**으로
빠졌다.

## 마크업이 아무것도 이름 짓지 않는다

소스는 **N번 복제되는 템플릿**이다 — 손으로 쓴 행은 N을 표현할 수 없고, **N이
목적**이다. N=0/1/3에서 확인. 손으로 쓴 숫자는 전부 비웠다 — **템플릿 안의
플레이스홀더는 복제마다 한 번씩 복제되는 주장**이다. N=0은 이름 붙은 조건이고,
**교차 소스 행을 구조적으로 숨긴다** — 「쓸 만한 소스 없음」 아래의 교차 소스 행은
**아무것도 아닌 것들 사이의 관계를 주장**하기 때문이다.

## 레거시는 텍스트만, 일부러 얕게

알림 3개를 콘솔로, 4개 삭제, 약 45개 축약, 사실을 나르던 0.72rem 칩 하나를 키움.

**문자열 일곱은 바이트 단위로 되돌렸다 — 하네스가 그것을 핀으로 박기 때문이다.**
그리고 **그중 넷은 단언이 아니라 슬라이서 앵커**다: 하네스가 토스트 텍스트를
매칭해서 대상을 찾으므로, **토스트를 줄이면 하네스가 아무것도 비교하지 않게
된다.** 그 파일에서는 **사용자 문구가 테스트 인프라의 하중을 받고 있다.**

> ⚠️ **바이트 단위 되돌림은 diff를 남기지 않는다.** 41파일 어디에도 그 일곱
> 문자열을 기록한 산출물이 없다 — 이 사실은 커밋 메시지에만 있다.

## 그때 남아 있던 것

- 워크리스트 라우트는 `sort` 미지원 값·미선언 `params` 키에 400, 모르는 규칙에
  404를 내고 `limit`을 `MAX_WORKLIST_UNITS`로 클램프한다.
- `seed_valid_die_ref_floor.py`는 **기본이 드라이런**이고 `--apply`가 있어야 쓴다.
  `replace_map`을 쓰지 않는 **추가 전용**이다.
- 참조 카탈로그가 이 시점 **`?rule=`에 묶여 있다.** 규칙이 선언되지 않은 운영
  환경에서 목록이 통째로 안 나오는 결함으로 3시간 뒤 `36323f7`에서 드러난다.
