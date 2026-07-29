# 맵을 열 때 규격을 기억하지 않는다 — 로드 시 프리셋 라우팅 서버 절반 (F5)

> 2026-07-30 03:35 · 도메인 Server(맵 인프라 · 선언 조회 · 정체성 캐노니컬화)
> 상위: [guide/config/map_overlay_config §2-bis](../guide/config/map_overlay_config.md)(**운영 선언 절차 — 정본**) · [CONFIG_GUIDE §5.8-bis](../guide/CONFIG_GUIDE.md) · [architecture/backend §2](../architecture/backend.md) · 보드 [PROJECT_STATUS F5](../process/PROJECT_STATUS.md)
> 선행: [7b 맵 정체성 캐노니컬화](./20260729_014707_core_value_1_instrument_replaced.md) · [valid_die_ref 서버 절반](./20260729_101500_valid_die_ref_server_half.md)
> 후속: 클라 절반(map-pm — F1ⓑ 뒤) · 계약 채점(contract-keeper)

## 배경 — 틀린 규격은 클릭 낭비가 아니라 데이터 사고다

맵을 열 때 어떤 물리 규격으로 열지는 지금 **운영자의 기억**이거나, 아무것도 안 고르면
**패널에 남아 있던 이전 맵의 설정**이다. 앞은 V1 계기에 클릭으로 잡히고, 뒤가 더 나쁘다 —
규격이 틀리면 `inside`가 달라지고, `inside`가 달라지면 **저장 가능한 셀 집합이 달라져**
대조 게이트에서 거부된다.

핵심 어려움은 테이블 단위로 답할 수 없다는 것이다. **같은 테이블 안에서도 맵 키에 따라
프리셋이 다르다** — 제품마다 랏 이름 형식이 다르기 때문이다.

## 해석 사슬 — 순서가 계약이다

```
맵 키 → (키 컬럼에서 lot 추출) → ① 제품코드 조회 테이블 → 제품코드 → 프리셋
                                      │ 행 없음 (정상!)
                                      ▼
                                  ② 텍스트 패턴 규칙(순서 있음, 첫 매치 승리) → 프리셋
                                      │ 매치 없음
                                      ▼
                                  ③ 라우팅 없음 — 지금 동작 그대로
```

## 설계를 좌우한 두 사실 (사용자 확인)

**① 조회 테이블은 운영에만 있고 이 환경엔 없다.** 그래서 **부재가 정상 구성**이어야 한다.
코드에 환경 분기를 넣으면 운영에서만 도는 경로가 생겨 여기서 영영 검증할 수 없다 —
**코드는 하나, 선언만 다르다.** 미선언이면 ①을 건너뛰고 ②로 간다.

**② 그 테이블은 불완전하다** — 모든 lot이 있지 않다. 그래서 **조회 miss는 예외가 아니라
정상**이고, 경고를 띄우지 않는다. 조용히 ②로 넘어간다.

miss를 조용히 만들면 운영자가 선언을 검증할 창이 없어진다. 그래서 결과는 **로그가 아니라
응답 필드**로 낸다 — `lookup{declared, status, product_code}`. 이것이 ①이 왜 안 켜지는지
보는 유일한 창이며, 그 사용법이 config 가이드 §3-4에 표로 있다.

## 절대 우선순위 — 서버가 강제한다

```
wafer_map_metadata(저장된 규격)  >  라우팅  >  패널
```

규격이 이미 등록된 맵은 서버가 `status: "meta_present"` + `preset_key: null`로 **거절**한다.
클라의 규율에 맡기지 않고 구조로 막은 이유: SSOT가 "메타가 정렬의 유일한 기준"이라 했고,
규격을 덮으면 저장 가능 집합이 바뀐다. 라우팅은 **메타 없는 맵의 첫 열기 기본값**이고,
그 맵을 한 번 Push하면 메타가 생기므로 두 번째부터 자동으로 안 걸린다 — 별도 잠금 스위치가
필요 없다.

## 만들지 않은 것 — 새 조회 메커니즘

교차 테이블 선언 조회는 이 시스템에 이미 세 형태로 있다(`table_bindings` ·
Enrichment `reference_views` · F3 `value_suggest`). 새 모듈은 **Enrichment의 형태**를 따랐다:
키별 선언 객체를 로드 시 정규화·검증하고 **잘못된 조각은 고쳐 주지 않고 사유와 함께
버린다**, 그리고 요청마다 디스크에서 다시 읽는다(파일이 작다 — map-presets와 같은 규율).

키 분해·정규화도 새로 쓰지 않았다:

```
map_overlay.resolve_binding → map_key_parts → canonical_bind_value / canonical_map_key
```

**두 번째 정규화 구현은 없다.** 7b가 고친 결함(`LOT_01`이 `LOT_1`을 못 찾는다)이 여기서
재현될 자리가 셋인데(메타 조회 · lot 토큰 · 조회된 제품코드) 셋 다 같은 함수를 경유한다.

## 선언 위치 — `maps.json`이 아니라 `map_overlay_config.json`

프리셋 **본문**이 `maps.json`에 사니 자연스러워 보이지만, `maps.json`은
`POST/DELETE /api/map-presets`가 **파일 전체를 다시 쓰는 API 관리 파일**이다. 손으로 적은
운영 규칙을 둘 자리가 아니다. `map_overlay_config.json`은 기계가 쓰지 않는 선언 전용
config이고, **교차 테이블 선언 조회(`table_bindings`)가 이미 거기 산다.** 규칙은 프리셋을
**키 또는 `name`**으로 참조하는데, 이는 `transfer_plan_config.target_map.preset`이 같은 두
파일 사이에서 이미 쓰는 참조 형태다.

