# 문장을 «별명»으로 부른다 — 소유자 판정 2026-08-21 00:4x · **대기열 1순위**

> 소유자: 「**지금 자연스럽지 못한 자리가 맵퍼가 낸 정규 문장 - 클레임으로 바인드 여기네**」
> → 「**맵퍼 구조를 문장에 별명을 붙여 부르게 만들고 그 별명에 바인드를 한다면?**」
> → 「**맵퍼 별명문장 부르기 1순위**」

---

## 왜 — 지금은 «이름이 있는데 꼴찌로» 쓰인다

`mapper` 가 `say(SHAPE, …)` 하면 `profile` 이 어느 `mapping` 인지 이렇게 고른다:

```
1순위   구조         has_object · qualifiers
2순위   subject_type  그래도 여럿이면
3순위   object_type   그래도 여럿이면
4순위   sentence      «마지막»에 이름이 나온다
```

**`sentence` 가 그 이름이다.** `SentenceShape` 의 클래스 속성 이름이 그대로 id 가 되고
(`__set_name__`), config 의 `sentence` 가 그것을 가리킨다. **이미 양쪽에 안정된 이름이 있는데
동점을 깨는 최후 수단으로만 쓴다.**

구조 매칭을 고른 이유도 코드에 있다 — 「the naming runs config → mapper, so renaming a
`mapping_id` cannot reach this file」. **config 이름이 mapper 로 새는 걸 막으려던 것인데,
`sentence` 는 config 이름이 아니라 mapper «자신의» 이름이라 그 걱정이 애초에 없다.**

## ~~그리고 구조 매칭은 이미 «금 가 있다» (실측)~~ ← 🔴 총괄 정정: 죽은 파일에서 쟀다

```
ledger_dt_job_mapper.py:24-25
    COUNTED    = SentenceShape(has_object=True)
    FIRST_WORK = SentenceShape(has_object=True)     ← 구조가 «동일»
```
`FIRST_WORK` 는 **선언돼 있고 한 번도 안 쓰인다**. 쓰는 날 `COUNTED` 와 동점이다.
**「아직 도달하지 않아서 안전」한 상태이고, 이 프로젝트가 여러 번 데인 모양이다.**

---

## 도착지

```
문장은 «별명»으로 불린다. mapping 은 그 별명으로 지목된다. 매칭은 «키 조회 하나».
```

### 사라지는 것

```
setup_bundle._ambiguous_sentences   컴파일 시점 모호성 거절 — 모호할 수가 없어진다
_sentence_signature                 구조 서명 계산 (roleframe._resolve 와 «같은 식»이어야 하는 부담도)
say() 의 subject_type · object_type  selector 인자
구조 비교                            has_object 로 mapping 을 «고르는» 일
```

### 치르는 것 — 실측한 값

```
lot_event   shape 5 → mapping 6     FIRST_SIGHT 가 subject_type 으로 둘로 갈린다
                                    → 별명 방식이면 매퍼가 «둘로 이름 붙여야» 한다
dt_job      shape 3 → mapping 2     selector 0건. FIRST_WORK 는 안 쓰인다
sentence    6 중 2 만 갖고 있다      → 6/6 이 되어야 한다
```

🔴 **매퍼가 문장을 더 잘게 이름 붙이는 것은 배포 세부가 새는 게 아니다.** `lot_event` 이
`subject_type=holder` / `item` 으로 가르는데, 그 둘은 매퍼가 `subject_type_of()` 로 **프로필에
물어서 받은** 값이다. `Lot`·`Wafer` 라는 이름을 아는 게 아니라 「담는 쪽·담기는 쪽」이라는
자기 도메인 지식만 쓴다. **그건 매퍼가 원래 알아야 하는 것이다.**

---

## 🔴 착수 «전»에 재고 시작할 것

```
A  오늘 mapping 6 + 2 가 «서로 다른 별명 8개»로 갈리는가 — 하나라도 안 갈리면 멈추고 보고
B  SentenceShape 의 has_object · qualifiers 가 매칭 말고 «다른 일»을 하는가
   (say() 가 qualifiers 키 집합을 자기 검사에 쓴다 — 그건 남아야 한다. has_object 는?)
C  FIRST_WORK 처럼 «선언되고 안 쓰이는» shape 이 또 있는가 — 있으면 별명을 줄지 지울지 보고
```

## 이름의 «소유자»는 바뀌지 않는다

