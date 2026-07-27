# 자동저장을 **지웠다** — `replace_map` 위에서 keystroke마다 쓰는 손은 손이 하나여야 한다

> 커밋 `b35bc9f` · 2026-07-28 07:23 · 도메인 Client(맵 에디터·계획 패널) + Server(config 백업·/health)
> **이 커밋의 서버 절반**(물리 zone 컬럼 · `validate` 재작성 · V1~V5)은 별도 항목에 있다 →
> [DOE 층 구조가 band에서 구역으로](./20260728_071500_doe_zone_model_server_half.md). 여기는 나머지 —
> 클라이언트 저장 규율, C3 주간 config 백업, 그리고 라이브에서 진단한 함정 두 개를 기록한다.
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 계약: [MAP_EDITOR_SPEC §6](../spec/MAP_EDITOR_SPEC.md) · 복원: [ROLLBACK_PROCEDURE](../guide/ROLLBACK_PROCEDURE.md)

## 배경 — 자동저장은 편의가 아니라 **무기**였다

legend(=DOE) 저장의 서버 연산은 `replace_map`이다 — 보낸 행들이 그 맵의 계획 **전체를 갈아치운다.**
그 위에서 keystroke 단위 자동저장은 "덜 잃는 장치"가 아니라, 편집 중간의 어중간한 상태로
서버의 진짜 계획을 덮을 기회를 keystroke마다 만드는 장치였다. 서버 절반 항목의 표현을 빌리면,
초록색 자동저장 칩이 붙은 채로.

그래서 방향을 뒤집었다. **서버 쓰기는 줄이고, 로컬 초안은 넓힌다.**

## 변경 내용

### ① 서버 registry writer는 `pushMapData` 하나

자동저장 경로를 삭제했다. 이 커밋 시점에 registry를 서버에 쓰는 참조는 `pushMapData` 경유
**2곳뿐**이었다 — 사용자가 ⚡ Push를 누르는 순간이 곧 서버가 바뀌는 유일한 순간이다.
편집 중 유실 방지는 서버가 아니라 **로컬 초안**이 맡는다: painting·drag·fill·paste·legend-rename
등 편집 경로 **10곳**이 전부 초안을 쓰게 됐다. 이전에는 일부 경로만 초안을 남겨서,
"새로고침 생존"이 어떤 편집을 했느냐에 따라 복불복이었다.

### ② 초안에는 **자기가 태어난 서버 상태의 지문**이 박힌다

```js
// map_editor.js — 초안 저장 시점의 서버 fingerprint를 함께 기록
localStorage.setItem(doeDraftKey(selectedTable, mapKey), JSON.stringify({
  /* ...doe, cells..., */ registryFp, cellsFp,
}));

// 로드 시 — 서버 fp와 일치하는 초안만 복원한다
const doeFresh   = draft.registryFp !== null && draft.registryFp === serverFp;
const cellsFresh = draft.cellsFp   !== null && draft.cellsFp   === serverCellsFp;
```

지문이 어긋난 초안(다른 자리에서 이미 서버가 바뀐 뒤의 초안)은 조용히 적용하지 않고
stale 알림을 낸다. `replace_map` 위에서 stale 초안을 복원해 저장하면 **남의 편집을 되돌리는
저장**이 되기 때문에, 우선순위 판정은 값이 아니라 지문으로 한다. 판정은 호출부가 하고
`applyDoeDraftRecord`는 적용만 한다 — band 모델 시절 초안은 읽는 시점에 zone으로 이행하되,
표현 불가능하면 서버 컬럼과 **같은 방식으로 거부**한다.

### ③ 데이터 보호 게이트 둘은 남기되, **문구가 사용자를 탓하지 않게** 고쳤다

`zone-columns-missing`(서버에 zone 컬럼이 없으면 저장 보류)과 `legendReplaceScope` fingerprint
게이트는 유지됐다. 바뀐 것은 말투다 — 이전 문구는 "저장 실패"처럼 읽혀서 계획 자체가 잘못된
것으로 오해하게 했다. 게이트는 **계획이 아니라 저장 조건**을 막는 것이므로, 문구가 그렇게
말하게 했다.

### ④ `tsv.js` — 클립보드 파서를 뽑아내자 Excel 인용 규칙이 들어갈 자리가 생겼다

기존 TSV 파싱은 `clipboard.js`의 `paste` 핸들러 안 네 줄 인라인이었다. 개념이 엉킨 게 아니라
**위치가 엉켜서** 재사용이 불가능했다. 순수 함수(문자열 → 격자)로 추출해 그리드와 DOE 패널이
같은 리더를 쓰게 했고, 그 김에 이전 파서에 없던 Excel 인용 규칙이 들어갔다:

```
#2f7d63⇥B⇥16⇥라이너⇥ADFE1H_01⇥"MID1↵MID3"⇥TOP1
```

MID 셀에 자재가 두 줄이면 Excel은 셀을 `"..."`로 감싼다. 구 `split('\n')` 파서는 이 **한 셀을
두 레코드로** 쪼개서, 둘째 조각(`MID3"⇥TOP1`)이 다음 값의 행에 붙었다. 6컬럼 TSV가 이 커밋
시점의 엑셀 왕복 계약이다.

### ⑤ C3 — config 주간 백업 (`server/config_backup.py`)

