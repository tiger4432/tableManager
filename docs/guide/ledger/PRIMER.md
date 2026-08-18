# 입문 — 한 행의 여행: 모든 구성요소의 역할과 실물 예시

> **Status:** 🟢 Living | **Last-verified:** 2026-08-19 | **Owner:** Server / Ledger
> **Source-of-truth:** `server/ledger/vocabulary.py` · `server/ledger/roleframe.py` · 선언 절차 [ONTOLOGY_LEDGER_SETUP](../ONTOLOGY_LEDGER_SETUP.md)

> 실제 DB의 스플릿 행 하나가 원장 원자가 되기까지. 각 요소가 «언제 등장해
> 무엇을 하는지»를 실물로. (03 사전 화면의 원고이기도 하다)

## 0. 출발 — 실물 행 (lot_event 표, 라이브)

```
lot=CL-2601-006 · event_type=split · child_lot=CL-2601-006-A1
slot_numbers="01:02:03:…:25" · wafer_ids="WF.010601:WF.010602:…"
event_time=2026-05-03 02:17
```

이 행은 아직 **뜻이 없다.** 그냥 문자열이다. 아래 요소들이 뜻을 붙인다.

## 1. 여행 순서대로 — 요소 × 역할 × 이 예시에서

| # | 요소 | 정체 (비유) | 역할 | 이 예시에서 실물 |
|---|---|---|---|---|
| 1 | **소스 테이블** | 세계의 수첩 | 사실이 행으로 눕는 곳. 뜻 없음 | 위의 행 |
| 2 | **table_config** | 표의 주민등록 | 이 표의 행을 «하나»로 세는 법 | business_key = lot\|event_type\|event_time |
| 3 | **PROFILE** | 이 소스의 독해 지침서 | 「이 표를 어떻게 읽는가」 전부: 묶음·문장 선택·컬럼 잇기·시각·전제. **모양이 똑같은 문장이 둘이면 mapping마다 `sentence`로 「내가 그 문장이다」를 적는다** — 안 적으면 compile 시점 `ambiguous_sentence` | unit=row_pair(lot,event_type,event_time) · use lineage/split · occurred_at=event_time(Asia/Seoul) |
| 4 | **엔진 group** | 제본기 | Profile의 UNIT대로 행들을 «분자(한 사건)»로 묶음 — 코드 아닌 선언이 구동 | 부모행+자식행 2행 → 스플릿 분자 1개 |
| 5 | **MAPPER 훅** | 통역사 | (구조 변환일 때만) 분자가 «무슨 뜻»인지 해석해 Claim들로. 🔴 **통역사는 선언의 «낱말»을 모른다** — 자기가 하는 말의 «모양»만 알고, 그 모양을 실현하는 Profile mapping을 엔진이 찾아 준다(`SentenceShape`/`ProfileSentences`). 그래서 이 배포가 랏을 Batch라 불러도 mapper는 안 바뀐다 | split 분자 → Claim(갈라짐: 자식→부모) 1 + Claim(소속: 랏·슬롯·웨이퍼) ×19 |
| 6 | **PACK** | 표준 문장 양식집 | Claim의 빈칸(role)을 받아 **payload 철자로 컴파일**. 사람 문장↔문법의 다리 | 소속 Claim → 술어 has_wafer, payload {keys:{wafer}, qualifiers:{slot}} 로 접기 |
| 7 | **vocabulary.py** | **국어사전 + 문법책** | 아래 §2 상세 | has_wafer 항목: 주어는 Lot만, 목적어는 Wafer ref, 걷기는 「도달만·통과 금지」 |
| 8 | **게이트** | 검문소 | 원자마다 사전(7)의 서명과 대조 — 하나라도 틀리면 **분자 전체** 거절 | has_wafer의 목적어가 Wafer ref인가? qualifiers에 slot 있는가? |
| 9 | **봉투** | 규격 서류 양식 | 모든 원자의 고정 7필드 모양 | 아래 §3의 실물 원자 |
| 10 | **원장** | 등기부 | 통과한 문장이 영구히 눕는 곳. 추가 전용 | ledger_events에 20행 삽입 |
| 11 | **읽기측** | 해석기들 | 걷기·대조·여정이 원자를 «질의 시점에» 해석 | 걷기가 derived_from만 건너 혈통 복원 |