```
별명을 짓는 쪽    mapper   (SentenceShape 의 이름)
가리키는 쪽       config   (mapping 의 sentence)
```
**지금과 같다.** 바뀌는 것은 그 이름이 «1순위»가 되는 것뿐이다. `mapping_id` 는 그대로
config 의 것이고 mapper 에 안 닿는다.

---

## 🔴 통째로 착지한다

매퍼 구현 · `roleframe._resolve` · 검증기 · 스켈레톤 · 라이브·샘플 config · 마이그레이션이 한 커밋.

**착지 전 확인:**
```
1  lot_event 배치 프리뷰 원자 696 · incomplete 0 · DB 쓰기 0      ← 뜻이 안 바뀌었다는 숫자
      🔴 696 이 아니면 «착지 금지». 이 수가 라운드 사이의 체크포인트다
2  dt_job 도 같은 방식으로 재고, 앞 라운드와 같은 수                 ← 두 소스 다 봐야 한다
3  say() 호출에 subject_type · object_type 인자가 «0건»
4  _ambiguous_sentences · _sentence_signature 가 «사라졌다»
5  소스 하나를 폼만으로 새로 만들어 저장 → 거절 0
6  마이그레이션이 옛 config 의 mapping 에 sentence 를 «채운다»
      ← 채울 수 없는 mapping 이 나오면 그게 A 의 실패다. 추측해서 채우지 말 것
```

## 이번에 «하지 않는» 것

| | 무엇 | 왜 |
|---|---|---|
| B | 안 쓰이는 shape 정리 | C 의 측정 결과를 보고 판정한다 |
| C | 커서 소스별 지문 | 이 라운드 «뒤». 모양 변경을 다 끝내고 지문을 세운다 |

---

## 🔴 마이그레이션과 `setup_version` 4 는 «이 라운드»가 진다 (소유자, 2026-08-21)

①②③ 라운드에서 옮겨 왔다. **스크립트는 최종 모양 하나만 알면 된다.**

```
한 스크립트가 덮는다
  source_preparers · mappers 절 → driver 안으로        (이미 손으로 끝남, 멱등이어야 한다)
  profiles 절 → source 안으로                          (이미 손으로 끝남)
  approval_status · binding_origin  기본값이면 떨어낸다   ①
  driver → read · prepare · map · bind                 ②
  emits · packs 제거                                    ③
  mapping 마다 sentence 채우기                          ← 이 라운드
  setup_version → 4
```
🔴 **`sentence` 를 «추측해서» 채우지 말 것.** 채울 수 없는 mapping 이 나오면 그것이
「착수 전에 잴 것 A」의 실패다 — 이름을 지어내지 말고 멈추고 보고한다.

## 별명이 «많아지는» 것 — 소유자 판정: 지금은 감수한다

> 소유자: 「**별명 문장해서 많아지는 문제는 일단 이렇게 구현하고 나중에 숏컷 뚫어서
> 당연한건 같이 생성되게 하면 됨**」

**이 라운드는 별명을 하나씩 다 적는다.** 줄이는 장치는 만들지 않는다.
나중에 「당연한 것은 같이 생성」하는 숏컷을 별건으로 얹는다 — **그건 편의층이고, 토대가 먼저다.**

---

## 🔴 범위 추가 — `mappings` 를 «별명 키 맵»으로, `mapping_id` 는 사라진다 (소유자, 2026-08-21)

> 총괄: 「별명이 키가 되면 `mapping_id` 가 넷째 사본이 됩니다. 같이 넣을까요」
> 소유자: 「**같이 넣어**」

앞의 「이번에 하지 않는 것 A」를 **취소한다.** 별명이 1순위 키가 되는 것과 목록을 맵으로
바꾸는 것은 한 몸이고, 이 라운드가 이미 마이그레이션을 지고 있어 **지금이 제일 싸다.**

### 도착 모양

```json
"bind": {
  "mappings": {
    "<별명>": { "use": "lot-lineage@1/register",
                "bind": { "subject": …, "occurred_at": … } }
  }
}
```
**별명이 키, 값은 「어느 `claim` 이고 그 칸을 어떻게 채우나」 둘뿐이다.**

### 같이 사라지는 것

```
mapping_id              별명과 1:1 이 된다 — id 노릇을 하는 것은 별명 하나
RoleEmission.mapping_id → RoleEmission.sentence 로. «선언된 이름»을 쓴다
mappings 가 목록인 것    맵이면 별명 중복이 «불가능»해진다
```

