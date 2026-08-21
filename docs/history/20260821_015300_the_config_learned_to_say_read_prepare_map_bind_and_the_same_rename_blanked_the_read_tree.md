# 설정이 실행 순서대로 말하게 됐고, 바로 그 개명이 읽기 트리를 통째로 비웠다

> **커밋:** `a55f3059` (01:53) · `326240ce` (02:07) | **일자:** 2026-08-21 새벽
> **레인:** 서버(원장 설정 문법) + 클라(온톨로지 탐색기)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **검증:** 서버 **320 passed · 1 skipped**(이 변경이 닿는 12개 스위트) · 클라 하니스
> `ontology_authoring_panel` 41 · `ontology_explorer` 56 · `structure` 113 · `dom_patch` 27 · `npm run build` 번들 해시 **동일**

## 배경 — 「애초에 지금 컨피그 스키마가 잘못돼 있는건데」

소유자 판정 셋이 한 커밋에 들어갔다. 반쯤 착지시키면 **양쪽 어느 모양으로도 못 읽는
라이브 설정**이 남기 때문이다.

핵심은 `driver` 하나가 **서로 다른 두 단계**를 이름 붙이고 있었다는 것이다. 물리 배치를
**읽는** 일과 그것을 문장으로 **바꾸는** 일은 컬럼 우주가 다르다. 전날 「준비기를 어디에
두느냐」로 한 라운드를 통째로 태운 것이 그 대가였다.

```
before                                after
relation                              relation    그대로 — prepared_columns 가 여기서 시작
driver { unit identity group_by       read    { unit identity group_by order_by
         order_by occurred_at                    occurred_at cursor registration_probe }
         cursor registration_probe     prepare { … }   준비기 본문, 한 글자도 안 고침
         preparation mapper }          map     { … }   매퍼 본문, `emits` 만 빠짐
profile { packs mappings }             bind    { mappings }
```

**네 본문은 이름과 깊이만 움직였다.** 파일은 정렬되어 저장되므로 디스크에서는
`bind · map · prepare · read` 순으로 앉고, 사람이 보는 순서는 스켈레톤이 만든다.

## 「어느 주장인가」의 재진술 셋이 사라졌다

- `map.emits` — 매퍼 구현이 아는 것은 `SentenceShape`이지 주장이 아니다. 「이 매퍼가 낼 수
  있는 주장」은 매퍼가 **대답할 방법이 없는 질문**이었다. 이제 `bind.mappings[].use`에서
  **컴파일**되어 `MapperDescriptor.emits`가 된다 — 옮긴 게 아니라 지울 수 있었던 이유는
  `setup_registry`에는 실행 소비자가 있고 **선언 쪽엔 없었기** 때문이다.
- `bind.packs` — 같은 `use`가 가리키는 팩들의 `sorted(set(...))`. 양방향 등식 검사까지
  같이 갔다. `ProfileDescriptor.pack_ids`는 **먼저 재 보고** 지웠다 — 그 검사 밖에 소비자 0.
- `RoleEmission.claim_ref` — `mapping_id`로 프로필에서 푼다. RoleFrame 컬럼과 스키마 버전은
  **불변**이고, 바뀐 것은 **누가 채우는가**다.
- `binding_origin`이 `user_declared`일 때 — 생략하고 기본값에서 읽는다. 운영자 파일 40줄,
  샘플 45줄이 나갔다.

🔴 **`validate_role_frame`의 가드는 지우지 않았다.** 두 값이 이제 같은 `use`에서 파생되므로
각 규칙은 **자기 출처와 자기를** 비교한다. 그래도 남긴 이유는 그 가드가 막던 상태가
**쓸 수 없게 됐기** 때문이고, 그 함수는 자기가 만들지 않은 프레임도 받는 **경계**다.

🔴 **`approval_status`는 required로 남았고, 그 비대칭이 알맹이다.** 지시서는 둘 다 생략하라고
했지만 측정이 절반을 거절했다. `roleframe._evaluate_binding`은 `approved`라고 말하지 않는
바인딩을 실행하지 않는데, v1 리더는 같은 부재를 `pending`으로 읽는다 — 생략하면
「말해야 승인」이 「말 안 하면 승인」으로 뒤집히고 **한 파일을 두 리더가 다르게 답한다.**

