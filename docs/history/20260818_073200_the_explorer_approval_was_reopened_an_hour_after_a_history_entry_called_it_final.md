# 탐색기 승인이 한 시간 만에 다시 열렸고, 그 전에 히스토리 항목이 「최종 상태」로 덮어써졌다

**날짜:** 2026-08-18 01:19~06:47 · **커밋:** `bea0484` `af2a1d3` `1860714` `2d1ad86` `2622503`
`cbe139e` `96acdf7` · **레인:** 온톨로지(Config Explorer)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

---

## 배경

Ontology Config Explorer 라운드는 다섯 시간 반에 걸쳐 커밋 일곱 개로 착지했고, **일곱 개
모두 본문이 제목 한 줄뿐이다.** 「왜」는 같은 커밋이 함께 넣은 `docs/history/` 항목과
`ontology_config_explorer_plan/` 문서에 있는데, 그 항목들 대부분은 **자기를 실은 커밋의
해시를 달고 있지 않다** — 파일명 날짜로는 덮인 것처럼 보이지만 해시로는 도달할 방법이 없는
상태였다. 이 항목이 그 연결이다.

| 커밋 | 시각 | 「왜」가 착지한 자리 |
|---|---|---|
| `bea0484` | 01:19 | `docs/history/20260818_011042_…explorer.md`(같은 커밋이 추가) |
| `af2a1d3` | 01:26 | 위 항목을 **편집** + 계획 문서 02 |
| `1860714` | 02:24 | `…022041_…completion_followup.md` |
| `2d1ad86` | 02:49 | `…024236_…completion_audit_followup.md` |
| `2622503` | 02:58 | `…025727_…completion_approved.md` |
| `cbe139e` | 03:02 | **자기 히스토리 항목 없음** — SSOT·계획 문서 헤더만 |
| `96acdf7` | 06:47 | `…064143_…explorer_handoff.md` |

## 승인이 「최종」으로 적힌 뒤 다시 열렸다

`af2a1d3`은 코드를 한 줄도 바꾸지 않고, **이미 착지한 히스토리 항목의 마지막 절을
덮어썼다.**

```diff
-## 현재 상태
-
-`ONTOLOGY_CONFIG_EXPLORER_IN_REVIEW / NOT_APPROVED`. exact commit을 지정 독립 Audit에 제출한 뒤
+## 최종 상태
+
+exact commit `bea0484cd8ab99aab8b4155e7dd5c1178df1b22a`을 지정 독립 Audit이 `APPROVE`했다.
+`ONTOLOGY_CONFIG_EXPLORER_COMPLETE / APPROVED`로 동기화하고 main에 fast-forward 병합했다.
```

58분 뒤 `1860714`이 그 「최종」을 스스로 취소했다. 그 커밋이 넣은 항목의 첫 문단이
**이전 `COMPLETE`는 이 넓은 계약에 대해서는 과한 표현이었다**고 적었고, 계획 문서 01의
제목은 「완료 범위를 다시 연 이유」로 바뀌었다. `af2a1d3`이 승인한 것은 compiled Registry
탐색과 기본 draft lifecycle이었고, 사용자 pending 문서의 전체 계약에는 Binding·SourcePlan,
참조 오류 세분류, 정확한 경로 history, dirty 이동 3선택, active/draft 비교,
immutable review→revise, activation consumer 수렴, file-backed transfer 예제가 더 있었다.

기록해 둘 사실은 **부분 승인이 있었다**가 아니라, **추가 전용이어야 할 기록이 사후에
편집돼 부분 승인을 「최종 상태」라고 말하게 됐다**는 쪽이다. 그 문장은 지금도 그 파일에
그대로 있다.

## 전체 계약이 실제로 닫힌 경위

전체 완료 후보 `1860714`은 독립 Audit에서 **REJECT**됐다. 반례 셋 —① 저장한 초안을 다시
편집한 뒤 keep으로 이동했다 돌아오면 미저장 버퍼가 서버 저장본으로 되돌아갔다 ②
file-backed transfer 샘플의 계보가 마지막에서 `CoreDie→FinalChip`으로 갈라졌다 ③ 참조 엣지
diff가 target 교체를 `removed`+`added`로만 표현했다.

`2d1ad86`이 셋을 최소 범위로 닫았다. ③의 뿌리는 엣지 **정체성이 target을 포함한 내용
식별자**였다는 것이고, 고침은 「논리 위치」와 「비교 내용」을 갈라 놓는 것이었다.

