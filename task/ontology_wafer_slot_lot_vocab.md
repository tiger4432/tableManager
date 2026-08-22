# wafer · slot · lot trace — 어휘 세트 제안과 지금 셋업

> 2026-08-22 저녁. 라이브 원장·라이브 설정·`dt_log` 실물을 직접 재서 씀.
> 라이브 설정은 **읽기만** 했다 (mtime 21:45:49, 소유자 것).

---

# 0. 한 줄

**어휘는 하나도 안 늘려도 된다.** 지금 선언된 6개가 `dt_log` 의 문장을 전부 덮는다.
**막힌 것은 어휘가 아니라 «dt 쪽 신원»이다** — 그 컬럼(`dt_id`)이 비어 있다.

---

# 1. 실측 — 지금 원장이 말하는 것

```
원자 총 222,886    그중 새 셋업(ledger-v2:) 2,115 · 나머지 220,771 은 v1/합성
```

새 셋업이 만든 것 (`source_translator_ver` 가 `ledger-v2:` 인 것만):

```
Lot   register       first_sight_holder     25     이 랏이 있다
Lot   has_wafer      in_slot               907     Lot -> Wafer + {slot}
Lot   slot_map       merge_slot_join       113     Lot -> Lot + {from,to,wafer}
                     split_slot_carry      113
Lot   derived_from   descent                40     Lot -> Lot
Wafer register       first_sight_item      125     이 웨이퍼가 있다
DTJob has_netdie     job_die_count         396
DTJob register       job_register          396
```

선언된 어휘 6 · 개체 4:

```
entities   Lot@1{lot} · Wafer@1{wafer} · DTJob@1{dt_job} · die@1{substrate_id,x,y}
vocab      register@1      Lot/Wafer/DTJob  -> none
           has_wafer@1     Lot -> Wafer     + slot          (required)
           slot_map@1      Lot -> Lot       + from,to,wafer (required)
           derived_from@1  Lot -> Lot
           has_netdie@1    DTJob -> value
           transfer@1      die -> die
```

---

# 2. 🔴 자리는 신원이 아니다 — 소유자 상설 규칙이 이 소스에서 «측정으로» 확인된다

소유자 상설: **「랏이란 단위를 잊으라」 — 단위는 웨이퍼, 랏은 값.**
`dt_log` 34,939행에서 그게 참인지 직접 쟀다.

## 먼저 틀릴 뻔한 것 — 철자가 「이동」처럼 보인다

원본 그대로 세면 **웨이퍼 136장이 자리를 2~5곳 옮긴 것처럼** 보인다. 표본을 꺼내니:

```
WF.010101 -> CL-2601-001/01 · CL-2601-001/1 · CL_2601_001/01 · CL_2601_001/1 · None
```

**이동이 아니라 `-`/`_` 와 `01`/`1` 이다.** 규모:

```
core_lot   714 -> 699 (변형 15)      core_slot  61 -> 52 (변형 9)
dt_lot     696 -> 696 «드리프트 0»    dt_slot    50 -> 50 «드리프트 0»
```

**core 쪽만 흔들리고 dt 쪽은 깨끗하다.** 그리고 `(core_lot,core_slot)` 이 `(None,None)` 인
자리 하나에 **웨이퍼 117종**이 몰려 있다 — 이건 자리가 아니라 결측이다.

## 정규화하고 결측을 뺀 «뒤»에도 자리는 신원이 아니다

```
한 웨이퍼가 붙은 자리 수      1곳 932장 · «2곳 20장»
한 자리가 가진 웨이퍼 종수    1종 968곳 · «2종 2곳»
```

**그러므로 키는 `wafer`, 자리(`lot`,`slot`)는 한정어다.**
지금 `has_wafer@1` 이 정확히 그 모양이다 — 바꿀 것 없다.

---

# 3. 어휘 세트 제안 — **새 술어 0개**

`dt_log` 가 말하는 문장은 넷이고, 넷 다 기존 어휘로 적힌다.

```
문장                                   어휘                      상태
─────────────────────────────────────────────────────────────────────
core 웨이퍼가 이 랏 이 슬롯에 있었다     has_wafer  Lot->Wafer+{slot}   그대로 쓴다
core 웨이퍼·dt 스트립이 처음 보였다      register                       그대로 쓴다
die 가 core (x,y) 에서 dt 자리로 갔다   transfer   die->die            🔴 §4 참조
이 전사가 어느 잡·장비였나              transfer 의 «한정어»            선언 확장 (새 술어 아님)
```

**전사의 문맥(`dt_job` · `dt_eqp`)은 새 술어가 아니라 `transfer@1` 의 한정어다.**
지금 `required: [] · optional: []` 로 비어 있다. 여기에 이름을 넣는 것이
「기존 키 확장」이고, 그게 최소 수정이다.

⚠️ 시각은 한정어가 아니라 원자의 `occurred_at` 이다 — `read.occurred_at` 이 이미
`{"column":"event_time","timezone":"Asia/Seoul"}` 로 잡혀 있다. **중복 선언하지 말 것.**