```jsonc
"preset_routing": {
  "dt_map": {
    "lot_key_part": "lot",
    "product_lookup": { "table": "product_master", "key_column": "lot",
                        "value_column": "product_code" },   // 선택 — 미선언이 정상
    "product_presets": { "AB12": "CORE" },
    "rules": [ { "name": "tape lots", "match": "prefix", "value": "T", "preset": "TAPE" } ]
  }
}
```

## 아무 프리셋도 지어내지 않는다

`status != "ok"`이면 `preset_key`/`preset`은 **항상 null**이다. 답을 붙일 수 있는 자리는
`_resolve_answer` 하나뿐이라 구조적으로 보장된다. 특히 **매치한 규칙의 프리셋이 없으면
다음 규칙으로 넘어가지 않고 거절**한다(`preset_missing`) — 넘어가면 아무도 고른 적 없는
프리셋이 답이 되고 오타가 영원히 안 보인다.

## 스케일

맵 로드당 **메타 조회 1회 + 조회 1회**, 둘 다 `LIMIT 1`. 미선언 테이블은 **DB를 아예 건드리지
않는다**(이 환경의 정상 상태가 공짜다 — 테스트가 쿼리 0건을 단언한다). 동적 테이블은
`business_key_val`·`updated_at`만 색인하므로 조회 키 컬럼은 순차 스캔이다 — 인덱스 요구를
config 가이드에 명시하고 최초 사용 시 로그로 1회 알린다.

**색인된 `business_key_val`로 우회하지 않은 이유**: 그것은 `str(v).strip()`을 저장해
`canonical_key_value`와 **다른 정규화**다. 둘이 어긋나면 **miss가 만들어지는데**, 이 설계는
miss를 의도적으로 조용하게 만들었으므로 그 오답이 영영 안 보인다.

## 검증 — 역주입 11건 전부 사망

새 코드 경로를 실제로 실행하는지부터 확인했다(server-pm 교훈). 픽스처의 정규화 축 셋이
살아 있음을 먼저 단언하고(`test_fixture_axes_are_live`), 그 위에서 INV별 결함을 **소스에
직접 주입**해 해당 테스트가 실제로 죽는지 봤다. 바이트 단위 복원 + sha256 대조(autocrlf
함정 회피, `git checkout --`는 동시 작업자 때문에 금지).

| 주입한 결함 | 결과 |
|---|---|
| 조회 테이블 부재를 치명적으로 (INV-R-1) | KILLED |
| 정상 miss가 warning을 낸다 (INV-R-2) | KILLED |
| 매치 없으면 첫 규칙으로 폴백 (INV-R-3) | KILLED |
| 끊긴 프리셋 참조를 다음 규칙으로 흘림 (INV-R-3) | KILLED |
| 조회 쿼리 2회 (INV-R-5) | KILLED |
| 미선언인데 메타 조회 선행 (INV-R-5) | KILLED |
| 규칙을 이름순 정렬로 평가 (INV-R-6) | KILLED(정·역 순서 **쌍**이 검출자) |
| 저장된 규격 검사 제거 (우선순위) | KILLED |
| lot 토큰 캐노니컬화 생략 (INV-R-4) | KILLED |
| 제품코드 캐노니컬화 생략 (INV-R-4) | KILLED |
| 메타 조회가 원문 키 사용 (INV-R-4) | KILLED |

INV-R-4는 테스트 파일 안에도 mutation twin 3쌍이 있다(`canonical_key_value`를 raw `str()`로
격하하면 답이 움직인다) — 자체 정규화를 들인 구현은 이 트윈을 통과하지 못한다.

`sqlite` 수치 affinity가 `'007' == 7.0`을 참으로 만들어 결함 축을 죽이는 것을 피하려고,
캐노니컬화 축은 **DB가 아니라 파이썬 문자열 비교가 판정하는 자리**(패턴 매칭·제품코드 사전
조회·`map_id` 정확 일치)에 걸었다.

**스위트 1279 passed**(기준선 1228 + 신규 51).

## 수정 파일

| 파일 | 내용 |
|---|---|
| `server/map_preset_routing.py` | 🆕 해석기 — 정규화·검증, ①②③ 사슬, 우선순위 강제 |
| `server/main.py` | `GET /api/maps/preset-routing` 신설(가산 — 기존 경로 불변) |
| `server/config/map_overlay_config.json.sample` | `preset_routing` + `__example_dt_map`(어떤 테이블에도 매칭 안 됨) |
| `server/tests/test_map_preset_routing.py` | 🆕 51건 |
| `docs/guide/config/map_overlay_config.md` | §2-bis 운영 선언 절차 · §3-4 반영 확인 표 · 키 사전 |
| `docs/guide/CONFIG_GUIDE.md` | §1 표 · §5.8-bis · §5.9 · 기능별 테이블 체크리스트 |
| `docs/architecture/backend.md` | §2 엔드포인트 행 + Source-of-truth |
| `docs/process/DOC_OWNERSHIP.md` | 신규 서브시스템 행 |

## 남은 것

- **클라 절반**(map-pm, F1ⓑ 뒤): 응답 소비 + `matched_by` 표시 + `status != ok`에서 종전 동작 유지.
- **`GET /api/maps/preset-routing`은 신규 REST 경로**라 경계 계약 — 총괄 비준 대상(소비자가
  아직 없어 되돌리기 자유롭다).
- `PRIMITIVES.md`·`MAP_EDITOR_SPEC.md` 등재는 map-pm이 같은 파일을 편집 중이라 **미착수**.