> **생략이 읽히려면 기본값이 «아무것도 주지 않아야» 한다.**
> `user_declared`는 자격이 있고 `approved`는 없다.

## 착지 커밋이 스스로 적어 둔 「통과 못 한 것」이, 14분 뒤의 커밋이 됐다

읽기 트리(「정의」 탭)는 **스켈레톤**을 걷는데 — 스켈레톤은 **설정**을 서술한다 — 손에 쥔
것은 `selection.compiled`, 즉 **런타임 자신의 객체**였다. 두 쪽이 필드를 같은 철자로 부르는
동안엔 이 어긋남이 **보이지 않았다.** `a55f3059`가 그것을 끝냈다.

```
a55f3059 착지 직후 측정 — 스켈레톤 잎 중 값을 찾은 것
before   53 found · 44 missing        after   2 found · 56 missing
```

소유자가 `dt_job`을 열자 **자기가 방금 요청한 배열이 올바른 순서로 서 있고 안이 비어
있었다.** 「작성」 패널은 내내 옳았다 — 거짓말한 것은 읽는 쪽 절반이다.

```js
// client2/src/ontology_explorer_view.js  renderReadTree
-  const document_ = state.selection?.compiled;
+  // 🔴 THE SKELETON DESCRIBES THE CONFIG, SO IT IS WALKED AGAINST THE CONFIG.
+  const document_ = state.selection?.raw;
```

한 낱말이 전부이고 나머지 디프는 **왜인지 적은 주석**이다. 다음 사람도 `compiled`에
손을 뻗을 **좋은 이유**를 똑같이 갖게 되기 때문이다.

소유자 화면에서 재측정: `읽기 > 단위` None → `group`, `준비 > implementation_id`
None → `direct-join`, `준비 > implementation_version` None → `1`,
`accepts_verified_join_rules` None → `false`. 나머지 세 종류는 구현 에이전트가 쟀다 —
predicate 10 → 43, pack 88 → 91, entity 6 → **3**. 엔터티만 잃는데, 잃는 것은 **아무도 쓴 적
없는데 컴파일러가 채운 값 셋**이다.

⚠️ **첫 새로고침은 캐시된 번들을 줬고 다시 `None`이라고 답했다.** 재측정 전에 페이지가
실제로 무엇을 로드했는지 확인해야 했다.

## 아키텍처 영향

- 선언 문법(`ledger_skeleton.json` · `ledger_config.json`)만 `read`/`prepare`/`map`/`bind`로
  간다. **컴파일된 plan은 의도적으로 `driver`/`profile`을 유지했다** — 개명하면 철자 하나
  때문에 `backfill`·`source_preparation`·`runtime_v2`·`roleframe`이 같이 움직인다.
- 읽기 트리는 이 커밋 이후 **선언을 읽는다**. `compiled`는 런타임 소유물이고 자기 이름을
  가질 자격이 있다는 것이 그 경계의 뜻이다.

## 그때 남아 있던 것

- `setup_version`은 **3에 머물렀고 마이그레이션 스크립트가 없었다.** 둘 다 별명 라운드
  소관이라, 이 시점에 쓴 스크립트는 다시 쓰여야 했다. 두 설정은 **손으로** 옮겼다
  (운영자 749 → 693줄, 샘플 698 → 643줄).
- 운영자 라이브 설정(`server/config/ontology/ledger_config.json`)은 gitignore이며 이미
  옮겨져 있었다. **옛 사본을 이 코드에 얹으면 거절한다** — 실측된 앞 세 줄:
  `bundle.sources.<id>.bind: must be an object` · 같은 경로 `field is required` ·
  `bundle.sources.<id>.driver: field is not allowed`.
- 같은 커밋에서 자기가 재던 필드와 함께 은퇴한 테스트:
  `test_profile_packs_mapping_use_and_mapper_emits_are_mutually_closed` — 두 필드가 없어져
  **그 세 거절을 유발할 방법이 사라졌다.** 대체 테스트는 「무엇이 그것들을 지울 수 있게
  만들었나」를 단언한다.
