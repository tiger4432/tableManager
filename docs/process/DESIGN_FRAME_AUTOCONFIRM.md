# 🧭 DT · CORE 프레임 자동 확정 체인 — 개발 계획서

> **Status:** 🟡 Plan (착수 전) | **개정:** 2026-08-09 (정본 전환 반영) | **Owner:** 총괄
>
> ⚖️ **사용자 결정 2026-08-09 — 확정 정본은 `dt_inventory`다.**
> `frame_confirmation` / `frame_confirmation_source` 기반 별도 확정 이력은 **폐기 예정**이고
> 새 기능은 그 경로에 쓰지 않는다. `dt_inventory`가 `dt_job` 단위로 **DT/Core 프레임 ·
> lot/slot · 좌표 변환 메타**를 함께 들고, 갱신은 **일반 enrichment 또는 일반 chain의
> upsert**로 한다. 이 문서의 초판(§`frame_confirmation` 기록 · 수동 우선 · 전파 S3)은
> **구현 대상이 아니다.**

```text
dt_log ──(정렬 채점 · 게이트)──> dt_inventory
        frame · lot/slot · 변환 메타 upsert

dt_log + dt_inventory ──(확정 메타 적용)──> dt_map
        표준 좌표 파생뷰 replace_map
```

---

## 0. 한 문장

**정렬기가 이미 「어느 프레임인가」에 답한다. 이 트랙이 하는 일은 그 답을 `dt_inventory` 한 행으로 쓰는 것과, 그 행이 있을 때 `dt_map`을 표준 좌표로 다시 만드는 것 둘뿐이다.**

새 채점기도 새 스키마도 없다. 위험은 「어떻게 판정하나」가 아니라 **「언제 판정하지 않나」**, 그리고 **「파생뷰를 얼마나 자주 갈아엎나」**에 있다.

---

## 1. 이미 있는 것 — 실측 2026-08-09

| 필요한 것 | 어디 | 상태 |
|---|---|---|
| 8후보 채점 | `map_alignment.score_candidates` | ✅ 라이브 |
| 신뢰도 문턱 | `map_overlay_config.alignment.min_margin_dies` / `min_discriminating_dies` (20/20) | ✅ 유도 근거 있음 |
| 판정 어휘 | `ruling.reason_code` · `state` · `metric` · `geometry_assumed` | ✅ |
| 후보별 배치 | `ruling.by_frame` | ✅ 2026-08-09 |
| **정본 표** | `dt_inventory` — `dt_job`(업무키) · `dt_lot` · `dt_slot` · `dt_frame` · `core_frame` · `dt_x_base/sign/offset` · `dt_y_…` · `core_x_…` · `core_y_…` | ✅ **컬럼 17개 전부 선언돼 있다** |
| 파생 체인 | `chain_rules.json` → **`dt_log_to_dt_map`** | ✅ **이미 존재** |
| 체인 실행기 | `chain_ingestion_worker` + 매퍼 | ✅ |
| upsert 경로 | `crud.apply_batch_updates` (업무키 `dt_job`) | ✅ |

**⇒ 새로 지을 실행 코드는 셋이다: ① 게이트 ② 확정 프레임 → 변환 6파라미터 유도 ③ 파생 재생성 트리거.**

---

## 2. 게이트 — 자동이 쓰는 조건

`dt_inventory`에 자동으로 쓰는 것은 **아래 전부**가 참일 때만이다. 하나라도 거짓이면 **행을 안 쓰고 사람 대기열로 남긴다**(실패가 아니다).

```
① state == "scored"                          승자가 있다
② margin        >= min_margin_dies           문턱은 config, 코드에 상수 금지
③ discriminating >= min_discriminating_dies
④ ruling.metric == "index"                   ← DT 단계에서는 정확 축만
⑤ ruling.geometry_assumed == False           빌린 규격 위에서 자동 확정하지 않는다
⑥ 그 `dt_job` 행의 해당 컬럼이 비어 있거나 자동 출처다
```

🔴 **④가 이 계획에서 가장 중요한 줄이다.** 값·점유 축은 **평평하다** — 실측에서 8후보가 같은 다이를 차지했고, 보행 축이 거울을 대체한 뒤로는 `tl`/`tr`이 **같은 기하**라 값 축에서 **항상 동점**이다. 값 축의 「승자」는 기계가 밀 종류의 답이 아니다.

🔴 **⑤의 근거**: 「이 둘은 같은 웨이퍼다」는 **조작자가 낼 자격이 있는 주장**이지 기계가 낼 것이 아니다.

⚠️ **문턱을 낮춰 발화율을 올리려는 유혹이 반드시 온다.** `map_overlay_config.json`의 `__derivation`이 그 자리를 막는다 — 20 미만이면 4/88 보행이 순위를 받고, 실측에서 그 1등은 8후보 중 **2건에서 틀린 프레임**이었다. **발화율은 문턱이 아니라 `dt_index` 충전율로 올린다.**

📌 **⑥이 옛 계획의 「수동 우선」을 대체한다.** 별도 이력이 없으므로 우선순위는 **행의 출처 표기**로 판정한다. `cell_sources`의 `SOURCE_PRIORITY`가 이미 「수동이 자동을 이긴다」를 하고 있고, `dt_inventory`도 일반 upsert 경로를 타므로 **그 층이 그대로 적용된다** — 두 번째 우선순위 규칙을 만들지 않는다.

