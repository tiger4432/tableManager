# 매퍼가 config의 «이름»을 모르게 됐다 — 배선 리터럴 17 → 0

**날짜:** 2026-08-18 23:12~23:30 · **커밋:** `509cc2a` `350a3c8` `77cf39a`
**레인:** 서버(원장 단순화 2라운드 · lot_event 매퍼 개주) · **측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경 — 완성 조건이 「코드 0줄」이다

소유자 정의: **다른 스키마의 운영 환경에서 코드 한 줄도 안 고치고 선언 교체만으로 발화한다.**
`lot_event` 매퍼는 그 조건을 못 지키고 있었다 — **선언을 두 번 들고 있었기 때문이다.**

착수 «전» 실측(`6892456`, 481줄 기준, AST로 문자열 상수를 세어 라이브 config의 이름 집합과
대조):

| 종류 | 개수 |
|---|---|
| `mapping_id` | **6** |
| `claim_ref` | 0 |
| predicate | **5** |
| entity type | **11** |
| qualifier | **7** (업무 어휘 — 남긴다) |
| 합계 | **29** |

세는 도구(`4360095`)가 `WIRING LITERALS`로 묶는 것은 `mapping_id + claim_ref + entity type`
= **17**이다. predicate 5는 따로 찍는다. 그리고 **어느 것도 자기가 베끼는 config에 대조되고
있지 않았다** — 철자가 다른 배포는 **깨끗하게 컴파일되고 런타임에 죽었다.**

## `509cc2a` — 선택을 이름이 아니라 «모양»으로

```python
@dataclass(frozen=True)
class SentenceShape:
    """What a mapper needs a sentence to be ABLE TO SAY -- never what it is called.
    ...
    It does NOT know that this deployment's declaration spells the predicate `has_wafer@1`,
    names the mapping `positional_row`, calls the two entity types `Lot@1`/`Wafer@1`, or
    files the values under role ids `subject`/`target`.
    """
```

매퍼는 **그 문장이 무엇을 나를 수 있어야 하는가**만 말한다 — 목적어가 필요한가, 어떤
qualifier를 이름하는가. `ProfileSentences`가 그 모양을 실현하는 프로필 매핑을 찾는다.

두 결과가 따라온다.

- 배포가 predicate·entity type·mapping을 **아무렇게나 개명해도 매퍼는 그대로**다.
- 엔터티 타입 철자는 **주장하는 대신 배운다** — 「이 프로필은 슬롯에 물건을 담는 것을 뭐라고
  부르나」를 물어보지, `"Lot"`이라고 쓰고 맞기를 바라지 않는다.

그리고 **버전은 통째로 비교한다.** 은퇴한 매퍼는 `_base()` 철자를 비교해서 `Wafer@1`과
`Wafer@2`가 서로 매치됐다 — **식별키가 다른 두 엔터티 버전이 조용히 호환**됐다는 뜻이다.

배선(매핑 조회·역할 조립·첫 관측 중복 제거)이 매퍼에서 엔진으로 옮겨 갔다. 그 배선을 매퍼가
소유하면 **매퍼는 필연적으로 그것을 조종하려고 선언 이름을 댄다** — 그것이 `mapping_id`와
철자들이 도메인 해석만 하면 되는 파일에 Python 리터럴로 앉아 있던 경위다.

**측정된 반증:** 모든 predicate와 두 엔터티 타입, 여섯 중 넷의 `mapping_id`를 개명한 config에
대고 새 매퍼는 같은 문장을 냈고, 옛 매퍼는 네 케이스 전부를 `invalid_lot_event_contract`로
거절했다. **그것이 새 테스트다** — 「돌더라」가 아니라 「옛것은 죽고 새것은 산다」를 같은
입력에서 함께 재는 판별 케이스다.

## 남은 둘, 그리고 방향이 거꾸로였다는 판정

`509cc2a` 뒤 `mapping_id` 2개가 남았다. split의 슬롯 유지와 merge의 슬롯 합류는 **같은 문장**
이다 — 같은 predicate, 같은 주어/목적어 타입, 같은 세 qualifier. **다른 것은 그것을 계산한
규칙뿐**이고 그건 각 원자의 `derivation`이 기록한다. 선언에 그 둘을 가를 것이 없었다.

`77cf39a`의 커밋 본문이 그 자리를 이렇게 판정했다.

> The mapper's last two declaration literals were `mapping_id` values it reached into config
> to steer resolution with. That direction is backwards: a rename in `ledger_config.json`
> broke the mapper at RUN TIME, and nothing caught it at compile time.

