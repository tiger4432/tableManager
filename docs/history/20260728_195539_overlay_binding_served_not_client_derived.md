# "오버레이 설정이 안 먹힌다" — 서버는 지키고 있었고, 클라가 읽지 않고 있었다

> 커밋 `17f65bd` · 2026-07-28 19:55 · 도메인 Server(paint-rules 바인딩 서빙) + Client(맵 에디터 바인딩 소비)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 선언: [map_overlay_config](../guide/config/map_overlay_config.md)

## 배경 — 증상이 문자 그대로였다

사용자 신고는 "오버레이 설정이 적용되지 않는다"였다. 진단 결과 서버는 `table_bindings`
선언을 모든 이름 모양(대문자·한글·숫자 시작·`tx`/`ty`)에서 **완벽히 지키고 있었다**.
문제는 에디터가 그것을 **읽지 않았다**는 것이다 — 클라는 자기 유도기를 따로 갖고 있었고
그 유도기는 리터럴 소문자 `x`/`y`를 요구했으며, `/api/maps/overlay`를 호출하는 클라
코드는 **한 줄도 없었다**. 선언은 서버 안에서만 참이었다.

같은 질문("어느 컬럼이 좌표인가")에 매처가 셋이었다: 서버의 `derive_table_binding`,
클라 로드 경로의 대소문자 무시 이름 매처, 클라 오버레이 경로의 `deriveMapBinding`.
셋이 다른 답을 낼 수 있었고 실제로 냈다.

## 변경 내용

### ① 서버가 해석본을 서빙한다 — 그리고 추측에 이름표를 붙인다

유도 로직을 코어(`_derive_table_binding_full`)로 내리고, 그 코어가 `(바인딩, guessed)`를
반환하게 했다. `guessed=True`는 값 컬럼이 후보 매칭이 아니라 **추측**(첫 비-키·비-좌표·
비-시스템 컬럼)이라는 뜻이다. 여기서 경로가 갈린다:

```python
# server/map_overlay.py — 이 커밋 시점
def derive_table_binding(table, val_candidates=None):
    """데이터 경로용. 값 컬럼 후보가 하나도 안 맞으면 x/y 부재와 같은 **명시 거부**."""
    binding, guessed = _derive_table_binding_full(table, val_candidates)
    if binding is None or guessed:
        return None
    return binding

def resolve_binding_info(cfg, table):
    """[F1] 클라 전달용 — 추측도 나가되 반드시 표기된다."""
    b = (cfg.get("table_bindings") or {}).get(table)
    if isinstance(b, dict) and b.get("columns"):
        ...
        return {..., "source": "declared"}
    binding, guessed = _derive_table_binding_full(
        table, resolve_value_column_candidates(cfg))
    if binding is None:
        return None
    binding["source"] = "fallback_guess" if guessed else "derived"
    return binding
```

핵심은 추측을 **삭제한 것이 아니라 격리한 것**이다. 종전에는 후보가 하나도 안 맞으면
첫 데이터 컬럼을 추측해 데이터 경로에 그대로 흘렸다 — 캔버스는 그럴듯하게 칠해지는데
값의 출처가 임의 컬럼인 **미끼(decoy)**다. 이제 추측은 `GET /api/maps/paint-rules`가
`source: "fallback_guess"`로 표기해 서빙할 때만 존재하고, 데이터 경로는 거절한다.
데이터 경로 소비자들도 정직하게 강등됐다(오버레이 엔드포인트는 미끼 셀 대신
`source_missing`, `_painted_values`는 `unverified`).

### ② 클라의 복사본 두 개를 지웠다

`deriveMapBinding`(~40줄)과 대소문자 무시 x/y 매처가 삭제되고, 서빙받은 바인딩 캐시
하나가 그 자리를 대신했다.

```js
// client2/src/map_editor.js — fillColumnDropdowns, 이 커밋 시점
const served = servedBindingCache.get(selectedTable) || null;
const pick = (dropdown, col) => { if (col && cols.includes(col)) dropdown.value = col; };
if (served) {
  pick(el.colMapX, served.x);
  pick(el.colMapY, served.y);
  pick(el.colMapVal, served.val);
}
```

