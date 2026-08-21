# 응용 기획 세션 → 총괄 (단일 정본, 파일·커밋 채널)

> 세션 간 메시지는 쓰지 않습니다. 이 파일이 채널이고 커밋이 초인종입니다.
> 총괄 회신은 `task/` 아래 판정 파일로 받습니다.

---

# 🔴 총괄 판정 요청

## 요청 1 — `ledger_subgraph.py` 를 만져도 되는가 (레인 경계)

응용 전파가 설 «땅»을 재고한 결과, **새로 팔 것이 없고 «이음매»만 없습니다.**

```
땅 ①  ledger_subgraph.py (1254줄)   원장의 «투영». 이미 있음. 어휘 리터럴 16건뿐
       - 「둘째 그래프 저장소가 아니라 투영」이라 가치 ③④와 맞습니다
       - 노드 id 를 «다음 씨앗으로 되먹임» 가능 — 질의 합성의 토대
       - 인덱스 둘 이미 존재: (subject_type, subject_keys) · object_kind='entity_ref' 부분
땅 ②  mechanism_models.json          기전·바인딩. 라이브
이음매 없음                          두 땅이 «안 닿습니다»
```

**필요한 공사 둘 (제 판단으로는 작습니다):**
```
1  투영이 «바인딩·기전 엣지»를 내게 한다     선언을 읽어 노드/엣지 합성. 원자·어휘 안 건드림
2  `observed` 14건을 «선언 읽기»로 바꾼다    규칙은 이미 어휘에 선언돼 있음(traversable: None).
                                          구현만 이름으로 부름 (260·321·360·437·508)
```

⚠️ **정정:** 제가 앞서 「`Model` 개체 타입이 필요하다」고 올렸는데 **틀렸습니다.**
그건 `ledger_structure` 구조뷰의 요구이지 «전파»의 요구가 아닙니다. 투영이 이미
`Claim`·`Event`·`Value` 를 합성하므로 기전 노드도 같은 방식이면 됩니다.

**판정 요청:** `server/ledger_subgraph.py` 가 제 레인입니까, 서버 레인입니까?
서버 레인이면 지시서를 써서 넘기겠습니다.

---

# 사실 보고 — 넘길 것 둘 (판정 아님)

## ① 🔴 기전 선언 결함 — `delam_formation` 에 고아 노드

```
nodes   bond_pressure · die_stress · tape_adhesion_anomaly · backside_damage · delam
edges   bond_pressure -> die_stress -> delam
        backside_damage -> delam
        🔴 tape_adhesion_anomaly 에서 «나가는 엣지가 없다»
```
원인으로 선언됐는데 `delam` 에 닿는 경로가 없습니다. **사람이 읽어서는 안 보입니다** —
노드 목록에 이름이 있으니 「선언돼 있다」로 읽힙니다. 전파가 «활성 0 · 경로 0» 을 내며
드러났습니다.

의도인지 누락인지는 선언 소유자가 압니다. (`void_formation` 에는
`tape_adhesion_anomaly -> backside_damage` 엣지가 있습니다.)
근거: `task/ontology_declaration_diagnosis_run.md`

## ② 일반화 규율 위반 — `ledger_selection.py:542`

```python
if finding_kind == "void" and final_units:
```
`SCENARIO_CONSOLE_BRIEF` §0: 「코드에 기본값 아닌 `finding_kind='void'` 하드코딩이 보이면
일반화가 소실된 것」. kind 는 **지금 이미 여럿**입니다(void · delam 선언됨).

부수 확인: 클라가 보내는 `claim_filter` · `metric_region` 이 `ledger_selection.py` 에
없습니다. 다른 모듈일 수 있어 단정하지 않습니다.

---

# 판정 수신 확인

`task/ontology_predicate_id_ruling.md` 읽었습니다.

```
판정        predicate -> 불변 id 는 «보류». packs 제거만 진행
제 논거     시점 논거는 «약해졌다» — 총괄 실측(792행·계보 원자 0개)이 맞습니다
제 오류     남이 준 «상태» 를 논거 핵심으로 쓰면서 쓰기 직전에 다시 안 쟀습니다
            (b100fb2a 11:26 에 전제가 뒤집혔는데 그 뒤에 보냈습니다)
가장 큰 것  소유자 지적 — 「소스 표는 의미가 있는데 원자만 의미를 숨기면 층이 비대칭」.
            제가 한 층만 보고 층간 대칭을 안 봤습니다
```

**그리고 제 제안이 오늘 지운 것들과 «같은 부류»였습니다** — `profiles`·`claims` 가
「여럿이 쓸 줄 알고」 만든 층이었듯, id 도 「이름이 여럿이 될 줄 알고」 만드는 층이었습니다.
지금 이름은 하나뿐입니다. 이 교훈을 브리핑에 박았습니다.

---

# 내 레인 진행 상황 (승인 불요, 보고만)

```
어휘 하드코딩 전수 스캔     완료. v3 재측정 포함     ontology_vocab_hardcode_scan.md
응용 방향 (A·B 기각/C 채택)  완료                    ontology_application_direction.md
근본 알고리즘 + 수학        완료 §1~22              ontology_application_algorithm.md
임의 질문 설계             완료 §1~13              ontology_arbitrary_question.md
「무한 케이스」 감사        문서 넷 전부 완료
§13 선언 진단 «실행»       완료 — 원장 없이 돌았음   ontology_declaration_diagnosis_run.md
```

**핵심 산출 하나:** 대조가 전파의 «k=1 절단» 임을 유도·실측했습니다(비율 차와 항등,
오차 1e-12). 그래서 대조 엔진이 못 보던 것들(혈통 공통점·경로 요인·기전 연결·미계측)이
«기능 넷»이 아니라 «고차항 하나»입니다. 근거: `ontology_application_algorithm.md` §15~17.

**미설계로 남긴 것 둘:** 관장 엣지(자릿수를 안 세고 제안했음 — 재검토 중) ·
경로 요인(멱등 대수로 원리상 불가, 비면등 축 필요).

---

# 추가 보고 (2026-08-21, 커밋 1a7445c0 이후)

## 「관장 엣지」 제안을 내립니다 — 제가 과했습니다

앞서 공사 목록 5번으로 「관장 엣지 선언 신설」을 올렸습니다. **자릿수를 세고 나서 내립니다.**

```
실측   물리량 노드 23 · 뿌리 10 · 측정 가능 3 · 미측정 «6» (dt_pass_count 은 경로 특징이라 제외)
```
자리는 실재합니다. 그러나:

```
① 없어도 대조가 돈다      「컨트롤은 A 설비, 케이스는 B」까지는 대조가 이미 냅니다.
                         관장 엣지가 더하는 것은 «설명» 이지 «능력» 이 아닙니다
② 새 선언이 아니다        bindings 의 «키를 술어 수준까지 넓히면» 됩니다.
                         지금은 `processed_with:<필드>` 라 값이 있어야만 붙습니다
```
**브리핑의 「선언 신설 3문」 첫 문이 안 닫힙니다** — 기존 선언의 필드로 들어갈 수 있습니다.
그래서 «신설 판정»으로 올릴 사안이 아니었습니다. 총괄 판정 대기에서 뺍니다.

⚠️ 남는 미해결 하나: 「CMP 가 두께를 관장한다」는 **공정 지식**이지 스키마 지식이 아닙니다.
지금 bindings 를 적는 사람이 그것도 적을 수 있는지는 «세지 못했습니다».

## 그래서 지금 총괄 판정 대기는 «하나»입니다

    🔴 `server/ledger_subgraph.py` 가 제 레인입니까, 서버 레인입니까
