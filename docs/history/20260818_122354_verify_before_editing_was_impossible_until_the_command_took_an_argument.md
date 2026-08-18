# 「고치기 전에 확인하라」는 명령이 인자를 받기 전까지 지킬 수 없는 규칙이었다

**날짜:** 2026-08-18 12:23 / 12:24 · **커밋:** `4ff500e` → `279689e` · **레인:** 서버 + 문서(원장 셋업 경계)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경

`docs/guide/ONTOLOGY_LEDGER_SETUP.md`는 운영자에게 **고치기 전에 검증하라**고 지시한다.
그런데 검증 명령 `python -m ledger.setup`은 `DEFAULT_ONTOLOGY_ROOT`에 하드와이어돼 있었고
인자를 하나도 받지 않았다. 그러니 초안을 검증하는 **유일한** 방법은 운영 파일을 먼저
덮어쓰는 것이었다 — 그 문서가 금지하는 바로 그 순서다.

즉 가이드의 규칙과 도구의 능력이 어긋나 있었고, 운영에서는 안전한 순서를 **따를 수가
없었다.** 규칙이 느슨해서가 아니라 그것을 실행할 손이 없었다.

## `4ff500e`가 한 일

`--root <디렉터리>`가 **같은 읽기 전용 검증을 아무 config root에나** 겨눈다. 생략하면
동작은 종전 그대로 운영 root이고, 그 「그대로」는 가정이 아니라 테스트로 단언된다.
`load_setup()`이 이미 root를 받고 있었으므로 실제 변경은 **인자와 그 거절들과
테스트**다(`server/ledger/setup.py` 185 → 251줄).

**하중을 지는 부분은 응답의 `config_root`다.** 어떤 파일에 대한 PASS였는지 말할 수 없는
운영자는 안전한 경로를 얻은 것이 아니다. 그래서 초안 실행이 운영 root가 아니라 초안을
이름으로 지목하는지를 테스트가 단언한다.

**인자를 틀리는 세 방식이 던져지는 대신 이름으로 거절된다.** 초안을 겨누는 운영자는
셋 다 만나기 때문이다 — 없는 경로, `ledger_config.json`이 없는 디렉터리, 그리고
**디렉터리 대신 파일 자체를 가리키는 것**. 마지막 것은 「root」라는 낱말이 명백히
배제하지 않는 독법이라 메시지가 그렇게 말해 준다. 셋 다 stderr에 한 줄을 찍고 종료코드
2로 끝나며 보고서를 인쇄하지 않는다.

🔴 **거절 처리는 `--root` 인자 자체에만 걸려 있다.** 나쁜 config는 여전히 raise한다 —
그것이 검증의 **답**이고, 곱게 정리해 버리면 실패한 검증이 통과처럼 읽힌다.

수정된 초안을 검증한 뒤에도 운영 `ledger_config.json`이 **바이트 단위로 동일**하다는
것을 테스트가 단언한다. docstring의 약속이 아니라 파일에 대한 사실로.

## `279689e`가 한 일

가이드 §13.2 — **그 규칙이 물었던 바로 그 자리**에 `--root`를 적었다. 어느 경로를 받는지
(**파일이 아니라 디렉터리**), 답의 `config_root`가 초안 검증과 운영 검증을 가르는 값이라는
것, 초안 검증이 운영 파일을 건드리지 않는다는 것.

## 검증

기록자가 네 경로를 직접 돌렸다(`server` 디렉터리에서). 초안 root는 운영
`ledger_config.json`을 임시 폴더로 복사해 만들었다.

```powershell
conda run -n assy_manager python -m ledger.setup                    # 운영 root
conda run -n assy_manager python -m ledger.setup --root <초안폴더>
conda run -n assy_manager python -m ledger.setup --root <초안폴더>/ledger_config.json
conda run -n assy_manager python -m ledger.setup --root <없는경로>
conda run -n assy_manager python -m ledger.setup --root <빈폴더>
```

- 인자 없는 실행: `readiness: "ready"`, `setup_version: 3`, `sources`에 `lot_event` 하나,
  `destructive_actions` 셋이 전부 false. `config_root`가 운영 root를 가리킨다.
- `--root <초안폴더>`: 같은 `snapshot_sha256`, 그러나 `config_root`가 **초안 폴더**를
  가리킨다 — 이 값 하나가 초안 검증과 운영 검증을 가른다.
- 파일을 가리킨 경우:
  `--root: …\ledger_config.json is a file — point --root at the directory that CONTAINS it, not at the file`
- 없는 경로: `--root: no such path: …`
- config 없는 폴더: `--root: … holds no ledger_config.json`

커밋 본문의 원자 기준선 CASE DIFF 0 · 불변식 로케이터 10/10은 기록자가 재실행하지
않았고 **커밋의 주장**으로 남긴다.

## 그때 남아 있던 것

- ⚠️ **거절 메시지의 em dash가 cp949 콘솔에서 깨진다.** 위 「is a file — point …」의
  대시가 이 상자에서는 대체 문자 세 개로 찍혔다. 메시지 자체는 읽히지만 운영 콘솔의
  인코딩이 다르면 그 자리가 지저분해진다. 코드 변경이라 문서 레인이 손대지 않았다.
- `docs/process/FORK_SESSION_BRIEF.md`의 「다음 합법적 작업 순서」는 **운영 파일을 먼저
  고치고 그다음 검증**하라고 적고 있었다 — `--root`가 없애려던 바로 그 순서다. 이 두
  커밋은 그 문서를 손대지 않았고, 뒤따른 문서 정비 라운드가 고쳤다.
- 셋업 경계의 파괴적 동작(reset·replay·migration)은 여전히 이 명령에 없다.
  `destructive_actions`가 전부 false로 보고되는 것이 그 계약이다.
