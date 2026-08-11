# config에서 키 하나를 지우면 이제 상속된다 — 조용히 은퇴한 정체성으로 풀리는 대신

**날짜:** 2026-08-11 09:28 · **커밋:** `68db020` · **레인:** 서버(config 해석)
**측정 상자:** 이 워크스테이션의 격리 DB `assy_qa`. **운영이 아니다.**

---

## 배경

전전날 정체성 재키잡기 사고(`7097a67`)와 전날 보드 판정(`3fe4438`)이 겨눈 것이 이
커밋이다. `table_config`에서 한 가지를 바꿨더니 무관해 보이던 config 사슬이 깨진
이유는 **결합이 아니라 아무것도 상속하지 않았기 때문**이었다. `resolve_binding`은
`cols.get("key_columns") or ["lot", "slot"]`로 읽었고, 키를 지워 테이블 자신의 선언을
따르게 하려던 조작자는 **은퇴한 정체성을 아무 문장도 없이 그대로** 받았다. 관례
폴백이 틀린 답을 설정된 답처럼 보이게 만들고 있었다.

## 해법 — 키 단위 해석, `table_config` 파생 위에

```
local declaration  >  table_config derivation  >  refuse by name
```

관례 폴백은 삭제됐다. 핵심은 분리다: `_derive_table_binding_full`은 테이블에 리터럴
`x`/`y`가 없으면 전체를 포기한다 — 그래서 `core_wafer_map`(좌표가 `core_x`/`core_y`로
네임스페이스됨)은 base 전체가 `None`이고 `map_key_columns`는 아예 참조되지 않았다.
`derive_binding_parts`는 각 키를 **독립적으로** 유도하므로, 정체성이 좌표가 유도
가능한지 여부에 더는 매이지 않는다.

```python
# derive_binding_parts(table, val_candidates=None, allow_guess=False):
#   "`table_config` 알" `({key: value}, guessed)`, 키 단위로.
#   이 테이블 config가 말할 수 없는 키는 그냥 결과에서 ABSENT다.
```

측정으로 아무것도 안 움직였음을 확인했다: `resolve_binding`·`resolve_binding_info`
둘 다 **19/19 라이브 테이블에서 HEAD와 동일**했다. 무언가 실제로 바뀌었다는 것은
두 트랩으로 확인했다:

```
delete `key_columns` from core_wafer_map
    old -> ["lot","slot"]   (은퇴한 정체성, 조용히)
    new -> ["wafer_id"]     (상속, 그리고 상속으로 보고됨)

inject 2026-08-04 defect, dt_log.x = "x"
    old -> 존재하지 않는 컬럼을 담은 binding
    new -> None, `x: refused`, 테이블·키·컬럼을 대는 로그 한 줄
```

## `val`만은 상속하지 않는다 — 예외가 아니라 의미론

블록이 이미 선언돼 있는데 `val`을 생략하는 것은 **이미** 「이 맵은 값을 안 나른다」는
뜻이다. 상속하면 점유-전용 사이트에 값 컬럼을 쥐어 줘 점유 판을 값 판으로 뒤집는다.
`test_map_alignment_columns`가 이것을 잡았다. 순수 유도 binding은 여전히 `val`을
요구한다.

## `config_resolve_report`가 새 도메인을 얻었다

`binding` 도메인 — (테이블, 키)당 한 행, 출처는 `declared`/`inherited`/`absent`/
`refused`(닫힌 사유 어휘를 재사용). 라이브 config: **34개 유효, 6개 무효, 0개 거절**,
`bonding_map`과 `valid_die_ref`가 상속으로 해석된다. 이 도메인은 **마지막에** 등록됐다
— `contracts/config_resolve_report`가 `resolve_report()["domains"][0]`을 enrichment로
고정하고 있어서다.

## 온톨로지가 다섯 번째 정체성 선언 자리였다

