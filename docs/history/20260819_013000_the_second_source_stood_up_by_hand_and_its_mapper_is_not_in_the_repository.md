# 두 번째 소스가 손으로 세워졌고, 그 매퍼는 저장소에 없다

**날짜:** 2026-08-19 00:37~01:25 · **커밋:** `0cc8ea9` `71865b7` `587c291` `778b3b2`
**레인:** 서버(원장 · 두 번째 소스) · **측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경

원장 v2는 그때까지 **소스 하나**로만 돌았다. 「소스를 하나 더 붙일 수 있는가」는 설계
주장이었지 관측이 아니었다. `dt_job` — `dt_log`를 잡 단위로 묶어 **잡이 존재한다**와
**다이를 몇 개 날랐다** 두 가지를 말하는 소스 — 가 그것을 관측으로 바꿨다.

**분자 14, 원자 28, 커서 전진, 거절 0.**

## 문장이 «값»을 목적어로 말할 수 있게 됐다

`0cc8ea9`. 「다이 개수」는 엔터티가 아니라 수다. 그런데 그때까지 목적어는 **무조건 엔터티
참조로 조립**됐다.

```python
    """Shape the object a mapper handed over the way the Claim DECLARES it.
    ...
    * `value` and `event_ref` -- the object IS the value. ... Assembling an Entity reference
      here was the reason a Claim declaring `"object": {"kind": "value", ...}` could not be
      said by a mapper at all;
    * `none` -- a Claim with no object has no object Role, so this method is never reached.
    ...
    The refusal is the point: a kind added to the Vocabulary and not answered here must fail
    by name rather than silently take the entity path and mint a wrong atom.
    """
```

**어휘가 허용하는 목적어 종류 넷을 전부 이름으로 답한다.** 새 종류가 어휘에 추가되고 여기에
답이 없으면 **엔터티 경로로 조용히 흘러 틀린 원자를 찍는 대신** 이름을 대고 죽는다.

## 모양이 자기 이름을 나른다 — 세 번 적던 낱말이 한 번이 됐다

`71865b7`. 한 시간 전 `77cf39a`가 남긴 두 문자열 상수를, 파이썬이 이미 기록하고 있는 것에서
가져오게 했다.

```python
    def __set_name__(self, owner: type, name: str) -> None:
        """A shape bound to a class attribute already HAS a name: the attribute's.

        Two shape-identical sentences used to be told apart by a string the mapper declared
        twice -- once as a constant, once at the call site -- next to the same word a third
        time in the Profile. Two of those three are the mapper's own vocabulary, and Python
        already records the one that matters, so this takes it rather than asking again.
        """
```

**선언이 말하는 것은 바뀌지 않는다** — 자동 이름은 여전히 프로필의 `sentence`에 대조되고,
아무 문장도 이름하지 않는 config는 여전히 동점을 못 푼다.

그리고 **한 인스턴스가 두 속성 이름에 묶이면 클래스 생성 시점에 거절**한다.

```
one SentenceShape is bound to both {self.sentence!r} and {auto!r}; a shape carries the name
of the sentence it says, so two sentences need two shapes
```

이름은 둘 중 하나일 수밖에 없고, 그러면 **다른 호출 지점이 자기가 뜻하지 않은 문장을 말한다 —
조용히, 그리고 둘이 같은 답으로 풀리는 동안은 정확하게.** 하나의 모양을 두 문장이 공유하던
것이 바로 이 변경 직전의 상태였다.

## 🔴 세계 시각이 없다고 «선언»한 첫 소스다

`dt_log`의 `event_time`은 문자열이고, **세 가지 서로 다른 형식**에 **널 522건**, 시간대 기준이
섞여 있다. 그것을 가리켰다면 **세계 시각이 아닌 것이 세계 시각으로 읽히는 원자**가 나왔을
것이다. 그래서 `occurred_at: {basis: "ingested"}`로 선언했고, 원자가
`occurred_at_basis = ingested`를 **스스로 싣는다.**

## 두 시간의 값 — 그리고 그것을 랭킹으로 만든 것

