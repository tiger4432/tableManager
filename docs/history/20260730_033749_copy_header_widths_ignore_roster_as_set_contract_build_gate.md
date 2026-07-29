# 헤더 칸이 맵 셀 한 칸이었다 — 열 폭 병합 · 로스터를 집합으로 채점 · 계약을 실제로 돌리는 게이트

> 2026-07-30 03:37 · 도메인 Client/Map · 계약(contracts) · 빌드 게이트 · 기준 `5a14e77`
> 상위: [spec/MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md) · [guide/DOE_GUIDE §4.1](../guide/DOE_GUIDE.md) · [architecture/PRIMITIVES §7](../architecture/PRIMITIVES.md) · [process/CONTRIBUTING §2-bis](../process/CONTRIBUTING.md)
> 선행: `064550f`(COPY HEADER MODE 신설 + F2 수렴점 `eachSavableCell` 도입 — **히스토리 미등재 커밋**)
> 후속: [회사 양식 되붙이기(왕복의 나머지 절반)](./20260730_041654_company_sheet_round_trip_paste.md) · [문서 동기화](./20260730_043738_docs_sync_round_trip_routing_build_gate.md)

## 배경 — 네 갈래가 한 커밋에 있고, 공통점은 「아무도 안 보는 자리」다

이 라운드는 서로 다른 네 가지를 한 번에 담았다. 묶인 이유는 기능이 아니라 **결함의 형태**가
같아서다 — 넷 다 *화면에도 로그에도 흔적을 남기지 않는* 자리였다.

1. 내보낸 헤더가 잘려 나갔다(사용자가 눈으로 본 유일한 증상).
2. 머리줄 로스터가 근거 없는 비대칭을 안고 있었다.
3. 그 로스터를 채점한다던 계약이 실은 **표본 세 단어**만 걷고 있었다.
4. 그리고 **계약의 클라 절반을 실행하는 것이 이 저장소에 하나도 없었다.**

---

## ① 헤더 칸의 폭이 맵 셀 하나였다

`copyGridToExcel`의 표 전체 열 수는 이렇게 잡혀 있었다.

```js
const totalCols = headerOn ? Math.max(visualCols + GAP_W + AUX_W, groups.length * 2) : visualCols;
```

`groups.length * 2`는 **칸마다 열 하나**라는 뜻이다. 격자 셀은 32px 정사각이므로
`MIDLOT_01`은 글자가 들어갈 자리 자체가 없었고, 우측 보조표의 `DESC`도 같은 이유로 잘렸다
(넷 다 32px 한 칸이었다). 회사 실제 양식은 각 그룹이 여러 열에 **병합**돼 있어서 긴 라벨이
읽힌다.

**균등 분배는 기각됐다.** 라벨 길이가 제각각이라 `1H`와 `MIDLOT_01`에 같은 폭을 주면 긴 쪽이
다시 잘린다. 그래서 폭은 글자 수에서 나오고, 남는 열은 그 최소 폭에 **비례해** 나눈다.

```js
const HDR_COL_PX = 32;     // 격자 셀 한 칸의 폭 — 아래 `width: 32px`와 같은 수
const HDR_PAD_PX = 12;     // headCellStyle/headValStyle의 좌우 padding 합 (6px × 2)
const HDR_CHAR_PX = 7;     // 10pt Arial bold 한 글자의 보수적 폭
const HDR_MIN_SPAN = 2;    // 빈 라벨도 맵 셀 하나로는 내보내지 않는다
const HDR_MAX_SPAN = 8;    // 문장 길이의 DESC 하나가 표를 인쇄 한 장 밖으로 밀지 않도록
```

분배는 **최대 잔여법**이다. 내림만 하면 몇 열이 증발한다.

