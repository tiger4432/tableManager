# `effort_metric.json` 세팅 — V1 계기(상호작용 점수) 배점

> **Status:** 🟢 Living | **Last-verified:** 2026-07-29 (§3 확인 절차 정정 — `GET /api/effort/config` 에코는 **형식만** 검사하므로 존재하지 않는 라우트 이름도 통과한다(실패할 수 없는 검사). 실 라우트 id·클라 콘솔 경고로 교체. 직전: 신설 — 계기 서버 구현과 동시) | **Owner:** Backend
> 상위: [폴더 인덱스](./README.md) · 계기 정의의 정본은 [data_model §2.4](../../architecture/data_model.md) · 응답 계약은 [backend](../../architecture/backend.md) · 왜 이 계기인가는 [SYSTEM_OVERVIEW §1](../../overview/SYSTEM_OVERVIEW.md)

<!-- Loader evidence (2026-07-29):
  load: server/effort_metric.py load_config (missing/corrupt -> {} = defaults)
  weights: effort_metric.resolve_weights (per-key validation; bool/non-numeric/negative/NaN -> warn + that key's default)
  transitions: effort_metric.resolve_context_preserving_transitions (non-list -> [] ; malformed entry -> dropped + warn)
  serve: main.get_effort_config -> GET /api/effort/config (effort_metric.get_public_config)
  aggregate: main._get_effort_stat -> crud.get_effort_stats(db, weights) (weights re-read per cache miss)
-->

## 1. 언제 이 파일을 만지는가

- **배점을 재조정할 때** — 키입력/마우스/화면이동의 상대 비용을 바꿀 때
- **컨텍스트를 유지하는 화면 전이를 0점으로 선언할 때** — 예: 맵 에디터 안에서 자재 서브컨텍스트로 넘어가는(`map_editor` → `map_editor:material`) 것처럼 사용자가 "이동했다"고 느끼지 않는 전이
- **파일이 없어도 정상입니다** — 전 항목 기본값(`key:1 · mouse:3 · nav:5`, 전이 목록 비어 있음)으로 동작합니다.

> ⚠️ **배점을 바꾸면 과거 데이터까지 새 배점으로 다시 읽힙니다.** 저장되는 것은 원시 카운트뿐이고 점수는 조회 시점에 계산되기 때문입니다(의도된 설계 — 배점을 바꿔도 before/after 비교가 살아 있습니다). 반대로 말하면 **배점을 바꾼 뒤의 숫자는 바꾸기 전의 숫자와 직접 비교할 수 없습니다.** 기준선을 재는 중이라면 배점을 고정하십시오.

## 2. 세팅 절차

1. **스냅샷**(파일이 이미 있을 때만 의미 있음): `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. 파일이 없으면 `effort_metric.json.sample`을 `effort_metric.json`으로 복사합니다.
3. 값을 수정합니다:

   ```json
   {
     "weights": { "key": 1, "mouse": 3, "nav": 5, "nav_preserved": 0 },
     "context_preserving_transitions": [
       { "from": "map_editor", "to": "map_editor:material" }
     ]
   }
   ```

   각 가중치는 **0 이상의 유한한 숫자만**(음수·문자열·boolean·NaN은 경고 후 **그 키만** 기본값으로 되돌아갑니다 — 음수를 허용하면 "많이 클릭할수록 점수가 좋아지는" 뒤집힌 계기가 됩니다).

   🚨 **라우트 이름은 개념어가 아니라 클라이언트가 실제로 쓰는 id입니다.** 어휘의 정본은 `client2/src/effort_meter.js`의 **`ROUTE_IDS`**(= `countNav` 호출부가 넘기는 id 전량)이며, 2026-07-29 기준 `grid` · `map_editor` · `admin` · `enrichment` · `graph` · `trace` · `grid:table` · `grid:viewmode` · `grid:log_jump` · `enrichment:rule` · `map_editor:material`입니다(규약 `페이지:서브컨텍스트`). "DOE"·"dt map" 같은 **기능 이름을 그대로 적으면 그 항목은 아무 전이와도 매칭되지 않습니다** — 그런데 서버는 형식만 검사하므로 그대로 서빙합니다(§3 참조).

   **라우트 이름은 정확히 일치해야 합니다 — 와일드카드(`*`)는 거절됩니다.** `{"from": "*", "to": "*"}` 같은 항목은 매칭이 정확 일치라서 **아무것도 면제하지 못하면서 선언한 것처럼 보이는** 무력 리터럴이 됩니다. 서버는 이런 항목을 무시하지 않고 거절하며(경고 로그 + 서빙 목록에서 제외), 나머지 정상 항목은 그대로 유지합니다. 면제하려는 전이는 **하나씩 명시**하십시오.
4. 저장 — 반영은 자동입니다: **다음 조회부터** 디스크에서 다시 읽습니다. 재기동·reload 불필요.
   (단 대시보드 집계는 60초 TTL 캐시를 거치므로 숫자에 반영되기까지 최대 1분 걸립니다.)

## 3. 반영 확인

```bash
curl http://127.0.0.1:8080/api/effort/config
```

```json
{"weights": {"key": 1, "mouse": 3, "nav": 5, "nav_preserved": 0}, "context_preserving_transitions": []}
```

- 이 응답이 **클라이언트가 읽는 유일한 정본**입니다. 클라는 자기 사본을 두지 않습니다.
- 값이 안 바뀌면 편집한 파일이 `.sample`이거나 `.bak`인지 확인하십시오(실파일은 확장자 없는 `effort_metric.json`).
- 잘못된 값은 **서버 로그**에 남습니다: `[EffortMetric] weight 'mouse' must be finite and >= 0 ...` / `[EffortMetric] REJECTED malformed transition entry ...` / `[EffortMetric] REJECTED wildcard transition entry ...`. 경고가 보이면 그 항목은 무시되고(가중치는 기본값으로) 서빙 목록에서 빠집니다.

> 🚨 **이 응답에 항목이 보이는 것은 "면제가 동작한다"는 증거가 아닙니다 — 배점에만 쓰십시오.**
> 서버는 전이 항목의 **형식만** 검사합니다(`from`/`to`가 비지 않은 문자열인가, `*`가 없는가). **라우트 이름이 실제로 존재하는지는 검사하지 않으므로**, `{"from": "doe", "to": "dt_map"}`처럼 존재하지 않는 이름도 **그대로 되돌려줍니다.** 즉 이 curl로 "확인"하면 아무것도 면제하지 못하는 오타 항목이 **항상 통과**합니다 — 실패할 수 없는 검사는 검사가 아닙니다(2026-07-29 QA 지적).
>
> **실제 확인 방법**: 브라우저에서 아무 화면이나 열고 **개발자 도구 콘솔**을 보십시오. 클라이언트(`client2/src/effort_meter.js`)가 서빙된 목록을 자기 라우트 어휘(`ROUTE_IDS`)와 대조해, 아무것도 면제하지 못하는 항목마다 **한 줄씩 에러를 찍습니다**:
>
> ```
> [effort_meter] context_preserving_transitions entry EXEMPTS NOTHING — unknown route id: doe, dt_map. Entry: {from: "doe", to: "dt_map"} | known route ids: grid, map_editor, ...
> ```
>
> **콘솔에 이 줄이 없으면 항목이 살아 있는 것이고, 있으면 그 항목은 무효**입니다. 같은 내용을 콘솔에서 직접 물어볼 수도 있습니다 — **운영 빌드에서도 됩니다**:
>
> ```js
> window.__assyEffort.getConfig()
> // { loaded, weights, context_preserving_transitions: [인정된 것], rejected_transitions: [{entry, reason}], known_routes: [...] }
> ```
>
> `loaded: false`면 **설정을 아예 못 받은 상태**입니다(허용목록이 비어 있는 것과 결과는 같지만 원인이 다릅니다 — 이 경우 콘솔에 `GET /api/effort/config failed` 경고도 함께 뜹니다).
>
> ⚠️ **항목은 `{"from": ..., "to": ...}` 객체만 유효합니다.** `"grid>trace"` 같은 문자열 축약은 **서버가 버리므로** 클라이언트도 거절합니다 — 한쪽만 관대하면 작성자가 쓴 항목이 한쪽에서만 지켜지고 아무도 알려주지 않습니다.
> **점수로도 확인할 수 있습니다**: 면제가 실제로 걸리면 그 이동은 `nav`가 아니라 `nav_preserved`로 쌓입니다(§5의 두 카운트는 따로 저장됩니다).

## 4. 잘못됐을 때

파일을 지우면 **전 항목 기본값**으로 즉시 돌아갑니다 — 이 파일에 한해서는 삭제가 가장 빠른 복구입니다. 스냅샷 복원:

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore effort_metric_<yymmdd>.json.bak --yes
```

→ [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md)

## 5. 키 참조

| 키 | 타입 / 기본값 | 의미 |
|---|---|---|
| `weights.key` | 0 이상 숫자, 기본 `1` | 키 입력 1회의 비용 |
| `weights.mouse` | 0 이상 숫자, 기본 `3` | 마우스 클릭 1회의 비용 |
| `weights.nav` | 0 이상 숫자, 기본 `5` | **컨텍스트를 잃는** 화면 이동 1회의 비용 |
| `weights.nav_preserved` | 0 이상 숫자, 기본 `0` | **컨텍스트를 유지하는** 화면 이동 1회의 비용. 기본 0이라 오늘 점수에 영향이 없습니다 |
| `context_preserving_transitions` | 객체 배열, 기본 `[]` | 유지 이동으로 분류할 전이의 **허용목록**. 항목 형식 `{"from": "<라우트id>", "to": "<라우트id>"}` (정확 일치, 와일드카드 거절). 라우트id 정본은 `client2/src/effort_meter.js`의 `ROUTES` — 서버는 **이름의 실존을 검사하지 않습니다**(§3의 확인 방법) |

(`_`로 시작하는 `_*_doc` 키는 sample의 주석용 — 코드가 읽지 않습니다.)

> **면제한 이동도 버리지 않고 셉니다 (`nav_preserved`).** 허용목록에 걸린 전이는 `nav`에서 빼는 것이 아니라 **`nav_preserved`로 따로 집계**되어 저장됩니다(현재 배점 0 → 점수 영향 없음). 수집 시점에 버리면 그 면제 판단이 저장된 숫자에 굳어 되돌릴 수 없고, **이 계기는 소급 산출이 불가능**하므로 판단이 틀렸을 때 기준선이 영구히 틀린 채 남습니다. 둘 다 보관하면 나중에 `weights.nav_preserved` **하나만 올려** 과거 데이터를 통째로 재채점할 수 있습니다 — 허용목록이 저장이 아니라 **해석**이 되는 것입니다.
>
> **기본은 "상실"입니다 (`context_preserving_transitions`).** 목록에 **선언되지 않은 모든 전이는 이동 가중치(5점)로 계산**됩니다. 반대로 하지 않은 이유는 낙관 편향입니다 — "웬만한 이동은 컨텍스트가 유지된다"고 기본값을 잡으면 계기가 공수를 실제보다 낮게 보고하고, 그 편향은 계기를 소유한 쪽에 유리한 방향으로만 작동합니다. 목록은 **비어 있는 상태로 출발**하며, 항목은 라우팅을 소유한 쪽(클라이언트)이 제안하고 총괄이 승인해 추가합니다. 판정 자체는 클라이언트가 수행하고, 서버는 이 목록을 그대로 서빙할 뿐입니다.
