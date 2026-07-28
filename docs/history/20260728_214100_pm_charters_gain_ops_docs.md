# PM 헌장에 운영 문서 네 편이 등재됐다 — 감사가 지적한 공백

> 커밋 `deed6d2` · 2026-07-28 21:34 · 도메인 Process(docs/prompts PM 헌장)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)
> **동반 항목**: [관문 4](./20260728_213436_gate4_log_shaped_push_structural_discriminator.md) · [self-frame 유령 형제](./20260728_213700_self_frame_fail_count_only_sibling.md) · [replace_map 정직한 범위](./20260728_213900_replace_map_honest_scope_400_over_noop.md)

## 배경

문서 감사가 server/client PM 헌장(`docs/prompts/server_pm.md`·`client_pm.md`)의 참조
목록에서 운영·설정 문서 네 편이 빠져 있음을 지적했다 — CONFIG_GUIDE · DEPLOY_SETUP ·
PRODUCTION_READINESS · FEATURE_CHECKLIST. 헌장에 없는 문서는 PM 에이전트의 착수 시
로드 대상에서 빠지고, 로드되지 않는 문서는 실무에서 갱신 의무도 잊힌다 — 문서가
있는데 아무도 읽지 않는 상태의 전형적 진입로다.

## 변경 내용

두 헌장에 각 1줄, 그러나 **도메인별 의무를 붙여** 등재했다 — 같은 문서 네 편이라도
읽는 이유가 다르다:

- **server_pm**: CONFIG_GUIDE는 설정 온보딩 지도 + `guide/config/` 파일별 절차,
  DEPLOY_SETUP은 환경변수·재기동 단위. 그리고 의무 한 줄 —
  *"config 파일·리로드 경로·키를 바꾸면 CONFIG_GUIDE와 guide/config/ 양쪽 갱신이 의무다."*
- **client_pm**: CONFIG_GUIDE는 클라가 **소비하는** 선언의 원천(stages·paint-rules·
  binding·default_legend), DEPLOY_SETUP은 번들 재빌드·커밋 의무 등 배포 함정,
  FEATURE_CHECKLIST는 기능 변경 시 점검 항목 갱신 대상 여부 확인.

## 검증

문서 변경뿐 — 커밋의 스위트 결과(893 passed)는 동반 항목의 코드 변경 몫이다.