```js
function distributeSpans(texts, total) {
  const mins = texts.map(headerSpanFor);
  const base = mins.reduce((a, b) => a + b, 0);
  if (base === 0 || total <= base) return mins;
  const surplus = total - base;
  const share = mins.map(m => surplus * m / base);
  const out = mins.map((m, i) => m + Math.floor(share[i]));
  const order = share.map((s, i) => ({ i, frac: s - Math.floor(s) }))
    .sort((a, b) => (b.frac - a.frac) || (a.i - b.i));
  let used = out.reduce((a, b) => a + b, 0);
  for (let k = 0; used < total; k++) { out[order[k % order.length].i]++; used++; }
  return out;
}
```

🔴 **합이 정확해야 하는 이유는 미관이 아니다.** 행마다 열 합계가 다르면 엑셀이 표 전체를
밀어 버린다. 그래서 이 커밋은 격자 행도 `totalCols`까지 채우도록 고쳤다 — 종전에는 보조표가
끝난 아래쪽 행들이 **짧은 채로** 나갔다. 헤더를 끄면 `totalCols === visualCols`라 채움 루프가
아무 일도 하지 않으므로, 헤더 없는 복사본의 바이트 동일성(INV-ⓐ-1)은 유지된다.

보조표 네 칸도 각자 폭을 갖게 됐고(`auxColumnSpans` — 열마다 **그 열의 가장 긴 내용**에서
폭이 나온다. 머리글만 보면 `DESC`가 4자 폭을 받고 그 아래 문장이 전부 잘린다), HTML 쪽은
`colspan`, 평문 쪽은 「글자 + 나머지 열은 빈 칸」으로 나가 **TSV 열 수와 colspan 합이 같아진다.**

**실측(커밋 기록)**: 브라우저에서 방출된 클립보드 HTML로 잰 결과 344px 헤더가 더 이상 344px
그리드 열을 강제하지 않고, 맵 셀은 36px에 머물렀다. 소스의 폭 상수는 `HDR_COL_PX = 32`이며
격자 `<td>`의 `width: 32px`와 같은 수로 고정돼 있다 — 둘이 갈리면 이 계산 전체가 조용한
거짓말이 된다고 주석이 못 박았다.

부수로 `Base` 하드코딩도 사라졌다. 첫 열 그룹의 **값**은 `getCurrentMapKey()`에서 나오는데
**이름**만 `bonding_map`의 컬럼명 `Base`로 박혀 있었다. 📋 Copy to Excel은 모든 맵 테이블에
있으므로 `dt_map`(`map_key_columns = lot·slot`)에서 내보내면 헤더가 `Base | LOTID_03` —
이름과 값이 서로 다른 테이블을 가리키는 상태였다. `mapKeyGroupLabel()`이 선언에서 이름을
만들고, 선언이 없으면 컬럼명을 주장하지 않고 `MAP KEY`로 물러선다.

---

## ② `IGNORED_HEADERS` 4 → 13, 그리고 여덟 단어는 **예비**다

로스터는 「머리줄로 알아보되 값으로는 버린다」는 단어 목록이다. 모르는 척하면 사용자가 자기
양식을 되붙일 때 그 줄이 **데이터 행**이 되어 값 이름이 `VALUE`이고 STACK이 `COUNT`인 행이
생긴다.

**`COLOR*` 비대칭.** `칠함*`은 로스터에 있는데 `COLOR*`는 없었다. 둘은 폐기된 머리줄
(`tp-ch-row l1`, `b35bc9f`에 도입되어 `7694b42`에서 그 줄 통째로 삭제)이 **나란히 그린 같은
줄의 두 단어**다. `칠함*`을 남겨 두는 유일한 근거(옛 내보내기·손으로 만든 시트가 아직 그
단어를 담고 있다)가 `COLOR*`에도 똑같이 성립하므로, 하나만 있는 것은 **근거 없는 비대칭**이었다.
⚠️ 두 별표 항목은 **하위호환 전용**이다 — 2026-07-30 실측으로 `client2/src` 어디에도 별표 붙은
머리글 문자열을 렌더하는 곳이 없다.

**롤업 8단어가 6이 아니라 8인 이유.** 같은 머리줄의 **두 형태의 합집합**이다.