---

# 4. 🔴 진짜 막힌 자리 — dt 쪽에 «신원»이 없다

`transfer@1` 은 `die -> die` 이고 `die@1` 의 키는 `{substrate_id, x, y}` 다.

```
core 쪽    substrate_id = core_wafer   ✅ 있다 (81% 채움 · 953종)
dt 쪽      substrate_id = ???
```

**`dt_id` 컬럼이 있는데 채움이 «0%» 다.** 그래서 dt 쪽엔 자리밖에 없다:

```
(dt_lot, dt_slot)          928종 · 드리프트 0 · 채움 90%
dt_x, dt_y                 FULL
dt_cell_key                34,939종 = 행 수  -> 이건 «행 id» 지 개체가 아니다
```

## 갈래 둘 — 소유자 판정이 필요하다

```
가  자리를 신원으로 쓴다     substrate_id = dt_lot|dt_slot 를 prepare 에서 만든다
    지금 되나              된다. dt 쪽 드리프트 0
    언제 틀리나            자리가 «재사용»되는 날. core 쪽이 이미 그 병을 보여준다
                           (정규화 뒤에도 자리 2곳이 웨이퍼 2종을 갖는다)
    부작용                 원장 안에만 있는 이름이 생긴다 — 밖에서 그 id 를 못 부른다

나  dt_id 를 채운다         소스가 이미 그 칸을 «가지고» 있다. 채우면 core 와 같은 모양
    비용                   원장이 아니라 «인제션» 쪽 일
```

**저는 (나)를 권합니다.** (가)는 지금 데이터에서만 참인 가정 위에 신원을 세우고,
그 가정이 깨지는 날 **이미 쌓인 전사 원자 전부**가 틀린 곳을 가리키게 됩니다.
다만 dt_id 를 채우는 게 이번 범위 밖이면, **(가)로 가되 「자리를 신원으로 썼다」를
설정에 적어 두는 것**이 차선입니다.

---

# 5. `transter_event` 지금 상태와 다음 칸

라이브 설정에 이미 있고, 이렇게 비어 있습니다:

```
relation      dt_log
read          unit "row" · occurred_at {event_time, Asia/Seoul} · order_by [dt_cell_key]
              identity []      <- 비었다
              group_by []      <- 비었다
prepare       direct-join · input_columns [] · output_columns {}
map           input_columns [] · unit {}
bind.mappings {}                <- 비었다 = 화면의 그 빨강
```

`dt_log` 에서 실제로 쓸 수 있는 칸(채움률):

```
FULL   dt_eqp · dt_cell_key · dt_job · product · dt_x · dt_y · core_x · core_y · c_bn
99%    event_time
95%    core_lot · core_slot
90%    dt_lot · dt_slot
81%    core_wafer
75%    dt_index
0%     tape_lot · tape_slot · tx · ty · cx · cy · dt_id · eventtime
       dt_event_id · dt_job_id · b_wx · b_wy · core_wafer_id · c_wx · c_wy
```

🔴 **테이프 좌표계는 «통째로» 비어 있다.** 지금 이 소스로 그릴 수 있는 경로는
**core → dt 두 마디뿐**이고, 테이프는 마디가 아니라 없는 것입니다.

## 채울 순서 (막히면 그 칸에서 멈춥니다)

```
1  identity      core_wafer 를 «반드시» 넣는다. core_lot/core_slot 은 넣지 않는다 (§2)
2  prepare       core_lot·core_slot 정규화 — '_' 를 '-' 로, 슬롯 앞 0 제거
                 §2 의 변형 24개가 여기서 죽는다
3  map           die 좌표: core_x·core_y / dt_x·dt_y
4  bind.mappings 문장 셋 + (dt 신원 판정 뒤) 전사 하나
                 first_sight_core_wafer   register
                 in_core_slot             has_wafer  Lot->Wafer+{slot}
                 die_to_dt                transfer   die->die     <- §4 판정에 걸림
```

**2번을 건너뛰면 같은 웨이퍼가 원장에서 «네 자리»에 앉습니다.** 그건 나중에
정정 원자로는 못 되돌립니다 — `has_wafer` 넷이 전부 「사실」로 쌓입니다.

---

# 6. 판정 요청 — `slot_map` 이 지금 아무것도 말하지 않는다

라이브 원자로 쟀습니다.

```
서로 다른 slot_map 사실 226   -> has_wafer 두 개로 재현되는 것 «226» (100%)
서로 다른 (랏,랏) 짝    40    -> derived_from 이 이미 덮는 것 «40» (100%)
from == to              226/226 (100%)   슬롯 이동이 «한 건도» 없다
한 웨이퍼의 서로 다른 슬롯 수  전부 1 (125/125)
```

그리고 이건 **데이터가 아니라 «선언» 때문입니다** — `slot_map@1` 은 한정어 `wafer` 를
**required** 로 요구합니다. 웨이퍼를 이름 대는 순간, 그 문장은 양쪽 `has_wafer` 가
이미 말한 것 이상을 말할 수 없습니다. **자유도가 0입니다.**

