# 후보 공간이 「회전×면」에서 바뀐 지 사흘, 리빙 문서 넷이 낡은 사본을 그대로 갖고 있었다

**날짜:** 2026-08-11 07:35 · **커밋:** `6cc7a6e` · **레인:** 문서(리빙 동기화)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경

`db1ee42`가 정렬 후보의 두 번째 축을 「거울(front/back)」에서 「걸음 방향(시작 모서리)」으로
바꿨다. `MAP_ALIGNMENT_SPEC §2.4`는 그 커밋과 함께 갱신됐지만, **같은 사실을 담고 있던
사본 넷은 갱신되지 않은 채** `§9.7`·`data_model`·`frontend §4.2`+헤더·`docs/README`의
정렬 행·`PRIMITIVES §4`(항목 둘)에 남아 있었다. 이 커밋이 그 넷을 고친다.

## 낡았던 문장, 그리고 고친 문장

```diff
- `candidate_frames`가 만드는 공간은 **4회전 × 2면**이고 y반전은 별칭으로 상쇄돼...
+ `candidate_frames`가 만드는 공간은 **4회전 × 2시작모서리**이고(`db1ee42` — 종전
+ 「4회전 × 2면」은 **거짓이 됐다**, §2.4) y반전은 별칭으로 상쇄돼...
```

`alignment.sides` 선언도 같은 부류다 — 후보 조립기에서 은퇴해 호출자가 0인데,
`guide/config/map_overlay_config.md §5`와 `CONFIG_GUIDE §S9`는 여전히 그 키를 세팅하는
절차를 조작자에게 가르치고 있었다. 행은 지우지 않고 **은퇴 표시**만 했다 — 그 키가 남긴
교훈(「탐색을 좁혀도 보고는 좁히지 마라」)이 키와 함께 죽지 않았고,
`STATE_NOT_CONSIDERED`가 생산자 없이 코드에 남아 있어서다.

## PRIMITIVES가 삭제된 장치를 재사용하라고 가르치고 있었다

`§4「프레임 창으로 규격 갈아끼우기」`의 「어디」가 `physFrameOverride`/`withPhysFrame`을
가리키고 있었는데, 그 둘은 닷새 전 `62520b9`에서 이미 삭제됐다(HEAD 실측: 정의 0건,
남은 것은 주석뿐). `frontend.md §4`는 2026-08-06부터 옳게 적고 있었으므로, **두 리빙
문서가 닷새 동안 정면으로 어긋난 채** 있었던 것이다. 항목은 「프레임은 *인자*다」로
다시 썼다.

## 세 번째로 반복된 실패 — 문서를 만든 커밋이 등재까지 하지 않았다

`DT_CORE_FRAME_CHAINS`·`DT_CORE_FRAME_CHAINS_GUIDE`·`DT_ALIGNMENT_METADATA_CHAIN_SPEC`
세 문서가 `DOC_OWNERSHIP.md`와 `docs/README.md` 양쪽에 **행이 없는 고아**로 출하돼
있었다. 이 커밋은 이것을 `MAP_ALIGNMENT_SPEC`(2026-08-05)·`TRACE_FIXTURE_SPEC`
(2026-08-04)에 이은 **세 번째 같은 실패**로 명시한다.

## 그 밖에 추적된 것

두 성능 제안서 `docs/proposal/FETCH_AND_AUDIT_HISTORY_PERFORMANCE_PROPOSAL.md`(109줄)와
`docs/proposal/UPSERT_THROUGHPUT_NEXT_STEP_PROPOSAL.md`(70줄)를 **미구현 상태로 검증하고**
새로 추가했다 — 검증만 하고 구현은 하지 않았다는 사실이 이 커밋 자신의 진술이다. (이
가운데 이력 페이징 제안은 이날 뒤에 온 `dab9152`의 근거가 됐다.)

## 검증

이 커밋은 문서 11개(+제안서 신규 2개)만 건드렸다 — 코드 변경 없음, 이 커밋 자체가 실행
가능한 회귀를 갖지 않는다. 「Net broken links 6 -> 1」류 수치는 이 커밋에 없고
(그 형태의 링크 감사 수치는 다음 커밋 `686dfbe`의 것이다), 이 커밋이 스스로 대는 근거는
grep 실측(예: `physFrameOverride`/`withPhysFrame` 정의 0건, `index_group_count`/
`bin_fingerprint_shift` 호출자 0건 재확인)이다.

## 그때 남아 있던 것

- `map_overlay_config.json:88`의 `__alignment_sides_comment` 주석 키가 낡은 채 남았다 —
  이 커밋은 config를 문서 소관 밖으로 명시하고 손대지 않았다.
- `server/main.py`에 `get_cell_history`가 두 번 정의돼 같은 경로를 두 번 등록하는 상태가
  이 커밋 시점에도 **아직 살아 있다**(줄 2296·3765로 적혔다) — 해소는 이날 뒤에 오는
  `dab9152`.
- 「DT/Core 프레임 파생 체인이 `confirmed_meta_for`를 직접 불러 `FrameConfirmation` 행을
  남기지 않는다」는 항목이 **총괄 판정 대기**로 명시적으로 열린 채 남았다.
- 새 두 번째 걸음 축(`tl`/`tr`)에서 그룹 최소화 지표가 갈리는지 동점인지는 **이 커밋
  시점까지 아무도 재지 않았다** — 배선 자체가 아직 없다.