## 2. vocabulary.py — 「아직도 모르겠는」 그것

**원장 언어의 국어사전 + 문법책**이다. 딱 세 가지를 담는다:

**① 낱말 목록 (닫힌 집합)** — 이 원장이 말할 수 있는 동사 전부
(register, pin, derived_from, has_wafer, slot_map, processed_with, transferred,
observed, measured, has_param, assigned_to_experiment + 예약 same_as/frame_confirmed).
목록이 닫혀 있는 이유: 아무나 낱말을 만들면 읽는 쪽이 해석 불능이 된다.
🔴 **개수는 여기 적지 않는다** — 이 목록은 코드 절반(`vocabulary.PREDICATES`)과 선언 절반
(`server/config/ledger_vocabulary.json`)의 병합이라 배포마다 다르고, 이 자리에 숫자를
박아 두면 낱말이 하나 늘 때마다 조용히 낡는다. 지금 이 환경이 아는 낱말을 세는 것은
`vocabulary.all_predicates()`다.

**② 낱말마다 문형(서명)** — 실물 항목:

```python
"has_wafer": {
    "subject": ["Lot"],                          # 주어가 될 수 있는 것
    "object": {"kind": "entity_ref",             # 목적어의 모양
               "types": ["Wafer"]},
    "traversable": False,                        # ③ 걷기 규칙 (아래)
}
"derived_from": {
    "subject": ["Lot"],
    "object": {"kind": "entity_ref", "types": ["Lot"]},
    "traversable": True, "direction": "subject_to_object",   # 걷기가 «건너는» 유일한 낱말
}
```

이 서명이 곧 **게이트의 검사 기준**이다. Pack이 뭘 컴파일하든, 서명에 안 맞으면
원장에 못 들어간다. (그래서 Pack이 틀려도 원장이 오염 안 된다 — 권위는 여기)

**③ 걷기 규칙** — traversable 3상태: True(혈통처럼 재귀로 건넘) /
False(닿으면 주석으로 가져오되 통과 금지 — has_wafer) / None(걷기가 아예 안
가져옴 — observed 10만 개를 혈통 조회에 끌고 오면 죽는다).
**걷기 코드가 아니라 이 선언이 걷기의 행동을 정한다** — 선언과 구현이 어긋나면
걷기는 추측하지 않고 이름을 대며 거절한다.

왜 .py인가: 닫힌 집합을 테스트로 못박기 위해(조용히 자라는 어휘 방지). 지금은
코드 v0 + config 확장(R-M, origin: code|config 구분)의 이중 출처다.

## 3. 도착 — 실물 원자 (라이브 원장에서 인용)

```json
{"predicate": "derived_from", "subject_type": "Lot",
 "subject_keys": {"lot": "CL-2601-006-A1"},
 "object_kind": "entity_ref",
 "object_payload": {"type": "Lot", "keys": {"lot": "CL-2601-006"}},
 "occurred_at": "2026-05-03T02:17:00+09:00", "source_who": "lot_event"}

{"predicate": "has_wafer", "subject_type": "Lot",
 "subject_keys": {"lot": "CL-2601-006"},
 "object_kind": "entity_ref",
 "object_payload": {"type": "Wafer", "keys": {"wafer": "WF.010601"},
                     "qualifiers": {"slot": "01"}},
 "occurred_at": "2026-05-03T02:17:00+09:00", "source_who": "lot_event"}
  … (×19)
```

문자열이던 행이 「CL-2601-006-A1은 CL-2601-006에서 갈라져 나왔다」 + 「01번
자리에 WF.010601이 있다」×19 라는 **검사받은 문장 20개**가 됐다.

## 4. 한 문장 요약

**소스**는 사실을 눕히고, **Profile**은 읽는 법을 선언하고, **엔진**이 묶고,
**Mapper**가 뜻을 해석하고, **Pack**이 문장으로 작문하고, **vocabulary**가
문법을 검사시키고(게이트), **봉투**에 담겨 **원장**에 눕고, **읽기측**이 질의
시점에 해석한다. — 사용자가 만지는 건 Profile(항상)과 Mapper 훅(예외)뿐이다.

## 5. 읽기측 상세 — 눕는 문장이 답이 되기까지

