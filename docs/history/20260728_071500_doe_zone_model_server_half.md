# DOE 층 구조가 band에서 **구역**으로 옮겨왔다 — 그리고 컬럼 하나가 `number`였다

> 2026-07-28 07:15 · 도메인 Server(전사 계획 엔진 · 제품 소유 스키마)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 계약: [MAP_EDITOR_SPEC §6](../spec/MAP_EDITOR_SPEC.md) · 설정: [CONFIG_GUIDE §5.8](../guide/CONFIG_GUIDE.md)
> 정본 벡터: `contracts/doe_band_rules/vectors.json` (클라 하네스와 서버 테스트가 **같은 파일**을 채점한다)

## 배경 — 저장이 하나도 되지 않고 있었다

클라이언트는 zone 모델(STACK + 1H/MID/TOP)로 착지했는데 **서버 쪽 절반이 없었다.**

1. `stack`·`mat_1h`·`mat_mid`·`mat_top`이 `server/product_tables.py`에 **선언만 돼 있고 물리 ALTER가 실행되지 않았다.**
   라이브 DB의 `map_split_registry`는 `… knobs, bands`에서 끝나 있었다(읽기 전용 조회로 확인).
   그 상태에서 클라가 zone을 쓰면 `crud.py`가 미선언 컬럼을 드롭하고 **200을 돌려준다** — 그리고 legend 저장은
   `replace_map`이라, 그 200이 **층 구조가 없는 행으로 계획 전체를 갈아치운다.** 초록색 자동저장 칩과 함께.
   클라는 이 상태를 스스로 감지해 저장을 보류하고 있었다(`zone-columns-missing`).
2. `transfer_plan.REGISTRY_ROLES`가 여전히 `bands`를 **필수**로 요구했다. 그래서 `bands`를 지우려는 모든 사이트에서
   `GET /api/transfer-plan/validate`가 404였고, 컬럼은 "폐기됐지만 선언은 유지"라는 상태에 묶여 있었다.

## 변경 내용

### ① 물리 컬럼 — 그리고 `stack`은 **`number`가 아니라 `string`**이어야 했다

`install_product_tables.py --apply --overwrite-drift`로 선언을 반영하자 config watcher가 ALTER를 실행했다.
그런데 `stack`이 `"number"`로 선언돼 있어 물리 컬럼이 `double precision`으로 만들어졌다. **그 타입으로는 이 모델이 성립하지 않는다:**

```
'16'   -> 16          (정상)
'0x10' -> RAISES ValueError    ← crud.cast_value_by_type. 저장 자체가 실패한다
'nope' -> RAISES ValueError
'7.5'  -> 7.5                  ← 조용히 "고쳐진다". 다음 읽기에서 7층이 된다
```

읽을 수 없는 STACK은 **왕복에서 살아남아야 한다.** V5가 그것을 근거로 차단하고, 패널이 사용자에게 자기가 적은
글자를 보여 주고, `planRowToRecord`가 원문을 엑셀로 내보낸다. 숫자 컬럼은 그 셋 중 무엇도 담을 수 없다.
`'7.5'`가 `7.5`로 저장되고 다음 읽기에서 7로 잘리는 것은 **이 zone 모델이 닫으려는 결함 그 자체**다.

→ `product_tables.py`에서 `"stack": "string"`으로 고치고, 잘못 만들어진 `double precision` 컬럼을
`DROP COLUMN` 후 `sync_dynamic_tables_schema`로 재생성했다(전량 NULL임을 먼저 확인).
**`sync_dynamic_tables_schema`는 없는 컬럼을 추가만 하고 타입은 바꾸지 않는다** — 이 경로는 문서화했다.

### ② `bands`가 필수 역할에서 빠지고, zone 넷이 그 자리에 들어갔다

```python
REGISTRY_ROLES = ("ref_table", "map_key", "value", "stack", "mat_1h", "mat_mid", "mat_top")
REGISTRY_LEGACY_ROLE = "bands"      # 선택 — 있으면 폐기 계획을 읽고, 없으면 없는 대로 간다
```

폐기됐고 writer가 없는 컬럼은 **필수 역할일 수 없다.** 다만 실계획이 아직 거기 있으므로
`bands_to_zones`가 읽어 옮긴다 — **그리고 표현할 수 없는 배치는 접지 않고 거부한다:**

```
n = 1        -> MID 단독 (스택 전체를 덮는 한 구간이 곧 "그 사이 전부")
n > 1        1H  = band[0]   (정확히 1층만 덮을 때)
             TOP = band[n-1] (정확히 STACK층만 덮을 때)
             MID = 남은 것. 남은 것이 **하나 이하**여야 한다
거부         구간 4개 · 읽을 수 없는 `to` · 역전된 `to` · 1층에서 시작하지 않는 첫 구간
```

`prevTo`는 읽을 수 없는 `to`를 **건너뛴다** — band를 편집 중인 패널에서는 그것이 옳았다(보여 주고, 표시하고,
계속). 마이그레이션에서 건너뛰면 **스택이 조용히 짧아진다.** 그래서 여기서는 거부다.
접은 결과를 저장하면 `replace_map`이 서버의 진짜 계획을 그 손실 읽기로 덮는다.

### ③ V1~V5 — 그리고 사라진 검사들

```
V5  STACK을 양의 정수로 읽을 수 없다      <- 가장 먼저 판정한다
V2  STACK 1인데 1H·TOP이 둘 다 있다
V1  MID 구역이 비어 있지 않은데 MID가 없다  <- 조건부. 구역이 0층이면 발동하지 않는다
V4  자재 토큰을 읽을 수 없다
V3  로트 전체와 그 로트의 슬롯이 같은 BIN에  <- 계획 전체의 성질
```

