# `packs` · `claims` 절을 «통째로» 지운다 (소유자 판정 2026-08-21 14:3x)

> 소유자가 층을 하나씩 밀어붙여 도달한 결론이다. 총괄이 매 단계 실측으로 검증했다.
>
> 1. 「packs 가 아직도 있는데 claims 로 바꾸기로 하지 않음?」 → 「그냥 namespace 로 냅둔 건가」
> 2. 「굳이 claims 도 불필요하지 않나 … **실질적 클레임은 vocab 만 남잖아**」
> 3. 「애초에 리니지 정의를 굳이 child derived from parent 이렇게 지어놔서 그렇지
>    **그냥 맵퍼가 subject derived from object 이거랑 동치**잖아」
> 4. 「**packs 도 아예 삭제 가능하네. claims 도 필요없고. 그냥 맵퍼가 say 한 문장 id 에
>    vocab 만 달아주면 되는 거 아님?**」 → 총괄 실측 보고 → **「ㅇㅇ 저렇게 진행해」**

---

## 🔴 도착지

```
bind.mappings.<sentence> = { predicate: "<vocab id>", bind: { role: … } }
```
**`packs` 절이 사라진다.** 절이 5 → 4 (라이브는 4 → 3).
매퍼가 말한 문장 이름에 **술어를 직접 달고**, 역할 재료는 `bind` 가 정한다.

---

## 재 놓은 사실 — 여기서 시작한다 (다시 재지 말 것)

### ① 같은 술어가 서로 다른 역할 집합을 요구하는가 → **0건**
```
derived_from@1  쓰는 곳 1
has_netdie@1    쓰는 곳 1
has_wafer@1     쓰는 곳 1
register@1      쓰는 곳 2   ← 역할 집합 «동일»
slot_map@1      쓰는 곳 1
갈리는 술어 수: 0
```
**갈렸다면 이 라운드는 불가능하다.** 술어만으로 roles 를 못 정하니까.

### ② vocabulary 가 claim 의 `roles` 를 «전부» 유도한다
```
술어             vocabulary 선언                        claim 의 roles
has_netdie@1     object=value                          count · subject · occurred_at
register@1       object=none                           subject · occurred_at
has_wafer@1      object=entity_ref · qual.req=[slot]    subject · target · slot · occurred_at
derived_from@1   object=entity_ref                     parent · child · occurred_at
slot_map@1       object=entity_ref
                 qual.req=[from,to,wafer]              subject·target·from·to·wafer·occurred_at
```
**qualifier 이름이 한 글자도 안 틀린다.** claim 이 그걸 한 번 더 적고 있었다.
```
subject      항상. vocabulary.subjects 가 «종류»를 정한다
occurred_at  항상
target       object.kind != none 이면 있다
qualifier들  object.qualifiers 가 이름까지 선언한다
```

### ③ `emit` 은 하나 빼고 전부 기계적이다
```
5개    emit.subject = $subject                기계적
1개    lineage: emit.subject = $child          🔴 유도 «불가»
```
**그리고 그건 역할 이름 탓이다.** 매퍼는 이미 이렇게 부른다:
```python
sentences.say(self.DESCENT, child, all_refs, obj=parent)
#                           ↑ 주어 자리        ↑ 목적어 자리
```
**`parent`/`child` 를 `subject`/`target` 으로 개명하면 `emit` 은 여섯 다 유도된다.**
`derived_from` 이라는 술어 이름이 이미 「주어가 목적어에서 나왔다」를 말한다.

### ④ `register` 두 문장도 claim 이 아니라 `bind` 가 가른다
```
first_sight_holder   use=…/register   subject entity Lot@1    keys{lot: lot}
first_sight_item     use=…/register   subject entity Wafer@1  keys{wafer: wafers}
```
**같은 claim 이다.** 가르는 것은 `entity_type` 이고 그건 `bind` 에 있다.
vocabulary 는 `register@1` 의 subjects 로 `[Lot@1, Wafer@1, DTJob@1]` 을 이미 허락한다.
**claim 의 기여가 0이다.**

---

## 바뀌는 층 · 그대로인 것

