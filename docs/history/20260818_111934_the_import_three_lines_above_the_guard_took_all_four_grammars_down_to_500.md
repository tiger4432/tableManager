# 가드보다 세 줄 위에 있던 import가 네 문법 전부의 드라이런을 500으로 만들었다

**날짜:** 2026-08-18 11:19 · **커밋:** `ab8657f` · **레인:** 서버(원장 단순화 2라운드)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경

같은 날 `e47d325`가 v1 번역기 다섯을 은퇴시켰다. `server/ledger/dry_run.py`는 그 은퇴
목록에 없었지만, 네 개의 `_preview_*` 함수가 **함수 본문 첫 줄들에서** 그 번역기들을
지연 import하고 있었다.

지연 import는 보통 「필요할 때만 무겁게」를 뜻하지만 여기서는 **가드보다 먼저 실행되는
것**을 뜻했다. `_preview_lineage`의 경우 `from mappers.ledger_lot_event_mapper import
group_lot_event_frames`가 `configured_mapper(source_cfg)` 가드보다 **세 줄 위**에 있었다 —
「설정된 매퍼가 있으면 옛 번역기는 안 쓴다」는 분기가, 옛 번역기를 **이미 import한 뒤에**
평가됐다.

커밋 본문이 적은 측정 방법이 이 순서를 못 박는다: `_preview_lineage`에 **모든 인자를
`None`으로** 넣어 부르면 인자 오류가 아니라 `ModuleNotFoundError`가 났다. 즉 import가 먼저
탄다. 결과는 가드 뒤에 숨은 부분 고장이 아니라 **네 문법(`lineage`·`observation`·
`declared`·`transfer`) 전부에 대한 `POST /admin/ledger/dry-run` 500**이었다.

## 이 커밋이 한 일

죽은 dispatch와 네 `_preview_*` 본문을 지우고, `preview()`가 `DryRunUnavailable`을 던지게
했다. `main.py`는 그 예외를 **이미** `declaration_rejected` 거절로 렌더하고 있었으므로
라우트 쪽 변경은 없다. 파일은 **596 → 179줄**이 됐다(`git show ab8657f^:server/ledger/
dry_run.py | wc -l` / 같은 명령의 `ab8657f`).

기록자가 현재 트리에서 실제로 던져지는 문장을 확인했다.

```
REFUSED_KO: 'lot_event' 드라이런을 실행할 번역기가 없습니다 — v1 번역기 4종이
2026-08-18에 은퇴했고, v2 미리보기는 아직 이 화면에 연결되지 않았습니다.
선언 검증(1단)과 저장(3단)은 그대로 동작합니다.
REFUSED_EN: no executor for dry-run of source 'lot_event': the v1 translators were
retired on 2026-08-18 and the v2 preview is not wired to this route yet
```

**이것은 미리보기의 복구가 아니고, 복구인 척하지도 않는다.** `ledger.setup
.preview_selected_cursor_batch`는 쓰기 0으로 같은 일을 이미 할 수 있고 원자 기준선 하네스가
그것을 몬다 — 다만 **그것을 부르는 HTTP 라우트가 없다.** 그 배선이 진짜 수리이고, 그
사실이 `preview()`의 docstring에 이름으로 적혔다.

## 남긴 것과 그 이유

- **`begin_read_only`는 남았다.** 「쓰기 0」을 약속이 아니라 **구조**로 만드는 자리이기
  때문이다 — `SET TRANSACTION READ ONLY`를 건 뒤 `SHOW transaction_read_only`로 PostgreSQL
  자신에게 되묻는다. v2 미리보기가 배선될 때 필요한 것이 정확히 이것이다. 이 함수를
  거는 PostgreSQL 테스트 둘도 함께 남았다.
- **세 번째 드라이런 PG 테스트는 죽었다.** 「원자를 «만들면서» 원장 행 수와 커서를 그대로
  두는가」를 보던 유일한 팔이고, 보장의 구현 방식에 무관심했다는 점에서 셋 중 가장 좋은
  단언이었다. 그것이 은퇴한 번역기를 몰았기 때문에, **초록으로 읽히는 문장으로 약화되는
  대신 여기서 함께 죽었다.** 테스트 파일이 그 사실을 제자리에 적어 두었으므로 v2
  미리보기를 배선하는 사람이 이 팔을 되살릴 것을 안다.
- 부수 효과 하나가 커밋 본문에 이름으로 적혔다: `ledger/dry_run.py`는 이제
  `ledger/config.py`를 **한 번도 import하지 않는다.** `config.py` 호출자 목록에서 스스로
  빠진 것이다.

## 아키텍처 영향

원장 셋업 화면의 **2단(미리보기)이 내려갔고, 그 사실이 화면에 문장으로 뜬다.** 500과
「지금은 못 한다」는 운영자에게 전혀 다른 답이고, 이 커밋이 바꾼 것은 후자로 바꾼 것뿐이다.

## 검증

- 커밋 본문 주장: 원자 기준선 CASE DIFF 0, 불변식 로케이터 10/10(0 손실), 수집 4,511 무변동.
  ⚠️ 기록자는 이 셋을 **커밋의 주장**으로 남긴다(재실행하지 않았다).
- 기록자가 직접 확인한 것: 현재 트리에서 `dry_run.preview(None, None, "lot_event")`가
  `DryRunUnavailable`을 던지고 위 두 문장을 싣는다. 줄 수 596 → 179도 두 리비전에서 각각
  셌다.

## 그때 남아 있던 것 — 그리고 판정이 필요한 자리

- 🔴 **거절문의 「저장(3단)은 그대로 동작합니다」는 `source` 타깃에 대해 거짓으로 보인다.**
  `POST /admin/ledger/save`는 `declaration_token(target, name, declaration)`과 **같은 값의
  토큰**을 요구하고(`server/ledger_admin.py`), 그 토큰은 드라이런 응답으로만 화면에
  건네진다. `source` 타깃의 드라이런은 이제 항상 거절하므로 토큰이 발급되는 지점이
  없고, 저장은 `dry_run_stale`로 막힌다. `predicate` 타깃은 `_ledger_predicate_dry_run`이
  `preview()`보다 **앞에서** 반환하므로 영향이 없다. **총괄 판정 대상**이다 — 문서로 고칠
  수 있는 것이 아니다.
- `server/ledger/dry_run.py`의 **모듈 docstring 최상단은 이 커밋이 손대지 않았다.** 여전히
  「실제 번역기를 읽기 전용 트랜잭션에서 태운다」·「무엇을 재사용하는가」를 현재형으로
  설명한다. `preview()`의 새 docstring과 같은 파일 안에서 어긋나 있다.
- `server/main.py`의 `post_ledger_dry_run` docstring도 같은 이유로 낡았다 — 「🔴 실제
  번역기를 태운다」가 그대로다. 코드 주석이라 문서 레인이 고치지 않았다.
- v2 미리보기(`ledger.setup.preview_selected_cursor_batch`)를 라우트에 잇는 일은 이 커밋
  범위 밖에 그대로 남았다.
