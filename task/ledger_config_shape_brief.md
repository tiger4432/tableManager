# 설정 «모양» 개선 ①② — 소유자 판정 2026-08-20 21:3x

> 소유자: 「**애초에 지금 컨피그 스키마가 잘못돼 있는건데**」 → 「**컨피그 모양 개선안 보여줘**」 → 「**1,2 간다**」

**흡수 라운드(`ledger_profile_absorption_brief.md`) «다음»에 오는 별개 커밋이다.**

---

## 🔴 순서 판정 — 마이그레이션은 «여기»로 옮긴다

흡수 라운드에 붙였던 마이그레이션 스크립트와 `setup_version` 올리기를 **이 라운드로 옮긴다.**

```
커밋 1  프로필 흡수          마이그레이션 «없이» · setup_version 3 그대로 · 통째로
커밋 2  ① + ② + 마이그레이션 + setup_version 4      ← 최종 모양 하나만 아는 스크립트
```

**왜:** 마이그레이션을 흡수 라운드에서 쓰면 두 시간 뒤 ①②가 그것을 다시 쓰게 만든다.
**스크립트는 «도착한 모양» 하나만 알면 된다.** 소유자 라이브 설정은 이미 손으로 앞서 있어
그동안 거절될 일이 없다.

---

## ① 승인 메타데이터를 바인딩 본문에서 뺀다

**실측:** 라이브 설정 750줄 중 **80줄(11%)**이 `approval_status`·`binding_origin`. 각각 40회.

```json
"subject": { "kind": "entity", "entity_type": "Lot@1",
             "approval_status": "approved",         ← 모든 바인딩마다
             "binding_origin": "user_declared",     ← 그리고 안쪽 keys 마다 또
             "keys": { "lot": { "kind": "column", "column": "lot",
                                "approval_status": "approved",
                                "binding_origin": "user_declared" }}}
```

이 둘은 **「이 바인딩이 무엇인가」가 아니라 「누가 어떻게 정했나」**다. 값이 한 종류뿐이면
파일의 8분의 1이 상수를 반복하고 있는 것이다.

### 하는 일 — 「지운다」가 아니라 「기본값이면 안 적는다」

```
파일     기본값이면 «생략». 다른 값이면 «적는다»
읽는 쪽   없으면 기본값으로 읽는다 — 기본값은 검증기에서 뽑을 것, 내 기억이 아니라
스켈레톤  두 필드를 optional 로. 화면에서 «비어 있음»이 정상 상태가 된다
```

### 🔴 착수 «전»에 반드시 재고 시작할 것

```
A  두 필드에 실제로 나타나는 «값의 집합»을 세라. approved / user_declared 말고 다른 값이
   하나라도 있으면 «멈추고 보고». 그때는 생략이 뜻을 지운다
B  두 필드를 «읽는» 코드가 무엇을 하는가. 소비자를 세어라 — grep 아니라 소비자
```

⚠️ **「선택 필드를 지우면 꺼진다」를 오늘 이미 한 번 겪었다.** 없어서 0인 것과 무해해서 0인 것은
다르다. **상태가 아니라 숫자로 확인한다** — 아래 6번(원자 696)이 그 자리다.

---

## ② 소스 안이 「순서」를 말하게 한다

지금 `driver`가 **읽기와 변환을 한 이름 아래** 섞고 있다. 오늘 준비기·매퍼를 어디 넣을지
고르느라 라운드를 쓴 것도 이 때문이다.

```
전                                          후
relation                                    relation            ← 그대로. 표는 입력이다
driver { unit, identity, group_by,          read    { unit, identity, group_by, order_by,
         order_by, occurred_at, cursor,               occurred_at, cursor, registration_probe }
         preparation, mapper,               prepare { … }       ← driver.preparation 그대로 올라온다
         registration_probe }               map     { … }       ← driver.mapper 그대로 올라온다
profile { packs, mappings }                 bind    { packs, mappings }
```

**표 → 읽기 → 준비 → 매핑 → 연결.** 네 단계가 «형제»로 서서 흐름이 보인다.

🔴 **`relation`은 옮기지 않는다.** `prepared_columns`가 `source["relation"]`에서 출발한다
(`config_authoring.py`). 옮기면 그 자리가 따라 바뀌고, 얻는 것은 없다. **바뀌는 층만 바꾼다.**

🔴 **본문은 한 글자도 안 바꾼다.** 네 덩이의 «내용»은 그대로고 이름과 깊이만 바뀐다.

### ⚠️ 파일은 알파벳순으로 쓰인다 — 순서는 «스켈레톤»이 만든다