`ontology_config`가 토큰 `@map_key_columns`를 얻었다 — `node.identity`를 아예 생략하면
「맵 정체성을 그대로 상속」이라는 뜻이다. `table_config`를 다시 읽지 않고
`map_overlay.derive_binding_parts`를 직접 호출해서, **그래프와 맵이 구조적으로
어긋날 수 없게** 했다. `DtCell`·`BondCell`·`IN_DT_JOB`·`RECORDED_AS_WAFER` 네 자리가
전환됐다(live + `.sample`), 8/8 테이블이 양쪽에서 동일하게 정규화되고 거부는
0/0이다.

```diff
   "node": {
     "label": "DtCell",
     "identity": [
-      "dt_job",
+      "@map_key_columns",
       "dt_x",
       "dt_y"
     ],
```

## 🔴 레인이 지시를 거절했다 — `CoreCell`은 `wafer_id`로 키잡지 않았다

지시는 `CoreCell`도 다른 넷처럼 `wafer_id`로 전환하는 것이었다. 레인은 하지 않았고,
그 이유를 실측으로 남겼다: `assy_qa`에서 `core_wafer_map` 24,200행 중 **9,674행
(40.0%)** 이 `wafer_id`가 비어 있고, **200개 lot/slot 그룹 전부**가 그런 행을 최소
하나 포함한다. 3fe4438이 확정한 「그룹 단위로는 정당한 측정」이 **행 단위에서는
성립하지 않는다** — `compose_identity`는 구성 요소가 null이면 `None`을 돌려주는데
`extract_graph_items`는 그래도 계속 진행하므로, 전환했다면 **9,674개 다이가 조용히
누락**됐을 것이다. 그래프 자신의 선언이 이미 이 사실을 말하고 있다 —
`RECORDED_AS_WAFER`는 의도적으로 희소하다고 문서화돼 있고, **부재 자체가 enrichment
작업 항목**이다.

```
grep 확인: server/config/ontology_mapping.json.sample의 CoreCell.identity는
이 커밋 뒤에도 ["core_lot", "core_slot", "core_x", "core_y"] 그대로다.
```

## 그 외 config가 흡수하지 못한 변경들

`bin_map.x`/`y`만 삭제됐고(본딩 단계 BIN 축이 거절→해결로, `x=dt_x, y=dt_y` 상속),
`bin_map.bin`(`c_bn`)은 **남았다** — 파생이 거기서는 `dt_index`를 답해 옳은 답을
틀린 답으로 바꾸기 때문이다. `basis_cells_for`가 `map_alignment`에서 공개됐고
`frame_confirmation`의 사설 사본은 사라졌다 — 부수 개선으로, 읽기 실패가 배치 전체를
중단시키던 것이 이제 다른 모든 읽을 수 없는 참조처럼 `None`을 돌려준다.

## 검증

20개 테스트 파일 회귀, HEAD 베이스라인 대비: **71건 실패 → 69건 실패**, 새로 깨진 것
없음, 기존 실패 두 건 해소. 신규 테스트 3개는 HEAD의 블록-치환 로직을 되살려 뮤테이션
검사했다 — 셋 다 빨갛게 확인.

## 그때 남아 있던 것

- **`CoreCell`은 이 커밋 이후에도 `core_lot`/`core_slot` 기반이다** — 지시된 전환은
  하지 않았고, 그 판단 근거(40% 결측)가 이 커밋의 본문에 남는다.
- **배포 노트**: `ontology_mapping.json`·`chain_rules.json`·`transfer_plan_config.json`,
  `server/mappers/` 아래 두 파일은 설계상 gitignore돼 있다 — 이미 돌고 있는 배포는
  이 커밋과 같은 편집을 **손으로** 적용해야 한다. `.sample` 파일만 저장소로 나간다.
- 5개 config 중복 보고 중 **하나만** 이 메커니즘으로 해소됐다(좌표가 더는 어떤 plan
  config에도 철자되지 않는다) — 나머지 넷은 각자의 편집이 따로 필요했다는 것이
  이 커밋 자신의 「정직한 집계」다.
