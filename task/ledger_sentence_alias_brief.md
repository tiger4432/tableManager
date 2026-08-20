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

## 🔴 그리고 구조 매칭은 이미 «금 가 있다» (실측)

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
2  dt_job 도 같은 방식으로 재고, 흡수 전과 같은 수                  ← 두 소스 다 봐야 한다
3  say() 호출에 subject_type · object_type 인자가 «0건»
4  _ambiguous_sentences · _sentence_signature 가 «사라졌다»
5  소스 하나를 폼만으로 새로 만들어 저장 → 거절 0
6  마이그레이션이 옛 config 의 mapping 에 sentence 를 «채운다»
      ← 채울 수 없는 mapping 이 나오면 그게 A 의 실패다. 추측해서 채우지 말 것
```

## 이번에 «하지 않는» 것

| | 무엇 | 왜 |
|---|---|---|
| A | `mappings` 를 목록에서 «별명 키 맵»으로 | 별명이 1순위가 되면 자연스러워 보이지만 별건이다. 매칭을 먼저 바꾸고 모양은 그다음 |
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