효과가 두 갈래로 갈렸다. 선언 바인딩(`tx`/`ty`, 대문자 테이블)이 이제 **선언만으로**
로드·오버레이된다 — 어떤 클라 관례 매처로도 불가능했던 일이다. 반대로 서빙 답이 없으면
자동 선택도 없다(첫 컬럼이 남고, 드롭다운 자체가 수동 탈출구다).

**순서가 결함이었다.** `switchTable`이 `fetchPaintRules`를 fire-and-forget으로 쐈는데
드롭다운 프리셀렉트는 그 왕복이 채우는 캐시를 읽는다. `await`을 붙이지 않으면 프레임의
자동 로드가 **첫 컬럼을 x/y로** 들고 달린다 — 조용한 0셀(또는 엉뚱한 컬럼) 로드다.

### ③ 추측의 운명은 경로마다 다르다

- **로드 경로**: 프리셀렉트하되 경고 — 드롭다운 `title`(경고 톤) + 토스트. 사용자가
  드롭다운을 눈으로 보고 확정하는 자리이기 때문이다. 새 컨트롤은 추가하지 않았다.
- **오버레이 경로**: 거절. 여기서는 아무도 컬럼을 보지 않는다.

```js
// client2/src/map_editor.js — 오버레이 소스 해석, 이 커밋 시점
if (binding.source === 'fallback_guess') {
  return fail(
    `${sourceTable}: 값 컬럼을 확정할 수 없습니다 — 후보에 없는 '${binding.val}' 추측뿐입니다. `
    + `엉뚱한 값이 겹쳐 보이는 것을 막기 위해 겹치지 않습니다. ...`);
}
```

### ④ N행 받았는데 0셀 — 초록 성공이 감추던 것

받은 행 수와 파싱된 셀 수는 다른 숫자다. 선택된 x/y 컬럼에서 좌표가 숫자로 읽히지 않으면
NaN 필터가 전부 떨군다. 종전에는 그 결과가 "0셀 로드 완료"라는 **초록 토스트**로 나갔다 —
거의 확실한 원인(x/y 선택 오류)이 성공의 옷을 입고 있었다. 이제 `fetchedRows > 0`인데
파싱된 셀이 0이면 원인을 지목한 경고다. "아직 안 만들어진 맵"은 행이 진짜 0일 때만 참이다.
같은 라운드에서 "서버가 오버레이를 정렬한다"는 안내 문구가 클라가 변환한다는 사실로
교체됐다.

## 아키텍처 영향

한 질문에 매처가 셋이던 구조가 **하나**로 접혔다. 좌표 바인딩 해석은 이제 서버의
단일 책임이고, 클라는 소비자다. 그 결과 `map_overlay_config.table_bindings` 선언이
처음으로 **끝까지 효력을 갖는다** — 종전에는 서버 내부 경로에서만 참이고 화면에서는
거짓이었다. 그리고 "추측"이 시스템의 1급 개념이 됐다: 없는 것도 아니고 믿을 것도 아닌
제3의 상태로, 표기된 채 경로마다 다른 대우를 받는다.

## 검증

| 무엇을 | 어떻게 | 결과 |
|---|---|---|
| 원 진단 5건 | 진단을 냈던 QA가 자기 지적을 재검 | 5/5 FIXED |
| 미끼 차분 | 결함 버전 번들과 수정 버전을 **같은 픽스처**로 대조 | 수정 전 미끼 칩 4개 → 수정 후 거절 |
| 전체 스위트 | conda `assy_manager` | 880 passed · 하네스 green |

라이브 결함-버전 차분이 이 라운드에서 가장 강한 증거였다 — "고쳤다"가 아니라
"고치기 전에는 같은 입력으로 이렇게 틀렸다"를 보여줬다.

## 그때 남아 있던 것

- 추측(`fallback_guess`)은 **로드 경로에 여전히 존재**했다 — 경고와 함께 프리셀렉트된다.
  거절은 데이터 경로와 오버레이 경로에서만이다.
- 서버가 서빙한 것은 **컬럼 이름 해석**까지다. 이 커밋 시점 좌표 변환(정렬) 자체는
  클라가 수행했다.