⚠️ **지우자는 제안이 아닙니다.** `ledger_trace._map_slot` 이 이걸 읽습니다(은퇴 대상이지만
아직 돕니다). 그리고 저는 같은 날 「도출되니 지워도 된다」로 축 하나를 죽인 적이 있습니다.
**판정만 요청드립니다** — 슬롯이 «바뀌는» 전사가 실제로 있습니까? 있다면 `wafer` 를
required 에서 빼야 이 술어가 일을 합니다. 없다면 은퇴 라운드 재료입니다.

---

# 7. 남는 구멍 하나 (적어만 둡니다)

`transfer` 는 `die -> die` 인데 **웨이퍼에서 다이로 가는 «엣지»가 없습니다.**
`die@1` 의 `substrate_id` 가 웨이퍼 이름을 «담고» 있을 뿐이라, 관계가 아니라 «키 접두»입니다.
walk 은 키 접두를 못 넘습니다. 「이 웨이퍼의 다이들이 어디로 갔나」를 그래프로 물으려면
그 자리가 필요합니다 — **다만 새 술어가 답인지 조회가 답인지 아직 안 쟀습니다.**

---

# 8. 「본질적인 이벤트면 원장에 채우는 게 맞나」 — 맞습니다, 판별식 하나를 붙여서

소유자 질문 (2026-08-22 밤). 판별식이 실제로 판별하는지 **라이브 원자에 먹여** 봤습니다.

## 판별식 — 「이 원자를 만들 때 «규칙»을 썼나」

```
본 것      행을 그대로 읽었다                 재해석에 «재저장 불필요»
결론       규칙을 적용해서 냈다               규칙이 바뀌면 «조용히 틀린다»
```

**`bind.mappings` 의 이름이 이미 그걸 말합니다** — `in_slot`(읽기) 對
`merge_slot_join`·`split_slot_carry`(규칙).

## 지금 6개를 그 시험에 태운 결과

```
술어                시험                                          판정
────────────────────────────────────────────────────────────────────────
has_wafer          slot 을 말하는 «유일한» 술어. 사실 238          🟢 본 것 — 남긴다
transfer           그 시각에 일어난 이동                            🟢 본 것 (아직 원자 0)
has_netdie         잡의 die 수                                     🟢 본 것
────────────────────────────────────────────────────────────────────────
slot_map           226/226 이 has_wafer 두 개로 재현                🔴 결론
derived_from       40/40 이 slot_map 과 «상호» 재현                 🟡 둘 중 «하나»면 족하다
register           Wafer 125/125 · Lot 25/25 가 다른 원자에 이미 있다 🟡 아래
```

## `register` 는 지우면 안 됩니다 — 지금 «구별할 것이 없을» 뿐입니다

`register` 의 일은 walk 에서 `[root]`(등록됐고 부모가 없다 = 진짜 꼭대기)와
`[dead_end]`(등록도 없고 부모도 없다 = 그냥 못 본 것)를 가르는 것입니다.

지금 데이터엔 **등록 없이 등장하는 개체가 하나도 없어서** 그 구별이 이미 무너져 있습니다.
이건 「필요 없다」가 아니라 **「아직 그럴 일이 없어서 안전해 보인다」**입니다.
소스가 늘면 그날 살아납니다.

## 그래서 셋업할 때의 규칙

```
채운다      소스 행이 «말한» 것.  주어·목적어·한정어·시각을 행에서 그대로 옮긴다
안 채운다   규칙을 돌려서 «낸» 것. 대응·병합·분기·정규화 결과
```

⚠️ **결론을 원자로 쌓아도 «되돌릴 수는» 있습니다** — 실측: v2 원자 2,115개 전부가
`source_raw_ref` 와 `source_event_id` 를 가지고 있고, 원본 행 키가 그 안에 들어 있습니다.
**문제는 되돌릴 수 있느냐가 아니라, 규칙이 바뀐 날 «어느 원자가 낡았는지 아무도 안 알려준다»는
것입니다.** 그래서 결론은 원자가 아니라 읽는 쪽에 두는 편이 쌉니다.

## 그리고 이건 「무엇을 못 쓰게 한다」가 아닙니다

목적어가 **개체 참조**로 남아 있으면 낱말이 바뀌어도 그래프는 안 죽습니다.
실측 — v2 원자의 목적어 종류:

```
entity_ref  1,173   낱말을 다시 읽어도 «걸을 수» 있다
(none)        546   register
value         396   has_netdie — 걸을 수 없다. 값이면 값으로 충분한 것만 value 로
```

**`has_wafer` 를 나중에 다른 뜻으로 읽고 싶어도 재저장이 필요 없는 이유가 이것입니다** —
주어·목적어가 개체로 남아 있어서, 바뀌는 것은 «그 엣지를 뭐라 부르는가»뿐입니다.
