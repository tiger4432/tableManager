# CLAUDE.md

> 🗄️ **SUPERSEDED** by [process/CONTRIBUTING](../process/CONTRIBUTING.md) · `.claude/agents/*` on 2026-07-27. 히스토리 추적용으로만 보존됩니다.
>
> **아카이브 근거:** 프로젝트와 무관한 일반 LLM 행동 지침이며 어느 헌장도 이 파일을 참조하지 않습니다. **원래 이름이 `CLAUDE.md`라 그대로 두면 프로젝트 지침 파일로 오인될 수 있어** 이관하면서 이름을 바꿨습니다(구명: `docs/prompts/CLAUDE.md`).

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

## 5. assyManager 프로젝트 헌장 (Project-Specific Charter)

이 저장소에서 작업할 때는 위의 일반 원칙에 더해 **핵심 개발 헌장 스킬 [`StableDevelopmentProtocol`](file:///c:/Users/kk980/Developments/assyManager/.agents/skills/StableDevelopmentProtocol/SKILL.md)을 반드시 소환·준수**한다. 네 가지 타협 불가 가치:

1. **의존성 안전** — CRUD/공용 시그니처 변경 시 호출부(라우터·워커·테스트) 전수 Grep 후 연쇄 갱신, `pytest` 통과. 서버 스키마 ↔ client2 셀 형태/WS 이벤트/API 계약을 한쪽만 바꾸지 않는다.
2. **대규모 최적화** — 모든 쿼리·루프·페이로드는 **"1,000만 행에서도 안전한가?"**를 통과한다. JSON 풀스캔·큰 OFFSET·전량 로드 금지, 인덱스 컬럼/GIN·1000행 청킹·LIMIT·delta 동기화 사용.
3. **문서·이력 무결 동기화 (docs-as-code)** — 주요 변경은 `docs/history/`에 기록 후 `python docs/history/gen_index.py` 실행. 아키텍처/동작 변경이면 SSOT([`docs/overview/SYSTEM_OVERVIEW.md`](file:///c:/Users/kk980/Developments/assyManager/docs/overview/SYSTEM_OVERVIEW.md))와 소유 리빙 문서([`docs/process/DOC_OWNERSHIP.md`](file:///c:/Users/kk980/Developments/assyManager/docs/process/DOC_OWNERSHIP.md))를 같은 작업에서 갱신.
4. **작업 인계 요약** — 종료 전 변경·수정파일·검증결과·미해결/다음단계 요약을 남긴다.

**현행 아키텍처 주의(낡은 정보 방지):** 메인 클라이언트는 웹 `client2`(AG-Grid), 구 PySide6 클라이언트 없음. DB는 PostgreSQL/JSONB. 백엔드는 5-프로세스 + Outbox. 상세는 SSOT 참조. 정식 기동은 `python run_decoupled_app.py`.
