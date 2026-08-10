# DT 정렬 메타데이터 자동화가 본문 없는 커밋으로 착지했고, 같은 커밋에서 하네스가 게이트이기를 그만뒀다

**날짜:** 2026-08-09 19:03 · **커밋:** `a501d6d` · **레인:** 서버(체인) + map2
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 🔴 먼저 기록해야 할 사실 — 이 커밋에는 본문이 없다

```
feat: add DT alignment metadata automation
```

**끝이다.** 92파일 · 18,561 추가짜리 커밋인데 제목 한 줄 뒤가 비어 있다. **왜**는 전부
이 커밋이 **스스로 추가한 `docs/history/` 여섯 파일**에만 있고, 그 파일들은 **커밋 해시를
달고 있지 않다.** 그러니 해시에서 출발하는 사람은 근거에 도달할 방법이 없다 — 이 항목이
그 연결을 만든다.

관련 항목: `20260809_150000` · `20260809_153000` · `20260809_160000` · `20260809_170000` ·
`20260809_180000` · `20260809_183000`.

## 18,561줄이 무엇이었나

| 분류 | 파일 | 추가 줄 |
|---|---:|---:|
| `agent_workspace/reports/` (에이전트 보고서) | 44 | **15,966** |
| `docs/` | 14 | 843 |
| `.codex/` | 13 | 523 |
| **`server/` 생산 코드** | **7** | **413** |
| `server/tests/` | 5 | 379 |
| `server/scripts/` (시드 생성기) | 1 | 327 |
| 클라 소스 + dist | 8 | 110 |

**생산 코드는 전체의 2.2%다.** 가장 큰 다섯 파일은 **전부 에이전트 보고서 마크다운**이고
코드가 한 줄도 없다. 🔴 **커밋의 크기를 변경의 크기로 읽으면 안 되는 표본이다.**

정적 픽스처 JSON은 **하나도 없다** — 327줄짜리 시드 스크립트가 실행 시점에 라이브 DB
행에서 표본을 **생성한다.**

## 자동화가 실제로 하는 일

두 홉짜리 체인 인제션 캐스케이드다. **스케줄러도, 자기 호출 HTTP도 없다.**

```
dt_log (CREATE/EDIT)
  → S1: wafer_map_metadata (target_table="dt_log", map_id=dt_job).grid_metadata
  → S2: dt_inventory(dt_job).dt_frame
```

두 번째 홉은 **체인이 만든 이벤트**로 발화하는데, 워커는 그런 이벤트를 **기본적으로
막는다.** 규칙이 `allow_chain_trigger`로 **명시적으로 옵트인**해야만 돈다 — **키가 없으면
falsy이고 곧 차단**이며, 기본 true인 경로는 없다.

사이클은 **런타임이 아니라 config 로드 시점**에 거절한다.

```python
def _validate_chain_cascade_graph(rules):
    """Reject cycles made solely from opt-in chain-trigger edges at config load."""
    ...
        if node in visiting:
            raise ValueError("allow_chain_trigger cycle: " + " -> ".join(trail + [node]))
```

그리고 라우트가 **자기 검증을 잃었다.** `GET /api/maps/alignment/view`는 이제 매퍼가 부르는
것과 **같은 서비스**(`alignment_view_service`)에 위임한다 — **라우트와 체인이 갈라질 수
없게** 하려는 것이다. 쓰는 것은 **승자 프레임과 배치뿐이고 좌표는 절대 쓰지 않는다.**

## 🔴 스키마 변경이 저장소 밖에서 일어났다

이 커밋에 **마이그레이션 파일이 없고 새 테이블·컬럼도 없다.** `wafer_map_metadata`와
`dt_inventory.dt_frame`은 부모 커밋에 이미 있었다.

그런데 `20260809_160000`이 산문으로만 적어 둔 사실이 있다 — **`dt_inventory.dt_frame`의
물리 컬럼 타입이 `double precision`에서 `text`로 바뀌었다.** **추적되는 마이그레이션이
아니다.** 저장소만 가지고 이 이력을 재생하는 사람은 그 변경을 받지 못한다.

## 🔴 하네스가 게이트이기를 그만뒀다 — 전날의 판정과 반대 방향으로

전날 `6541e35`는 `alignment_verdict`를 게이트에서 빼면서 **`KNOWN_RED`에 넣지 않고 벤치도
고치지 않았다.** 「초록으로 보이게」 만들지 않겠다는 것이었다.

이 커밋은 `client2/scripts/check_harnesses.mjs`에서 **종료 코드 자체를 없앴다.**

```js
-const fail = msg => { console.error(`\n✗ ${msg}\n`); process.exit(1); };
+// Lead PM direction 2026-08-09: keep every diagnostic visible, but do not make harness
+// failures/config drift an exit-code gate while the candidate-contract migration is triaged.
+const fail = msg => { console.error(`\n✗ ${msg}\n`); };
```

