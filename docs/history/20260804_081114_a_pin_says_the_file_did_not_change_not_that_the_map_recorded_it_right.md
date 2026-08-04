# 핀은 「파일이 안 바뀌었다」고 말하지 지도가 그것을 옳게 적었다고 말하지 않는다

> **일자:** 2026-08-04 오전 | **관련 커밋:** `cc36ef4`(리빙 문서 동기화) · `5327d35`(코드맵 재측정) · `ed9cfdb`(dist 1차 재빌드)
> **담당:** doc-keeper · code-mapper(각각 다른 소관, 파일이 겹치지 않아 동시 진행)
> **대상:** `docs/architecture/CODE_MAP.md` · `docs/qa/FEATURE_CHECKLIST.md` · `docs/architecture/frontend.md`·`backend.md` · `docs/spec/MAP_EDITOR_SPEC.md` · `docs/architecture/PRIMITIVES.md` · `docs/guide/SERVER_STARTUP_GUIDE.md`

## 코드맵 — 초록 핀 아래에서 112줄이 틀려 있었다

`1dc761b`에서 마지막 검증됐고 `ed9cfdb`까지 재측정했다. 블롭 해시 **41 → 50**으로
핀을 늘렸고, **옛 41개 중 20개가 낡아 있었다.**

드리프트보다 중요한 발견은 이것이다.

> `crud.py`의 **뒷절반 전체가 112줄 틀려 있었다 — 초록 핀 아래에서.**
> `get_effort_stats` 이후 전부(`apply_row_update_internal`·`derive_replace_map_scope`·
> `apply_batch_updates`·`set_cell_manual_priority_batch`)가 `1dc761b`에서
> **정확히 112만큼** 짧았다. 블롭 해시는 그대로였고, 그래서 앞선 패스가
> 재측정 대신 **표본 검사**를 했으며 그 표본이 **맞는 앞절반에 떨어졌다.**
>
> **핀은 파일이 바뀌지 않았다고 말한다. 지도가 그것을 옳게 적었다고 말하지 않는다.**

이제 표본은 **파일 끝쪽에서** 뽑는다.

`main.py`에는 이동(shift)이 아니라 **재작성 구역이 셋** 있다
(`get_column_filter_condition` · `get_table_data`의 본문 · `export_table_csv`).
거기에 계단식 오프셋을 적용하면 **다른 코드에 착지**하므로 no-offset으로 표시했다.

정확하다고 단언했는데 아니었던 개수들:

| 항목 | 적혀 있던 수 | 실측 |
|---|---|---|
| `reseatCellsToStoredCoords` 호출부 | 3 | **4** (`:591`의 cols/rows 리스너) |
| `isValidDieAt` | 5 | **6** (`canvasSeatKeys`) |
| 검사 11-b 서버 히트 | 1 | **2** (`coordinate_transformer.py:50` **와** `:138`) — **앞 리비전에서도 틀렸었다.** 지명된 항목이 존재했으므로 그 주장이 검증된 것처럼 읽혔다. **이 지도 자신이 문서화해 둔 함정이다** |
| `transfer_plan.js`의 `notifyMapContext` 앵커 | 서로 모순되는 두 세트(~1603, ~1520) | 실제 **1706** |

그리고 검사 12(「`mm`은 일부러 비워 둔 이름이다」)는 정정이 아니라 **은퇴**했다 —
`cd3e0f4`가 진짜 밀리미터 공간을 착지시키면서 **코드가 그 문장을 거짓으로 만들었다.**
되살리면 **이제는 올바른 코드를 금지하게 된다.**

## 리빙 문서 — 세 문서가 테스터에게 「출하된 동작을 불합격시켜라」라고 지시하고 있었다

마지막 스윕 이후 31개 커밋이 쌓였고, 이 라운드가 `client2` 레이아웃을 구조적으로
바꿨다.

**정정이 아니라 삭제한 것** — 기계가 이미 그 수를 찍기 때문이다:

- `FEATURE_CHECKLIST`와 `frontend.md`의 **하네스 개수.** `ASSERTIONS` 프로토콜과
  바닥값으로 대체했다. **산문은 기계가 알 수 없는 것을 나른다. 다시 적은 개수는
  부채 항목이 실측 42에 대고 28이라고 말한 방식이다.**
- 「mm은 일부러 비어 있다」 — `cd3e0f4` 이후 거짓. 소스에 대조한 뒤 진짜 스펙으로
  교체했고, **옛 문장이 하중을 지고 있던 주장은 지켰다** — **저장 좌표는 여전히
  칸수이지 mm가 아니다.**

**삭제가 아니라 정정한 것** — 과소 계수는 검사를 무장 해제하기 때문이다:
계약 개수 **5 → 6**, 산문 **과** 그 절 자신이 하중을 진다고 표시해 둔 bash 예시 양쪽에서.

**지시받지 않고 스윕 중에 발견한 것:**

- `FEATURE_CHECKLIST:568`이 테스터에게 **출하된 동작을 불합격시키라고** 지시하고
  있었다. 「키 삭제가 `missing`을 낸다」는 `2c2a777`에서 참이기를 그쳤다.
  같은 거짓 주장의 사본이 **두 개 더** 있었다(`PRIMITIVES`, `FEATURE_CHECKLIST:136`).
- `MAP_EDITOR_SPEC:585`가 **더는 존재하지 않는** cols×rows 호환 게이트를 서술했다 —
  **차원이 다른 것이 맵 규칙 6의 요점**이다. 대신 살아남은 거절 둘을 문서화했고,
  그중 함정 하나를 같이 적었다: 소스가 `phys_chip_x/y` 없이 격자를 선언하면
  타깃의 피치로 역채워져 **화면은 완벽히 정렬되고 600개 값 중 570개가 틀린다.**
- `backend.md`의 라우트에 `not_declared`도 `inactive_subtractions`도 없었다.
- `SERVER_STARTUP_GUIDE`가 **작동할 수 없는 명령 셋**을 찍고 있었다 — 이 저장소에
  존재하지 않는 `requirements.txt`(환경은 conda다), 틀린 `scripts/` 경로,
  이 시스템이 기동에 쓰지 않는 uvicorn 줄.

## 그때 남아 있던 것

- `ed9cfdb`는 이 배치의 **첫 번째** dist 재빌드다(두 번째이자 마지막은 `843af4f`).
- `5327d35`가 검증한 범위의 상한은 `ed9cfdb`이고, 그 뒤의 이음새 라운드
  (`2f3fa6f`·`cafd61f`·`4a0c402`)와 `092b83f`는 **이 코드맵에 반영돼 있지 않다.**