소유자가 손으로 작성하는 동안 매 저장을 실시간 검증했다. **저장 약 20회, 거절 약 40건,
사람이 판단해야 했던 것은 다섯 남짓.** 나머지는 다른 데 이미 적힌 것을 옮겨 적기, 필드 이름
외우기, 물리 표를 안 봐서 생긴 것이었다.

`task/ontology_setup_friction_observed.md`가 그것을 **수단의 등급**으로 정리했다.

> ① 구조적 제거 > ② 유도 > ③ 제약 입력 > ④ 진단 개선

**④는 최후 수단이다.** 그날 밤 착지한 거절문 개선은 왕복을 줄였지만, **애초에 물어보지
않았으면 왕복이 없었다.** 자기 성과를 가장 약한 등급으로 스스로 매긴 것이 이 문서의 값어치다.

### 관찰이 즉시 만든 결함 하나

`basis`를 쓰는 소스에서 매퍼가 **시각 컬럼 이름을 되묻게** 됐다.

```python
occurred_column = context.source_plan.driver.occurred_at.column      # ← 되묻는 중
```

소유자 판정: **「`basis`를 쓴다고 시각이 달라지면 안 되지, 다 `occurred_at`이어야지」.**
문서가 처방까지 적었다 — `source_preparation`이 `__source_row_ref`를 얹는 그 자리에서
`__occurred_at`도 얹는다(값은 이미 그 함수 안에 있고 지금은 검증에만 쓰고 버린다).
**부수 효과가 진짜 이득이다: 매퍼가 `context.source_plan`을 읽을 이유가 완전히 사라진다** —
남은 유일한 용처가 이것이다.

## 🔴 그리고 이 소스의 매퍼는 저장소에 없다

`587c291`이 커밋한 것은 `ledger_config.json`과 관찰 문서 둘뿐이다. 그 config가 이름하는
`implementation_id: "dt-job-role"`을 제공하는 파일은 이 박스의
`server/mappers/ledger_v2_dt_job_mapper.py`(65줄, `class DtJobRoleMapper`)이고,
**`.gitignore:56`이 `server/mappers/*`를 통째로 제외한다.** 추적되는 매퍼는 강제로 추가된
`ledger_v2_lot_event_role_mapper.py` 하나뿐이다.

부지별 매퍼를 무시하는 것은 그 자체로 정책이지만, **그래서 「end to end로 돈다」는 그 파일이
있는 박스에서만 참이다.** 신뢰 목록이 코드에서 유도되는 구조(`e1a7a6f`)와 맞물려, 이 소스가
어느 박스에서 돌지는 **저장소가 아니라 파일 시스템이 정한다.**

## 아키텍처 영향

한 config에 소스 둘이 공존한다. 값 목적어와 `basis` 선언은 **원리적으로만 있던 두 경로**였고
이 밤에 처음 실제로 태워졌다.

## 검증

- 기록자가 직접 확인한 것: `587c291`의 config에 `sources`가 `dt_job`·`lot_event` 둘이라는 것,
  `.gitignore`가 `server/mappers/*`를 제외하며 `git ls-files server/mappers/`에
  `ledger_v2_dt_job_mapper.py`가 없다는 것, 그 파일이 디스크에 있고 `implementation_id`가
  `dt-job-role`이라는 것. 인용한 docstring·판정문이 각 diff에 실재한다는 것.
- ⚠️ 분자 14 / 원자 28 / 저장 20회 / 거절 40건은 **커밋과 관찰 문서의 측정**이다. 기록자는
  백필을 돌리지 않았다.

## 그때 남아 있던 것

- **매퍼가 `context.source_plan`을 되묻는 상태 그대로다.** 처방은 문서에 있고 코드에는 없다.
  이 시점에 `server/ledger/source_preparation.py`와
  `server/mappers/ledger_v2_lot_event_role_mapper.py`는 다른 레인의 작업 트리 변경을 안고 있다.
- 컬럼 이름을 타이핑하는 자리가 소스 하나에 **최소 12곳**이라는 실측이 관찰 문서에 있다.
  그중 일부는 같은 밤 컬럼 픽커(`0f99b2d`)가 다루고, 나머지는 다루지 않는다.
- `778b3b2`가 그 밤의 착지와 대가를 보드에 옮겼다.