```
바뀐다   설정 모양      packs 절 삭제 · mappings.<sentence> 에 predicate 직접
         컴파일러       pack/claim 해소 → 술어 해소
         마이그레이션    스크립트 «필요». 기존 설정을 새 모양으로
         지문           바뀐다 → 커서 재스탬프 «필요» (도구 있음)

그대로   vocabulary 절 · entities 절 · sources 의 read·prepare·map
         매퍼 코드 (문장 이름은 안 바뀐다)
         이미 쌓인 원자 — 과거는 과거 지문으로 남는다 (append 원칙)
```

⚠️ **`lineage` 역할 개명(`parent`/`child` → `subject`/`target`)은 이 라운드 «안»이다.**
그게 있어야 `emit` 이 사라진다. 매퍼의 `say` 호출은 위치 인자라 **안 바뀐다.**

---

## ⛔ 멈춤 조건 — 셋 중 «하나라도» 어긋나면 멈추고 보고

총괄이 «아직 못 잰» 것들이다. 이 중 하나라도 깨지면 도착지가 성립하지 않는다.

```
1  has_netdie 의 `count` 역할
      vocabulary 는 「object 는 value」까지만 말한다.
      «어느 역할이 그 값인가»를 정할 규약이 필요하다.
      「주어도 시각도 qualifier 도 아닌 역할이 정확히 하나」로 유도되는지 잴 것.
      둘 이상이면 → 멈춤

2  `target` 이 «선택»인 경우
      object.kind != none 인데 target 이 optional 인 claim 이 있으면
      「object 가 있으면 target 이 required」 규칙이 깨진다 → 멈춤

3  pack 을 «단위»로 읽는 코드
      roleframe.py:521 · :979 가 pack 을 id 로 찾는다.
      술어 해소로 «치환»되면 진행. 다른 일을 하고 있으면 → 멈춤
```

나머지는 진행하면서 재고, 숫자는 나오는 대로 한 줄씩. **「못 쟀다」도 답이다.**

---

## 🔴 받아들이는 시험

```
1  마이그레이션이 «멱등»하다        두 번 돌려 「unchanged」
2  이관 전/후 원자가 «같다»          같은 행 · 같은 등록 스냅샷으로 전후를 각각 재서
                                    원자 수 · incomplete 0 · DB 쓰기 0 이 «같을 것»
                                    ⚠️ 고정 숫자를 쫓지 말 것 — 전후 «불변»을 본다
3  여섯 문장이 여섯 술어로 여전히 간다
       first_sight_holder→register@1 · first_sight_item→register@1
       in_slot→has_wafer@1 · descent→derived_from@1
       split_slot_carry→slot_map@1 · merge_slot_join→slot_map@1
4  화면: 라이브 설정 거절 0 · missing 0 · 「N layers · complete」
       ⚠️ 층 수가 «줄어든다». 척추가 그걸 정직하게 말하는지 볼 것
5  폼만으로 새 소스 «거절 0 · active» 여전히 도달       ← 오늘의 기준선
6  커서 판별식 셋 여전히 초록                            test_ledger_setup_registry.py
```

---

## 이번에 «하지 않는» 것

| | 무엇 | 왜 |
|---|---|---|
| A | 이미 쌓인 원자 손대기 | 과거는 과거. 원장은 append 다 |
| B | vocabulary 절 손질 | 이 라운드가 «거기에 기댄다». 흔들지 않는다 |
| C | 매퍼 문장 이름 변경 | 문장 이름은 그대로. 바뀌는 건 그 밑이다 |
| D | 문자열 시각 | 다음이다. 다만 둘 다 지문을 움직이므로 «붙여서» 하면 재스탬프가 한 번으로 끝난다 — 순서는 총괄이 정한다 |

---

## 절차

```
마이그레이션    scripts/ 에 «멱등» 스크립트. --check 를 먼저 붙일 것
                (migrate_ledger_config_to_v4.py 가 본이다 — 같은 모양으로)
setup_version   올릴지는 «측정 후» 판단하고 보고할 것
파이썬 고치면    재시작은 총괄이 한다. 포트로 판정
커밋            경로 명시. `-a`/`-A` 금지
백틱            커밋 메시지는 `-F` 파일로
조용해지면      30분 넘을 것 같으면 «한 줄» 남길 것
```