| 형태 | 단어 |
|---|---|
| 격자 형태(`ROLLUP_COLUMNS`, `rollupToGrid`가 방출) | MAT · BIN · MAP · 가용 · 사용 · 잔여 |
| 렌더 형태(`tp-ch-row`, 사람이 실제로 긁는 것) | MAT · MAP · 가용 · 사용≈ · 잔여≈ (화면엔 BIN 열이 없다) |

`사용≈`·`잔여≈`가 별도 항목인 것은 화면이 `사용<span class="ap">≈</span>`로 그려서
평문으로는 `사용≈` 한 덩어리로 도착하기 때문이다. 대소문자·바깥 공백만 접는 판정기는 그
기호를 벗기지 않고, **여기서 벗기기 시작하면 정규화 규칙이 하나 더 생긴다.** 그리고 `가용`은
`≈` 없이 렌더되므로(실측) `가용≈`는 오히려 `never_ignored`에 들어가 — `≈` 제거 정규화를
도입하면 죽는 단언이 된다.

🔴 **여덟 단어는 오늘 아무것도 사지 않는다.** `rollupToGrid`는 export돼 있으나 importer가
**0건**(2026-07-30 실측)이라, 그 함수 자기 주석이 설계 의도로 선언한 「②를 복사해 ①에
붙여넣는다」 왕복은 **배선돼 있지 않다.** 이 커밋은 그것을 숨기지 않고 계약의 트립와이어로
고정했다 — 아래 ③.

---

## ③ 계약이 로스터를 **표본**으로 채점하고 있었다

`COUNT`는 2026-07-29에 `IGNORED_HEADERS`에 추가됐다. 그때 계약의 **331개 단언이 전부
초록이었다.** 하네스는 자기가 들고 있는 벡터만 채점하고, 벡터는 로스터의 세 단어를 걷고
있었을 뿐이기 때문이다. **단어를 걷는 것은 그 단어가 동작함을 증명하고, 집합에 대해서는 아무
것도 증명하지 않는다.**

이번에 `ignored_headers`를 집합 단언으로 넣었다. 로스터는 재입력하지 않고 `doe_bands.js`
소스에서 통째로 떼어 온다 — 자기 로스터를 든 하네스는 영원히 자기와 일치한다.

```js
// Sorted arrays, not Sets: the failure line has to SHOW which word appeared or vanished.
rec('ignore-roster', 'IGNORED_HEADERS membership', 'the exact set',
  [...spec_.members].sort(), [...LIVE].sort());
rec('ignore-roster', 'IGNORED_HEADERS', 'has no duplicate entry', LIVE.length, new Set(LIVE).size);
```

**그리고 그 단언은 바로 이 커밋에서 실제로 발화했다.** 로스터가 4→13으로 늘었을 때 362개
단언 중 **발산한 것은 이 하나**였다. 나머지 361개는 아홉 단어가 새로 생긴 것을 몰랐다.

같이 들어간 것들:

- **소속(membership)과 거동을 둘 다 고정.** 목록이 맞아도 그 목록을 읽는 술어가 틀릴 수 있다.
- **음성 축**: 모르는 단어는 `null`을 답해야 한다. `IGNORE`를 답하면 `looksLikeHeader`가
  평범한 데이터 두 칸을 머리줄로 받아 **사용자의 첫 행을 먹는다.**
- **교차 소스**: `ROLLUP_COLUMNS`의 모든 단어가 로스터에 있는지 — 롤업 컬럼이 개명되고 로스터가
  안 따라가면 `COUNT` 결함이 개명 한 번 뒤에 그대로 재현된다. 양쪽 다 소스에서 떼어 오므로
  **계약 파일만 고쳐서는 만족시킬 수 없다.**
- **예비 트립와이어**: `rollupToGrid`의 importer 수가 0인지를 `client2/src`+`client2/tests`
  주사로 단언한다(주석 제거 후 검사, `doe_bands.js` 자신은 제외). 이것은 결함이 아니라
  **선언된 전제에 박은 핀**이다.