쓰기측(1~10)은 문장을 **눕히기만** 한다. 답은 전부 읽기측이 질의 순간에
계산한다. 구성은 «재판관 하나 + 해석기 다섯 + 그들을 구동하는 선언 셋».

### 5-0. 해소기 — 모든 해석기가 공유하는 재판관

같은 자리에 경쟁 주장이 여럿 누울 수 있다(원장은 모순을 품는 대장이다).
어느 주장이 이기는지는 **5단 사전식 순위** 하나가 정한다:

```
(계급 0핀>1확정>2관측>3추론) → (출처 서열) → (날짜 있음>없음) → (최신) → (id)
```

- 계급이 최외곽이라 **아래 단은 계급을 절대 못 뒤집는다** — 사람 확정을 나중에
  온 추론이 이길 수 없는 이유가 코드가 아니라 튜플 모양이다.
- 실물: 머지 랏 슬롯 01에 부모 주장 둘 → R-L 판정 전엔 「후보 2, 미해소」,
  판정 후엔 slot_map이 발언권을 얻는다. **원장은 한 글자도 안 바뀌고 답이
  바뀐다** — 재판 규칙만 바뀌었으므로.

### 5-1. 해석기 다섯 (전부 같은 원자·같은 재판관을 씀)

| 해석기 | 답하는 질문 | 작동 방식 | 실물 예시 |
|---|---|---|---|
| **걷기** `/trace` | 「이건 어디서 왔나」 | vocabulary의 traversable 선언대로 — derived_from만 재귀로 «건너고», has_wafer는 닿은 랏의 주석으로, observed는 아예 안 가져옴. 질문 3개의 반복: 이 자리에 누가 있나(has_wafer) → 어디서 왔나(derived_from) → 부모의 어느 자리였나(slot_map). 끊기면 «어느 질문에 답 못 했는지»가 나온다 | CL-2601-006-A1/01 → 「01에 WF.010601」→「CL-2601-006에서 갈라짐」→「부모의 01이었다」 |
| **대조** `/siblings?scope=` | 「마킹한 것들은 나머지와 뭐가 다른가」 | 항목 목록 없음 — 걷기가 닿은 **모든 payload 잎**이 후보. 후보마다 세 관문: 실재(통계)·상류(시간)·기전(물리 경로) | 압력 잎이 후보로 떠서 PPP — 저압 갈래에서 보이드 경로로 1순위 (선언 0개로) |
| **여정** `/journey` | 「두 장이 걸은 길은 어디서 갈라졌나」 | n=2 전용. (계열·스텝·회차)로 구간을 묶고, 같은 구간 접고 갈라진 구간만 열며, 육하로 카드 | 「같은 길 2구간, 갈라진 곳 6곳 — 본딩 1회차·압력」 |
| **표/맵** `/lots` `/lot_map` | 「어느 것이 튀나」「어디에 났나」 | 표는 행=지표·열=대상, 기저(중앙값) 대비 배수로 히트. 맵은 등록 프레임+유효 다이 마스크 위에 칩 투영 | 사다리 2.30×→4.97× 색칠 |
| **구조 뷰** `/structure` | 「이 원장은 무엇을 말할 줄 아나」 | 유형 수준 집계(GROUP BY 한 방) + 선언과 대조해 드리프트 검출 | 노드 6·엣지 55·원자 21만, 미선언 엣지는 «드리프트»로 |

### 5-2. 읽기측을 구동하는 선언 셋 — 「등재 ≠ 소비」의 정체

원자가 있어도 이 선언들이 없으면 화면에 **안 나온다**:

| 선언 파일 | 무엇을 정하나 | 없으면 |
|---|---|---|
| `siblings_axes.json` | **기하**: 모집단의 단위(unit_columns), 원장 주어와의 다리(ledger_subject — 「이 표의 base_wafer_id가 곧 Wafer 주어다」), 마킹·귀속 축 | 대조가 「걷기 불가 — 주어 선언 없음」으로 거절 |
| `mechanism_models.json` | **왜**: 물리량 그래프 + bindings(잎→물리량) | 기전 관문이 전부 «모름» — 원인이어도 설명 못 함 |
| `ledger_journey.json` | **이름·구간**: 어느 술어가 여정을 싣나(segments), 한국어 라벨 | 여정이 원시 경로로 렌더(못생기게 — 의도) |

**실물 예시** (라이브/샘플 파일에서 인용):

