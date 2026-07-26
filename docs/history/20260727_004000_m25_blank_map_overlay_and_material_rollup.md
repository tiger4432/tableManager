# M2.5 맵 에디터 — 빈 맵에서도 오버레이 · 자재 목록을 자재 ID 기준으로 재구성

> 커밋 `4ba13ae` · 2026-07-27 00:40 · 도메인 Client / 맵 에디터 + 계획 패널
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 계약: [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md)
> 같은 커밋의 다른 두 트랙: [격리 개발 환경](./20260727_000000_isolated_dev_environment.md) · [정렬 일원화](./20260727_004500_align_consolidation_meta_single_source.md)

## 배경

`4ba13ae`는 세 트랙이 한 커밋에 들어갔다 — 같은 파일들에서 diff가 서로 얽혀 분리할 수 없었다.
그중 격리 환경과 정렬 일원화는 각각 별도 항목으로 남아 있고, **이 항목은 세 번째 트랙(M2.5 UI)**을 기록한다.

### 1) 본딩 계획은 "맵이 없는 상태"에서 시작한다

실제 작업 순서가 이렇다 — 빈 격자를 열고, EDS fail·defect를 **먼저 겹쳐 보고**, 그 다음에 칠한다.
그런데 오버레이 경로에는 "기준 맵이 로드돼 있어야 한다"고 거절하는 지점이 **세 곳** 있었다.

| 위치 | 종전 동작 |
|---|---|
| `handleAddOverlayClick` | `gridData`가 비어 있으면 토스트 띄우고 반환 |
| `addOverlayLayer` | `targetKey`가 없으면 "먼저 기준 맵을 로드하세요" 에러 |
| `addOverlayForSource` | `getCurrentMapKey() \|\| key` — **소스 키를 타깃 키로 위조** |

세 번째가 가장 나쁘다. 미로드 상태에서 소스 맵의 키를 타깃 키 자리에 밀어 넣어,
**존재하지 않는 (타깃 테이블, 소스 키) 조합의 규격을 조회**하게 만들었다.

### 2) 타깃 키가 두 가지 다른 것을 뒤섞고 있었다

- **캔버스에 실제 올라온 맵** = `loadedIdentity` (로드 시점에 고정)
- **메타 입력창에 타이핑된 것** = `getCurrentMapKey()`

규격(`wafer_map_metadata`) 조회를 이끌 수 있는 것은 전자뿐이다. 후자로 조회하면
로드하지도 않은 키를 타이핑한 것만으로 **다른 맵의 규격을 기준 삼아 판정**하게 된다(스펙 F2 항목).

## 변경 내용

### 규격이 없으면 거절이 아니라 "화면 기준"이다

변환 코드는 **한 줄도 새로 쓰지 않았다.** 타깃 프레임은 이미 화면 컨트롤로 폴백하고 있었고,
막고 있던 것은 그 위에 얹힌 가드뿐이었다.

```js
// client2/src/map_editor.js — addOverlayLayer
// No loaded map ⇒ there is no registered target spec to look up. That is **not** a refusal:
// the frame then comes from the live on-screen grid controls (`currentFrame()`), which is the
// very state a bonding plan starts in — blank canvas, EDS/defect overlaid before anything is
// painted. The old guard here made that impossible.
const targetKey = (targetOverride && targetOverride.key)
  || ((loadedIdentity && loadedIdentity.table === targetTable) ? loadedIdentity.mapKey : '');
```

대신 **그 사실을 칩으로 드러낸다.** "등록 규격에 맞춰 정렬됨"과 "지금 화면 격자에 맞춰 겹침"을
같은 칩으로 보이면 후자가 전자로 위장한다.

```js
// 무엇에 맞춰 정렬했는가 — 등록 규격(wafer_map_metadata)인가, 지금 화면의 격자 설정인가.
const targetBasis = tgtMetaFrame ? 'spec' : 'screen';
// -> 칩: 「화면기준」 (title: 화면 규격을 바꾸면 정렬도 함께 바뀝니다)
```