- **비활성(inert) 픽스처 방어**: 「양방향이 없는 경계 케이스」·「미지 단어가 없는 음성 목록」은
  `die()`로 죽인다 — 한 방향만 있는 픽스처는 항상 같은 답을 내는 술어도 통과시킨다.

그리고 **채점되지 않는 키가 생기는 자리**를 막았다. 종전 소비 게이트는 `*_cases` 키만
대조했는데 `ignored_headers`는 집합이라 그 이름을 쓸 수 없다 — 어느 게이트도 덮지 않는 키가
정확히 축이 조용해지는 방식이라, `CONSUMED_OTHER` 집합과 그 게이트를 따로 만들었다.

**362 → 396 단언**이 됐고, 14번째 항목과 12번째(하나 뺀) 항목 양쪽을 잡는 것이 증명됐다.

---

## ④ 🔴 **아무도 계약의 클라 절반을 돌리지 않았다**

이 라운드에서 가장 값나가는 발견이다. `contracts/<name>/client_harness.mjs`는 이음새의 클라
절반을 `vectors.json`에 채점하는 파일인데, **2026-07-30까지 그것을 실행하는 것이 하나도
없었다.** `pytest server/tests/`는 서버 절반만 채점하고, `client2/package.json`에는 스크립트가
없었다. 아무도 안 돌리는 계약은 주석이다.

가정이 아니다 — `split_registry_harness.mjs`는 심볼 5개가 개명된 뒤 **몇 주 동안** 추출
단계에서 예외로 죽어 있었고, 부르는 게이트가 없어 그 실패가 보이지 않았다. contract-keeper가
2026-07-30에 계약 4종 전부 같은 상태임을 보고했다.

