# The switch saved no disk read, and none of the 35 minutes is the ledger

**Date:** 2026-08-13 10:58 · **Domain:** Server (인제션 / 원장) · **Status:** 착지 — `ba664c5`

> ⚠️ **모든 수치는 이 개발 워크스테이션과 그 위의 개발용 `assy_manager` 실측이다.
> 운영의 증거가 아니다.**

---

## 배경 — 요구는 한 줄이었고, 스위치 하나가 아니었다

요구: **처리한 파일을 옮기지 말 것. 재처리는 원장과 대조해 막을 것.**

기존에 `dedup_by_signature`가 있었으므로 스위치를 끄면 되는 일처럼 보였다. **아니었다.**
그리고 그 이유가 둘인데, 둘 다 코드가 이미 알고 있던 것이다.

## 이미 있던 것은 «의미»의 절반이었고 «비용»의 절반은 줄 수 없었다

**시그니처가 게이트를 묻기 «전»에 무조건 계산되고 있었다.** 그래서 그 스위치는 디스크
읽기를 **한 번도** 아껴 준 적이 없다.

그리고 더 중요한 것 — **기존 skip이 «옮기기»에 의존하고 있었다.** skip 경로 자신이 파일을
아카이브로 옮기고, 그 이유가 코드에 적혀 있었다: **옮기지 않으면 스윕이 같은 파일을 영원히
집어 든다.**

> **코드가 이미 「옮기기 없이는 skip이 종료하지 않는다」고 적고 있었다.**

그래서 종료 논증을 물려받을 수 없었고, **원장 위에서 새로 세워야** 했다.

## 실측 — 파일이 안 옮겨지면 `raws/`가 되는 바로 그 집합에서

```
    listdir + stat   1.0 s      (575 files/s hashing is per-FILE-bound, not
    full sha256     39.4 s       byte-bound: 4.9 MB/s over many small files)
```

22,626 파일 / 194.6 MB — 오늘 `archives/`가 들고 있는 것, 즉 파일이 안 옮겨질 때 `raws/`에
쌓일 바로 그 집합이다.

🔴 **해시 속도가 4.9 MB/s다. 같은 모듈이 자기 상단에 적어 둔 수는 `~935MB/s`였다.**

```python
   sha256이 blake2b보다 2배 빠르다(CPU의 SHA 확장 명령 사용, ~935MB/s). 라이브 드릴
```

**그 수는 «큰 파일 한 장»에서 잰 것**이고, 작은 파일이 많으면 파일당 open 오버헤드가
**~190배로 지배**한다. 그 간극이 1단(tier 1)을 만들 값어치의 전부다. 정정이 **정정 대상
문장에서 30줄 아래**, 같은 파일 안에 앉았다.

## 🔴 그런데 정직한 수는 스윕이 아니다

1단 적중이 **파일당 ~92 ms**이고, 프로세스 재기동 후 첫 스윕으로 환산하면 **~35분**이다.

**그중 어느 것도 원장이 아니다** — 파일마다 `SessionLocal()`을 새로 열고,
`_snapshot_table_context()`가 `table_config.json`을 **파일마다 디스크에서 다시 읽는다.**

살아 있는 프로세스는 **1.0 s 스윕만** 낸다 — 메모리 스윕 캐시가 안 바뀐 파일을 아예
디스패치하지 않기 때문이다. 그래서 **35분은 매 주기가 아니라 재기동당 한 번**이다. 1단은
그래도 13배 절감이고 skip 경로에서 순수 디바운스 대기 6.3시간을 걷어낸다.

권고된 후속(스윕이 이미 들고 있는 `stat`으로 1단 조회를 끌어올려 배치)이 **1단 자체보다 큰
이득**인데, 이 커밋은 그것을 **가져가지 않고 판정에 남겼다.**

## 승격을 «선언»했다 — SCHEMA_CANON R6

`filepath`가 표식이기를 그만둔다. 인덱스 `idx_fic_path_stat`, stat 세 컬럼은 **전부
nullable**로 남긴다 — SQL `=`는 NULL에 대해 참이 될 수 없으므로 **NULL 행은 1단을 만족할
수 없고 전체 해시로 떨어진다.** 안전한 방향이고, 마이그레이션 이전의 모든 행이 하는 일이다.

**일부러 UNIQUE가 아니다**: 한 경로가 시간에 따라 다른 내용을 담으므로 `(table_name,
filepath)` 유일 제약은 정당한 갱신을 거절한다. 그래서 1단은 **전순서로 읽는다**(R7).

`mtime` 변환도 판정이었다:

```python
def mtime_ns_to_datetime(mtime_ns: int) -> datetime:
    """`st_mtime_ns` -> tz-aware UTC datetime **truncated to whole microseconds**.
    ...
    """
    return _EPOCH_UTC + timedelta(microseconds=int(mtime_ns) // 1000)
```

float `datetime.fromtimestamp`가 아니라 **정수 산술**이다 — 비트 단위로 재현되지 않는
값은 **조용히 빗나가고**, 빠른 경로가 **에러 없이 존재하기를 멈춘다.** SQLite와
PostgreSQL 양쪽에서 왕복 검증했고 **+1 µs 고장이 양쪽에서 정확히 miss**하는 것도 확인했다.

## 🔴 마이그레이션이 최적화가 아니라 «선행 조건»이다

마이그레이션 안 된 DB에서는 전체 엔티티 SELECT가 `UndefinedColumn`을 낸다 — **원장을
읽는 것조차 실패한다.** 워처는 살아남는다(원장 호출 세 곳이 각각 잡아서 로그한다). 그런데
**체크포인팅과 dedup을 통째로 꺼서** 살아남고, 그것이 no-move와 겹치면 **모든 파일이 매
스윕마다 재적재된다.**

