# 총괄(포크) 야간 운영 메모 — 2026-08-19 밤

컴팩트 대비. **판정과 근거는 여기 없다** — 그건 보드(`docs/process/PROJECT_STATUS.md`)와
`task/ontology_picker_spec.md`, `task/ontology_screen_qa_walks.md`에 있다.
여기 적는 것은 **기계적인 것뿐**: 누구에게 어떻게 말하고, 무엇으로 확인하는가.

## 소유자 상태

**잔다.** 새벽에 **UI 목업**을 준다. 그때까지 **소유자 판정은 못 받는다** — 필요하면 적어 두고
다음 항목으로 넘어간다. 소유자 마지막 지시: **「야간 화면 절대 완성」.**

## 구현자

```
session : local_769337c4-2976-4adf-98cd-c4f53a621908
전사    : ~/.claude/projects/C--Users-kk980-Developments-assyManager/64851641-....jsonl
```
🔴 **세션 id와 전사 파일 이름이 다르다.** 전사를 읽어 확인할 때 위 쌍을 쓴다.

**세션은 스스로 다시 시작하지 못한다.** 한 턴 돌고 멈춘다 — 「기다리지 말고 계속」 같은 규칙으로는
안 된다. **보고를 읽으면 그 자리에서 다음을 보내야 한다.** 2026-08-19에 이걸로 다섯 번 멈췄고
(5·27·66·15·4분) 다섯 번 다 소유자가 먼저 알아챘다.

**보고 채널은 파일이 정본이다** — `task/implementer_pickup_report.md`. 메시지는 알림일 뿐이고
**잘려서 도착한다**(오늘 세 번). 파일을 읽어라.

## 야간 감시

15분간 파일 쓰기·커밋·전사 증가가 하나도 없으면 알림이 온다. **알림이 오면 구현자에게
`send_message`로 「계속 가세요」를 보낸다.** 알림 문구 자체에 그 지시가 적혀 있다.

## 브라우저 — 이게 오늘의 가장 큰 변화

소유자가 엣지에 클로드 확장을 깔았다. `mcp__claude-in-chrome__*`로 **소유자가 로그인한 화면**을
직접 본다. **관리자 토큰은 넣지 않는다** — 이미 인증된 세션을 쓰는 것이지 자격증명을 다루는 게 아니다.

```
list_connected_browsers → tabs_context_mcp → navigate → read_page / computer / javascript_tool
tab : 839164602   ·   http://localhost:8080/admin.html#ontology → "Ontology Explorer"
```

**측정 전 반드시 둘:**
1. `[...document.querySelectorAll('script[src]')].map(s=>s.src)` 가 `dist/admin.html`이 가리키는
   해시와 같은가. 다르면 `location.replace('/admin.html?cb='+Date.now()+'#ontology')`
2. **서버 프로세스가 그 커밋 이후에 떴는가.** `Get-NetTCPConnection -LocalPort 8080` → `StartTime`.
   2026-08-19에 이 둘로 네 번 헛돌았다

**규율:** 구현자가 「걸었다」고 하면 **같은 걸음을 내가 다시 걷고** 나서 소유자에게 올린다.
오늘 결함 둘이 보고서가 아니라 화면에서 나왔다.

🔴 **시험 선언을 만들면 반드시 지운다.** 오늘 밤 세 번 치웠다(`zz`·`zz-claims@1`·`zz-shape@1`·
`zz-empty@1`). 소유자 설정에 남기면 아침에 그가 본다.

## 소유자 설정 — 백업 위치

```
스크래치패드 overnight_backup/{ledger_config.json, table_config.json}   (2026-08-19 밤)
그 폴더 안 .before_* 넷 · git 추적 대상이라 git checkout 으로도 복구
```
정상 상태: **낱말 5 · 엔터티 3 · 팩 2 · 준비기 2 · 매퍼 2 · 프로필 2 · 소스 2.**
이 숫자와 다르면 누가 뭘 남긴 것이다.

## 아침에 할 것

1. **밤새 결과를 브라우저에서 직접 걷는다** (`task/ontology_screen_qa_walks.md` W1~W10)
2. **소유자 설정이 위 숫자인지** 확인
3. **UI 목업을 받아** 지금 화면과 대조 — 무엇이 CSS만으로 되고 무엇이 구조를 건드리는지 갈라서 올린다
4. 문서 정비(doc-keeper) — 카운터 70+, `CODE_MAP.md`가 이 라우터를 「라우트 7종」이라 적었는데 실제 13개
