# 설계 — `/trends` 의 grain 을 무엇으로 대체하나

> 총괄 지시 (2026-08-23 19:5x): 「호출자 0 은 «대체가 필요 없다»가 아니라 «계약 파기 값이 0»이다.
> 고정된 것은 이름이 아니라 «행의 grain» 이다」 — 맞습니다. 넷을 냅니다.
> 🔴 읽기 전용 · 코드 0줄. 아래 숫자는 전부 «직접 불러서» 나온 것입니다.

---

# 0. 먼저 — ④ 의 답이 예상 밖입니다. **지금 «잃을 것이 없습니다»**

`/trends` 를 실제로 불렀습니다:

```
'found' 등장       «0»
'scanned_clean'    48
```

**이 원장에서 `/trends` 는 불량을 한 건도 못 셉니다.** 분모(스캔)만 나오고 분자가 0입니다.

## 왜 — grain 이 «이미» 어긋나 있습니다

```
분모 (scans)      inspection_run r JOIN bonding_map b
                  -> (r.base_wafer_id, b.leg)          «테이블 컬럼»
분자 (observed)   predicate='observed' AND subject_type='Wafer'
                             AND object_payload ? 'bonding_leg'
                  -> 실측 «0행»
```

원장이 `bonding_leg` 을 «다른 자리»에 둡니다:

```
subject_type=Wafer      observed 114,492 · payload 에 bonding_leg  «0»
subject_type=WaferLeg   observed      18 · payload 에 bonding_leg   18
```

**SQL 은 「Wafer 주어의 payload」에서 찾고, 원장은 「WaferLeg 주어의 «주어 키»」에 둡니다.**
같은 질의 «안»에서 두 grain 이 어긋나 있습니다.

⚠️ **이건 이 박스의 원장 모양입니다.** 운영 번역기가 Wafer payload 에 넣는다면 돌 것입니다 —
**운영은 제가 못 봅니다.** 다만 어긋남의 «모양»(주어 키 vs payload)은 데이터가 아니라
선언이 정하는 것이라, 대체 설계는 그 둘을 «따로 말할 수» 있어야 합니다.

---

# 1. ① 호출자가 grain 을 «선언»하면 어떤 모양인가 — **응답에 이미 있습니다**

`/trends` 응답이 `grain` 을 «내보내고» 있습니다:

```json
{ "subject_type": "Wafer",
  "identity_fields": ["wafer"],
  "context_fields": ["bonding_leg"],
  "context_role": "planned_bonding_experiment_unit",
  "aggregation_unit": "void_by_experiment_unit",
  "marking": "identity.mark_key" }
```

**새 스키마를 지을 것이 없습니다 — 지금 «내보내는» 이 구조를 «받으면» 됩니다.**
총괄이 앞서 「선언처럼 생겼는데 출처가 코드」라고 하신 그 객체이고,
**출력을 입력으로 뒤집는 것**이 이 설계의 전부입니다.

```
지금   코드가 grain 을 «정하고» 응답에 «설명»한다
후     호출자가 grain 을 «주고» 서버가 그대로 «쓴다».  응답은 받은 것을 되비춘다
```

🔴 **한 가지만 늘어납니다** — §0 때문에 축마다 «두 식»이 필요합니다:

```
axis: { name: "bonding_leg",
        denominator: { relation: "bonding_map", column: "leg", join: … },   테이블 쪽
        numerator:   { from: "subject_keys" | "object_payload", key: "bonding_leg" } }  원자 쪽
```

🔴 **정정 (총괄이 잡음, 20:2x) — 「어느 파일에 두나」는 이 라운드에서 «떼어냅니다».**

제가 처음에 「`config/siblings_axes.json` 의 형제로 두라」고 적었는데 **그 파일은
이 박스에 «없습니다».** 로더가 샘플로 폴백하고 있고, 그 샘플은 **git 에 추적됩니다**:

```
server/config/siblings_axes.json            «없음»
실제로 읽히는 것                             server/config/sample/siblings_axes.json.sample  (추적됨)
```

그대로 시키면 구현자가 **샘플에 선언을 씁니다** — 여기선 돌고, 운영에 라이브 파일이
생기는 날 «조용히» 사라집니다.

⚠️ **저는 그 경로를 «출력에서 보고도»** 문장은 라이브 이름으로 썼습니다
(`load_axes_config()` 가 `path: …/sample/…sample` 을 찍어 줬습니다).
제 메모리에 있는 부류인데(「grep 은 실제로 도는 config 를 건너뛴다」) **증거를 손에 쥐고 틀렸습니다.**

```
이 라운드에서 정할 것    grain 을 «입력으로 받는다» + 축마다 두 표현        (§3 · §5 의 2·3)
이 라운드에서 «안» 정할 것  그 선언을 «어느 파일»에 두나 — 별건입니다
여전히 유효한 것        「두 번째 «선언 표면»을 만들지 말 것」 — 모양은 attribution 과 같습니다
```

---

# 2. ② 노드 id 마킹과 만나는 자리 — **`marking` 필드가 그 자리입니다**

응답의 `"marking": "identity.mark_key"` 가 정확히 은퇴 대상입니다. 그리고:

```
identity_fields + context_fields  =  (wafer, bonding_leg)
WaferLeg 원자의 «주어 키»          =  {"wafer": …, "bonding_leg": …}   ← «같은 쌍»
```

