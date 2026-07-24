# StableDevelopmentProtocol 스킬 도입 및 프롬프트 정비

## 현상 (Context)
문서 체계 정비(커밋 `8cdd00e`) 이후, 정비된 docs/guide를 근거로 **모든 에이전트가 준수할 핵심 개발 규율**을 스킬로 성문화하고 프롬프트(SOP·CLAUDE.md)와 스킬 레지스트리를 이에 맞춰 정비할 필요가 있었다. 또한 기존 에이전트 스킬 일부에 낡은 실행 명령(`cd client && python main.py`)이 남아 의존성/환경 사고를 유발할 소지가 있었다.

## 조치 (Solution)

### 1. 신규 스킬 `StableDevelopmentProtocol` 작성
`.agents/skills/StableDevelopmentProtocol/SKILL.md` 신설. 4대 핵심 가치를 프로젝트 실제 규격에 접지하여 강제:
1. **의존성 안전** — 시그니처 영향 전수 분석(라우터·`chain_ingestion_worker`·`tests` 연쇄 갱신 + `pytest`), 서버-클라이언트 계약(`{value,is_overwrite,priority_source}`·WS 이벤트·API) 보존, GC 안티패턴 금지.
2. **대규모 최적화** — "1,000만 행에서도 안전한가?" 게이트. JSON 풀스캔·큰 OFFSET·전량 로드 금지, `business_key_val`/GIN·1000행 청킹·`BackgroundTasks`·delta 동기화.
3. **문서·이력 무결 동기화(docs-as-code)** — history 기록 + `gen_index.py`, SSOT/소유 리빙 문서 동시 갱신.
4. **작업 인계 요약** — 변경·수정파일·검증·미해결/다음단계.

Pre-Flight/Post-Flight 체크리스트와 정식 실행 명령(`python run_decoupled_app.py`) 포함.

### 2. 프롬프트 정비 (등록 및 강제)
- `docs/prompts/starting_prompt.md`: 상단에 **[최우선] 핵심 개발 헌장 준수 의무** 블록 추가, §5 스킬 목록 최상위에 `StableDevelopmentProtocol ⭐[필수]` 등록.
- `docs/prompts/CLAUDE.md`: "§5 프로젝트 헌장" 섹션 추가(4대 가치 + 현행 아키텍처 주의).

### 3. 기존 스킬 정합화
- `.agents/skills/SubAgentExecution/SKILL.md`: §2 실행 명령 표를 `run_decoupled_app.py`/`client2 npm run dev` 기준으로 교체, 구 PySide6 클라이언트 부재 명시.
- `docs/process/CONTRIBUTING.md`: 집행 스킬로서 StableDevelopmentProtocol 교차링크.

## 검증 (Validation)
- 신규/수정 파일의 상호 링크(SSOT·CONTRIBUTING·DOC_OWNERSHIP·data_preservation) 경로 확인.
- 히스토리 인덱스 `python docs/history/gen_index.py` 재생성.

## 영향 (Impact)
문서(지도/SSOT)에 이어 **행동 규율까지 단일 헌장으로 수렴**. 이후 모든 에이전트는 작업 전후 동일 체크리스트를 통과하므로, 의존성 사고·비확장 코드·문서 드리프트·문맥 유실이 구조적으로 억제된다.