---

## 3. 🔴 새 유도 하나 — 확정 프레임 → `base/sign/offset` 12개

`dt_inventory`의 변환 메타는 **선언형**이다(축마다 `base` · `sign` · `offset`). 채점기가 내는 것은 **프레임(회전 + 시작 모서리)과 원점**이므로, 그 둘을 12개 필드로 옮기는 유도가 **이 트랙에서 유일하게 새로 쓰는 수식**이다.

🔴 **이 저장소는 좌표 대수를 손으로 옮기다 네 번 값을 치렀다.** 그래서 규율은 하나다:

- **손으로 쓰지 않는다.** `map_overlay.make_frame_transform`을 불러 **세 점을 찍어** 선형부를 읽는다(변환은 아핀이므로 세 점이면 정해진다). `start_for_placement`가 이미 이 방식을 쓰고 그 주석이 이유를 적어 뒀다.
- **검산은 왕복이다.** 유도한 12파라미터로 셀을 변환한 결과가 `make_frame_transform`의 결과와 **전 셀에서 같아야** 한다. 한 단언이 부호·축교환·오프셋 셋을 다 잡는다.
- ⚠️ **퇴화 픽스처 금지.** 회전 0 · 오프셋 0 · 정사각 격자에서는 틀린 유도가 통과한다. 검산은 **회전 90/270 × 비대칭 유효맵**에서 한다.

---

## 4. 단계

### S1 · 측정 먼저 — 실행 코드 0줄
라이브 `dt_job` 전체에 게이트를 **판정만** 돌려 세 수를 낸다: 자동 발화 가능 · 사람 대기 · **탈락 사유 분포**. 읽기 전용 스크립트 하나, 쓰기 없음.
📌 「대부분 `dt_index` 없음으로 탈락」이면 **이 트랙보다 순번 충전이 먼저**다. 그 답이 나오기 전에는 자동화의 가치를 모른다.

### S2 · 게이트 함수
순수 함수 하나 — `(ruling, thresholds, existing_row) -> (fire, reason_code)`. **채점기 안에 넣지 않는다**: 채점은 읽기이고 게이트는 정책이다. 테스트는 이 함수에만 붙는다.

### S3 · 프레임 → 12파라미터 (§3)
왕복 검산 포함. **`dt_frame`과 `core_frame`은 독립 축**이므로 각각 자기 6개를 채운다.

### S4 · `dt_inventory` upsert
일반 enrichment/chain 경로. 업무키 `dt_job`. **새 쓰기 경로를 만들지 않는다.**

### S5 · `dt_map` 재파생
`dt_log + dt_inventory → dt_map`, `replace_map`. ⚠️ **여기가 이 계획의 비용 지점이다** — 보드 실측: `replace_map` 퍼지가 `cell_sources` 데드 튜플을 **수십만** 낸다(셀당 8행 × 2만 셀, **안 바뀐 맵을 다시 밀어도 똑같이**). 확정이 바뀔 때마다 통째로 갈아엎으면 이력이 「조작자가 16만 셀을 바꿨다」고 **거짓말**한다.
⇒ **차분 인식이 선행이거나 최소한 같은 라운드**여야 한다(보드 ②와 같은 항목).

### S6 · CORE — D1 이후에만
`_BINFP_MIN_SUPPORT = 3`이 실제 bin 카디널리티에서 발화하지 않는다(`core_wafer_map`은 `c_bn` 2종 → 121다이 소스가 `matched=70, reason=None`). **이 판정 전에 CORE 축을 배선하지 않는다.**
⚠️ 결합 채점기(#36)의 픽스처는 후보 공간이 `front` 고정 + 좌상/우상으로 바뀐 뒤 **다시 재야 한다** — `seed_dt_index_walk.py`의 `core_frame` 정답 둘이 `*_back`이었고 그 절반은 도달 불가다.

---

## 5. 착수 전 답할 것

1. **`wafer_map_metadata`는 누가 쓰나?** 맵 에디터의 다시 그리기가 그 표를 읽는다(`grid_start_x/y`·`rotation`). 정본이 `dt_inventory`로 가면 ⓐ 체인이 메타도 같이 쓰거나 ⓑ 에디터가 `dt_inventory`를 읽어야 한다. **정하지 않으면 화면이 옛 정본을 계속 본다.**
2. **기존 `frame_confirmation` 27행은?** 권고: **그대로 둔다**(추가 전용 이력, 읽기만). 옮기면 두 정본이 잠시 공존한다.
3. **S5의 재파생 주기.** 확정마다인가, 배치인가. 차분 인식 없이 확정마다면 데드 튜플이 지배한다.

---

## 6. 하지 않는 것

- 새 채점기 · 새 좌표 변환기 · 새 프레임 어휘 · 새 스키마 — **0개**
- 새 쓰기 경로 — `dt_inventory`는 일반 upsert를 탄다
- 화면 신설 — 자동 확정은 화면이 없다
- 문턱 조정 · 값 축 자동 확정 (§2)

---

**연결:** [`PROJECT_STATUS.md`](PROJECT_STATUS.md) · [`../spec/MAP_ALIGNMENT_SPEC.md`](../spec/MAP_ALIGNMENT_SPEC.md) · [`DESIGN_TRACKS.md`](DESIGN_TRACKS.md)
