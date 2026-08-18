# 다섯 파일 루트가 한 파일이 됐고, 변환기는 버리는 대신 거절했다

**날짜:** 2026-08-18 09:09~10:32 · **커밋:** `8f2fd36` `9f696ad` `92b204f` `313ce72`
`141d95e` `caba302` `b4c5870` `382b78c` `d7a2c91` · **레인:** 서버(원장 단순화 1라운드)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경 — 목표 한 줄이 마감을 정했다

`task/ledger_config_target_shape.md`(`8f2fd36`)가 오전 마감을 이렇게 적었다.

> **셋업하는 사람이 «파일 하나»를 열고 닫으면 끝난다.**

그때까지 온톨로지 루트는 세 디렉터리에 다섯 파일이었다 — `manifest.json`이 나머지를
열거하고, `catalog/tables.json`·`catalog/virtual_joins.json`·`dataflows/chains.json`·
`dataflows/enrichments.json`이 각자 자기 `schema_version`을 들고 있었다.

**경로는 안 옮겼다.** 목표 문서가 이유를 적었다 — 소유자가 그날 오전 내내 그 자리에 손으로
썼고, 자리를 옮기면 익힌 것이 한 번 더 헛돈다.

## 사라진 것과 그 이유 — 「비어 있어서」가 아니다

| 사라진 것 | 목표 문서가 적은 이유 |
|---|---|
| `manifest.json` | 파일이 하나면 열거할 것이 없다 |
| `dataflows/chains.json` | 스위치의 한쪽(`legacy`)이 어디로도 연결돼 있지 않고 `parity_status`는 **대조되지 않는 문자열**이다 |
| `dataflows/enrichments.json` | 소비자 0. 스냅샷 해시에만 들어가 커서를 막았다 |
| `catalog/virtual_joins.json` | 규칙을 켜면 오히려 실행이 «거절»된다 — 검증된 조인 공급 경로가 항상 비어 있다 |
| 파일마다의 `schema_version` | `setup_version` 하나가 문법 세대를 말한다 |

`parity_status: approved`가 영구히 증명 불가가 된 경위는 같은 날 legacy 은퇴가 만들었다.
대조 대상인 v1 번역기가 사라져 `test_ledger_v2_lot_event_parity`가 잴 것이 없어졌고,
그 사실이 chains 제거 판정을 뒷받침한 근거로 프로그램 문서에 적혔다.

## 「선언이 곧 활성화」와, 그 때문에 변환기가 거절해야 했던 것

`sources`에 있으면 돈다. 별도 스위치를 두지 않는다 — 「선언은 했는데 아직 돌리기 싫다」는
이미 막혀 있기 때문이다. 프로필 바인딩이 하나라도 `approved`가 아니면 로드 자체가 거절되므로
**작성 중인 소스는 원래 못 돈다.**

그런데 이 규칙이 변환기를 위험하게 만든다. `server/scripts/convert_ontology_to_single_file.py`의
docstring이 그 위험을 이름으로 적었다:

```
A selector saying anything ELSE is a decision somebody made that would silently invert --
a source marked `legacy` would START RUNNING the moment the switch disappears, because
declaration becomes activation. That is refused.
```

즉 **은퇴하는 선택자를 「비어 있으니 버린다」로 처리하면 꺼져 있던 소스가 켜진다.**
`mode: "v2"`인 항목만 접어 없앨 수 있고(그건 목표 모양의 기본값과 같은 말이다), 그 외 값은
멈춘다. 변환기는 **아무것도 지우지 않는다** — 새 파일을 쓰고 무엇이 어디로 갔는지 표로 찍고,
교체는 원자 디프를 확인한 운영자의 몫으로 남긴다.

그 설계가 만든 부작용도 docstring에 적혔다. 새 로더는 그 파일 하나 말고 다른 JSON이 있는
루트를 **이름을 대고 거절한다**(`unlisted_config_file`). 그래서 **변환 직후의 루트는 로드되지
않는다** — 원본이 아직 옆에 있기 때문이다. 그건 단일 파일 약속이 작동하는 모습이지 실패가
아니다.

## 섹션을 파일에서 빼는 것과 로더에서 빼는 것은 다른 행위다

`virtual_joins`는 `LOGICAL_SECTIONS`에서 빠졌지만 `OPTIONAL_SECTIONS`로 남았다. 코드가
그 구분을 자기 자리에서 설명한다.

```python
#: 🔴 OPTIONAL, AND THE DISTINCTION IS DELIBERATE.  The operator root stops carrying a
#: `virtual_joins` section ... But the LOADER keeps the ability to read one, because a
#: different root does use it: `server/config/sample/ontology/transfer_explorer/` ...
#: Removing the section from a FILE and removing support from the LOADER are not the same
#: act, and only the first was asked for.
OPTIONAL_SECTIONS = ("virtual_joins",)
```