**뒤집었다.** 프로필 매핑이 **선택적** `sentence` 필드를 얻어, 자기가 실현하는 **매퍼 어휘의
낱말**을 말한다. 선택인 이유는 모양이 이미 유일한 매핑까지 자기를 다시 적게 만들면 안 되기
때문이고, 실제로 lot_event 프로필은 **여섯 매핑 중 둘에만** 선언한다.

## 🔴 동점은 이제 «컴파일 타임 거절»이다

> An unordered match elects a representative: correct until a third mapping joins the class,
> at which point the representative changes and everything that already worked breaks with
> nothing naming the cause.

그래서 동점이면 런타임에 첫 매치를 고르는 대신 `ambiguous_sentence`로, **그것을 선언하지
않은 각 매핑의 경로에서** 거절한다.

이 검사가 성립하려면 **컴파일 타임 서명과 런타임 해석기의 판별자가 똑같아야 한다.**
코드가 그 요구를 자기 자리에 적었다.

```python
    """This MUST stay the expression `ledger.roleframe.ProfileSentences._resolve` matches
    on, or the two disagree and the disagreement is invisible: a signature computed slightly
    differently here would either refuse a config that runs fine, or -- far worse -- let an
    ambiguous one compile and be resolved arbitrarily at run time ..."""
```

**그리고 설계를 바꾼 실측이 있었다.** 첫 서명은 `(has_object, qualifiers, subject_type)`이었고,
그것이 **출하된 transfer 샘플을 거절했다** — `job_contains_die`와 `job_occupies_slot`은
**목적어 엔터티 타입**(`DTDie@1` 대 `LotSlot@1`)으로 갈리며 완벽히 구별 가능하다.
해석기의 판별자보다 거친 서명은 **잘 도는 config에 늑대가 나타났다고 외친다.** 그래서 목적어
타입이 서명과 `_resolve` **양쪽에** 들어갔고, 매퍼는 이미 배운 목적어 타입을 함께 넘긴다.

## 매퍼에 남은 두 낱말은 이제 «매퍼의 말»이다

```python
    # ... the mapper names the two in its OWN vocabulary and the Profile says which mapping
    # realizes each.  These are this mapper's words, not the config's: rename anything in
    # `ledger_config.json` and they still hold.
    SPLIT_SLOT_CARRY = "split_slot_carry"
    MERGE_SLOT_JOIN = "merge_slot_join"
```

**이름이 남은 것과 config를 아는 것은 다르다.** 센서스가 세는 것은 「라이브 config의 이름
집합과 일치하는 문자열」이므로, 매퍼 자신의 어휘는 0으로 센다 — 그게 정의상 맞다.

## 아키텍처 영향

명명 방향이 **config → 매퍼**가 됐다. `ledger_config.json`의 `mapping_id`를 개명해도 이 파일에
닿지 않는다. 배선 리터럴 **17 → 0**, predicate **5 → 0**, entity type **11 → 0**;
qualifier 이름 **7 (11 자리)**은 업무 어휘라 남는다.

## 검증

- 기록자가 직접 확인한 것: 착수 전 표(6/0/5/11/7)와 센서스 도구의 `wiring` 정의
  (`mapping_id + claim_ref + entity type`)를 대조해 **17**이 어떻게 나오는지 셌다. 인용한
  docstring·주석·커밋 본문 문장이 각 diff에 실재한다는 것도 확인했다.
- ⚠️ 「센서스 6→2→0」과 「원자 CASE DIFF 0」은 **커밋의 측정**이다. 기록자는 센서스를
  재실행하지 않았다.
- ⚠️ 두 커밋의 센서스 수는 **자기가 판정하려는 변경이 이미 들어간 뒤**의 파일을 잰 것이다.
  그것이 이 도구의 용법(전후 같은 방식으로 재기)이므로 오염은 아니지만, **전 수치는
  `6892456`의 표에서, 후 수치는 커밋 본문에서** 온 서로 다른 실행이다.

## 그때 남아 있던 것

- `350a3c8`이 테스트 더블을 **유일한 호출자인 테스트 파일로** 옮겼다. 매퍼 파일에 남아
  있던 33줄이고, 운영 파일에 테스트 전용 코드가 사는 것을 끝냈다.
- 이 시점의 `SPLIT_SLOT_CARRY`/`MERGE_SLOT_JOIN`은 **문자열 상수**다. 한 시간 뒤 `71865b7`이
  이것을 `SentenceShape` 자신이 이름을 나르는 형태로 바꾼다 — 다른 커밋의 이야기다.
- 매퍼 «구현»이 요구하는 고정 철자(낱말 base 이름·qualifier 집합)를 강제하는 것은
  `setup_bundle.py`가 아니라 `server/mappers/` 쪽이다. 이 라운드는 그 경계를 건드리지 않았다.
