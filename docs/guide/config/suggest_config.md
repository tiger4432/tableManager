# `suggest_config.json` 세팅 — 입력 제안(고유값 조회) 노브

> **Status:** 🟢 Living | **Last-verified:** 2026-07-29 (신설 — F3 고유값 조회 API와 동시) | **Owner:** Backend
> 상위: [폴더 인덱스](./README.md) · API 계약과 왜 이 알고리즘인가는 [backend §2.1](../../architecture/backend.md) · 인덱스 운영은 [POSTGRES_OPERATIONS §3.1](../POSTGRES_OPERATIONS_GUIDE.md)

<!-- Loader evidence (2026-07-29):
  load: server/value_suggest.py load_config (missing/corrupt -> {} = defaults)
  validate: value_suggest.resolve_settings (bool/non-int/negative/zero -> warn + that key's default; default_limit > max_limit -> clamped)
  maps: value_suggest._resolve_column_map (non-dict or malformed entry -> dropped + warn)
  serve: main.get_column_unique_values -> GET /tables/{t}/columns/{c}/values
  index policy: value_suggest.index_targets, consumed by server/scripts/setup_db_performance.py Step 3.8
-->

## 1. 언제 이 파일을 만지는가

- **제안 목록의 길이를 바꿀 때** (`default_limit` / `max_limit`)
- **"N자 이상 입력해야 제안"을 정책으로 강제할 때** (`min_prefix_length`)
- **접두 인덱스를 만들 대상을 조정할 때** (`index_min_rows` / `index_columns` / `index_exclude`) — 디스크가 아까운 컬럼을 빼거나, 작은 테이블에도 강제로 넣을 때
- **파일이 없어도 정상입니다** — 전 항목 기본값으로 동작합니다.

> ⚠️ **이 파일은 인덱스를 만들지 않습니다.** 대상 목록만 결정하고, 실제 생성은 `server/scripts/setup_db_performance.py`(Step 3.8)가 합니다. **값을 바꾸면 그 스크립트를 다시 돌려야** 반영됩니다.

## 2. 세팅 절차

1. **스냅샷**(파일이 이미 있을 때만 의미 있음): `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. 파일이 없으면 `suggest_config.json.sample`을 `suggest_config.json`으로 복사합니다.
3. 값을 수정합니다:

   ```json
   {
     "default_limit": 50,
     "max_limit": 200,
     "min_prefix_length": 0,
     "max_probe_values": 400,
     "timeout_ms": 1500,

     "index_min_rows": 10000,
     "index_columns": { "parts": ["maker"] },
     "index_exclude": { "bonding_map": ["pkg_id"] }
   }
   ```

4. 저장 — 조회 노브는 **다음 요청부터** 즉시 반영됩니다(요청당 1회 스냅샷).
5. `index_*`를 건드렸다면 **인덱스를 다시 반영**합니다:
   ```bash
   cd server && conda run -n assy_manager python scripts/setup_db_performance.py
   ```

## 3. 키 사전

| 키 | 기본값 | 의미 · 잘못 넣으면 |
|---|---|---|
| `default_limit` | `50` | `limit` 미지정 시 값 개수. `max_limit`보다 크면 **경고 후 `max_limit`으로 클램프** |
| `max_limit` | `200` | 호출자가 요청할 수 있는 상한. 초과 요청은 거절이 아니라 **이 값으로 잘리고 `truncated: true`** |
| `min_prefix_length` | `0` | 이보다 짧은 prefix는 **400으로 거절**하고 사유를 말합니다. 기본 0 = 빈 prefix 허용 — **성능 때문이 아니라 정책용 노브**입니다(빈 prefix도 값 1개당 seek 1회라 안전) |
| `max_probe_values` | `400` | 요청당 인덱스 seek 상한. 문자열 컬럼에서는 값 개수 + 1을 넘지 않으므로 사실상 **숫자 컬럼 전용 안전장치**입니다. **이 상한에 걸려 멈추면 `truncated: true`** |
| `timeout_ms` | `1500` | PostgreSQL `statement_timeout` + 루프 전체 마감시각. **초과하면 잘림이 아니라 `unavailable_reason`** (§4) |
| `index_min_rows` | `10000` | 이 행수 이상인 테이블만 자동으로 접두 인덱스 대상이 됩니다. 그 미만은 스캔이 이미 빨라 디스크만 먹습니다 |
| `index_columns` | `{}` | `{테이블: [컬럼,...]}` — 선언하면 **그 테이블은 정확히 이 목록만**(행수 기준 무시). 작은 테이블에 강제로 넣을 때 씁니다 |
| `index_exclude` | `{}` | `{테이블: [컬럼,...]}` — **항상 이깁니다.** 값이 사실상 전부 유일해 드롭다운이 무의미한 컬럼(업무키 등)이나, 인덱스가 큰 컬럼을 뺄 때 |

정수가 아닌 값·음수·(길이·시간 계열의) 0은 **경고 로그 + 그 키만 기본값**으로 되돌아갑니다. `index_columns`/`index_exclude`가 객체가 아니거나 항목이 문자열 리스트가 아니면 **그 항목을 무시하지 않고 거절**합니다(파일에는 선언돼 있는데 아무 효과가 없는 상태가 가장 위험하므로, 로그에 남깁니다).

### 대상 선정 규칙 (요약)

```
datetime 컬럼          -> 절대 대상 아님 (API가 400으로 거절하는 타입)
index_exclude 에 있음  -> 제외 (최우선)
index_columns 에 선언  -> 그 목록만            (행수 무시)
그 외                  -> 행수 >= index_min_rows 인 테이블의 선언 컬럼 전부
```

`number` 선언 컬럼도 **대상입니다.** API가 숫자 컬럼에도 답하기 때문입니다 — 여기서 빼면 그 컬럼은 답하다가 시간 초과로 죽고, 사유 문자열은 **아무도 만들지 않을 인덱스 이름**을 대게 됩니다(2026-07-29 라이브에서 실제로 그렇게 났습니다).

## 4. 반영 확인

```bash
# 값이 나오는지
curl "http://localhost:8080/tables/bonding_map/columns/base/values?prefix=c&limit=10"
```

```json
{"table":"bonding_map","column":"base","prefix":"c","values":["CDIE","CHIP_VAR"],
 "truncated":false,"limit":10,"unavailable_reason":null}
```

- **`truncated: true`** = 목록이 잘렸다는 뜻이고, 소비자는 이것을 표시해야 합니다. 조용히 자르면 드롭다운이 "이게 전부"라고 암시합니다.
- **`unavailable_reason`이 채워지면 `values`는 항상 빈 배열입니다.** "결과 없음"과 "조회 실패"를 같은 모양으로 내지 않기 위한 계약입니다. 가장 흔한 사유:

  ```
  조회 시간 초과 (1500ms) — 접두 인덱스 idx_suggest_bonding_map_base 가 없습니다.
  server/scripts/setup_db_performance.py 를 실행하세요.
  ```

  **사유 문자열을 끝까지 읽으십시오 — 문장이 상황마다 다릅니다.** "스크립트를 실행하세요"는 그 컬럼이 **실제로 빌더의 대상일 때만** 나옵니다. 대상이 아니면 무엇이 막고 있는지를 말합니다(아래 판정은 `value_suggest.index_targets`에 직접 물어서 나옵니다 — 정책이 한 곳에만 있습니다):

  | 사유에 나오는 말 | 뜻 | 할 일 |
  |---|---|---|
  | `… 를 실행하세요.` | 대상인데 아직 안 만들어졌다 | 스크립트 실행 |
  | `index_exclude['테이블'] 에 제외되어 있어` | 빌더가 **영원히** 안 만든다 | 제외 목록에서 빼고 재실행 |
  | `index_columns['테이블'] 목록에 이 컬럼이 없어` | 강제 목록이 선언돼 있고 이 컬럼은 밖 | 목록에 추가하고 재실행 |
  | `약 N행으로 index_min_rows(…) 미만이라` | 자동 대상 기준 미달 | `index_columns`에 명시 선언하고 재실행 |
  | `INVALID 상태입니다` | 이름은 있지만 죽은 인덱스 | 사유가 제시하는 `REINDEX`/`DROP` 실행 후 재실행 |

  인덱스가 실제로 있고 유효한데도 시간 초과면 사유가 "인덱스는 존재합니다"로 바뀌며 원 예외를 함께 싣습니다 — 그때는 `timeout_ms`나 데이터 쪽을 봐야 합니다.

인덱스 목록 확인 — **유효성까지 봐야 합니다**(`to_regclass`나 `pg_indexes` 이름 조회는 INVALID 인덱스도 정상으로 보여줍니다):

```sql
SELECT ci.relname AS indexname, i.indisvalid AND i.indisready AS usable,
       pg_get_indexdef(i.indexrelid) AS indexdef
FROM pg_index i
JOIN pg_class ci ON ci.oid = i.indexrelid
JOIN pg_namespace n ON n.oid = ci.relnamespace
WHERE n.nspname='public' AND ci.relname LIKE 'idx_suggest_%'
ORDER BY usable, indexname;
```

## 5. 함정

- **`index_*`만 바꾸고 스크립트를 안 돌리면 아무 일도 일어나지 않습니다.** 이 파일은 선언이고, 스크립트가 유일한 반영 경로입니다.
- **대상에서 뺀 컬럼의 인덱스는 자동 삭제되지 않습니다.** 스크립트가 `Orphaned suggestion indices`로 DROP 문을 **출력만** 합니다 — config 로드가 일시 실패한 상태에서 일괄 DROP이 도는 사고를 막기 위한 의도된 설계입니다. 판단은 사람이 하고 명령은 손으로 실행합니다.
- **`CREATE INDEX CONCURRENTLY`는 열려 있는 트랜잭션을 기다립니다.** 워커가 `idle in transaction`이면 스크립트가 멈춘 것처럼 보입니다 — `pg_stat_activity`를 보십시오. **여기서 Ctrl+C로 끊으면 그 이름으로 INVALID 인덱스가 남고, 이후 스크립트는 이름이 있다는 이유로 영원히 건너뜁니다.** 스크립트가 Step 3.8 시작에 그 목록을 먼저 출력하니 놓치지 마십시오.
- **`index_columns`에 적었지만 만들어지지 않는 컬럼이 있을 수 있습니다.** 미선언 컬럼이나 `datetime` 선언 컬럼은 애초에 제안 대상이 아니라 조용히 빠집니다 — 스크립트 로그의 `[Suggest] index_columns[...] names ...` 경고를 확인하십시오.
- **대소문자를 무시합니다 — 단, 기준은 "이 데이터베이스의 `lower()`"입니다.** `cd`를 쳐도 `CDIE`가 나옵니다(라이브 데이터가 대문자 코드라 그렇지 않으면 드롭다운이 무용지물입니다). 이 동작은 노브가 아니라 인덱스 정의(`lower(col)`)에 박혀 있고, 접두도 **같은 `lower()`** 로 접습니다. 그래서 **두 값이 "같다"고 판정되는 범위는 DB가 접어주는 딱 그만큼입니다** — 이 DB(`Korean_Korea.949`)의 `lower()`는 ASCII와 일부 비-ASCII(키릴 등)는 접지만 U+00C4 같은 라틴-1 확장은 접지 않습니다. ASCII 접두는 왕복 없이 처리되고(모든 구현이 A-Z→a-z만은 동일), 비-ASCII 접두일 때만 DB에 한 번 물어봅니다.
- **`number` 컬럼 제안은 저장형입니다** — `01`을 쳐도 `1`을 찾고, 돌려주는 것도 `1.0`이 아니라 `1`입니다([backend §2.1](../../architecture/backend.md)의 정규화 규율).
