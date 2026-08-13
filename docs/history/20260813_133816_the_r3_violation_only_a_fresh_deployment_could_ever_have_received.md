# The R3 violation only a fresh deployment could ever have received

**Date:** 2026-08-13 13:38 · **Domain:** Server (config `.sample` 감사) · **Status:** 착지 — `272da5b`

> ⚠️ **이 박스에서는 아무것도 바뀌지 않는다.** 바뀐 두 파일은 추적되는 `.sample`이고,
> 라이브 config는 언제나 올바른 값을 들고 있었다.

---

## 배경 — gitignore가 사는 대가

`server/config/*`는 **설계상** gitignore다 — 배포가 운영자의 조정된 사본을 덮어쓰지 못하게.
추적되는 것은 `.sample`뿐이다. 그 설계가 사는 실패 모드는 **둘이 조용히 벌어지고 아무도
듣지 못한다**는 것이다. 이 커밋은 두 방향을, 파일별로, 라이브 데이터베이스에 대고 감사했다.

## R3 위반이 추적되는 쪽에만 있었다

`core_wafer_map.map_key_columns`가 `["wafer_id"]`를 선언하고 있었다. `wafer_id`는
`composite_key_source = [core_lot, core_slot, core_x, core_y]`에 **없다.**

그리고 규칙 위반보다 나쁜 것이 그다음이다 — 같은 선언 블록의 여는 `__comment`가
`wafer_id`를 **일부러 희소하게 둔다**고 적고 있다: *「wafer_id is deliberately sparse:
absence is the enrichment work item」*. **희소한 비-키 컬럼으로 범위를 잡는 purge는
아무것도 범위 잡지 못한다** — 아직 enrich되지 않은 모든 행에 대해 `replace_map`이 200을
답하고 **0행을 지운다.**

```json
"__map_key_columns_comment": "R3 (SCHEMA_CANON): map_key_columns must be a SUBSET of
  composite_key_source. This said [wafer_id], which is not key material here ...",
"map_key_columns": ["core_lot", "core_slot"]
```

라이브 config는 **언제나** 올바른 `["core_lot", "core_slot"]`을 들고 있었고, 그것이 여기
아무도 이 결함을 본 적 없는 이유다 — **깨진 선언은 «새 배포»에만 도달할 수 있었다.**

### 재검산 하나

커밋 본문은 그 희소성 주석이 「세 필드 위」에 있다고 적었고, 새로 넣은 주석 자신은 「두
필드 위」라고 적는다. 실제로는 그 문장은 선언 블록의 **여는 `__comment`** 안에 있고
`map_key_columns`에서 20여 줄 위다. **내용은 맞고 위치 표기만 틀렸다** — 같은 라운드의
`3e5031b`이 라인 앵커를 걷어낸 것과 같은 부류다.

## 규칙은 눈에 띈 한 테이블이 아니라 «전 테이블»에 다시 돌렸다

한 테이블에 적용한 규칙은 적용하지 않은 규칙이다. 두 파일의 모든 테이블에 R3를 재실행했다.
**전: `.sample` 1건 위반, 라이브 0건. 후: 0건과 0건.**

## `.sample`이 오버레이 바인딩 하나를 빠뜨리고 있었다

`map_overlay_config.json.sample`에 `core_usage_map`의 바인딩이 없었다. 그 테이블은 **두
테이블 config 모두에 선언돼 있으므로** 새 박스는 테이블은 받고 **칠할 방법은 못 받는다.**
컬럼이 네임스페이스돼 있어서(`core_x`/`core_y`/`used_count`) **파생으로 닿을 수 없는** —
그 파일 자신의 `__derived_note`가 선언을 요구하는 바로 그 경우다.

```json
"core_usage_map": {
  "columns": { "x": "core_x", "y": "core_y", "val": "used_count",
               "key_columns": ["core_wafer"] }
}
```

사유는 라이브 파일에도 **주석 키로** 실렸다 — 운영자의 박스는 `.sample`을 절대 읽지 않으므로,
안 그러면 **올바른 값을 들고 있으면서 그것이 무엇을 막고 있는지는 기록이 없는** 상태가 된다.

## 의도적으로 하지 «않은» 것

라이브 `table_config.json`은 `.sample`이 들고 있는 선언 **넷**을 안 들고 있다 —
`dt_job_attribution`(252행), `eqp_frame_attribution`(5행), `map_doe`·`map_doe_source`(각 0행,
넷 다 물리적으로 존재). 그것을 채택하면 **도는 모든 프로세스가 로드하는 것이 바뀐다.**
레인 넷이 이 트리에 대고 측정 중이라 잊은 것이 아니라 **대기열에** 넣었다.

무해로 확인된 것: 라이브 `ingestion_settings.json`이 `.sample`이 선언한 열다섯 키를 생략하는데
**모든 기본값이 선언된 값과 같다** — 파일이 아니라 **코드에 물어서** 확인했다. 특히 tier 1이
True로 해소되므로 `831ab68`의 호이스트는 여기서 살아 있고 조용히 꺼져 있지 않다.

## 그때 남아 있던 것

- 2파일 +10/-1. 둘 다 추적되는 `.sample`이고, **이 박스의 동작은 하나도 안 바뀐다.**
- 라이브 `table_config.json`의 선언 넷 누락은 **그대로 열려 있다.**
- 검증: 세 파일 전부 파싱, config 정합 스위트 넷에서 102 passed + 1 skipped,
  `test_void_schema.py` 33 passed(그 안의 라이브-`.sample` 일치 테스트 포함).
