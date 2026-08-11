# `audit_history_config.json` 세팅 — 감사 이력 조회 상한

> **Status:** 🟢 Living | **Last-verified:** 2026-08-11 (신설 — `dab9152`+`2630790`, 엔벨로프 전환 `fde424c`) | **Owner:** Backend
> 상위: [폴더 인덱스](./README.md) · 엔드포인트 계약은 [backend §2](../../architecture/backend.md#이력--감사) · 인덱스는 [data_model §2.5](../../architecture/data_model.md) · 프로덕션 게이트는 [PRODUCTION_READINESS](../../process/PRODUCTION_READINESS.md)

<!-- Loader evidence (2026-08-11, commit fde424c):
  load: server/audit_history.load_config (missing/corrupt -> {} = defaults), server/audit_cache.resolve_recent_settings
         재사용: audit_cache는 이 파일을 audit_history.load_config()로 다시 읽는다 — 두 번째 로더를 만들지 않았다.
  resolve: audit_history.resolve_settings (default_limit/max_limit) · audit_cache.resolve_recent_settings (recent_*)
  serve: main.get_row_history / main.get_cell_history -> schemas.AuditHistoryPage(logs, truncated, next_cursor, limit, returned)
         main.get_recent_audit_logs -> schemas.AuditLogGroupPage(groups, truncated, next_cursor, limit_groups, returned)
                                       + 같은 두 사실을 헤더 X-Audit-Truncated / X-Audit-Next-Cursor 로도 **계속** 발행(폐기 아님)
  세 라우트 전부 엔벨로프다. 리스트 키만 다르다 — history 둘은 `logs`(감사 행), recent는 `groups`(트랜잭션 그룹,
  그룹마다 자기 `logs`를 또 가짐). 클라는 리더 하나(`timeline.js readHistoryPage(body, listKey)`)를 공유한다.
-->

## 1. 언제 이 파일을 만지는가

- **행/셀 감사 이력 패널의 페이지 크기를 조정할 때** — `default_limit`/`max_limit`.
- **대량 인제션 직후 「최근」 전역 타임라인 패널이 너무 오래 걸리거나, 반대로 너무 짧게 보일 때** — `recent_*` 네 키.
- **파일이 없어도 정상입니다** — 전 항목 기본값(아래 §5)으로 동작합니다. 이 기능 자체가 **2026-08-11 이전에는 무제한 스캔**이었으므로, 파일 부재 = 최신 기본값이 곧 상한입니다(부재가 무상한으로 되돌아가지 않습니다).

## 2. 세팅 절차

1. 파일이 없으면 `audit_history_config.json.sample`을 `audit_history_config.json`으로 복사합니다.
2. 값을 수정합니다:

   ```json
   {
     "default_limit": 200,
     "max_limit": 1000,
     "recent_max_scan_rows": 500000,
     "recent_scan_chunk_rows": 20000,
     "recent_logs_per_group": 500,
     "recent_refresh_max_delta_rows": 2000
   }
   ```

   양성 정수만 유효합니다(`bool`·문자열·0 이하는 **그 키만** 기본값으로 경고 후 되돌아갑니다 — `bool`은 파이썬에서 `int`의 서브클래스라 `True`가 조용히 `1`이 되는 것을 별도로 막습니다).

3. 저장 — 반영은 **다음 요청부터**입니다(요청당 1회 스냅샷 — `effort_metric.json`과 같은 규율). 재기동·reload 불필요.

## 3. 두 그룹, 왜 같은 파일인가

이 파일은 **같은 기능의 두 얼굴**을 담습니다 — "행/셀 하나를 클릭했을 때"(`default_limit`/`max_limit`, `server/audit_history.py`)와 "전역 타임라인 패널을 열었을 때"(`recent_*`, `server/audit_cache.py`)는 둘 다 `audit_logs`가 무제한으로 자라는 것을 어떻게 상한 짓는가의 문제이고, `audit_cache`는 이 파일을 **두 번째 로더로 다시 읽지 않고** `audit_history.load_config()`를 그대로 재사용합니다. 운영자가 "감사 이력을 어디까지 보여줄까"를 결정할 자리를 파일 하나로 묶어 둔 것입니다.

## 4. `recent_*` 넷의 뜻 — 그리고 무엇을 지키는가

- `recent_max_scan_rows`(기본 500,000)는 **최근 100개 트랜잭션 그룹을 찾는 발견(discovery) 걸음의 하드 천장**입니다. `audit_logs`에 `timestamp`-리딩 인덱스가 없던 시절에는 이 걸음이 매 청크마다 전체 정렬을 다시 했고(2,900,000행 픽스처에서 청크 하나가 3.6초), 대량 인제션은 트랜잭션 하나가 파일 하나이므로 **최신 200,000행이 그룹 2개일 수 있어** 100개를 채우려면 계속 더 걸어야 했습니다. 이 값은 성능 노브가 아니라 **제품 결정**입니다 — 대량 적재 직후 패널이 얼마나 과거까지 보여줄 수 있는지를 정합니다. 500,000은 실측 최악 ~400ms(10만행 파일 4개 연속 인제션)를 커버합니다.
- `recent_scan_chunk_rows`(기본 20,000)는 한 왕복에 훑는 행 수이자 **걸음의 바닥**이기도 합니다 — 100개 그룹이 처음 1,400행 안에서 다 채워져도 청크 하나는 통째로 읽습니다.
- `recent_logs_per_group`(기본 500)는 그룹당 보관하는 로그 수입니다. 대표 로그 하나만 화면에 실리므로 **캐시 편의**이지 기록이 아닙니다 — 더 깊은 내역은 `/audit_logs/transaction/{tx}`가 DB로 폴백합니다.
- `recent_refresh_max_delta_rows`(기본 2,000)는 **증분 병합 대 재구축의 분기점**입니다. 새 행이 이 값을 넘으면 한 행씩 파이썬에서 검증하는 증분 병합(행당 ~47µs)이 재구축(비용은 `recent_max_scan_rows`에만 의존)보다 비싸져, 재구축으로 넘어갑니다.

## 5. 반영 확인

전용 조회 엔드포인트가 없습니다(F9 config 해석 보고서는 `enrichment`/`virtual_join`/`binding` 세 도메인만 다룹니다 — 이 파일은 아직 등록되지 않았습니다, §8 참조). 반영은 **행동으로** 확인합니다:

- `GET /tables/{t}/rows/{row_id}/history?limit=1` 응답의 `limit` 필드가 요청한 값으로 clamp됐는지 봅니다(`max_limit`보다 큰 `limit`을 요청해 `truncated: true`와 clamp된 `limit`을 확인).
- `recent_*`는 서버 로그의 `[AuditCache] '<key>' must be a positive integer ...` 경고 유무로 오타를 확인합니다. 정상값은 침묵합니다(값이 화면에 echo되지 않으므로, 오타를 잡는 유일한 신호는 이 경고 줄입니다).
- `GET /audit_logs/recent` — 응답 **바디**의 `truncated`(§4의 discovery 천장에 걸리면 `true`)로 확인합니다. 바디는 CORS와 무관하므로 교차 출처(vite dev :5173)에서도 그대로 읽힙니다. 같은 사실이 `X-Audit-Truncated`/`X-Audit-Next-Cursor` **헤더**로도 계속 나가지만(폐기되지 않았습니다 — 헤더만 읽던 소비자가 있다면 계속 동작합니다), 🔴 **헤더는 같은 출처(:8080/:8081 직접 서빙)에서만 읽힙니다** — 이 헤더 둘이 서버 CORS `expose_headers`에 **아직 없어**(`server/main.py:164`) 교차 출처에서는 브라우저가 지웁니다([backend §2 감사 이력 조회](../../architecture/backend.md#이력--감사) 참조, 총괄 보고 대상). `client2/src/timeline.js`는 헤더가 아니라 바디를 읽으므로 오늘은 무해합니다.
- ⚠️ **`truncated: true`인데 `next_cursor: null`인 세 번째 상태가 이 라우트에는 정상적으로 존재합니다** — 행/셀 이력의 「`next_cursor`는 `truncated`일 때 정확히 non-null」 불변식이 여기는 **적용되지 않습니다**. 라이브 병합(`audit_cache.add_logs_batch`)이 투영 꼬리를 잘라내면 기록해 둔 재개 위치가 이미 잘려나간 구간을 가리키게 되고, 그 위치로는 이미 갖고 있는 그룹을 다시 돌려주게 되므로 "더 있지만 위치는 잃었다"가 정직한 답입니다. 클라의 공용 리더(`readHistoryPage`)는 이 상태를 `truncated: false`로 접습니다 — **오늘은 전역 탭이 페이저를 그리지 않기 때문에만 정확합니다.** 페이저를 추가하면 이 세 번째 상태를 바디에서 직접 읽어야 합니다(리더의 접기를 신뢰하면 안 됨).

## 6. 잘못됐을 때

파일을 지우면 **전 항목 기본값**으로 즉시 돌아갑니다(2026-08-11 이후 기본값 자체가 상한이므로, 삭제해도 무제한 스캔으로 되돌아가지 않습니다). 스냅샷 복원:

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore audit_history_config_<yymmdd>.json.bak --yes
```

→ [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md)

## 7. 인덱스는 이 파일이 아니라 마이그레이션이다

이 파일이 **상한을 얼마로 잡을지**를 정한다면, 그 상한 안에서 실제로 빠르게 답하는 것은 세 인덱스입니다(`idx_audit_recent_groups` · `idx_audit_row_history` · `idx_audit_cell_history`) — `models.py`에 선언돼 있어 **신규** 설치는 `create_all`로 자동으로 받지만, **기존** 데이터베이스는 `create_all`이 인덱스를 추가하지 않으므로 두 마이그레이션 파일을 손으로 한 번 돌려야 합니다. 이 config만 손대고 마이그레이션을 건너뛰면 상한은 낮아져도 **각 청크가 여전히 순차 스캔**입니다. 절차는 [DEPLOY_SETUP §6 8-ter](../DEPLOY_SETUP.md) · 게이트 판정은 [PRODUCTION_READINESS C4](../../process/PRODUCTION_READINESS.md).

## 8. 키 참조

| 키 | 타입 / 기본값 | 의미 |
|---|---|---|
| `default_limit` | 양의 정수, 기본 `200` | 행/셀 이력 조회에서 `limit`을 지정하지 않았을 때의 페이지 크기 |
| `max_limit` | 양의 정수, 기본 `1000` | 행/셀 이력 조회가 요청할 수 있는 `limit`의 천장. 초과 요청은 거절하지 않고 clamp + `truncated: true` |
| `recent_max_scan_rows` | 양의 정수, 기본 `500000` | `/audit_logs/recent` discovery 걸음의 하드 천장(행 수) — **제품 결정**, §4 |
| `recent_scan_chunk_rows` | 양의 정수, 기본 `20000` | discovery 걸음의 왕복당 청크 크기이자 최소 비용 |
| `recent_logs_per_group` | 양의 정수, 기본 `500` | 캐시가 그룹당 보관하는 로그 수(대표 1건만 화면에 실림) |
| `recent_refresh_max_delta_rows` | 양의 정수, 기본 `2000` | 이 값을 넘는 델타는 증분 병합 대신 재구축으로 폴백 |

`default_limit > max_limit`이면 `default_limit`이 `max_limit`으로 clamp됩니다(경고 로그와 함께).

> 🔴 **`audit_history_config.json.sample`은 지금 이 네 키(`recent_*`)를 적고 있지 않습니다 — 그 파일만 보고 옮겨 적지 마십시오.** 코드(`server/audit_cache.py`의 `RECENT_DEFAULTS`)는 이 파일에서 읽도록 이미 배선돼 있으므로, `.sample`에 없다는 이유로 이 네 키가 안 먹는다고 결론짓거나 상한이 적용 안 된다고 오해하면 안 됩니다. `.sample`이 따라잡을 때까지는 위 §2/§8과 이 문서가 **정본**입니다.
