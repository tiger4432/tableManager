# The 35 minutes was the walk to the question, not the question

**Date:** 2026-08-13 13:14 · **Domain:** Server (인제션 / 스윕) · **Status:** 착지 — `831ab68`

> ⚠️ **모든 수치는 격리 `assy_qa` 실측(2,001파일 / 52,001행 원장, 팔 교차, 중앙값 3회)이다.
> 22,626파일 트리와 ~92 ms/파일은 이 박스 측정이다. 운영의 증거가 아니다.**

---

## 배경 — 답이 맞았고 «묻는 자리»가 틀렸다

Tier 1은 「이 경로가 이 mtime·이 크기로 이미 종결됐나」를 묻는다. 그 답은 옳았다. 그런데 그 질문이
`_process_with_retry` **안**에 앉아 있었고, 그 지점은 이미 `os.stat`을 손에 든 두 호출자보다
**한 디스패치 아래**였다.

그래서 **HIT조차 그 자리에 도달하기 위해 파일당 파이프라인 전체를 지불했다** — 파일당
`SessionLocal()`, 파일당 디스크에서 `table_config.json` 재독(두 번), 파일당
`ingestion_settings.json` 재독. 측정: **HIT당 ~92 ms**, 22,626파일 트리에 **≈35분.**

그리고 **그 92 ms 중 어느 것도 원장이 아니다.** 그 파일들을 찾아내는 `listdir + stat`은
**1.0초**다.

## 이동한 것 — 배치로 묻고, 통과시킨 것을 «끝낸다»

`find_terminal_by_path_stat_batch`가 그 질문을 여러 파일에 대해 한 번에 묻고,
`settle_already_terminal`이 통과된 파일을 그 자리에서 마무리한다. 스윕과 트리 워크 둘 다 이미
stat을 들고 있으므로 **추가 syscall이 없다.**

실측(중앙값): 변경 없는 트리의 재기동 재스윕 **26.432초 → 0.602초**(13.21 → 0.30 ms/파일,
**43.9배**). 그중 신규/변경/`__force__` 파일 하나가 섞였을 때 31.0 / 31.2 / 28.5초 →
1.81 / 1.96 / 1.81초. **콜드 스윕은 1.0배로 변화 없음** — 그것이 「아무것도 건너뛰지 않았다」를
말하는 대조군이다.

## 술어를 다시 쓰지 않았다

각 파일이 단일 파일 질의가 만드는 것과 **동일한** `and_(filepath, file_mtime, file_size)` 삼중항을
기여하고, 같은 필터 아래 OR로 묶인다. 비교가 SQL에 남는다.

```
    **The predicate is not a re-derivation.** ... comparing the stat in Python instead
    would mean re-deriving how a `DateTime(timezone=True)` comes BACK from each
    backend (SQLite returns it naive, PostgreSQL returns it in the session's
    timezone), and a batch that gets that wrong either clears everything or
    clears nothing - both silent.
```

단일 파일 조회는 **손대지 않았고**, 배치가 통과시키지 않은 모든 것에 여전히 답한다. 어느 행이
이기는가도 같다 — 단일 조회가 부과하는 전순서를 청크 전체에 적용하고 경로당 첫 행을 남긴다.

## 배치 크기 500은 고른 것이 아니라 «잰» 것이다

2,001파일 기준 ms/파일: 50 → 0.37, 100 → 0.46, 250 → 0.41, 500 → 0.41, 1000 → 0.59,
2000 → 1.26. **전부 한 질의에 넣는 것이 500짜리 다섯 개보다 3배 나쁘다.** 먼저 무너지는 것은
PostgreSQL의 65,535 바인드 상한이 아니라 **OR arity에 따른 플래닝 비용**이다(파일당 바인드 3개,
청크당 ~1,500).

## 🔴 통과된 파일은 no-op이 아니다

종결된 파일이 아직 raws/에 앉아 있다면 그 **이동이 실패한 것**이고, 재시도를 떨어뜨리면 그
파일은 — 중첩 인제션이면 **그 디렉터리 통째로** — 영원히 거기 좌초한다. **이 결함은 tier-1 히트를
단락시키다가 이미 한 번 만들어진 적이 있다.**

`_settle_terminal_hits`가 히트가 진 빚을 갚는다. 그것도 `_handle_event`가 잡는 것과 **같은
`processing_files` 클레임 아래에서** — 그 클레임이 존재하는 이유인 경합 그대로다.

```python
            with self._processing_lock:
                if abs_path in self.processing_files:
                    continue
                self.processing_files.add(abs_path)
```

그리고 `archive_processed_files_enabled()`가 꺼져 있으면 **즉시 반환**한다 — 파일이 있던 자리에
남는 것이 «의도»인 모드이고, 35분이 측정된 것이 바로 그 모드라서 이 조기 반환이 핫 패스다.

## 지시서보다 호출 자리를 하나 더 배선했고, 그 사실을 적었다

배치는 스윕뿐 아니라 `_ingest_directory_tree`에도 들어갔다 — **지시서가 지명한 것보다 한 곳
많다.** 의도적으로 남겼다: 그 루프는 트리거마다 중첩 파일 전부를 재디스패치하고 스윕이 가진
in-memory 캐시에 해당하는 것이 없다. `archive_processed_files: false`에서는 **재기동마다 한
번이 아니라 매 사이클** 그 비용을 다시 문다. **두 줄을 지우면 되돌아간다**고 커밋이 스스로
적었다.

## 검증 — 재던 트리가 아니라 «커밋되는» 트리에서

40 passed (`test_sweep_tier1_hoist.py` 18, `test_nested_dir_ingestion.py` 22). 실제 코드에 주입한
결함은 전부 빨강으로 갔고, 그중 move-retry-dropped가
`test_locked_file_preserves_directory_then_retry_completes`를 빨갛게 만든다 — **아카이브 재시도가
호이스트된 경로를 실제로 지난다**는 뜻이다.

## 그때 남아 있던 것

- 3파일 +989/-12. 그중 693줄이 새 테스트 파일이다.
- **~92 ms/파일과 35분은 이 박스 측정**이고, 22,626파일은 이 박스 트리의 크기다.
- 파일당 config 재독·세션 생성이라는 **비용 자체는 사라지지 않았다** — 배치가 통과시키지 못한
  파일은 여전히 그것을 전부 지불한다. 이 커밋이 바꾼 것은 **누가 그 값을 무는가**다.
- Tier 1의 실패 방향은 그대로다: **mtime과 크기가 같은 채 내용만 바뀐 파일을 다시 읽지 않는
  쪽**으로 실패한다(모듈 상단에 명시돼 있다).
- 43.9배는 **변경 없는 트리의 재스윕** 숫자다. 콜드 스윕은 1.0배로 남았다.
