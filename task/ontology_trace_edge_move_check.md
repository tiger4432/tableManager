# 전사를 엣지로 — **「옮길 수 있나」를 소스마다** 실측

> 소유자 판정: 「ㅇㅇ edge로 해」 · 「이미 transfer 엣지 있잖아 «내가 만든거»」
> 총괄 지시 `ontology_application_ruling.md` 23:3x · **읽기 전용, 코드 0줄, 선언 파일 안 건드림**
> 앞 라운드: `task/ontology_trace_fold_check.md`

## 🔴 먼저 — 지시서의 전제 하나를 정정합니다

**「옮길 것은 소스 다섯」이 아닙니다. «선언으로» 옮길 수 있는 것은 «하나»입니다.**

```
dt_log                   4,669   ✅ 진짜 소스 (relation dt_log, 34,939행 살아 있음)
syn_process_ledger      67,240   ⛔ 씨딩 스크립트 — 원자를 «직접 쓴다» (seed_syn_process_ledger.py)
syn_world                  576   ⛔ 씨딩 스크립트
syn_complex_composite      425   ⛔ 씨딩 스크립트 (build_atoms())
syn_composite_chip          54   ⛔ 씨딩 스크립트
```

넷은 **번역기가 아니라 픽스처 생성기**입니다. 선언을 아무리 고쳐도 **안 바뀝니다** —
바꾸려면 그 스크립트를 고쳐서 다시 씨딩해야 합니다. 그건 선언 작업이 아닙니다.

📎 이름 정정: 보드에 `syn_eqp_log` 로 적힌 것의 실제 translator 접두는 `syn_process_ledger` 입니다.

---

## ③ 정본 모양 — 그대로 옮깁니다

```
source     transfer_event        relation  dt_transfer_log   (1,405행 · dt_job_id 10종)
read       unit=row · identity=[dt_cell_key] · order_by=[dt_cell_key]
           occurred_at = event_time (Asia/Seoul)
mapping    "die-transfer"        predicate transfer@1
  subject  kind=entity  entity_type=die@1
           mat_id = core_wafer_id · mat_type = "Wafer"(상수) · x = c_wx · y = c_wy
  target   kind=entity  entity_type=die@1
           mat_id = dt_job_id    · mat_type = "DT"(상수)    · x = b_wx · y = b_wy
```

🔴 **엣지를 만드는 것은 `target.kind = "entity"` 한 줄입니다.** `die@1` 이어서가 아닙니다.
선언된 개체 타입이면 `Wafer@1`·`DTJob@1` 도 똑같이 걸립니다.

⚠️ **한 가지 어긋남을 적습니다.** 커서의 translator_ver 는 `ledger-v2:c1e62b26…` 인데
원자 1,405개는 전부 `ledger-v2:acec87b3…` 입니다 — **지금 선언으로 쓴 원자는 0개**입니다.
모양은 일치합니다(die@1, 4키 동일). 해시만 다릅니다. 선언이 그 뒤에 편집됐다는 뜻입니다.

---

## ① 다섯이 «목적지의 신원»을 들고 있나

`entity_ref` 는 「어느 개체로 갔나」를 알아야 합니다. 선언된 개체는 넷뿐입니다:
`DTJob@1{dt_job}` · `Lot@1{lot}` · `Wafer@1{wafer}` · `die@1{mat_id,x,y,mat_type}`

```
소스                   목적지        to.keys                              원자수   판정
──────────────────────────────────────────────────────────────────────────────────────
syn_process_ledger    package_gate  base_wafer                          64,375   신원 ✅
dt_log                dt_job        dt_job                               4,640   신원 ✅
syn_process_ledger    dt_slot       dt_lot, dt_slot                      2,865   신원 ⛔
syn_world             dt_slot       dt_lot, dt_slot                        576   신원 ⛔
syn_complex_composite dt_slot       dt_lot, dt_slot                        275   신원 ⛔ (단서 있음)
syn_complex_composite bond_layer    base_wafer_id, bond_wafer,             150   신원 ⚠️
                                    bonding_leg, final_chip_id, layer
syn_composite_chip    dt_slot       dt_lot, dt_slot                         30   신원 ⛔
syn_composite_chip    bond_layer    final_chip_id, layer                    24   신원 ⛔
dt_log                dt_slot       dt_lot, dt_slot                         29   신원 ⛔
──────────────────────────────────────────────────────────────────────────────────────
                                                              합계       72,964
```

**「신원이 있다」를 이름 대조가 아니라 «원장 조회»로 확인했습니다:**

```
dt_job     값 347종 중 «등록된 DTJob»  347   (100%)   ✅
base_wafer 값 2,575종 중 «등록된 Wafer» 2,575 (100%)   ✅
bond_wafer 값 6종 중 «등록된 Wafer»       6   (100%)   ✅
dt_lot     값 218종 중 «등록된 Lot»        0   (  0%)   ⛔  ← 목적지가 원장에 «없다»
```

**신원 있음 69,015 / 72,964 = 94.6%.**
**그런데 그중 «선언으로 옮길 수 있는» 것은 dt_log 의 4,640 뿐입니다 — 6.4%.**

---

## ② 🔴 못 옮기는 것 — 이름을 댑니다. 사유가 «셋»입니다

### 사유 A — 목적지 개체가 원장에 «존재하지 않는다» (dt_slot, 3,775건)