```js
// DISCOVERY, NOT A LIST. Harnesses are found by scanning `contracts/*/client_harness.mjs`.
// A hardcoded list would recreate the exact bug this closes: contract #5 lands, nobody adds it
// here, and it is dead on arrival while the build stays green.
```

설계에서 명시적으로 고른 것 셋:

- **목록이 아니라 발견식 스캔.** 하드코딩 목록은 이 결함을 그대로 재생산한다 — 계약 #5가
  착지하고, 아무도 여기 안 적고, 빌드는 초록인 채 그것이 죽어 있다.
- **빈 스캔은 실패다.** `contracts/`가 옮겨지거나 이름이 바뀌면 "0개, 전부 초록"이 되는데,
  그것은 배선 안 된 종전 상태보다 나쁘다 — **없는 커버리지를 있다고 보고**하기 때문이다.
  디렉터리 부재도, 하네스 0개도 `exit 1`이다.
- **판정은 종료 코드만 읽는다.** `map_seam`은 "DECLARED DIVERGENCES"를 찍고도 0으로 끝나는데,
  그것은 벡터가 고정한 **이름 붙은 기대된 발산**이다(contract-keeper 헌장 규칙 5 — 익명의 영구
  빨강 금지). 러너가 하네스의 산문을 해석하면 파이프라인에 **두 번째 채점자**가 생긴다.
  실패했을 때만 하네스 자신의 출력을 그대로 흘려보낸다 — 어느 단언이 어떤 값으로 발산했는지는
  하네스가 말할 일이고, 여기서 요약하면 정확히 그것을 잃는다.

배선은 `prebuild`다.

```json
"check:contracts": "node scripts/check_contracts.mjs",
"prebuild": "npm run check:clipboard && npm run check:contracts",
```

**이것으로 "초록"의 의미가 바뀌었다.** 하나라도 발산하면 `dist/`가 생성되지 않는다.

---

## 같은 라운드의 나머지 — 그리고 커밋 메시지가 하나를 잘못 말한다

**`clearGrid`가 초안 writer를 부르지 않았다.** 편집 경로는 열 곳이 넘는데 여기만 빠져 있었고
(PRIMITIVES §1 「모든 편집 경로가 초안 writer를 불러야 한다」 위반), 결과는 둘이었다 —
① Clear Grid → 새로고침 → 낡은 초안에서 격자가 통째로 되살아났다 ② 범례·DOE 뱃지가 지워진
셀을 계속 셌다. 수정은 `deleteLegendValue`와 **같은 순서의 같은 세 줄**이다.

**[F2b] 저장 불가 셀의 분류와 정리.** 종전 대조 게이트는 「직렬화 안 된 non-empty 수」 한
수로 거부했는데, 그 안내문("격자 크기·시작 좌표·회전·물리 규격을 맞추십시오")이 **원 밖 셀에
대해서는 작동할 수 없었다** — 그 셀은 격자 밖이 아니라 원 밖이라 프레임을 아무리 맞춰도
사라지지 않는다. 그래서 한 수를 두 모집단으로 쪼갰다.

```js
// 격자 밖 — 그 키에 cellObj 자체가 없다. 현재 프레임이 맵을 덮지 못한다는 뜻이고
//           `replace_map`이 그 행들을 지운다. **진짜 절단 방어**(H2)이므로 거부는 그대로다.
// 원  밖 — cellObj는 있는데 `inside`가 거짓이다. 그리지도 세지도 저장하지도 않는 셀이다.
```

🔴 그리고 **원 밖은 다시 둘로 갈린다.** 출처가 ① 옛 `Fill All`이 사각 전체를 칠하며 남긴
흔적(서버에 없다) ② 파서가 인제션한 맵이 현재 물리 규격의 마스크를 벗어난 경우(**서버에 있다**)
인데, **좌표만으로는 구별되지 않는다.** ②를 지운 뒤 Push하면 `replace_map`이 그 행들을 서버에서
삭제한다 — H2와 같은 계급의 파괴다. 그래서 정리는 **"서버가 보낸 적 없다"가 증명된 키에만**
허용하고, 그 증명은 로드가 붙든 셀 키 집합(`serverCellKeys`)이 진다. 이 집합은:

- 로드 시작에서 `null`로 버려진다(로드가 예외로 끝나면 앞 맵의 집합으로 이 맵을 판정하는
  일이 없다),
- **절단된 응답에서는 "모른다"로 강등된다**(상한을 넘긴 맵에서 "서버에 없다"는 거짓일 수 있고,
  그 거짓 위에서 정리하면 실재하는 행이 다음 Push에서 삭제된다 — `readRegistryScope`가 절단을
  실패로 강등하는 것과 같은 규칙),
- **Push 성공 시 갱신된다**(방금 적재한 셀은 이제 서버에 있다. 안 갱신하면 나중에 규격을 줄여
  그 셀이 원 밖이 됐을 때 "서버가 보낸 적 없다"로 오판된다).

정리 동선은 새 패널도 새 모드도 아니다 — **이미 있던 거부 대화상자가 쓰기 1회 확인이 될 뿐**이다.

⚠️ **커밋 메시지와 diff가 어긋나는 지점 하나.** 커밋 메시지는 *"Fill All no longer strands
cells outside the valid-die set"*이라고 적었지만, **이 커밋의 diff에 `fillGrid`는 없다.**
유효 다이 필터는 `064550f`(이 커밋 이전, 직전 히스토리 동기화 시점보다도 앞)에서 이미
들어왔다. 이 커밋이 더한 것은 필터가 아니라 **그때 이미 격자에 남아 있던 셀을 치우는 길**이다.
diff가 근거이고 메시지는 저자의 요약이다.

---

## 검증

- **`contracts/doe_band_rules` 396 단언** — 이 항목을 쓰면서 다시 돌렸을 때도
  `DOE zone rules: OK (396 assertions)`였다. (이 하네스가 읽는 `doe_bands.js`는 그 시점
  작업 트리에서 깨끗했고, 더러운 `map_editor.js`는 `rollupToGrid` importer 주사에서만 읽힌다.)
- **로스터 집합 단언이 양방향으로 발화**하는 것이 증명됐다 — 14번째 항목 추가, 12번째로 축소
  둘 다 잡는다.
- `copy_header_count_harness.mjs`는 **작업 트리를 고정된 결함 이전 기준선**(`7524d00` =
  `064550f^`)에 대조한다. 기준선이 `HEAD`였던 시절이 있었고, F1ⓐ+F2가 착지한 순간 `HEAD`가
  **고쳐진 소스가 되어** 모든 "결함 버전은 발산한다" 단언이 자기 자신과의 비교로 바뀌었다 —
  이 하네스가 잡으려던 바로 그 계급의 실패라, 기준 커밋을 이름 있는 상수로 박았다.
- 이 라운드에 파이썬 스위트 수치는 없다. 변경이 전부 클라·계약·빌드 스크립트이고, 이 커밋이
  세운 게이트가 곧 클라 절반의 채점자다(`npm run build`).

## 수정 파일

| 파일 | 내용 |
|---|---|
| `client2/src/map_editor.js` | 열 폭 정책(`headerSpanFor`/`distributeSpans`/`auxColumnSpans`) · `mapKeyGroupLabel` · `classifyUnsavableCells`/`serverCellKeySet`/`serverCellKeys` · `clearGrid` 초안 writer · 격자 행 `totalCols` 채움 |
| `client2/src/doe_bands.js` | `IGNORED_HEADERS` 4→13 + 각 항목의 출처 주석. **평평한 리터럴 유지**(계약이 대괄호를 소스에서 떼어낸다 — 다른 상수를 참조하면 계약이 "집합이 다르다"가 아니라 "추출 실패"로 죽는다) |
| `client2/scripts/check_contracts.mjs` | 🆕 계약 하네스 러너 — 발견식 스캔, 빈 스캔=실패, 종료 코드만 판정 |
| `client2/package.json` | `check:contracts` 신설, `prebuild`에 연결 |
| `contracts/doe_band_rules/client_harness.mjs` · `vectors.json` | `ignored_headers` 집합 단언 + 소속/거동/음성/교차소스/예비 트립와이어/경계행, `CONSUMED_OTHER` 게이트 |
| `client2/tests/copy_header_count_harness.mjs` | 열 폭·로스터 축 확장 |
| `client2/tests/effort_instrument_harness.mjs` | 샌드박스에 `classifyUnsavableCells`/`serverCellKeySet` 추가(진짜 함수여야 Push가 요청까지 도달한다) |
| `docs/architecture/PRIMITIVES.md` · `docs/guide/DOE_GUIDE.md` · `docs/guide/VALID_DIE_MAP_GUIDE.md` · `docs/spec/MAP_EDITOR_SPEC.md` · `docs/README.md` | 대조축 정정 + 단일 술어 프리미티브 등재 |
| `client2/dist/**` | 번들 재생성(파일명은 빌드마다 바뀌므로 여기 적지 않는다) |

## 그때 남아 있던 것

- **`rollupToGrid`의 importer는 0건**이다. 로스터의 롤업 8단어는 표②→표① 붙여넣기가 **아직
  없는 상태**에서 실린 예비 항목이고, 계약이 그 사실 자체를 단언으로 들고 있다.
- **별표 두 항목(`COLOR*`·`칠함*`)이 가리키는 머리줄은 `7694b42`에서 이미 삭제됐다.** 앱은
  어디서도 별표 머리글을 렌더하지 않으며, 살아 있는 언급은 로스터 자신·그 주석·
  `transfer_plan.css`의 주석뿐이다.
- **`064550f`(COPY HEADER MODE 신설 + F2 수렴)와 `7524d00`(유효 다이 운영자 가이드)은 히스토리
  항목이 없다.** 직전 동기화 시점(`20f806a`)보다 앞이라 이 라운드의 범위 밖이었고, 이 항목은
  그 커밋들을 선행으로만 참조한다.
- 이 커밋 시점에서 `map_seam` 계약은 러너 아래에서 **초록**이다 — "DECLARED DIVERGENCES"를
  출력하지만 종료 코드는 0이고, 러너는 종료 코드만 읽는다.