설정 파일은 `sort_keys=True`로 쓰인다. 그래서 파일 안에서는 `bind · map · prepare · read`,
즉 **흐름의 반대**로 앉는다. **그건 고치지 않는다.**

**순서를 만드는 곳은 스켈레톤이다** — 화면의 행 순서는 스켈레톤이 정한다(오늘 `dt_job`이
`relation → profile_id → driver → …` 로 뜬 것이 알파벳순이 아닌 것이 증거다).
**스켈레톤에 read → prepare → map → bind 순으로 놓는다. 파일 정렬을 건드리지 말 것.**

### 화면 라벨 (소유자 규칙: 기호·짧은 영어·명사형)

```
read     읽기
prepare  준비
map      매핑
bind     연결
```
소유자가 다른 낱말을 주시면 그걸 쓴다. **라벨만 바꾸고 키는 위 영어 그대로.**

---

## 🔴 통째로 착지한다 — ①②는 «한» 커밋

마이그레이션·`setup_version` 4·스켈레톤·검증기·화면·테스트가 한 커밋이다.

**착지 전 확인:**
```
1. dt_job 을 열면 relation · 읽기 · 준비 · 매핑 · 연결 순으로 뜬다
2. 바인딩 행에 approval_status · binding_origin 이 «안» 보인다 (값이 기본값이므로)
3. 라이브 설정 줄 수가 750 → 대략 670 (80줄 감소)
4. 소스 하나를 폼만으로 새로 만들어 저장 → 거절 0
5. 🔴 lot_event 배치 프리뷰: 분자 20 · 원자 696 · incomplete 0 · DB 쓰기 0
      ← ①이 뜻을 지웠는지 여기서 «숫자로» 드러난다. 696 이 아니면 착지 금지
6. 마이그레이션: 병합 «전» 커밋의 샘플을 꺼내 스크립트에 태우면
      지금 트리의 샘플과 diff 0 (setup_version 줄 제외)
7. 옛 파일을 새 코드에 올리면 unsupported_setup_version 으로 거절된다
      ← 「field is not allowed」가 아니라. 이게 버전을 올리는 이유다
```

## 이번에 «하지 않는» 것

| | 무엇 | 왜 |
|---|---|---|
| A | 팩을 소스 안으로 | 오늘 1:1이지만 검증기가 «강제»하지 않는다. 강제된 1:1만 안으로 넣는다 |
| B | 파일 키 정렬 바꾸기 | 순서는 스켈레톤이 만든다. 정렬은 정본 직렬화라 해시 재료다 |
| C | 「첫 저장 전 후보 0」 | 별건, 소유자 판정 대기 |
| D | 커서 리셋 승인 장치 | 운영 판정 대기 |

---

## ③ 「닿을 수 없으면 선언도 닿지 않는다」 — 소유자 판정 2026-08-20 23:4x

> 소유자: 「**클레임과 맵퍼 함수는 완전 별개인데 왜 맵퍼에서 쓸 클레임을 정의함? 프로필에서
> 해야하는거 아니야?**」 → 「**닿을 수 없다면 선언도 닿으면 안됨**」 → 「**진행**」

**이건 결함 수리가 아니라 구조 판정이다.** ①②와 같은 성격이므로 같은 커밋에 붙는다.

### 정본은 하나다 — `profile.mappings[].use`

어느 `claim` 을 쓰는지 정하는 곳은 `profile` 이다. 그런데 그것을 되풀이하는 자리가 셋 있고,
**셋 다 자유도가 0** 이다.

```
① driver.mapper.emits      config_authoring.py:867   state="derived"
                           ground = mapper_emits_from_profile_uses
                           주석: 「Set equality is checked in BOTH directions;
                                  degrees of freedom: zero.」
② profile.packs            config_authoring.py:953   state="derived"
                           value = sorted(set(used_packs))   ← mappings[].use 에서 나온다
③ RoleEmission.claim_ref   roleframe.py:146          코드가 claim 을 «이름»으로 든다
```

### 왜 mapper 쪽이 특히 틀렸나

`mapper` implementation 은 `claim` 을 모른다 — `SentenceShape` 만 안다. 「이 mapper 가 낼 수 있는
`claim` 이 무엇인가」는 **mapper 쪽에서 대답이 없는 질문**이고, 대답을 가진 것은 `profile` 뿐이다.
그런데 `emits` 는 `driver.mapper` 안에 앉아 있다. **섹션이 틀렸다.**