### 자재 목록의 축을 (값, 구간)에서 **자재 ID**로 뒤집었다

사용자의 질문은 "이 테이프 얼마 남았고 어디에 얼마나 썼나"인데, 목록은 그 반대를 답하고 있었다.
같은 자재가 여러 그룹에 흩어져 **그 자재의 총 사용량이 화면 어디에도 없었다**
(실데이터: `TOP`이 값 1·구간 16에 12개, 값 F·구간 16에 10개 — 합 22를 아무도 보여주지 않았다).

(값, 구간)은 사라지지 않고 그 자재를 소비한 **자리**로 행 안에 접혀 들어간다.

### 그 재구성이 실제 결함을 드러냈다

같은 수량을 **두 곳에서 각자 계산**하고 있었다 — 저장부는 `Math.ceil`, 자재 목록은 `Math.round`.
총 100 / 3매면 DB에는 34가 저장되는데 화면은 33을 보여줬다.

```js
// 한 구간이 자재 1매당 배정하는 수량. 서버에 저장되는 `map_doe_source.qty`가 바로 이 값이다.
// ⚠️ 단일 구현이어야 한다. 저장부와 표시부가 각자 계산하면 화면 숫자와 DB가 갈라진다.
function bandShare(b) {
  const n = (b && Array.isArray(b.materials)) ? b.materials.length : 0;
  return n > 0 ? Math.ceil((Number(b.need) || 0) / n) : 0;
}
```

서버 규약이 올림이므로 **올림이 정본**이다 — 내림/반올림은 부족분을 숨긴다.

### 가용량 해석도 한 지점으로 모았다

`availableOf`가 `chips.remaining`만 보고 숫자를 그대로 찍고 있었다. 서버는 역할 바인딩이 강등되면
`remaining: null` · `remaining_reliable: false` · `warnings[source_degraded]` **셋을 함께** 내려보내는데
클라는 그중 하나만 보고 있었다. `availabilityOf`가 셋을 모두 통과시키고, 하나라도 서면
숫자를 감추고 「미상」으로 표시한다(원값은 title에만 남긴다).

### 읽기 경로의 confirm 대화상자 삭제

맵을 여는 도중 legend 마이그레이션 여부를 `confirm()`으로 물었다. **읽기 경로에 대화상자**였고,
묻는 내용도 "split registry"라는 내부 개념이라 맵을 여는 사람에게 아무 의미가 없었다.
문구를 고치는 대신 **삭제**했고(`map_split_migrated_*` localStorage 플래그도 함께 폐기),
대체 동작은 "registry 0건이면 묻지 않고 `legendMeta`를 깨끗이 초기화"다 —
그냥 두면 같은 테이블의 이전 맵 수정자·시각이 이 맵의 것처럼 보인다.

## 아키텍처 영향

- **정체(identity)는 안정된 것에 건다**: 규격 조회는 `loadedIdentity`(로드 시 고정)만 신뢰하고
  입력창 값은 신뢰하지 않는다.
- **같은 숫자를 두 번 계산하지 않는다**가 계획 패널에 두 번 적용됐다(`bandShare` 단일화,
  가용량은 서버 계산을 읽기만).
- 선언 부재는 실패가 아니지만 **드러나야 한다** — 거절 대신 폴백 + 근거 표기.
  이 규율은 오버레이의 소스 쪽(무보정 칩)에 이미 있었고, 이번에 타깃 쪽에도 붙었다.

## 검증

- 스위트 **457 passed / 0 failed** (커밋 `4ba13ae` 기준, 세 트랙 합산).

## 다음 단계

- 자재 행의 「가용」과 「사용」은 서로 다른 출처다(서버 집계 vs 이 계획의 배정 합).
  둘을 비교해 부족을 경고하는 판정은 아직 없다 — M2.6에서 밴드 수량이 두 정수로 바뀌면 재검토.
- `targetBasis: 'screen'` 상태로 오버레이한 뒤 화면 격자 설정을 바꾸면 정렬이 따라 변한다.
  칩 title로만 알리고 있으며, 재계산 시점의 사용자 확인은 없다.
