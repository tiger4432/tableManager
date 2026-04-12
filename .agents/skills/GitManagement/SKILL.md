---
name: GitManagement
description: 프로젝트의 형상 관리 및 커밋 컨벤션을 관리하는 전문가 스킬
---

# GitManagement Skill

이 스킬은 `assyManager` 프로젝트의 Git 형상 관리 표준을 정의합니다. 모든 에이전트는 이 가이드를 준수하여 코드를 관리해야 합니다.

## 1. 커밋 메시지 컨벤션
- **feat**: 새로운 기능 추가
- **fix**: 버그 수정
- **docs**: 문서 수정 (technical_manual, development_summary 등)
- **refactor**: 코드 리팩토링 (기능 변경 없음)
- **test**: 테스트 코드 추가 및 수정
- **chore**: 빌드 업무, 패키지 매니저 설정 등

## 2. 브랜치 전략
- `main`: 배포 가능한 상태의 안정적인 코드
- `feature/[기능명]`: 신규 기능 개발 브랜치

## 3. .gitignore 관리
- 로컬 DB (`.db`), 가상 환경 (`.venv`), 캐시 파일 (`__pycache__`)은 절대 포함하지 않습니다.
- 에이전트의 작업 로그 (`agent_workspace/`) 중 최종 리포트만 포함하고 임시 태스크는 배제합니다.

---
*PM Agent에 의해 관리되는 공식 형상 관리 지침입니다.*