`_resolve` 의 주석이 이 설계의 의도를 이미 적어 두었다:
「the naming runs config -> mapper, so renaming a `mapping_id` cannot reach this file」
**이름은 config 에서 mapper 로 한 방향으로만 흐른다.** `emits` 와 `claim_ref` 둘만 그 선을 거슬러 있다.

### 무엇을 한다

```
지운다   driver.mapper.emits
지운다   profile.packs
지운다   RoleEmission.claim_ref
         → compile_role_frame 은 mapping.claim_ref 에서 얻는다
           (이미 mapping_id 로 mapping 을 찾고 있다 — roleframe.py:1081)
남긴다   profile.mappings[].use            ← 유일한 정본
남긴다   RoleEmission.mapping_id           ← profile 이 소유하는 이름
```

🔴 **부수 효과이지 «이유»가 아니다:** 지금 `compile_role_frame` 은 `mapping` 을 찾아 놓고
`claim_ref` 와 대조하지 않는다(그 함수에서 `mapping` 은 조회 한 줄과 에러 메시지 한 줄에만 쓰인다).
`claim_ref` 가 없어지면 **어긋날 두 값이 없어져 그 검사가 필요 없어진다.**
구멍을 막는 것이 아니라 구멍이 있을 자리를 없앤다.

### 착수 «전»에 셀 것

```
A  setup_registry.py:790 이 emits 를 MapperDescriptor 에 싣는다 — «실행»이 그 필드를 읽는가
B  profile.packs 를 읽는 곳 — 검증 말고 실행·화면에 소비자가 있는가
C  RoleEmission.claim_ref 를 읽는 곳 — compile_role_frame 말고 또 있는가
```
**하나라도 실행 소비자가 있으면 멈추고 보고할 것.** 그때는 지우는 게 아니라 출처를 바꾸는 일이 된다.

### 받아들이는 시험

```
1  config 에서 세 자리가 사라진다 — 라이브·샘플 둘 다
2  mapper 가 claim 에 닿는 «경로가 없다» — claim_ref 소비자 grep 0건
3  lot_event 배치 프리뷰 원자 696 · incomplete 0 · DB 쓰기 0     ← 뜻이 안 바뀌었다는 숫자
4  마이그레이션이 옛 config 에서 emits·packs 를 «떨어낸다» (①②의 스크립트가 같이 한다)
5  화면에서 그 세 행이 사라지고, 소스 하나를 폼만으로 만들어 저장 → 거절 0
```

### 소유자 판정 — `bind` 는 레코드로 «남긴다» (2026-08-20 23:5x)

> 총괄: 「③이 `packs` 를 지우면 `bind` 안에 `mappings` 하나만 남습니다. 목록 그 자체로 접을까요」
> 소유자: 「**ㅇㅇ 남겨**」

```
간다    bind { mappings: [ … ] }      필드 하나짜리 레코드로 둔다
안 간다 bind: [ … ]                   목록으로 접지 않는다
```
접으면 나중에 `bind` 에 무엇을 더 붙일 때 다시 펴야 하고, 그때는 또 마이그레이션이다.
**이번 라운드는 `bind { mappings }` 까지다.**

---

## 🔴 순서 정정 — 마이그레이션·`setup_version` 은 «별명 라운드»로 옮긴다 (소유자, 2026-08-21)

> 소유자: 「**어차피 맵퍼 별명 문장하면 구조 다 바뀌는데 1,2,3 이랑 마이그레이션 의미있어?**」

**①②③ 자체는 의미가 있다 — 별명과 «겹치지 않는다».**
```
①  approval_status · binding_origin      bind «안»의 일. 별명은 bind 내용을 안 건드린다
②  driver → read·prepare·map·bind        절 이름과 깊이. 별명은 절을 안 건드린다
③  emits · packs · claim_ref 삭제         claim_ref 만 별명과 인접하다
```

**겹치는 것은 마이그레이션과 `setup_version` 하나뿐이고, 그건 두 번 쓸 이유가 없다.**
오늘 흡수 라운드에서 이미 같은 판단을 했다 — **스크립트는 «도착한 모양» 하나만 알면 된다.**

```
이 라운드(①②③)   마이그레이션 «없이» · setup_version 3 그대로
                   라이브·샘플은 손으로 이관 (소스 둘뿐이다)
별명 라운드         마이그레이션 «한 번» + setup_version 4
                   옛 모양 → 최종 모양을 한 스크립트가 덮는다
```

⚠️ 그래서 **이 라운드의 착지 확인에서 6·7번(마이그레이션 diff · `unsupported_setup_version`)을 뺀다.**
나머지는 그대로다 — 특히 **원자 696**.

---

## 🔴 총괄 정정 둘 — 구현자 실측이 지시서를 고쳤다 (2026-08-21 01:0x)