`server/config/`는 **일부러** gitignore라(현장 자산 오염 방지) git이 복구 경로가 아니다.
B4 롤백 드릴의 2단계 "config를 백업에서 복사"에는 이 커밋 전까지 **원본이 없었다** —
`install_product_tables.py`의 `.bak`은 설치 이력이지 배포 이력이 아니라, 어드민 UI로 한
손편집은 백업을 하나도 남기지 않았다.

- 주 1회 **파일별** 스냅샷 `<이름>_<yymmdd>.json.bak` — 묶음 아카이브가 아니다. 묶음을 복원하면
  스냅샷 이후 **다른** config에 한 정상 편집까지 되돌아간다.
- 보관 31일 FIFO에 **최신 4개 하한** — 하한이 없으면 두 달 멈췄다 재개한 잡이 자기 스냅샷을
  전부 지운다. 이력이 가장 필요한 순간에.
- 신선도는 크론 슬롯이 아니라 **디스크의 최신 스냅샷 나이**로 판정한다. 크론 시각에 PC가
  꺼져 있으면 그 주는 그냥 사라지는데, 재기동으로 한 주를 조용히 거르는 것이 정확히 이 백업이
  막아야 할 실패다. 밀린 스냅샷은 다음 기동 첫 틱에 떠진다.
- 실행 주체는 Auto-Update 스케줄러의 틱이다 — 수집기로 만들지 않았다. 수집기 산출물은
  그 테이블로 **인제션되는데** config 백업엔 대상 테이블이 없고, "산출물 0건 = FAIL" 규칙과도
  충돌한다. 시간 기반 프로세스가 시스템에 하나뿐이라 그 틱만 빌렸다.
- `/health`의 `checks.config_backup`이 `missing`/`stale`을 `degraded`로 보고한다 — **절대 503이
  아니다**(백업 부재는 서빙 불능이 아니다). 판정 근거가 이 잡의 상태 파일이 아니라 스냅샷 파일
  자체라, 잡이 죽어도 신호는 살아 있다.

복원 드릴은 격리 스택에서 **두 번 실측**했다(0.17s / 0.33s). 드릴에서 config-watcher의 1초
debounce 함정을 확인해 판별 신호와 함께 문서화했고, 롤백 절차 전체가
[ROLLBACK_PROCEDURE](../guide/ROLLBACK_PROCEDURE.md)로 분리됐다 — 코드만 되돌리면 여전히
깨져 있는데 `/health`는 `ok`라고 말한다는 것까지 드릴로 실측된 상태였다.

### ⑥ 라이브에서 진단한 함정 — PowerShell의 `set`은 환경변수를 만들지 않는다

어드민 토큰이 안 먹히는 라이브 잠금을 진단해 보니 원인이 셸 문법이었다. PowerShell에서
`set ASSY_ADMIN_TOKEN=admin`은 `Set-Variable`의 별칭이라 `ASSY_ADMIN_TOKEN=admin`이라는 이름의
**PowerShell 변수**를 만들고 끝난다 — 에러가 없어 성공처럼 보이고, 자식 프로세스는 아무것도
못 본다. 판별법은 기동 로그의 `is NOT set` 경고가 사라졌는지 하나뿐이다.
[DEPLOY_SETUP §1-4](../guide/DEPLOY_SETUP.md)에 셸별 문법 표와 함께 박았다.

### ⑦ 온톨로지 전략 보고서 (코드 없음)

4-에이전트 딥다이브 결과가 `agent_workspace/reports/ONTOLOGY_STRATEGY_20260728.md`로 들어왔다.
라이브 관측(죽어 있는 매핑 2개 · `event_time`이 공정 시각이 아니라 적재 시각)과 설계 판단
(값 범주 4종 = 엣지 타입 · 대조적 PPR · "셀은 노드가 아니다")을 담은 **보고서**이며, 이 커밋에
그래프 코드 변경은 없다.

## 검증

| 무엇을 | 어떻게 | 결과 |
|---|---|---|
| 서버 스위트 | `pytest server/tests/` | **815 passed / 0 failed** (기준선 753) |
| 클라 하네스 3종 | `node contracts/<name>/client_harness.mjs` | 304 / 71 / 82 assertions, 전부 OK |
| C3 복원 드릴 | 격리 스택 2회 | 0.17s / 0.33s |
| 뮤테이션(서버 절반) | 결함 30종 주입 | 29 killed / 1 equivalent — [서버 절반 항목](./20260728_071500_doe_zone_model_server_half.md) 참조 |

## 그때 남아 있던 것

- **`ingestion_workspace/`는 자동 백업 대상이 아니었다** — 매퍼·수집기 스크립트가 거기 있는데도.
  config만 C3에 들어갔다.
- 첫 배포 직후에는 스냅샷이 없으므로 `/health`의 `checks.config_backup`이 **정상적으로 `missing`**을
  보고한다 — 스케줄러가 한 번 돌면 사라지는 상태다.
- config-watcher의 ALTER는 여전히 `print()`로만 나가고 로그 파일에 남지 않았다 — 운영자 콘솔
  스크롤백이 유일한 사후 증거였다.
- 온톨로지 보고서의 핵심 질문(`bonding_log.core_lot/core_slot`이 코어인가 테이프인가)은 사용자
  답변 대기 상태였다.
- `transfer_plan.css`가 이 커밋에서 전면 재작성됐다(868줄 변경) — 그 재작성이 떨어뜨린 것이
  하나 있었음이 26분 뒤 다음 커밋에서 드러난다 →
  [맵 에디터 5건 수정](./20260728_074941_map_editor_five_fixes_lag_overlay_reopen.md).
