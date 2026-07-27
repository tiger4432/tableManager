# 한 맵의 DOE가 모든 맵에 나타났다 — 원인은 코드가 아니라 **틀린 문서를 믿은 전제**부터였다

> 커밋 `269b39e` · 2026-07-27 23:35 · 도메인 Client(맵 에디터 legend·진행 카드) + Server(바인드 주소·DOE 코어)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 계약: [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md) · 모델: [DOE_BAND_MODEL](../spec/DOE_BAND_MODEL.md)
> 후속: 이 커밋이 착지시킨 DOE zone 순수 코어의 서버 절반은 이틀 뒤 →
> [DOE 층 구조가 band에서 구역으로](./20260728_071500_doe_zone_model_server_half.md) (`b35bc9f`)

## 배경 — 한 결함, 두 불만

사용자가 본딩 맵을 열자 **입력한 적 없는 DOE 4개 값**이 있었다 — 서로 다른 맵 키 4곳에서
온 값들이. 문자 단위로 재현됐다: legend가 **테이블 전역** registry를 읽어 값 기준으로 접고
최신 쓰기가 이기는 구조라, `elle`은 맵 QQ에서 오고 나머지는 AAA에서 왔다. 새로고침하면
같은 병합이 다시 일어났다 — "새로고침하면 맵이 리셋된다"는 별개 불만의 실체가 **같은 결함**이었다.

퍼뜨린 것은 쓰기 쪽이다. registry 행이 없는 맵 키는 "안 보고 지울 것이 없다" 분기를 타서
replace 권한을 받고, **빌려 온 어휘를 `replace_map`으로 썼다** — 무에서 계획 전체가 생겨나는
경로이고, bonding_map 키 10개가 같은 4개 값을 들고 있게 된 이유다. 쓰기를 차단하고
실측했다: 수정 전 4행 기록, 수정 후 1행 — 그 1행이 사용자가 실제로 입력한 행이다.

## 변경 내용

### ① 지시서의 전제 4개가 전부 틀렸고, 에이전트가 전부 **실측으로** 뒤집었다

- "map-scoped 읽기는 미사용"이 아니었다 — 다른 함수를 거쳐 **매 open마다** 돈다.
- 지목된 호출부는 맵 키를 **알 수 없는 위치**였다 — 메타 입력은 그 함수가 반환한 뒤 채워진다.
- `legendReplaceScope`는 전역 읽기로 "속은" 게 아니었다 — 읽기에 대한 주장으로서 정당하게
  성립했고, **오염은 payload에** 있었다. 그래서 가드도 payload로 옮겨졌다.
- "B를 열고 저장하면 A의 계획이 B에 들어간다"는 **칠해진 셀이 없는 맵에서만** 성립했다 —
  칠해진 맵은 기존 uniqueVals 재구성이 **우연히** 보호하고 있었다.

전제의 출처는 `CODE_MAP.md:894`였다 — "loadLegend는 맵 자신의 registry 행을 읽는다"고
서술했지만 **한 번도 그런 적이 없다.** 자신 있게 틀린 문서는 그냥 낡은 문서보다 나쁘다는
사례로, 교정 대상으로 라우팅됐다.

### ② 수정 — 출처 비트 하나와, 이름 붙은 두 읽기 모드

빌려 온 어휘 값에는 `vocab`(unclaimed) 비트가 붙는다. 맵이 그 값을 **보증하는 순간**
(자기 registry 행 · 칠해진 셀 · 사용자의 직접 편집) 해제되고, 보증 없는 값은 열 때 화면에서
내려가며 replace payload에서 걸러진다. 그리고 두 읽기 모드는 추론이 아니라 이름이 됐다:

```js
// map_editor.js — 이 커밋 시점
const REGISTRY_SCOPES = ['map', 'vocabulary'];
async function fetchRegistryRows(scope, refTable, mapKey) {
  // 'map'인데 mapKey가 없으면 throw — 이 사고를 만든 null은 다시 통과할 수 없다
  ...
  return parseLegendRegistryRows(result, scope === 'vocabulary');
}
```