### ① 판정: **「나」 — `binding_origin` 만 생략하고 `approval_status` 는 남긴다**

두 필드가 «대칭이 아니다». 실측:
```
roleframe.py:800       binding.approval_status != "approved" → «실행 경로»가 거절한다
source_profile.py:280  legacy 기본값 = approval_status «PENDING»
_APPROVAL_STATUSES     {pending, approved, rejected}
_BINDING_ORIGINS       {user_declared, system_suggested, imported}
```
**`approval_status` 는 게이트다.** 생략하고 기본값을 `approved` 로 읽으면
「승인이라고 말해야 승인」이 **「말 안 하면 승인」으로 뒤집힌다.** 게다가 다른 자리의 기본값은
`pending` 이라 둘이 어긋난다.

🔴 **원칙 (구현자 문장 그대로 받는다): 생략의 기본값은 «아무것도 주지 않는 값»일 때만 된다.**
`user_declared` 는 자격이 있고 `approved` 는 없다.

```
간다     binding_origin 생략        80줄 중 40줄. 위험 0
안 간다  approval_status 생략       효과는 나머지 40줄, 대신 게이트가 뒤집힌다
```
**효과 절반을 포기하고 안전을 산다.** 총괄이 처음에 둘을 한 덩이로 적은 것이 틀렸다.

### ③ 정정: 「대조 안 한다」는 **총괄이 엉뚱한 함수에서 쟀다**

지시서에 「`compile_role_frame` 은 `mapping` 을 찾아 놓고 `claim_ref` 와 대조하지 않는다」고
적었다. **거짓이다.** 그 대조는 바로 옆 함수에 있다:
```
validate_role_frame:910   row["claim_ref"] != mapping.claim_ref → invalid_claim_ref
                   :914   not in descriptor.emits              → unsupported_claim
```
같은 데이터가 두 함수를 다 지난다. **구멍은 없었다.**
([[a-snippet-reproduced-out-of-context-is-not-the-behaviour]] — 구현자가 그 이름으로 잡았다)

**그래도 ③은 «진행»한다. 근거만 바뀐다.**
```
전(틀림)  「대조가 없으니 구멍이다」                    ← 거짓
후(맞음)  claim_ref 를 mapping_id 에서 «유도»하면
          :910 은 자기를 자기와 비교하는 «동어반복»이 되고
          :914 도 use 에서 유도된 emits 와 비교하니 동어반복이 된다
          매퍼가 모르는 mapping_id 를 내는 경우는 :906 unknown_mapping 이 «이미» 잡는다
```
🔴 **가드를 「지우는」 게 아니라, 가드가 막던 상태가 «표현 불가»가 되어 동어반복이 되는 것이다.**
별명 라운드의 `_ambiguous_sentences` 와 같은 모양이다. 커밋 메시지에 그렇게 적을 것.

---

## 🔴 체크포인트 정정 — 「원자 696」을 «불변»으로 바꾼다 (구현자 실측, 2026-08-21)

**총괄이 세 지시서에 박은 상수 `696` 은 재현 불가능하다.** 구현자가 라이브 DB 에서 쟀다:

```
행 38 · 등록 스냅샷 «빈 것»   →  분자 19 · 원자 701 · incomplete 0
행 40 · 빈 스냅샷             →  분자 20 · 원자 731 · incomplete 0
696                           →  등록 스냅샷이 «있던» 때의 값
```
**셋 다 자기 입력에 대해 맞다.** 가르는 것은 ①읽은 행 수 ②등록 스냅샷 둘이고,
**설정 모양은 그중 어느 것도 아니다.** `register` 를 내는 소스는 `known_registrations` 를
필수로 요구하고 이미 등록된 주체를 거른다(`runtime_v2.py:93-94`).

### 그래서 합격 기준은 이렇게 읽는다

```
✖ 안 된다   원자가 696 이어야 한다            ← 입력이 안 적혀 있어 재현 불가
✔ 된다      «같은 행 수 · 같은 등록 스냅샷»으로 변경 «전»과 «후»를 각각 재고,
             두 수가 «같을 것». incomplete 0 · DB 쓰기 0 은 그대로
```
전은 워크트리를 HEAD 에 파서 잰다 — 흡수 라운드에서 이미 그렇게 했다(731 대 731).

🔴 **이 절이 위의 모든 「696」 문구를 대체한다.** 숫자를 쫓지 말고 «전후가 같은지»를 본다.
[[presence-is-not-confirmation]] 의 사촌이다 — 조건을 안 적은 수는 사실이 아니라 일화다.
