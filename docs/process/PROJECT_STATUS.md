# 📌 PROJECT STATUS — 진행 상황 & 문제 현황 (Living Board)

> **Status:** 🟢 Living | **Last-updated:** 2026-07-24
> **역할:** 프로젝트의 **현재 진행 상황·열린 문제·다음 단계**를 담는 단일 상태 보드. **컨텍스트 압축/세션 교체에도 살아남는 영속 상태**다.
> **규칙:** 총괄(및 각 PM)은 작업 **착수 전 이 파일을 읽고**, **완료 후 갱신**한다. 상세 이력은 [history/](../history/README.md), 현재 아키텍처는 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md).

---

## 🎯 현재 초점 (Current Focus)
- **비전 재정의 SSOT 반영 완료** — 제품 정체를 "교정 표면(Correction Surface) → 온톨로지/지식 그래프 기반"으로 재정의, 5대 핵심 가치 우선순위 확정. **다음: 척추(실시간 신뢰 전파 = 이슈 #0) 착수.**
- 맵 에디터 사용성 개선 (Client PM 도메인)은 병행 관찰.

## ✅ 최근 완료 (Recently Done) — 최신순
| 날짜 | 영역 | 요약 | 이력 |
|---|---|---|---|
| 2026-07-24 | 기획/문서 | SSOT §1 비전 재정의 — 5대 핵심 가치(최소공수 교정·온톨로지 기반·실시간 신뢰전파·레이어링·이력) + 가치 사슬 | — |
| 2026-07-24 | 프로세스 | 상태 보드(본 파일) 도입 — 진행·문제 파일 관리 원칙 | — |
| 2026-07-24 | 프로세스 | 총괄 위임 운영 원칙(§0-C): 소규모 수정·문서는 서브에이전트, 총괄은 검수 | `387158c` |
| 2026-07-24 | 맵에디터 | FRONT/BACK 반투명 워터마크 복원(표시 전용) | `05b1303` |
| 2026-07-24 | 맵에디터 | FRONT/BACK 라벨 그리드 밖(툴바 칩) 이동 + 반응형 정사각 채움(ResizeObserver) | `0130283` |
| 2026-07-24 | 스킬 | StableDevelopmentProtocol에 '사이드 이펙트 전수 분석' 원칙 추가 | `9a73313` |
| 2026-07-24 | 맵에디터 | 테이블 A→B 맵 이월(전환 시 유지/초기화 확인창) | `a41007e` |
| 2026-07-24 | 조직 | 총괄 + Server/Client 2-PM 체제 수립 | `b13c5b3` |
| 2026-07-24 | 스킬 | 도메인 스킬 4종 웹(client2) 전환 | `4337721` |
| 2026-07-24 | 스킬/프롬프트 | StableDevelopmentProtocol 헌장 + 프롬프트 배선 | `94e9359` |
| 2026-07-24 | 문서 | SSOT/거버넌스 체계 수립 + 문서 트리 재편 | `8cdd00e` |

## 🐞 열린 문제 / 알려진 이슈 (Open Problems)
| # | 심각도 | 문제 | 도메인 | 상태 |
|---|---|---|---|---|
| 0 | 중 | **체인 인제션 outbox 간헐 지연** — ①②③ 수정 완료(총괄 검수·커밋 대기), ④⑤ 보류. 조치: ②commit 우선→통지 fire-and-forget(타임아웃 3s), ①SYSTEM_RELOAD 부분 인덱스+조회 1s 스로틀, ③`processed_chain`/`payload->>tx` 부분·표현식 인덱스. 보류 ④LISTEN-after-check 레이스 ⑤실패 head-of-line(타이밍/커넥션 리스크로 분석만). 이력: [20260724_230117](../history/20260724_230117_chain_outbox_latency_fix.md) · 상세: [task/chain_outbox_latency.md](../../task/chain_outbox_latency.md) | Server | ①②③수정완료/④⑤보류 |
| 1 | 낮음 | `IntegrityAndQAExpert` 스킬 §3 QA 체크리스트가 아직 PySide 항목(QThread/DLL/PySide 임포트) — 웹 client2 QA 항목으로 미전환 | 프로세스 | 대기 |
| 2 | 낮음 | 맵 이월 시 A/B의 x·y·val 컬럼명이 크게 다르면 자동 정합 안 됨(저장 전 Advanced Column Mapping 수동 확인 필요) | Client | 대기(관찰) |
| 3 | 정보 | 미리보기 브라우저 pane이 비-compositing → rAF/ResizeObserver 자동발화·CSS transition 프리즈로 라이브 UI 자동검증 제약(실제 브라우저 무관) | 검증환경 | 알려짐 |

## ⏭️ 다음 단계 / 백로그 (Next / Backlog)
- 루트 `task/` 대기 항목: `cursor_based_pagination_pending.md`, `total_count_sync_pending.md`, `desktop_hybrid_wrapper_plan.md`.
- 이슈 #1(QA 스킬 웹 전환)은 여력 시 서브에이전트 위임.

## 🧭 환경 메모 (Env Notes)
- 로컬 테스트 테이블 `sample_map`은 `server/config/table_config.json`(gitignored)에만 존재 — 운영 무영향.
- 서버 기동: `python run_decoupled_app.py` (웹 :8080 + 워커 4종). 프론트 개발: `cd client2 && npm run dev`. dist는 추적·서빙 대상 → 소스 변경 시 `npm run build` 후 dist 커밋.

---
*갱신 규율: 이 보드는 상태의 단일 원천이다. 새 작업/문제/해결이 생기면 즉시 이 파일을 고친다. 이력 상세는 history, 이 파일은 "지금 어디까지 왔고 무엇이 문제인가"의 요약.*
