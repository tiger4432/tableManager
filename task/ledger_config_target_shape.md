# [Spec] 온톨로지 셋업 — 목표 파일 모양 (단일 파일)

> **마감:** 2026-08-18 오전 내 (소유자 지시)
> **목표 한 줄:** 셋업하는 사람이 **파일 하나**를 열고 닫으면 끝난다.
> 상위 문서: `task/ledger_simplification_program.md` · `task/ledger_config_single_file_pending.md`

## 결론 먼저 — 최종 모양

```text
server/config/ontology/
└─ ledger_config.json      # 이것 하나
```

`manifest.json` · `catalog/` · `dataflows/` 는 사라진다. 경로는 **바꾸지 않는다** — 소유자가
오늘 오전 내내 그 자리에 손으로 썼고, 자리를 옮기면 익힌 것이 한 번 더 헛돈다.

## 파일 안의 모양

```jsonc
{
  "setup_version": 3,

  "tables":            { /* 종전 catalog/tables.json 의 tables */ },
  "vocabulary":        { /* 그대로 */ },
  "entities":          { /* 그대로 */ },
  "packs":             { /* 그대로 */ },
  "source_preparers":  { /* 그대로 */ },
  "mappers":           { /* 그대로 */ },
  "profiles":          { /* 그대로 */ },
  "sources":           { /* 그대로 */ }
}
```

여덟 칸이고, **전부 필수**다(비어 있어도 키는 있어야 한다 — 종전과 같은 규칙).
`schema_version`은 사라지고 `setup_version` 하나가 파일 전체의 문법 세대를 말한다.

## 사라지는 것과 그 이유

| 사라지는 것 | 이유 |
|---|---|
| `manifest.json` | 파일이 하나면 열거할 것이 없다 |
| `dataflows/chains.json` | 스위치의 한쪽(`legacy`)이 어디로도 연결돼 있지 않고, `parity_status`는 대조되지 않는 문자열이다. **선언이 곧 활성화**로 대체 |
| `dataflows/enrichments.json` | 소비자 0. 스냅샷 해시에만 들어가 커서만 막았다 |
| `catalog/virtual_joins.json` | 규칙을 켜면 오히려 실행이 거절된다(검증된 조인 공급 경로가 항상 비어 있음). 기능을 실제로 살릴 때 새 섹션으로 다시 도입 |
| 각 파일의 `schema_version` | `setup_version` 하나로 통합 |

## 선언이 곧 활성화다

`sources`에 있으면 돈다. 별도 스위치를 두지 않는다.

「선언은 했는데 아직 돌리기 싫다」는 이미 막혀 있다 — 프로필 바인딩이 하나라도 `approved`가
아니면 로드 자체가 거절되므로 **작성 중인 소스는 원래 못 돈다**. 스위치를 하나 더 둘 이유가
없다. 정말로 「완성됐지만 지금은 끄고 싶다」가 필요해지면 그때 `sources.<id>.enabled`로
**그 소스의 선언 안에** 둔다. 별도 파일로 다시 가르지 않는다.

## 변환기

`server/scripts/`에 일회성 변환기를 둔다.

- 입력: 기존 5파일 루트. 출력: 새 단일 파일.
- **원본을 지우지 않는다.** 새 파일을 쓰고, 무엇이 어디로 갔는지 표로 출력한다.
- 변환 후 **원자 디프 0**을 확인하기 전에는 기존 파일을 손대지 않는다.
- `chains`/`enrichments`/`virtual_joins`에 **비어 있지 않은 내용**이 있으면 조용히 버리지 말고
  이름을 대고 멈춘다. 지금 라이브는 셋 다 비어 있으므로(chains는 lot_event 선택자 하나뿐)
  실제로는 통과한다.

## 합격 기준

- [ ] `server/config/ontology/ledger_config.json` 하나로 로드·컴파일·실행된다
- [ ] **원자 디프 0** — `task/evidence/ledger_atom_diff.py`로 확인(해시는 비교 대상 아님)
- [ ] 선언한 소스가 별도 스위치 없이 돈다
- [ ] 실행과 무관한 칸을 고쳐도 커서가 막히지 않는다
- [ ] 변환기가 기존 루트를 그대로 둔 채 새 파일을 만든다
- [ ] Explorer가 읽는 섹션 목록이 여덟 칸과 일치한다(chains가 화면에 없던 문제도 함께 소멸)

## 오전 내 범위에서 **뺀 것**

마감 안에 넣지 않는다. 간소화의 본체가 아니고, 지금 넣으면 위 합격 기준의 증명이 흐려진다.

- legacy 사체 제거(`--legacy` 플래그, `ledger/config.py`) — 진입점은 이미 막혔다
- 수집 오류 8건 정리
- Explorer 작성 모드(3라운드)
- 워커의 행별 도장 셋

이 넷은 마감 뒤 순서대로 이어 간다.
