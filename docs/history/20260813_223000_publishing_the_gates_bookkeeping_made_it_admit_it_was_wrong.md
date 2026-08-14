# Publishing the gate's bookkeeping made it admit it was wrong

**Date:** 2026-08-13 22:29/22:30 · **Domain:** Server (원장 R-F 구현) + 프로세스(R-H) · **Status:** 착지 — `0198e7e`, 판정 `2e7faeb`

---

## 구현 (`0198e7e`) — R-F 그대로

이름 붙은 거절 사유가 커서 행의 `refusal_reasons` JSONB로 영속됐다 — 자기가 설명하는
집계와 **같은 트랜잭션**으로 — 그리고 `GET /api/ledger/coverage`가 서빙한다.

```sql
refusal_reasons      JSONB,
```

- **총괄의 지시서가 스코프를 틀렸고 레인이 라이터를 읽어 잡았다**: 집계 둘은
  「latest-run scoped」가 아니었다 — `_advance_cursor`는 언제나
  `molecules_refused + EXCLUDED.molecules_refused`로 **커서 행 수명 누적**이었다.
  판정이 `sum(reasons) == molecules_refused`를 못 박으므로 브레이크다운도 누적이어야
  했다 — 수명 집계 옆의 latest-run 브레이크다운이 바로 판정이 금지한 «어긋남»이다.
  화면은 「누적」이라 말해야 하고 `last_at`이 최근성을 든다.
- `refusals_unaccounted`의 부호가 문서화된 클라 계약이 됐다: 0 정상, > 0 배포 이력,
  **< 0 실제 부기 결함**. 라이브 커서 두 행이 당시 1이었다 — 컬럼이 생기기 전에
  계수된 거절 하나, 이름은 프로세스와 함께 죽었다. 화면은 그것을 「1 거절, 사유
  없음」이 아니라 «이력»으로 렌더해야 한다.
- 추가된 질의 전부 원자 수에 O(1), `assy_manager`에서 warm 실측 0.15~0.4 ms급, 전체
  호출 4.3~4.7 ms. ⚠️ 909 원자 박스는 카탈로그 추정이 `count(*)`를 이기는 이유를
  **시연할 수 없다** — 구조적으로 선택했다고 적었지 측정을 가장하지 않았다.
- 마이그레이션은 카탈로그 게이트 + 역방향, DDL은 `ensure_schema`에도 있어 라이터가
  못 쓰는 테이블을 만나지 않고, 리더는 `pg_attribute`를 먼저 묻는다. 두 dev DB에
  적용(12 → 13 컬럼), 원자 수 909/878 무변동, **어느 쪽도 재백필 안 함**.

## 🔴 첫 읽기가 곧바로 생산자의 결함을 드러냈다

`lot_event_translator.py:350`이 `atoms.extend(self._slot_map(...) or [])` — `_slot_map`은
`gate.refuse` **격발 후** `None`을 반환하고 `or []`가 신호를 버렸다. 격리 스크래치
스키마에서 실측: 게이트는 `atomicity_violation`을 세고 로그는 「1 source row produced
nothing」이라는데 `refused_molecules`는 0에 머물고 **형제 원자 셋이 착지**했다.
출하 config에서는 도달 불가, `emit_has_wafer: false` 선언 하나로 도달 가능.
**여기서 고치지 않았다** — 착지 내용을 바꾸는 데이터 동작 결정이라 판정을 요구하고
멈췄다.

## 판정 R-H (`2e7faeb`) — 반쪽 착지는 옛 시스템이 새 옷을 입은 것

수리는 동작 변경이 아니라 **선언된 계약의 복원**이다: config 자신의 주석이 길이
불일치는 분자 «통째» 거절이라 약속하고 있었다 — 대안은 웨이퍼를 틀린 슬롯에 조용히
재귀속시키는 것이므로. 원칙이 승격됐다: **어느 조각에든 refuse가 격발하면 그 분자의
원자는 0개 착지한다. 조각 생존은 `incomplete`의 것이지 거절의 것이 아니다.** 거절
분자를 반쯤 착지시키는 원장은 현 시스템이 실격된 바로 그 모양이다. 라운드의 세 부수
판단(누적 의미론·부호 계약·구조적 추정 선택)도 같은 항목에서 승인됐다.

## 그때 남아 있던 것

- `0198e7e` 검증: 206 passed, 2 skipped. 쓰기 경로 양팔 + 단일 배치가 숨기는 케이스
  (`molecules_per_transaction=1`, 4 flush) 격발.
- 주입은 가드 수용 시 정상 리턴·포착 시 raise — `eb1ae8b` 레인이 틀렸다 플래그한 그
  형태를 피해서.