**grain 이 곧 개체입니다.** 그런데 `WaferLeg` 이 **어디에도 선언돼 있지 않습니다**:

```
라이브 v5 entities   DTJob@1 · Lot@1 · Wafer@1 · die@1        -> WaferLeg «없음»
v1 ENTITY_TYPES      Die · Equipment · Lot · Product · Recipe · Wafer  -> «없음»
실제 원자             subject_type='WaferLeg' 42건 · 서로 다른 주어 12
```

```
그러므로 경로   WaferLeg 을 «선언»한다 (소유자가 폼으로. 코드 0줄)
                -> grain 이 «개체 타입» 하나가 된다
                -> marking 이 encode_mark 대신 «그 개체의 노드 id» 가 된다
                -> 고정 두 축이 «사라집니다»
```

**이것이 §1(마킹 = 노드 id)과 만나는 자리이고, 앞서 제가 「§1 을 기다릴 필요 없다」고 한 것도
여전히 맞습니다** — 지우는 것은 지금 지워도 되고, 이 설계는 «그 자리에 무엇이 오는가»입니다.

---

# 3. ③ 최소 수정 경로 — **다섯 자리가 «한 목록»입니다**

SQL 을 읽었습니다. 그 쌍이 나오는 곳:

```
1  scans        GROUP BY r.base_wafer_id, b.leg, d.kind
2  observed_wafer  GROUP BY wafer, bonding_leg, kind [, subtype]
3  per_wafer    JOIN  ON o.wafer = s.wafer AND o.bonding_leg = s.bonding_leg AND o.kind = s.kind
4  per_wafer    (반대 방향 JOIN 도 같은 세 컬럼)
5  numbered     ORDER BY last_at, wafer, bonding_leg
```

**다섯 다 «같은 컬럼 목록»입니다.** 그러므로:

```
최소 수정   grain 을 «컬럼 목록»으로 파라미터화한다.  GROUP BY · JOIN ON · ORDER BY 가
            그 목록을 받는다.  SQL 의 «구조»는 안 바뀝니다 — 열 겹을 고치는 게 아닙니다
더 작은 것  없습니다.  분자와 분모를 잇는 «조인 키»라서, 목록을 안 만들면
            어느 자리도 못 바꿉니다 (하나만 바꾸면 조인이 깨집니다)
```

🔴 **다만 §1 의 「두 식」이 여기 물립니다** — 1·5 는 테이블 컬럼이고 2·3·4 는 원자 경로입니다.
목록 «하나»가 아니라 **축마다 두 표현**을 들고 다녀야 합니다. 그게 이 라운드의 실제 비용입니다.

---

# 4. ④ 잃는 것 — **원리상 하나, 지금은 «영»**

## 원리상 잃는 것: 「같은 웨이퍼의 다른 leg」이라는 «자체 대조»

grain 이 (wafer) 하나로 거칠어지면, **한 웨이퍼 안에서 leg 별 차이**를 못 봅니다.
그건 가장 «단단한» 대조입니다 — 웨이퍼 자신이 컨트롤이라, 상류 공정·재료가 «자동으로» 상쇄됩니다.

**그러므로 grain 은 거칠어지면 안 되고, «선언 가능»해져야 합니다.** 없애는 게 아닙니다.

## 지금 실제로 잃는 것: **없습니다**

```
found 0 · scanned_clean 48   -> 그 축이 지금 «아무것도 못 세고» 있습니다
그리고 bonding_map 의 (base, leg) 쌍이 «13»                    분모도 얇습니다
```

⚠️ **「지금 0이니 지워도 된다」로 읽지 마십시오.** 이 저장소가 그것으로 물린 적이 있습니다
(`packs` 를 지우자 `allowed_values` 가 영원히 빈 값이 됐고 읽는 쪽 넷은 살아 있었습니다).
**지금 0인 이유가 «어긋남»이지 «불필요»가 아닙니다** — 고치면 값이 생깁니다.

---

# 5. 그래서 순서 제안

```
1  WaferLeg 을 선언한다            소유자 · 폼 · 코드 0줄   -> grain 이 개체가 된다
2  grain 을 «받는» 계약으로 뒤집는다  응답의 그 객체를 입력으로. 축마다 두 표현
3  다섯 자리를 그 목록으로           SQL 구조는 그대로
4  marking 을 노드 id 로            encode_mark 은 그때 «쓸 데가 없어집니다»
```

**1 이 없으면 4 가 갈 곳이 없습니다.** 그리고 §0 의 어긋남은 **2 에서 저절로 드러납니다** —
분자 쪽 표현을 «선언»하는 순간 「주어 키냐 payload 냐」를 말해야 하기 때문입니다.

---

# 6. 제가 «안 잰» 것

```
운영의 원장 모양      Wafer payload 에 bonding_leg 이 있는지 «모릅니다». 이 박스만 봤습니다
grain 의 다른 소비자   ✅ «총괄이 쟀습니다» — 읽는 곳 «0». 내보내는 한 자리(ledger_trends)뿐입니다
                      -> 계약을 뒤집어도 깨질 하류가 없습니다. 이 설계가 생각보다 쌉니다
metric_state 위치     제 순회가 그 키를 못 찾았습니다. found/scanned_clean 문자열로 셌습니다
```
