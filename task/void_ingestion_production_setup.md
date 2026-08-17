# [Runbook] voids.json 외부 경로 인제션 — 운영 셋업

> **요청:** 소유자, 2026-08-18 — 「다른 외부 경로 인제션 받는 거 운영에 지금 셋업해야 해」
> **형식 확인:** voids.json (소유자 확인)
> **결론: 코드 변경 없이 config만으로 됩니다.** 단, 두 테이블 선언이 먼저 있어야 합니다.
> **주의: 이 문서의 실측은 개발 박스 기준입니다.** 운영 상태는 각 단계의 «확인»으로 직접 봅니다.

## 왜 항목이 두 개인가

같은 `voids.json` 한 파일이 **서로 다른 두 사실**을 말합니다.

- `inspection_run` — **분모.** 「이 패키지 층을 스캔했다」. 이게 없으면 「void 0건」과
  「스캔한 적 없음」이 구분되지 않습니다.
- `void_obs` — **관측.** 「그 스캔이 이 void를 봤다」.

그래서 external_sources 항목이 **같은 폴더를 가리키는 두 개**입니다. 파서(`voids_json`)는
이 두 테이블 이름만 받습니다 — 다른 이름을 쓰면 거절됩니다.

## 걸음 1. table_config에 두 테이블 선언

붙여 넣을 정본: `task/evidence/void_ingestion_table_config.json`
(2026-08-15 백업본에서 그대로 추출. 설계 사유가 적힌 `__comment`까지 보존)

| 테이블 | business_key | 복합키 재료 | 컬럼 |
|---|---|---|---|
| `inspection_run` | `run_uid` | method · base_wafer_id · base_x · base_y · stack_gate · observed_at | 9 |
| `void_obs` | `void_uid` | run_uid · inchip_x · inchip_y | 11 |

**확인:** 운영 `table_config.json`에 이 두 이름이 이미 있으면 걸음 1은 건너뜁니다.
개발 박스에는 지금 **둘 다 없습니다**(16개 선언 중 부재).

> ⚠️ 개발 박스에 있는 `void` 테이블 선언은 이 파서와 무관합니다. `voids_json`은
> `void`라는 이름을 받지 않고, 그 선언에는 business_key도 컬럼도 없어서 외부 소스
> 대상이 될 수 없습니다. 헷갈리지 않도록 적어 둡니다.

**왜 키가 필수인가:** 감시 폴더의 파일은 **다시 배달될 수 있습니다.** 키가 없으면 갱신이
아니라 중복이 쌓이므로, 워처가 키 없는 테이블을 아예 거절합니다.

## 걸음 2. 물리 반영

`POST /admin/reload-configs` (X-Admin-Token 필요)가 신규 테이블 **물리 CREATE**까지 합니다.

> 🔴 **이 호출은 무엇이 먹었는지 돌려주지 않습니다.** 캐시를 갱신하고 워커에 이벤트를
> 뿌린 뒤 끝입니다. 그래서 확인은 별도로 합니다.

**확인 — `GET /tables/{t}/schema`는 증거가 아닙니다.** 그건 config 싱글턴을 읽습니다.
물리 반영의 증거는 `information_schema`뿐입니다:

```sql
SELECT table_name, count(*) AS columns
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name IN ('inspection_run','void_obs')
GROUP BY table_name;
```

기대: 두 행, 각각 컬럼 9개와 11개.

반영이 불가능하면 `Config reload ABORTED: ...` ERROR가 남고 기존 상태가 유지됩니다 —
조용히 넘어가지 않습니다.

## 걸음 3. 인덱스 (선택이지만 권장)

`server/migrations/add_void_schema_indexes.sql`. void 면적(π·rx·ry) 질의를 위한 **식
인덱스**가 들어 있습니다. 면적은 컬럼으로 저장하지 않는다는 설계라, 「X보다 큰 void」를
쓰실 거면 이게 있어야 합니다. 되돌리기는 `add_void_schema_indexes_reverse.sql`.

## 걸음 4. external_sources 두 항목

운영 `ingestion_settings.json`에 추가합니다(파일이 없으면 만들고, 있으면 배열에 append):

```json
"external_sources": [
  {
    "enabled": true,
    "path": "<운영 폴더 절대경로>",
    "table_name": "inspection_run",
    "parser": "voids_json",
    "recursive": true,
    "options": { "filename": "voids.json", "max_file_mb": 128 }
  },
  {
    "enabled": true,
    "path": "<운영 폴더 절대경로>",
    "table_name": "void_obs",
    "parser": "voids_json",
    "recursive": true,
    "options": { "filename": "voids.json", "max_file_mb": 128 }
  }
]
```

지켜야 하는 것:

- `path`는 **절대경로**이고 관리 워크스페이스(raws/)와 겹치면 거절됩니다.
  UNC 경로(`//서버/공유/...`)도 절대경로면 됩니다.
- `filename`은 **홑 파일명 하나**입니다. 경로 조각이 들어가면 거절됩니다.
- **워처는 원본을 옮기거나 지우지 않습니다.** 읽기 전용으로 봅니다.
- 감시는 파일 이벤트 + **300초 재귀 스윕**을 함께 씁니다. 이벤트를 놓쳐도 5분 안에 잡힙니다.