그리고 「없는 키」와 「빈 키」가 갈라지지 않도록 **한 자리에서 한 번** 메꾼다 — 뒤의 독자들이
`.get()`으로 각자 처리하면 「조인 없음」과 「조인 섹션 없음」에 대해 두 독자가 다른 답을 갖게
된다.

## 게이트는 해시가 아니라 «원자 케이스»였다

`92b204f`가 그 판정을 도구로 만들었다(`task/evidence/ledger_atom_diff.py`).

> 해시는 컴파일된 레지스트리를 덮으므로 **컴파일러를 리팩터링하면 원장이 똑같은 문장을
> 말하는데도 움직인다** — 그날 실측 `363c693e → fd51baaf`, 케이스 디프 0.

같은 커밋이 **기준선을 뜬 그 손수 작성 config를 함께 커밋했다.** 그때까지 그 파일은 작업
트리에만 있었다 — 즉 그 시점까지의 기준선은 커밋되지 않은 입력에서 나온 것이었다.

## 하네스가 자기가 재는 대상의 개명에서 살아남은 방법

`313ce72`. 기준선 하네스는 `from ledger.cutover_v2 import ...`로 진입점을 고정 import하고
있었는데, **그 모듈명을 바꾸는 것이 바로 이 라운드의 리팩터링**이었다.

```python
_MODULES = ("ledger.setup", "ledger.cutover_v2", "ledger.setup_boundary")
...
raise SystemExit(
    "BASELINE HARNESS BROKEN: no setup loader + preview entry point found.\n"
    ...
    "Fix this harness before reading any diff as a pass -- a harness that cannot "
    "run is not a zero diff.")
```

고정 import였다면 **게이트가 정확히 필요한 순간에 사라졌을 것**이고, 조용한 skip이었다면
「아무것도 안 바뀌었다」로 읽혔을 것이다. 그래서 탐색으로 찾고, 못 찾으면 시끄럽게 죽는다.

## 개명은 둘로 나눠 착지했다

`b4c5870`이 `ledger/setup.py`를 만들고 호출자를 옮겼고, `382b78c`가 `cutover_v2.py` 185줄을
지웠다. **한 커밋이 아니다** — 새 이름이 도는 것을 먼저 확인하고 옛 경로를 지운다.

`d7a2c91`은 그 뒤 테스트를 **파일 단위가 아니라 테스트 단위로** 정리했다.
`test_ledger_v2_cutover.py` → `test_ledger_setup_boundary.py`로 옮기면서, 사라진 기계장치를
재던 테스트만 빼고 경계를 재던 테스트는 살렸다.

## 아키텍처 영향

`server/config/ontology/`는 `ledger_config.json` 하나가 됐고(`caba302`), 샘플 루트도 같은
모양이 됐다(`141d95e`). `manifest_fields`는 공개 스키마에서 사라지고 `config_file` 하나가
그 자리를 대신했다. `forbidden_sections`에 `manifest`·`chains`·`enrichments`가 들어가,
옛 모양을 그대로 붙여 넣으면 **이름을 댄 거절**이 난다.

## 검증

- 커밋 본문 주장: 원자 케이스 디프 0(해시는 움직였고, 케이스로 판정했다).
  ⚠️ 기록자는 재실행하지 않았다 — **커밋의 주장**으로 남긴다.
- 기록자가 직접 확인한 것: 변환기·로더·`OPTIONAL_SECTIONS`의 위 문장들이 그 커밋의 diff에
  실제로 들어 있다는 것, `382b78c`가 `cutover_v2.py`를 통째로 지웠다는 것.

## 그때 남아 있던 것

- `9f696ad`이 옛 다섯 파일 루트의 **스냅샷을 `task/evidence/ontology_root_before_20260818/`에
  통째로 남겼다.** 「섹션이 옮겨진 것인지 잃어버린 것인지」를 뒤에 판정하기 위한 사본이다.
- 목표 문서가 **마감 밖으로 뺀 넷**을 명시했다 — legacy 사체 제거, 수집 오류 8건, Explorer
  작성 모드, 워커의 행별 도장. 「이 넷은 마감 뒤 순서대로 이어 간다」고 적혀 있고, 그날 밤
  실제로 첫 셋이 이어졌다.
- 이 시점의 `LOGICAL_SECTIONS`는 **여덟 칸**이다(`tables` 포함). 같은 날 오후 일곱으로
  줄어든다 — 그건 다른 커밋의 이야기다.