```python
    def slot(edge: ReferenceEdge) -> tuple[str, str, str]:
        return edge.from_key, edge.reference_kind, edge.json_pointer

    def content(edge: ReferenceEdge) -> tuple[str | None, str, str, str, str | None]:
        return (
            edge.to_key, edge.target_id, edge.expected_kind, edge.status, edge.message,
        )
```

같은 이유로 중복 엣지 판정 키에서도 `to_key`가 빠졌다(`identity = (from_key, ref_kind,
ref_pointer)`) — 같은 자리에서 서로 다른 곳을 가리키는 두 선언은 이제 «중복»으로 거절된다.

①은 클라 쪽에서 체크포인트가 **커서만** 들고 있던 것이 원인이었고, 복원 조건이 문서
identity 전체 일치로 좁아졌다.

```javascript
  const restorable = Boolean(
    checkpoint?.dirty
      && checkpoint.viewPreference === 'active'
      && state.viewContext?.mode === 'active'
      && checkpoint.contextToken === state.viewContext?.context_token
      && checkpoint.draftId === draft?.draft_id
      && checkpoint.draftRevision === draft?.revision
      && checkpoint.draftTargetKey === draft?.target_key
      && typeof checkpoint.editorText === 'string',
  );
```

`2622503`이 승인을 기록했고, `cbe139e`이 SSOT의 `Last-verified` 줄과 계획 문서 01의 상태
헤더를 `COMPLETE / APPROVED`(`2d1ad863`)로 맞췄다 — **이 라운드에서 자기 히스토리 항목이
없는 유일한 커밋**이다. `96acdf7`이 인수인계 문서를 현재 승인 상태 기준으로 교체하고,
그때까지 Git 추적 밖에 있던 `task/ontology_config_explorer_pending.md`와 시각 기준본
`task/ontology_config_explorer_reference.html`을 추적 대상으로 들였다.

## 아키텍처 영향

Admin `#ontology`에 **compiled snapshot을 읽는 표면**이 생겼다. 응답 전체가 하나의 토큰
(`active:<hash>` 또는 `draft:<id>:<revision>:<previewhash>`)으로 묶이고, 클라 reducer가
active/view/selection/navigation/draft를 분리하며, 요청 세대와 기대 컨텍스트가 어긋난 응답은
성공 렌더로 가지 않는다. 초안 저장은 active bytes를 건드리지 않고 **같은 validator/compiler**로
전체 preview를 만들며, 활성화는 정확한 review revision + base/hash CAS + 백업 + atomic
replace + 재로드 확인을 거친다. 즉 «설정 선언»이 처음으로 코드가 아닌 **화면에서 탐색·검토
가능한 대상**이 됐다.

## 검증

레인이 각 커밋 시점에 기록한 수치는 다음과 같다(전부 conda `assy_manager` 기준).

| 커밋 | backend 직접군 | Explorer state harness | 그 밖 |
|---|---|---|---|
| `bea0484` | `411 passed, 1 skipped` | `17 assertions / 0 failed` | client contracts 7 |
| `2d1ad86` | `165 passed` | `35 assertions / 0 failed` | contracts 7, Vite 107 modules |
| `96acdf7` | `21 passed` | `35 / 0` | 승인 커밋이 main의 ancestor임을 확인 |

`2622503`의 항목이 적은 `01a00f3f-4249-7bf0-ab96-6d32c27273fe`는 **커밋이 아니라 지정 Audit
task의 식별자**다. 커밋 해시로 읽으면 안 된다.

## 그때 남아 있던 것

- **full server suite와 Explorer PostgreSQL E2E는 이 라운드 내내 미실행**이었다. 사용자
  지시에 따른 것이고, 어느 커밋도 통과로 주장하지 않았다.
- 운영 active config에 없는 DT/transfer/VerifiedJoin은 시연용으로 추가하지 않았다. identity
  경로는 별도 file-backed 샘플(`server/config/sample/ontology/transfer_explorer/`)에서만
  검증됐다 — 운영 선언에 대한 왕복 증거는 아니다.
- 운영 config/DB write, cursor reset/replay, migration, legacy 이동·삭제는 전부 금지 상태로
  남았고 별도 사용자 승인 대상이었다.
- `af2a1d3`이 덮어쓴 히스토리 항목(`20260818_011042_…`)은 이 라운드가 끝난 뒤에도 부분
  승인을 「최종 상태」라 적은 채로 남아 있었다. 전체 계약의 승인은 그 파일이 아니라
  `20260818_025727_…`에 있다.