### 🔴 폴더 구조가 고정 규격입니다 — 여기서 제일 많이 막힙니다

외부 루트 아래 경로가 **정확히 세 단계**여야 합니다:

```text
<외부 루트>/<WAFERID>/<WORK_YYYYMMDD_HHMMSS>/voids.json
```

- 첫 폴더 = **웨이퍼 식별자**(`base_wafer_id`)
- 둘째 폴더 = **작업 시각**. `WORK_20260818_143000` 또는 `20260818_143000` 두 형태만.
  이 값이 `observed_at`이 되고, **`inspection_run`의 키 재료**입니다
- 셋째 = `options.filename`과 일치하는 파일명

단계가 하나라도 많거나 적으면 그 파일은 실패합니다. 깊은 경로를 허용하면 **어느 폴더가
웨이퍼 식별자인지 알 수 없기 때문**에 일부러 막아 둔 규칙입니다. 즉 웨이퍼 ID와 스캔
시각은 **JSON 안이 아니라 폴더 이름에서** 옵니다 — 운영 폴더가 이 모양이 아니면 config로
해결되지 않고 배치 쪽을 맞추셔야 합니다.

`recursive: true`는 이 세 단계 구조를 훑는다는 뜻이지, 임의 깊이를 허용한다는 뜻이 아닙니다.

### 🔴 한 행이 걸리면 그 파일은 통째로 안 들어갑니다

키 게이트가 한 행이라도 거절하면 **그 파일에서 아무것도 쓰이지 않습니다.** 부분 적재가
없습니다. 고쳐서 다시 배달해야 하고, 거절 사유는 사유별 집계로 로그에 남습니다.

행이 거절되는 조건:

| 조건 | 내용 |
|---|---|
| 필수 필드 누락 | void 행에 좌표·반경 등 필수 값이 없음 |
| `stack_gate`가 정수가 아님 | 층 번호는 정수여야 함. `3.5` 거절 |
| 숫자가 유한하지 않음 | `NaN`/`Infinity` 거절 |
| 단위 미상 | 아래 참조 |
| 같은 run 안에서 같은 좌표 중복 | `duplicate_location` — 조용히 합쳐지지 않도록 거절 |

파일 단위로 실패하는 조건도 둘 있습니다:

- **void가 0건인 「깨끗한 스캔」 파일이 `runs`/`scans`를 선언하지 않은 경우.** 무엇을
  검사했는지 말하지 않으면 「깨끗함」과 「스캔 안 함」이 구분되지 않으므로 거절합니다.
- **명시한 `runs`가 void 행이 가리키는 층을 빠뜨린 경우.** 관측이 존재하지 않는 분모를
  가리키게 되므로 거절합니다.

### `unit`을 파일이 안 들고 오면 여기서 선언합니다

void 반경의 단위는 **추측하지 않습니다.** 파일 안에 `unit`이 없고 행에도 없으면 그 행은
거절됩니다. 파일이 단위를 안 실어 오면 `options`에 넣으십시오:

```json
"options": { "filename": "voids.json", "max_file_mb": 128, "unit": "um" }
```

우선순위는 **행 > 파일 metadata > options**입니다.

## 걸음 5. 반영

`POST /admin/reload-configs` 한 번 더. **새 항목은 재기동 없이 등록되고 초기 스윕까지
자동으로 돕니다.**

> 🔴 **기존 항목의 `path`·`parser`·`options`를 바꾸는 것은 다릅니다.** 워처가 도는 중에
> 바뀌면 거절되고 **프로세스 재기동이 필요**합니다. 운영에서는 「기존 것을 고치기」보다
> **「새 항목으로 추가」**가 무중단입니다.

**확인:** 두 테이블에 행이 들어오는지, 그리고 `file_ingestion_logs`에 SKIPPED/FAILED가
없는지 봅니다. 실패는 폴더가 아니라 원장에 남습니다 —
`file_ingestion_checkpoints`의 `status='FAILED'` 행과 `file_ingestion_logs`의 트레이스입니다.

## 실패했을 때 어디를 보나

| 증상 | 자리 |
|---|---|
| 항목이 아예 등록 안 됨 | 서버 로그의 `external_sources[N] ...` ERROR (항목별로 이름을 대고 거절) |
| 파일은 보이는데 행이 안 늘어남 | `file_ingestion_checkpoints` status, `file_ingestion_logs` 트레이스 |
| 같은 파일이 계속 스킵됨 | `dedup_by_signature`/`dedup_by_path_stat`. 강제 재처리는 파일명에 `__force__` |
| unit 관련 거절 | 위 걸음 4의 `options.unit` |

## 이 셋업이 못 하는 것

- **다른 형식은 못 받습니다.** 등록된 외부 파서는 `voids_json` 하나뿐이고 그것도
  `void_obs`/`inspection_run` 전용입니다. 다른 형식이 필요해지면 파서 코드가 필요합니다.
- 이 문서는 인제션까지입니다. 원장(ledger)으로 올리는 것은 별개 경로입니다.
