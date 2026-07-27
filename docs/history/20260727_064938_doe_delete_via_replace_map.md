# DOE 삭제 — 차집합 계산이 아니라 집합 교체(`replace_map`)로. 없던 것은 기능이 아니라 선언이었다

> 커밋 `3ebd38e` · 2026-07-27 06:49 · 도메인 Client / 맵 에디터·DOE 패널 (+ 현장 `table_config.json` 선언)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 저장 지도: [DOE_STORAGE_MAP](../spec/DOE_STORAGE_MAP.md) · 프리미티브: [PRIMITIVES §1 맵 전량 교체](../architecture/PRIMITIVES.md)

## 배경

DOE 항목을 지워도 **지워지지 않았다.**

진단이 어려웠던 이유는 **계획 행은 실제로 지워지고 있었기 때문**이다.
살아남은 것은 `map_split_registry`였고, `loadExistingMap`에는
"registry에만 정의된 값은 legend 행으로 다시 노출한다"는 분기가 있다.
그래서 다음 로드에서 **빈 껍데기로 되살아났다.**

코드는 삭제 지점 두 곳에서 이미 소리내어 그렇게 말하고 있었다.

```js
delete legendMeta[deletedVal]; // 서버 registry 행은 이력으로 잔존 (삭제 API 미사용)
```

### 총괄의 가설 4개가 전부 틀렸고, 틀린 것은 틀 자체였다

에이전트에게 "클라이언트 차집합 계산이 어디서 어긋나는가"를 찾게 시켰다. 사용자가 잘랐다 —
**DOE를 저장하는 것은 본딩 맵을 저장하는 것과 구조적으로 같은 조작이므로 replace를 쓰라.**

`replace_map`은 `crud.py`에 이미 있었고, 맵 Push가 이미 쓰고 있었다.
DOE 테이블에 **범위를 잡을 `map_key_columns` 선언이 없었을 뿐**이다.

> 선언 하나가 없어서 **prune 서브시스템 전체가 존재했다.**
> 그리고 **없는 선언은 없는 기능과 똑같이 생겼다.**

## 변경 내용

### 선언 — 셋 중 셋째가 이 버그의 범인이다

`map_key_columns = (ref_table, map_key)`를 `map_doe` · `map_doe_source` · **`map_split_registry`**에 선언했다.
세 번째가 항목을 되살린 그 테이블이다.

### 클라: 차집합 부기를 **비활성화가 아니라 삭제**

`pruneScoped`, `S.serverKeys`, 그리고 그 주변 부기가 전부 제거됐다.

```js
// [removed] `pruneScoped` — the client-side difference-and-delete step.
//
// It existed because a DOE save was an upsert, which can only add and overwrite, so
// something had to go back and delete what the user removed. That second step was
// conditional, and when it did not run the removal simply did not happen.
//
// The platform already had the operation: `replace_map` (crud.py, apply_batch_updates)
// purges a table's rows inside the map's scope and rewrites them in one transaction.
```

C1 불변식은 죽지 않고 **더 단순한 형태로 살아남았다** —
종전 "화면이 서버본에서 유래할 때만 차집합을 지운다" → 현재 **"화면이 서버본에서 유래할 때만 replace한다"**.
별개 삭제 단계의 가드가 아니라, **한 번의 쓰기에 붙은 가드 하나**다.

legend 쪽도 같은 규율을 `legendReplaceScope`로 명시했다 — 그 맵의 registry를 **성공적으로 읽은 사실**만이
그 맵을 replace할 권한을 준다. 테이블 전환·읽기 실패·맵 언로드에서 즉시 소멸한다.

```js
// client2/src/map_editor.js — setLoadedIdentity
// Replace authority belongs to ONE map. The moment the loaded map is not the map
// whose registry we read, the claim is void - a `replace_map` legend write under a
// stale scope would purge another map's rows.
if (!loadedIdentity || !legendReplaceScope
    || legendReplaceScope.table !== loadedIdentity.table
    || legendReplaceScope.mapKey !== loadedIdentity.mapKey) {
  legendReplaceScope = null;
}
```

### legend 읽기에 절단 가드가 **아예 없었다**

replace 의미론 아래에서 **절단된 읽기는 데이터를 파괴하는 읽기**다 — 못 본 행을 삭제하게 된다.
이제 절단이면 읽기를 실패시키고, 실패했으므로 replace 권한도 주장하지 않으며,
"이 맵에서는 DOE를 지워도 서버에 반영되지 않습니다"를 사용자에게 알린다.

## 남겨 둘 값이 있는 것 — 반사실(counterfactual)

> **동일한 요청이 선언 유무와 무관하게 `200 {"status":"success"}`를 반환한다.**
> 선언이 있으면 범위를 비우고, 없으면 아무것도 하지 않는다.

즉 **config 주도 서버 경로는 완전히 조용히 실패할 수 있다.**
그리고 그것이 작동함을 증명하는 방법은 하나다 — **선언을 빼고 다시 돌려 보는 것.**

## 아키텍처 영향

- 맵 Push와 DOE 저장이 **같은 프리미티브** 위에 섰다. "전량 교체"가 이 시스템의 맵 계열 쓰기 표준 형태다.
- 이 사건이 `PRIMITIVES.md`와 착수 규율("이건 무엇과 구조적으로 같은가")의 직접적 계기다 →
  [프리미티브 카탈로그와 에이전트 재편](./20260727_062045_primitives_catalog_and_agent_split.md)

## 알려진 구멍 둘 — 덮지 않고 보고했다

**ⓐ `replace_map`은 공집합을 표현할 수 없다.** `crud.py`가 범위를 `updates[0]`에서 가져오기 때문에,
어떤 값의 밴드를 전부 지우면 **보낼 것이 없어 아무 요청도 나가지 않는다.**
이것을 "저장됨"으로 위장하지 않고 헤더에 「⚠ 삭제 미반영」 칩과 토스트로 드러낸다.

```js
// `replace_map` takes its scope from updates[0], so an EMPTY set is not a write the
// server can act on - it would silently leave the plan's rows in place. That is a
// deletion we cannot express, and it must not be reported as a completed save.
const cannotExpress = (doeUpdates.length === 0 && S.serverRows.doe > 0)
  || (srcUpdates.length === 0 && S.serverRows.source > 0);
```

**ⓑ 형제 세션 안전성이 사라졌다.** 종전 prune은 **자기가 본 키만** 건드렸으므로
다른 세션이 추가한 행은 구조적으로 안전했다. replace는 **범위 전체를 비운다.**
동시 편집에서의 손실 가능성은 이 커밋으로 **해소되지 않았다** — 형태만 바뀌었다.
(완화책으로 `loadDoeFromServer`는 로컬 초안 유무와 무관하게 항상 호출되도록 했지만, 로드 이후의 동시 저장은 여전히 덮였다. ⚠️ **이 함수는 이후 `cdcddee`(M2.6)에서 제거됐다** — 위 서술은 이 커밋 시점의 코드다.)

## 검증

- 현장 `table_config.json`에 설치기로 선언 반영, 백업 생성됨.
- 스위트 **540 passed / 0 failed**.

## 다음 단계

- M2.6에서 `map_split_registry`가 DOE 테이블 자신이 된다 — 이 항목의 세 테이블 구조가 그때 재편된다.
- 공집합 표현 불가(ⓐ)는 서버 계약 문제다. `replace_map`이 범위를 `updates[0]`가 아닌
  명시 파라미터로 받는 형태가 필요하지만, 경계 계약 변경이라 총괄 승인 사항.
- 동시 편집 손실(ⓑ)에 대한 방어는 아직 없다.