`{dt_lot, dt_slot}` 은 선언된 개체 타입이 아니고, `dt_lot` 값 218종 중 등록된 Lot 이
**0개**입니다. `die@1` 로 찍으려면 x·y 가 필요한데 3,775 중 좌표가 있는 것은 **305건**뿐입니다
(나머지 3,470 은 `to.position` 이 아예 `null`).

📎 단서 하나: `syn_complex_composite` 의 275건은 `to.output.job` 을 **275/275 가지고 있습니다**
→ DTJob 으로 찍을 후보입니다. 다른 소스에는 그 필드가 **0건**입니다.

### 사유 B — 접으면 «leg 를 잃는다» (bond_layer, 174건)

`bond_wafer` 는 등록된 Wafer 라 `Wafer@1` 로는 찍힙니다. **그런데 `bonding_leg` 가 사라집니다.**
그게 지금 트렌드 표의 grain 입니다. `WaferLeg` 는 원장에 42원자가 있는데
**`entities` 에 선언돼 있지 않습니다.** 선언하지 않고 접으면 추적이 한 단 거칠어집니다.

### 사유 C — 그 소스가 «번역되는 소스가 아니다» (68,324건 · 전체의 93.6%)

신원이 완벽한 `syn_process_ledger` 의 64,375건이 여기 걸립니다.
**목적지 신원은 있는데 번역 경로가 없습니다** — 원자를 직접 쓰는 스크립트입니다.

🔴 **이게 셋 중 제일 큽니다. 그리고 「선언을 고친다」로는 안 움직입니다.**

---

## ④ 규모 — 두 가지가 섞여 있어 나눠 답합니다

### (가) 선언 쪽 — 작습니다

```
할 일    dt_log 위에 unit=row 전사 매핑 «하나»
바인딩   subject die@1 {mat_id=core_wafer, mat_type="Wafer", x=core_x, y=core_y}
         target  die@1 {mat_id=dt_job,     mat_type="DT",    x=dt_x,   y=dt_y}
         identity dt_cell_key · occurred_at event_time
```

**컬럼 실측 (dt_log 34,939행):**
```
dt_job 100% · dt_x 100% · dt_y 100% · core_x 100% · core_y 100% · dt_cell_key 100%
core_wafer 81%  (28,208행)          ← «여기가 상한»
event_time 99%
🔴 정본이 쓰는 이름들은 전부 0행:  core_wafer_id 0 · dt_job_id 0 · c_wx 0 · c_wy 0 · b_wx 0 · b_wy 0
```
⚠️ **정본 선언을 «복사»하면 0행이 나옵니다.** 같은 뜻의 컬럼이 **다른 이름**으로 채워져 있습니다.
`dt_transfer_log`(1,405행)와 `dt_log`(34,939행)는 **다른 표**이고 컬럼 이름만 겹칩니다.

⚠️ 그리고 이건 «옮기기»가 아니라 **«세분화»**입니다 — 지금 dt_log 는 job 단위로 묶어
4,640원자를 내는데, row 단위 전사는 **최대 28,208원자**가 됩니다. 6배입니다.

### (나) 픽스처 쪽 — 선언 작업이 아닙니다

68,324건은 씨딩 스크립트 넷을 고쳐 다시 돌려야 합니다. 스크립트에 이미 DELETE+재작성 경로가
있습니다(`seed_syn_*.py`). **제 레인도 구현자의 선언 레인도 아닙니다.**

### 시간 — 커서에서 잰 값

```
dt_log                 5,415원자 / 19초   ≈ 285 원자/초
syn_complex_composite  1,738원자 / 16초   ≈ 109 원자/초
-> 72,964 전부 다시 흘리면 대략 «4~11분» (쓰기만. 검증·재채점 별도)
```
⚠️ `syn_process_ledger` 는 86,465원자에 3시간 27분으로 찍혀 있는데 중간에 서 있었던 것으로 보여
**속도 추정에서 뺐습니다.**

---

## ⑦ 못 잰 것 — 먼저 적습니다

```
1  운영 환경             여기 72,964 중 «68,324가 픽스처»다. 운영에선 이 비율이 다르다.
                         운영의 그 자리는 진짜 소스일 것이고, 그러면 사유 C 가 사라진다
2  세분화 후의 원자 수     28,208 은 core_wafer 가 있는 «행 수»다. 중복 제거 뒤 값은 안 쟀다
3  dt_slot 275건의 job     to.output.job 이 «등록된 DTJob 인지»는 안 대조했다
4  bond_layer 를 leg 로     WaferLeg 를 선언하면 174건이 살아나는지 — 선언을 못 고치므로 못 쟀다
```

---

## 정리

**소유자 말씀이 맞습니다 — 엣지는 «이미 있습니다».** 새로 만들 개념이 없습니다.
그런데 **그 위로 옮기는 일의 94%는 선언 작업이 아니라 픽스처 작업**이고,
선언으로 되는 6%(dt_log 4,640)도 **정본을 복사하면 0행이 나옵니다** — 같은 뜻의 컬럼이
다른 이름으로 채워져 있어서, 바인딩을 «그 표에 맞춰» 다시 써야 합니다.

가장 큰 R&D 이득(「이 다이가 어디서 왔나」)은 **dt_log 한 소스만으로도** 열립니다 —
1,405 짜리 섬이 **28,208 로 커집니다.** 나머지는 픽스처를 다시 만드는 별개의 일입니다.