```jsonc
// siblings_axes.json — 기하: 모집단 단위와 «원장으로 가는 다리»
"geometry": {
  "unit_columns": ["base_wafer_id", "base_x", "base_y"],   // 모집단의 낱개 = 칩
  "ledger_subject": {                                       // 이 다리가 없으면 걷기 대조 불가
    "type": "Wafer", "key": "wafer", "column": "base_wafer_id"
  }                                                         // 「이 표의 base_wafer_id가 곧 Wafer 주어의 wafer 키다」
},
"attribution": [{ "relation": "bonding_log",
  "join": { "base_wafer_id": "base_id", "base_x": "bx", "base_y": "by" },
  "axes": [
    { "name": "bond_lot", "label": "본딩 랏", "column": "bond_lot" },   // 마킹·묶음 축
    { "name": "wafer",    "label": "웨이퍼",  "column": "base_id" }     // 주어 자체를 축으로 (WF 마킹)
  ]}]

// mechanism_models.json — 「왜」: 잎→물리량 바인딩 + 방향 엣지
"bindings": {
  "processed_with:params_actual.pressure_MPa": ["bond_pressure"]   // 이 잎은 본딩 압력을 잰다
},
"void_formation": { "edges": [
  { "from": "bond_pressure",   "to": "interface_unfill", "dir": "-" },  // 저압 → 미충전↑
  { "from": "interface_unfill", "to": "void",            "dir": "+" }   // 미충전 → 보이드↑
]}

// ledger_journey.json — 구간·이름
"segments":    { "processed_with": { "name_path": "step",          // 이 술어가 여정을 싣고,
                                     "family_path": "step_family" } }  // payload의 이 잎이 스텝 이름이다
"step_labels": { "BONDING": "본딩", "CMP": "연마" },
"field_labels": { "pressure_MPa": { "label": "압력", "unit": "MPa" } }
```

주의 하나: 세 파일 다 **원장 잎의 철자를 인용**한다(`params_actual.pressure_MPa`,
`step`…). 철자가 틀려도 오류가 아니라 침묵이다 — §5-3의 비대칭이 정확히 여기서
문다.

### 5-2-bis. 읽기 = 서브그래프 추출 (소유자 정식화)

다섯 해석기는 사실 한 기계의 다섯 얼굴이다:

```
① 추출 — 증언 더미에서 서브그래프를 오려낸다 (무엇을 기준으로 오리는지만 다름)
② 재판 — 해소기가 경쟁 주장을 판정한다 (전부 공유)
③ 렌더 — 오려낸 것을 질문 모양으로 그린다
```

| 해석기 | 추출 기준 | 렌더 |
|---|---|---|
| 걷기 | 한 대상에서 traversable 엣지로 닿는 것 | 홉 사슬 |
| 대조 | 마킹 집합 vs 나머지, 각각의 잎 전부 | 관문 붙은 후보 순위 |
| 여정 | 대상 «둘»의 공정 주석 | 구간 접힘/카드 |
| 맵 | 한 프레임에 앉는 칩들 | 좌표 투영 |
| 구조 뷰 | 전체 (유형 수준으로 접어서) | 유형 그래프 |

그래서 «서브그래프 탐색기»(보류 중 계획)가 이 다섯의 일반형이다 — 추출 기준을
사용자가 직접 쥐는 여섯째 얼굴.

### 5-3. 쓰기측과의 결정적 비대칭 (함정의 뿌리)

- **쓰기측 선언이 틀리면 → 게이트가 거절한다.** 시끄럽고, 즉시고, 이름이 붙는다.
- **읽기측 선언이 틀리면 → 그냥 안 보인다.** 축 미선언이면 후보가 안 뜨고,
  바인딩 오타면 영원히 «모름»이다 — 오류가 아니라 침묵. 러너북의 여덟째 함정
  («영원히 조용»)이 여기서 나오고, 합의 검사기(06)와 현황판(05)이 이 비대칭을
  죽이기 위해 존재한다.

한 줄 요약: **쓰기측은 문장을 검사해서 눕히고, 읽기측은 눕은 문장을 그때그때
재판해서 답을 만든다. 재판 규칙(해소·걷기 선언)이 바뀌면 원장은 그대로인데
답이 바뀐다 — 그게 이 구조의 목적이다.**
