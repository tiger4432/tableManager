# 은퇴 표지 `M1_SOURCE_CONFIG_REF.RETIRED.md` 가 소유자의 말로 지워졌다 — 가이드 셋은 이제 히스토리 항목을 가리키고, 코드 주석 «열두 줄»은 여전히 지워진 파일을 가리킨다

> **커밋:** `928cbdc1` — chore: delete server/M1_SOURCE_CONFIG_REF.RETIRED.md at the owner's word; the three guides that pointed at it now point at the history entry that records the retirement
> **일자:** 2026-09-15 22:28
> **레인:** 총괄(직접). 커밋 본문 «없음» — 제목 한 줄이 전부다. 소유자의 «말»은 커밋 제목이 인용할 뿐, 보드·채널에 그 지시의 줄은 이 시점에 «없다».
> **측정 상자:** 해당 없음 — 문서·표지 파일만. 코드·config·데이터 «무접촉».
> **스위트:** 해당 없음.

## ① 무엇이 지워졌나 — 162 줄의 «은퇴 표지»

2026-08-14 `source_config_ref`(M1 소스 역할 위임 경로) 은퇴 때 세운 표지다. 그 표지는 스스로 이렇게 적어 두고 있었다:
```
관례       map_doe 은퇴(c0fb735) · migrate_map_meta_to_wafer_id.RETIRED.md 가 세운 것 — 「은퇴는 그 옆에 «이름 붙은 산출물»을 남긴다:
          승인 · «실측된» 사유 · 은퇴가 «못 되돌리는» 것 · «정확한 부활 조건»」
왜 server/ 에    server/config/* 는 gitignore 라 「아무도 clone 하지 않는 표지는 영속이 아니다」
내용       ⓐ 무엇이었나(다섯 갈래 자리 표) ⓑ 왜 — 역할 다섯이 전부 missing 이던 «두» 원인(미등록 표 셋 · 선언 없는 컬럼 넷)
          ⓒ 은퇴가 «안 하는» 것(bonding_plan_config 는 살아 있고 core-summary 라우트가 «같은 이유로» 깨져 있음 — 소유자 판정 대기)
          ⓓ «값을 치른» 둘(코어 프레임 fail 소스 정렬 · fail_breakdown 의 소스별 키) ⓔ 부활 조건 «순서대로»
```
그 내용은 이제 git 에만 있다: `git show 928cbdc1^:server/M1_SOURCE_CONFIG_REF.RETIRED.md`.

## ② 변경 — 가이드 «셋»의 가리킴을 바꿨다

```diff
# docs/guide/config/bonding_plan_config.md · transfer_plan_config.md(다섯 자리) · config_reference/README.md
-> `server/M1_SOURCE_CONFIG_REF.RETIRED.md`
+> `docs/history/20260814_103500_the_deletion_removed_the_only_sign_and_left_the_capability_off.md`
```
그 히스토리 항목이 «은퇴를 기록한 자리»다 — 다만 그 항목 자신도(3·96 줄) `server/M1_SOURCE_CONFIG_REF.RETIRED.md` 를 근거로 «인용»하고 있다. 히스토리는 추가 전용이라 그 인용은 «그 시점의 사실»로 남는다.

## ③ 아키텍처 영향

- 「은퇴는 표지를 남긴다」 관례에서 «한 표지»가 빠졌다. 관례 자체가 은퇴한 것인지는 이 커밋이 말하지 않는다 — `server/migrations/` 의 표지 둘(`add_core_wafer_map_key_index.RETIRED.md` · `migrate_map_meta_to_wafer_id.RETIRED.md`)은 이 시점에 «그대로» 있다.
- 은퇴 기록의 «정본 자리»가 `server/` 의 표지에서 `docs/history/` 로 옮겨졌다 — 이 항목 하나에 대해서만.

## ④ 그때 남아 있던 것

- **코드와 시험이 여전히 지워진 파일을 가리킨다.** `server/transfer_plan.py` 주석 **9 자리**(:66 · :85 · :158 · :435 · :704 · :976 · :1435 · :2360 등) · `tests/test_transfer_plan.py` 2 · `test_transfer_plan_derivation.py` 1 · `test_availability_relaxation.py` 1 — 「approval, measured cause, revival」을 «그 파일»에서 읽으라고 적혀 있다. 이 커밋은 가이드 셋만 고쳤다.
- 표지가 «소유자 판정 대기»로 적어 둔 것 — `GET /api/bonding-plan/core-summary` 를 없앨지(화면 호출 0 · 역할 다섯 missing · M2 가 온전히 답함, S-28 과 한 자물쇠, 09-11 `c22b5e83` 에서 구현자가 «지어 놓고 멈춘» 것) — 는 표지가 사라져도 «판정된 기록이 없다».
- 표지가 적은 «값을 치른 둘»(코어 프레임 정렬 · fail_breakdown 소스별 키)은 `test_core_frame_fail_source_is_not_aligned` 가 «반대로» 박아 두고 있어 코드에 남아 있다 — 표지가 없어도 시험이 그 사실을 든다.
- 이 삭제를 요구한 소유자의 말 «원문»은 어디에도 없다. 커밋 제목의 「at the owner's word」가 유일한 기록이다.

---
📎 수(162 줄 · 자리 9 · 시험 4)는 `git show 928cbdc1^` 과 HEAD 에서 «센» 것이다.
📎 은퇴 당일: `20260814_103500_the_deletion_removed_the_only_sign_and_left_the_capability_off.md` · 같은 날의 이웃: `20260814_083700_both_virtual_joins_retired_and_the_derivation_was_already_dead.md` · 「판정을 구현으로 색인하면 구현과 함께 죽는다」(2026-08-29) — 이번엔 «문서»가 죽었고 색인(코드 주석)이 남았다.