구 B1/B2(`FROM>TO`·`FROM<1`)·B5(겹침)·B6(구멍)·B4/B9는 **완화된 것이 아니라 말할 수 없는 상태가 됐다.**
세 구역이 `1..STACK`을 구성적으로 덮기 때문이다. 코드에 그 검사가 없는 것은 누락이 아니며, 그 사실을
`test_removed_overlap_and_gap_checks_stay_removed_as_behaviour`가 **동작으로** 못 박는다(`hasattr` 단언은
다른 이름으로 되살아난 같은 검사를 잡지 못한다).

살아남은 하나가 **V5**다. 구 모델은 값의 높이를 덮인 층에서 **유도**해서, 배정되지 않은 위쪽 구간이 그냥
max를 낮추고 다른 규칙은 전부 통과했다 — 16층 스택이 조용히 15층이 됐다. zone은 높이를 유도하지 않고
STACK이 말한다. 그 구멍이 닫히는 것은 STACK을 **읽을 수 있는 동안뿐**이므로, V5는 차단이고 가장 먼저 차단한다.

### ④ 자재 토큰 — `_split_material`이 아니라 공유 문법

```
토큰 ::= lot ["_" slot] [":" BIN]
```

`_split_material`(선언된 `material_identity` 규칙, 마지막 `_` 기준)은 `ADFE1H_01:3`을 슬롯 `01:3`으로 읽어
**존재하지 않는 슬롯을 물어보고 멀쩡한 자재에 대해 확신에 찬 0을 낸다.** 그래서 해석은 공유 계약의
`parse_material_token`이 한다. `material_identity`는 **게이트로만** 남는다 — 클라는 config를 읽지 못하므로
파싱 규칙이 config에 살면 양쪽이 갈리고, 갈리는 순간 한 화면에 두 개의 가용치가 생긴다.

풀 키는 `json.dumps([lot, slot_or_None, bin])`이다. **분리자로 잇지 않는다** — 로트 이름에 나올 수 없는 문자가
없고, 보이지 않는 제어 문자는 합법인 것보다 **더 나쁘다**(도구가 지운다). 실제로 U+001F로 이었던 판에서
`MID1_12:3`과 `MID11_2:3`이 둘 다 "MID1123"이 되어 무관한 두 풀이 한 행으로 합쳐졌다.

로트 전체 토큰(`MID1`)은 문법상 정상이지만 **이 엔드포인트가 값을 매기지 않는다**(`source_scope_unpriced`) —
`get_lot_bin_summary`가 로트 하나의 `remaining`을 지어내지 않기로 한 것과 같은 이유다.

## 검증

| 무엇을 | 어떻게 | 결과 |
|---|---|---|
| 서버 스위트 | `pytest server/tests/` | **815 passed / 0 failed** (기준선 753) |
| 공유 계약 | `server/tests/test_doe_zone_model.py` (신규 27건) | 8개 벡터 그룹 전량 채점 |
| 클라 하네스 3종 | `node contracts/<name>/client_harness.mjs` | 304 + 71 + 82 assertions, 전부 OK |
| **뮤테이션** | 결함 30종 주입 → 계약 테스트 실행 → 바이트 단위 원복 | **29 killed / 1 survivor(등가 뮤턴트, 코드에 명시)** |
| 물리 컬럼 | `information_schema.columns` | 넷 다 `character varying` |
| 라이브 왕복 | 재기동 후 실제 :8080에 `replace_map` 저장 → 재조회 | `'0x10'`이 **원문 그대로** 살아 돌아왔고 V5가 발화 |
| 폐기 계획 | 라이브 `bonding_map\|AAA` 3행 `/validate` | `doe_count=3`, 구역별 소요 유도(46/322/168/…), `layer_range_invalid` 0건 |

**뮤테이션 검증이 실제로 구멍을 하나 찾았다.** `bandsToZones`의 역전 검사(`if val <= prev`)를 통째로 제거해도
계약 벡터가 전부 통과했다 — 벡터의 `[to 10, to 5]`가 역전 검사 없이도 "중간 구간이 2개"에서 어차피 거부되기
때문이다. `[to 1, to 1]`이 그 축을 활성화한다(역전 검사가 없으면 두 번째 구간이 빈 구간 `(2,1)`이 되고,
첫 구간이 1H로 빠지면서 남는 것이 하나뿐이라 **`ok: True`로 통과한다**). 회귀 테스트를 추가했다.

## 미해결 / 후속

- **`--overwrite-drift`의 부작용**: 항목 단위가 아니라 전부에 걸려서, zone 컬럼을 넣는 김에 폐기 2종
  (`map_doe`·`map_doe_source`)이 함께 선언되고 **빈 물리 테이블까지 새로 만들어졌다**(운영자가 이전에 지워 둔
  것이었다). 데이터 위험은 없지만 원치 않은 변경이며, 되돌릴지는 총괄 판단이다.
- **`material_identity`의 `separator`/`compose`가 이제 파싱에 쓰이지 않는다.** 게이트 의미만 남았으므로
  은퇴시킬지 재정의할지 결정이 필요하다(경계 계약 — `/api/transfer-plan/stages`가 노출한다).
- **자재별 KNOB의 저장처는 만들지 않았다.** 별도 절 참조 — 손으로 적는 컬럼이 답이 아니다.
