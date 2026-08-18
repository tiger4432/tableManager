# Ledger 온톨로지 Config Root

> 상태: 단일 파일 (`setup_version: 3`) — 2026-08-18
> 로더/컴파일러: `server/ledger/setup_bundle.py` → `server/ledger/setup.py`

이 디렉터리는 셋업의 정본이고, **파일은 하나다.**

```text
server/config/ontology/
├─ ledger_config.json      ← 셋업의 전부
└─ README.md               ← 이 파일
```

🔴 **이 root에 다른 `.json`이 있으면 로드가 거절된다**(`unlisted_config_file`). 검사는 **하위
디렉터리까지 재귀로** 본다 — 그래서 「원본은 옆에 둬야지」 하고 root **안에** 백업 폴더를
만들면 바로 걸린다. 백업은 **root 밖에** 둔다.

## `ledger_config.json`의 칸

필수 여덟, 그리고 선택 하나.

| 칸 | 담는 것 |
|---|---|
| `tables` | 물리 relation·column·key·index **사실** |
| `vocabulary` | 술어 |
| `entities` | 개체 유형과 그 identity key |
| `packs` | 술어 묶음 |
| `source_preparers` | 원본 행을 프레임으로 만드는 준비기 **선언** |
| `mappers` | 업무 해석 **선언** |
| `profiles` | 준비기·매퍼·팩의 조합 |
| `sources` | 무엇을 기록할지 |
| `virtual_joins` | *(선택)* 물리 join 계약 |

**선언이 곧 활성화다.** `sources`에 있으면 돈다. 켜고 끄는 스위치는 따로 없다 — 예전에
`dataflows/chains.json`이 그 역할이었고 은퇴했다.

## 파이썬 없이 소스 하나 세우기

범용 구현 `direct-join@1`(준비기)과 `declarative-role@1`(매퍼)만 쓰면 **코드 0줄로** 소스가
원자를 낸다. 업무 해석이 필요한 소스만 매퍼 파일을 하나 더 쓴다 —
`server/mappers/ledger_v2_*.py`에 파일 하나를 두면 되고, **어딘가의 목록에 이름을 등록할
필요는 없다.** 구현 클래스가 자기 id와 버전을 스스로 선언한다.

선언에 `module`·`function`·`path` 같은 키는 **쓸 수 없다.** config가 임의의 파이썬을 부르지
못하게 하는 경계이고, 그래서 config에는 **이름만** 적힌다.

## 확인

쓰기 없이 지금 상태만 본다:

```text
conda run -n assy_manager python -m ledger.setup
```

`readiness`·`setup_version`·`snapshot_sha256`·`sources`를 JSON으로 돌려준다.

## 옛 다섯 파일은 어디에 있나

2026-08-18 이전에는 `manifest.json`이 열거하는 다섯 파일이었다. 지우지 않고 옮겨 뒀다:

```text
server/config/_ontology_pre_single_file_20260818/
```

옮기는 도구는 `server/scripts/convert_ontology_to_single_file.py`이며(`--root` / `--out`),
**원본을 지우지 않고** 새 파일을 쓴 뒤 무엇이 어디로 갔는지 표로 출력한다.

`--legacy` CLI 플래그와 legacy 번역기는 은퇴했다. 실행 경로는 하나다.

⚠️ **이 config를 로드하거나 dry-run하는 것은 DB reset·cursor reset·백필을 부작용으로도
실행하지 않는다.**