이 박스의 개발용 `assy_manager`에 마이그레이션을 돌렸다(13,968행 보존, 두 컬럼과 인덱스를
`information_schema`에서 확인). 로컬 config가 이미 새 모드였기 때문이다.

그리고 **아무도 경고받지 못했을 이유**가 같이 고쳐졌다:

```python
# `*.sql` added 2026-08-13, and it is the SAME failure the comment above records,
# one file extension over. `add_ingestion_ledger_path_stat.sql` adds two columns
# to `file_ingestion_checkpoints`; without this line the banner said "no
# migration is recorded for this column - add one" while the migration that owns
# them sat in the tree. It went unnoticed until now because every earlier `.sql`
# migration here creates INDEXES, and this check does not look at indexes at all,
# so a `.sql` file had never owned a finding before.
```

**드리프트 스캔이 `*.py`만 글롭했다.** 배너가 「이 컬럼에 기록된 마이그레이션이 없다」고
말하는 동안 마이그레이션은 트리 안에 있었다. 여기서도 **술어가 대상을 놓친 것**이지 기전을
오해한 것이 아니다.

## 「무엇이 실패했나」가 살던 자리가 바뀌었다

그 사실은 파일의 **위치**(`err/`)에 살고 있었다. 이제 원장에 산다 — `status='FAILED'`,
경로, `note`의 짧은 사유, 그리고 전체 트레이스백은 여전히 인제션 로그에.

판단 셋을 가정하지 않고 적었다.

```python
# States that mean "I have already reached a terminal answer about this exact
# file". Tier 1 skips on these; tier 2 (content dedup) still skips on DONE only.
TERMINAL_STATUSES = (STATUS_DONE, STATUS_FAILED)
```

- **1단은 DONE «또는» FAILED에서 skip, 2단은 DONE에서만 skip.** 하나는 「이 «파일»에 대해
  종결된 답에 도달했다」이고 다른 하나는 「이 «내용»을 이미 적재했다」다.
- **잠긴 파일의 소진은 봉인하지 않는다** — 일시적이기 때문이다.
- **읽을 수 없는 파일은 `sha256:`이 아니라 `stat:`으로 키를 잡는다** — 내용 시그니처와
  절대 혼동되지 않도록. 표식을 열쇠로 눌러 담은 것이 아니라 **선언된 키**다(R6).

그리고 1단의 실패 방향을 **아무도 다시 발견하지 않아도 되게** 적어 두었다: mtime과 크기가
같은 채로 내용이 바뀐 파일을 **다시 안 읽는 쪽**으로 실패한다. 도달 가능한 상황이고
(mtime을 보존하는 복사 도구, 같은 마이크로초에 같은 길이로 다시 쓰기), **거래이지 공짜가
아니다.** 탈출구 둘(`dedup_by_path_stat: false`, 파일명 `__force__`)이 계속 돌아야 한다.

## 멱등성 — 그리고 «검사가 실패할 수 있음»을 증명한 고장 여섯

새 워처로 안 바뀐 트리를 연속 두 번 스윕: **해시 0, 적재 0, 행 0, 원장 행 0, 로그 행 0.**

**고장난 스윕도 0을 보고한다.** 그래서 고장 여섯을 주입해 각각이 옳은 테스트를 빨갛게
만드는 것을 확인했다.

🔴 **그 주입이 자기 테스트 하나가 «틀린 이유로» 통과하고 있던 것을 잡아냈다** — 파일이
아카이브로 치워져 있어서 두 번째 호출이 할 일을 못 찾아 초록이었다. 고쳤고, 그 함정을
파일 안에 적었다.

이 변경이 «만든» 결함 둘도 찾아서 고쳤다 — 1단 적중이 아카이브 재시도를 단락시켜 이동에
실패한 파일이 영원히 남았고, 파일 중간 크래시가 이제 FAILED로 봉인된다(그것이
「`err/`로 옮김, 자동 재시도 없음」의 충실한 번역이다).

## 빨간 여섯은 이 변경 것이 아니다 — 그리고 그것을 증명했다

이 박스에서 6건이 빨간데 **어느 것도 이 변경에 관한 것이 아니다.** 두 파일이 격리본이
아니라 **운영자의 실제 `ingestion_settings.json`을 읽는다.** 그 파일을 옆으로 치웠다가
되돌리는 것으로 증명했다:

| | |
|---|---|
| 설정 파일 없음 | **214 passed / 0 failed** |
| 설정 파일 있음 | **208 passed / 6 failed** |

수리는 공유 테스트 인프라 소관이라 **표시만 하고 안 가져갔다.**

## 그때 남아 있던 것

- **`.sample`은 오늘 동작 그대로다.** 운영 의도는 운영자가 판정하기 전까지 안 바뀐다.
  손복사 단계와 롤백 순서는 가이드에 있다.
- **파일당 ~92 ms 디스패치 오버헤드는 안 고쳤다.** 원장이 아니라 세션·config 재독이고,
  1단보다 큰 후속이 **판정 대기**로 남았다.
- **이 박스의 개발용 `assy_manager`에만 마이그레이션을 돌렸다.** 다른 DB는 안 돌렸다.
- 테스트 6건이 **운영자 실제 설정 파일에 의존해 빨갛다.** 표시만 됐다.
- 22,626 / 194.6 MB / 4.9 MB/s / ~92 ms는 **이 워크스테이션 한 대의 수**다. 운영 파일
  크기 분포가 여기와 같다는 근거는 이 라운드에 없다.