어휘 시딩 자체는 유지됐다 — 테이블의 값 어휘를 브러시로 깔아 주는 것은 기능이다. 금지된
것은 그 브러시가 **이 맵의 계획으로 저장되는 것**뿐이다.

### ③ 인제션 진행 카드 상한 — 병합이 아니라 **은닉**

좌측 진행 카드는 (테이블, 파일)마다 하나씩 상한 없이 쌓여 화면을 덮었다. 우측 토스트는
같은 문제를 `dedupeKey` 집계로 풀었지만, 진행률은 파일별로 의미가 있어 합치면 정보가
죽는다 — 그래서 **3장 표시 + 나머지 한 줄 집계**(`MAX_VISIBLE_PROGRESS_CARDS = 3`,
`collapseProgressOverflow`)로 갔다. 가려진 카드도 갱신은 계속 받고, 앞 카드가 완료되면
올라온다 — 대기열처럼 보인다. 두 벌이던 카드 제거 블록은 `dismissProgressCard` 하나로
모았다: 집계 카드를 자식 수에 세면 컨테이너가 영원히 안 지워지는데, 그 수정을 두 곳 중
한 곳에만 하는 것이 이 부류 버그가 살아남는 방식이다.

### ④ 바인드 주소 — `navigator.clipboard`가 판정해 줬다

런처가 `--host`를 안 넘겨 uvicorn이 loopback에 바인드돼 있었다 — 가이드 문서는 0.0.0.0이라
적고, 팀은 LAN으로 접속하는데. 관측이 판정했다: `navigator.clipboard`는 localhost에서만
정의되고 사용자들에게는 undefined였다(며칠 깨져 있던 Ctrl+C의 배경). `ASSY_API_HOST` 기본을
0.0.0.0으로 바꾸며, **방어선은 바인드 주소가 아니라 admin 토큰 + 경로 격리 검사**라는 것을
주석에 못 박았다 — 누군가 바인드를 좁히는 것을 방어라 믿지 않도록.

### ⑤ 동승 — DOE zone 모델의 순수 코어 (화면 미배선)

`doe_bands.js` + `contracts/doe_band_rules`(233 assertions), 그리고 서버의 BIN-aware
가용(로트 확장 포함)이 함께 착지했다. **이 시점엔 어느 화면에도 배선되지 않았다.** 여기서
나온 발견 둘 — U+001F로 이은 풀 키가 디스크에서 분리자를 잃어 `MID1_12:3`과 `MID11_2:3`이
한 행으로 합쳐진 것(230개 assertion이 아니라 **뮤테이션 테스트가** 잡았다), 그리고 가용이
COUNT(*)가 아니라 `remaining`이어야 하는 이유(COUNT(*)는 결코 "신뢰 불가"가 될 수 없는데
계약은 신뢰 불가한 가용이 잔여를 억제할 것을 요구한다) — 는 서버 절반이 착지한
[b35bc9f 항목](./20260728_071500_doe_zone_model_server_half.md)에 계약 전체와 함께 이어진다.

## 검증

| 무엇을 | 어떻게 | 결과 |
|---|---|---|
| 서버 스위트 | `pytest server/tests/` | **742 passed** |
| 클라 하네스 3종 | `node contracts/<name>/client_harness.mjs` | 110 / 59 / 233 assertions |
| 오염 확산 | 쓰기 차단 후 registry 기록 계수 | 수정 전 4행 → 수정 후 1행(사용자 입력분만) |

## 그때 남아 있던 것

- `CODE_MAP.md:894`의 틀린 서술은 이 커밋에서 **수정되지 않고 교정 라우팅만** 된 상태였다.
- DOE zone 코어는 순수 함수와 계약 벡터만 존재했다 — 서버 컬럼도, 화면 배선도 없었다
  (이틀 뒤 `b35bc9f`에서 착지).
- 칠해진 맵이 오염에서 보호되던 것은 설계가 아니라 **우연**(uniqueVals 재구성의 부수효과)
  이었다는 사실이 이 커밋의 조사로 처음 명시됐다.
