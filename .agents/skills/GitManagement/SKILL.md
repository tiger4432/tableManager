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

## 4. [중요] 변경 이력 관리 (docs/history)
- **모든 아키텍처 변경 및 주요 기능 추가 시**, 반드시 `docs/history` 디렉토리에 새로운 마크다운 파일을 생성하여 기록해야 합니다.
- 파일명 규칙: `YYYYMMDD_HHMMSS_설명이름.md`
- 상세 워크스루와 별개로, 프로젝트의 공식 이력으로서 정제된 내용을 포함해야 합니다.
- **이 작업은 커밋 전 필수 단계입니다.**

---
*PM Agent에 의해 관리되는 공식 형상 관리 지침입니다.*