🔴 **`_ambiguous_sentences` 가 그냥 사라지는 게 아니라 «불가능»해진다.** 지금은 두 mapping 이
같은 문장을 realize 할 수 있어서 컴파일에서 막았다. 맵의 키가 되면 **중복이 표현될 수가 없다.**
검사를 지우는 것과 검사가 필요 없어지는 것은 다르고, 이건 후자다.

### 마이그레이션에 한 줄 더

```
mappings 목록 → 별명 키 맵 · mapping_id 제거
🔴 별명이 없는 mapping 은 «키를 지어내지 말 것» — 「착수 전 A」의 실패로 보고한다
🔴 별명이 겹치는 mapping 이 나오면 그것도 멈춘다 — 맵이 그것을 표현할 수 없다
```

### 착지 확인에 추가

```
7  config 에 mapping_id 가 «0건»
8  mappings 가 맵이고 키가 별명이다 — 라이브·샘플 둘 다
9  compile_role_frame 이 emission.sentence 로 mapping 을 찾는다 (mapping_id 조회 0건)
```

---

## 🔴 왜 ①②③ 과 «나누는가» — 소유자 확인 2026-08-21

> 총괄: 「합치면 한 번에 끝나지만, 696 이 달라졌을 때 원인이 둘 중 하나로 안 좁혀집니다」
> 소유자: 「**ㅇㅇ 나눠 체크포인트는 둬야지**」

```
①②③        사본 삭제 · 이름 바꾸기        원자를 바꿀 «수 없는» 변경
별명 라운드   매칭 알고리즘 · 매퍼 구현       원자를 바꿀 «수 있는» 변경
```
**위험 등급이 다르고, 안전망은 원자 수 하나뿐이다.** 둘을 같이 흔들면 696 이 달라졌을 때
어느 쪽이 깼는지 못 가른다. **각 라운드가 696 을 다시 세우고 넘어간다 — 그게 체크포인트다.**

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

---

## 🔴 총괄 정정 — 위 「금 가 있다」 근거는 «등록되지 않는 파일»에서 쟀다 (2026-08-21 02:3x)

지시서가 `ledger_dt_job_mapper.py:24-25` 의 `COUNTED`·`FIRST_WORK` 구조 동일을 근거로 들었다.
**그 파일은 등록되지 않는다.** v2 실행 경로가 쓰는 것은 `ledger_v2_dt_job_mapper.py` 이고,
등록기(`ledger.implementations.mapper_declarations`)가 아는 매퍼는 셋뿐이다:
```
dt-job-role@1      <- mappers.ledger_v2_dt_job_mapper          REGISTER · COUNTED   둘 다 쓰임
lot-event-role@1   <- mappers.ledger_v2_lot_event_role_mapper  shape 5개 전부 쓰임
declarative-role@1 <- ledger.roleframe
```
**총괄이 `dt-job-role` 로 grep 해 세 파일을 얻고 «어느 것이 등록되는지» 안 보고 골랐다.**
[[grep-skips-the-config-that-actually-runs]] · [[my-filename-is-not-my-address]] — 세 번째다.

⚠️ **그 근거는 지워지지만 라운드는 그대로 선다.** 본론은 「이름이 양쪽에 이미 있는데 매칭에서
4순위로 쓰인다」이고, 그건 죽은 파일과 무관하다.

## ✅ 착수 전 관문 A·B·C — 통과 (구현자 실측)

```
A  갈린다.  살아 있는 shape 7 → mapping 8.  FIRST_SIGHT 를 «둘로» 이름 붙이면 8:8
            지금 sentence 보유 8 중 2 → 8/8 이 되어야 한다
B  has_object   매칭(:503)·에러 문구(:530) 말고 «소비자 없음»  → SentenceShape 에서 «제거»
   qualifiers   say() 자기검사(:428) 가 매칭과 무관하게 쓴다   → «남긴다»
C  살아 있는 매퍼에 안 쓰이는 shape «없음»
```
🔴 **B 의 판정: `has_object` 는 매칭을 위해 존재했으므로 매칭이 이름으로 바뀌면 같이 사라진다.**
`qualifiers` 는 자기검사라 남는다. 구현자가 「둘이 대칭이 아니다」로 가른 것이 정확하다.