그리고 하네스 **넷이 `KNOWN_RED`로** 들어갔고, **단언 바닥 셋이 삭제됐다** —
`map_editor2_shell_harness.mjs` **560**, `map2_placement_seat_harness.mjs` **42**,
`map_editor2_question_harness.mjs` **192**. 🔴 **그 수 아래로 떨어지는 회귀는 이 시점부터
측정 불가능하다.** 바닥이 있었다는 사실 자체가 사라졌기 때문이다.

`20260809_180000`이 그것을 **부채로 명시**한다 — "Accepted debt — harness gate is
report-only by Lead PM direction".

## 그 외 기록해 둘 것

- 🔴 **생산 매퍼에 디버그 `print()`가 실려 나갔다.** 체인이 돌 때마다 **모든 인제션
  페이로드가 표준출력으로 덤프된다.**

  ```python
      print('------------------- AUTO ALIGNMENT IS RUNNING------------------')
      print(payloads)
  ```

  같은 커밋이 `Server_console_safe_logging.md` 보고서를 함께 싣고 있다 — **자기모순이다.**
- **설정 키에 오타가 있다.** `alignment_rule`의 값이 `"dt_frame_confrimation"`(confirmation의
  오타)이고, 이 시점에 **세 파일이 그 철자를 공유한다.**
- **깨끗한 클론에서는 새 테스트 모듈이 수집조차 되지 않는다.** `.gitignore`가 `server/config/*`와
  `server/mappers/*`를 `*.sample`만 남기고 제외하는데, 테스트는 모듈 최상위에서 가드 없이
  라이브 매퍼를 import한다.

  ```python
  mapper = importlib.import_module("mappers.dt_alignment_metadata_mapper")
  ```

  skip이 아니라 **수집 시점 `ModuleNotFoundError`**다. 즉 **자동화 전체가 체크아웃 상태에서
  비활성**이고, 누군가 두 `.sample` 매퍼와 `chain_rules.json.sample`을 제자리에 복사해야
  비로소 존재한다.

## 검증

- 테스트 **19개**가 5개 파일에 추가됐다(`test_dt_alignment_metadata_mapper` 6 ·
  `test_syn_dt_alignment_samples` 5 · `test_chain_cascade` 3 ·
  `test_dt_inventory_metadata_mapper` 3 · `test_map_alignment` 2).
  `test_chain_cascade.py::test_rejects_opt_in_chain_cycles`가 위 사이클 가드를 지킨다.
- 🔴 **동반 문서들의 수가 서로 어긋난다.** 이 커밋에서 인용할 수 있는 수는 하나뿐이다.

  | 문서의 주장 | 판정 |
  |---|---|
  | "New cascade/identity tests: **13 passed**" | **어느 부분집합으로도 13이 안 나온다** (해당 두 파일 합 6, 새 파일 넷 합 17, 다섯 합 19) |
  | "**704 DT rows**를 만들었다" | **재현 불가.** 704 = 8 × 88은 **교체되기 전의 조밀 생성기** 수다 |
  | "88개 유효 다이 전부 · 연속 `dt_index` 1..88" | **같은 파일이 두 문단 뒤에서 스스로 반박한다** — 출하된 생성기는 **희소** 부분집합을 낸다 |
  | "결과: `3 passed`" | 철 지난 수. 해당 파일은 이 커밋에서 테스트 **6개**를 갖는다 |
  | "`alignment_verdict` **163중 6**" | **지지됨.** `check_harnesses.mjs`의 `KNOWN_RED` 항목 `{ ran: 163, failed: 6 }`와 일치 |

  🔴 **`20260809_160000` 한 파일 안에 생성기가 두 개 서술돼 있고, 첫 번째 것의 행 수가
  그대로 남았다.** 이 커밋에서 수를 하나만 인용해야 한다면 `163/6`이다 — **트리 자신이
  고정하고 있는 유일한 수**다.

## 그때 남아 있던 것

- **`dt_map` 투영과 그 `replace_map` 계약은 구현되지 않았다.** 커밋이 직접 범위 밖이라고
  적는다. `dt_log_to_dt_map` 규칙은 여전히 `"enabled": false`다.
- **`server/config/`에 `dt_frame_confrimation` 보강 규칙이 추적되지 않는다** — 부모 커밋의
  `server/config/` 어디에도 그 이름이 없다. 참조되는 규칙이 저장소 밖에 있다.
- 하네스 넷이 빨간 채로 `KNOWN_RED`에 있었고, 빌드는 그 위를 **종료 코드 없이** 지나갔다.
- `pytest.mark.skip`·`xfail`·`TODO`·`FIXME`는 **한 줄도 추가되지 않았다.** 비활성화는
  **표시가 아니라 게이트 삭제**로 이뤄졌다 — grep으로 찾을 수 없는 형태다.
