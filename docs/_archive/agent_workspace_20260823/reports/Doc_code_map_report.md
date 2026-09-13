# 보고서: 코드맵 + 에이전트 교훈 파일 체계 구축

- **발신:** doc-keeper / **수신:** 총괄 PM
- **지시서:** `agent_workspace/tasks/Doc_code_map_system_task.md`
- **일시:** 2026-07-25 / **기준 커밋:** cd3f90c
- **코드 무변경** (문서 + 에이전트 정의 md만). **커밋하지 않음** — 총괄 검수 후 커밋 요망.

## 1. 산출물 (신설 8 + 수정 8)

### 신설
| 파일 | 내용 |
|---|---|
| `docs/architecture/CODE_MAP.md` | 압축 구조 지도 ~300줄(상한 1,500줄 대비 여유 커서 **분할 불필요** — 단일 파일 유지). 서버 4대 파일 시그니처+라인앵커+역할, 소형 모듈, 기타 모듈 한줄 요약, client2 모듈(책임+export+소비 이벤트/API), 주요 호출 흐름 7개. 상단에 "전량 읽기 금지" + 유지보수 규율(모듈 맵 갱신=구현 에이전트, 정합 감사=doc-keeper) 명시 |
| `agent_workspace/memory/server-pm.md` | 공통 4건 + 전용 5건(outbox 인덱스 type_coerce, DDL 게이트+rollback, inline await 브로드캐스트, 재시딩 값 변경, 테스트 테이블명) |
| `agent_workspace/memory/client-pm.md` | 공통 4건 + 전용 3건(state 싱글턴, ensureCellObject, worktree 빌드 금지) |
| `agent_workspace/memory/qa-reviewer.md` | 공통 4건 + 전용 2건(clean tree 재현 실증, gitignored 전수 Grep) |
| `agent_workspace/memory/doc-keeper.md` | 공통 4건 + 전용 섹션은 빈 상태 개설(확정 교훈 없음) |
| `agent_workspace/memory/ui-designer.md` | 공통 4건 + 전용 2건(비-compositing pane 이슈 #3, transform/opacity만) |
| `docs/history/20260725_121549_code_map_and_agent_memory_system.md` | 히스토리(코드 스니펫 포함) |
| 본 보고서 | — |

각 memory 파일 상단에 운영 규칙 명시: "신규 교훈은 에이전트가 보고서에 **제안** → 총괄 검수 후 이 파일에 반영(직접 추가 금지)".

### 수정 (기존 내용 무변경 — 항목 추가만)
| 파일 | 변경 |
|---|---|
| `.claude/agents/server-pm.md` | Pre-Flight 6·7 추가(코드맵 먼저 / 교훈 파일 로드) |
| `.claude/agents/client-pm.md` | Pre-Flight 6·7 추가(동일) |
| `.claude/agents/qa-reviewer.md` | 착수 전 필독 4·5 추가(동일) |
| `.claude/agents/doc-keeper.md` | 착수 전 필독 5·6 추가(동일 + 감사 시 코드맵 출발점) |
| `.claude/agents/ui-designer.md` | 착수 전 필독 4·5 추가(동일) |
| `docs/README.md` | §2 아키텍처 표에 🟢 CODE_MAP.md 등재 + §5 이력 인덱스 개수 167→185 정정 |
| `docs/process/DOC_OWNERSHIP.md` | "코드 구조 지도" 소유 매핑 행 추가(CONTRIBUTING §8 체크리스트 준수) |
| `docs/history/README.md` | gen_index 자동 재생성(185 entries) |

## 2. 발견한 불일치 (코드 수정 안 함 — 판단 위임)

1. **`server/main.py` 중복 라우트**: `GET /tables/{t}/rows/{r}/cells/{c}/history`가 ~1614(response_model 있음)와 ~2020(없음)에 이중 정의. FastAPI 선등록 우선으로 ~2020은 사실상 사장(dead route). 코드맵에 주석 표기함. → **server-pm에 정리 위임 검토 권장.**
2. `client2/src/counter.js`: Vite 템플릿 잔재로 보임(미사용 추정) — 코드맵에 표기.
3. `docs/README.md`의 history 인덱스 개수가 167로 낡아 있었음 → 185로 정정 완료(경미하여 직접 수정).

## 3. PROJECT_STATUS 백로그 완료 처리 **초안** (보드는 건드리지 않았음 — 총괄 반영용)

§⏭️ 다음 단계/백로그의 "**[신규·사용자 요청 2026-07-25] 코드맵(압축 구조 문서) 체계**" 불릿을 삭제하고, §✅ 최근 완료 표 최상단에 아래 행 추가:

```markdown
| 2026-07-25 | 문서/조직 | **코드맵 + 에이전트 교훈 파일 체계** — `docs/architecture/CODE_MAP.md` 신설(서버 4대 파일 시그니처·라인앵커·호출흐름 7개 + client2 모듈 압축, ~300줄) + `agent_workspace/memory/` 교훈 파일 5종(제안→총괄 검수 반영 규칙) + `.claude/agents/` 5종 Pre-Flight에 "코드맵 먼저·교훈 로드" 배선 — 검수·커밋 대기 | [20260725_121549](../history/20260725_121549_code_map_and_agent_memory_system.md) |
```

## 4. SSOT 관련 제안 (선택 — 총괄 승인 필요, 미적용)

`SYSTEM_OVERVIEW.md`에는 손대지 않았다. 제안: SSOT의 문서 안내부(또는 §문서 지도 언급부)에 "구조 탐색은 [CODE_MAP](../architecture/CODE_MAP.md) 우선" 한 줄 추가하면 신규 세션의 발견성이 좋아진다. 원하시면 초안 1줄: `> 코드 구조 탐색은 [architecture/CODE_MAP.md](../architecture/CODE_MAP.md)에서 시작 — 소스 전량 읽기 금지.`

## 5. 검증

- `PYTHONIOENCODING=utf-8 conda run -n assy_manager python docs/history/gen_index.py` 실행 완료(185 entries).
- 라인 앵커는 HEAD cd3f90c의 grep -n 실측값(±20줄 규율 충족). 시그니처는 소스에서 직접 추출.
- `lead-pm.md`는 지시서 대상 5종에 포함되지 않아 무변경(의도 확인 요망 — 총괄은 메인 세션 페르소나라 제외로 이해함).
