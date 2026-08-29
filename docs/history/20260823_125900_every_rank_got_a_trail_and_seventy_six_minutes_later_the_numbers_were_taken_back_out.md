# 순위 «전부»에 자취가 붙었고, 76분 뒤 「수는 안 나간다」가 원문 그대로 되돌아왔다

> **커밋:** `5aa666d5` (10:56) · `036f6660` (11:43) · `16a0f460` (12:59)
> | **일자:** 2026-08-23 오전
> **레인:** 서버(증거 서브그래프)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 발견 쪽에서 물리량으로 들어가는 문이 없었다

발견 묶음을 seed 로 주고 `collect=quantity`를 물으면 **빈 답**이 왔다. 기계 그래프가
**원인 쪽에서만** 합성되고 있어서 **관측된 발견 쪽에서 들어오는 길이 없었다.**

`5aa666d5`가 그 한 줄을 열었다:

```python
# server/ledger_subgraph.py
for item in finding_refs:
    for model in models_by_name.values():
        if model.finding_kind != item["finding_kind"]:
            continue
        node = _quantity_node(model.name, model.target, model)
```

표 라우트는 **부호 붙은 seed 는 받고 `collect`는 안 받는다** — `evidence_subgraph_table`이
`positive`/`negative`만 받고 `evidence_subgraph`가 `collect`까지 받는다. 이건 diff 로 확인된다.

## 순위 1만 자취를 들고 있었다

`036f6660` 전에는 `for item in layers[0]: item["evidence"] = …` — **최상위 층에만** 증거 자취가
채워졌다. 그래서 읽는 사람은 어떤 후보가 **1등이 아니라는 것**은 볼 수 있어도 그것이
**대조군에서 한 번도 안 닿았다는 것**은 못 봤다.

바뀐 것은 **부호 계산이 아니라 «범위»다.** 부호는 이미 `parents`와 `seed_signs`에서 seed 별로
나오고 있었고, `_evidence(...)` 호출이 `for layer in layers for item in layer` 안으로 들어가면서
**모든 순위**가 seed 별 `+`/`−`와 홉 자취를 들게 됐다.

## 🔴 그런데 같은 커밋이 「어떤 수도 안 나간다」라는 🔴 규칙을 뒤집었다

`036f6660`은 같은 dict 에 `"reach": item["reach"]` 한 줄을 더하고 **스펙 문장까지 고쳐서**
그 reach 쌍이 「소유자가 받기로 한 것」이라고 적었다. 크기 근거로 **288 KB / 2,723 KB = 11%**를
들었다.

**76분 뒤 `16a0f460`이 그 문장을 원문 그대로 되돌렸다** — `docs/spec/LEDGER_EVIDENCE_SUBGRAPH_SPEC.md`의
「응답 어디에도 `reach` 가 없다」. 그리고 근거였던 수치가 **키가 아직 payload 에 실린 채로 잰
것**이라고 스스로 적었다. 재측정: **285 KB / 2,991 KB = 10%**, 작은 walk 는 94 KB / 24 KB (25%).
넓힌 증거 자취는 남고 **그 한 줄만** 빠졌다.

🔴 그리고 `036f6660`의 제목은 「라벨이 이름으로 시작한다」인데 **자기 본문이 "REACHES NOBODY
YET"이라고 적고 있다** — `_declared_key_order` 라벨 경로는 `die`·`DTJob`·`WaferLeg`에 대해
**아홉 시간 뒤 `5f132d3e`가 디코드 게이트를 걷어낼 때까지** 발화하지 못했다.

## 아키텍처 영향

- 증거 자취(`evidence[].sign` · `evidence[].hops`)가 **최상위 층이 아니라 모든 순위**에 붙는다.
- 순위를 «정하는» `reach`는 응답에 **안 실린다.** 그 규칙이 한 번 뒤집혔다가 **같은 날 오후에
  원문으로 복원**됐다.

## 그때 남아 있던 것

- 인스턴스 실행과 선언 실행이 **축 둘에서 여전히 어긋난다.**
- **노드로 선언됐지만 한 번도 안 닿는 물리량**이 그대로 재현된다.
- `_rank_layers`와 순위 규칙 자체는 이 두 커밋에서 **한 줄도 안 바뀌었다.**
- 수치 「288 KB / 2,723 KB」는 **오염된 근거**로 남는다 — 재려던 모양이 아니라 키가 실린 모양을
  쟀다. 유효한 것은 `16a0f460`의 285 KB / 2,991 KB 쪽이다.
