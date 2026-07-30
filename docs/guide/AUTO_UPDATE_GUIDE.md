# 📅 AssyManager Ingestion Auto Update & Scheduler 가이드

> **Status:** 🟢 Living | **Last-verified:** 2026-07-30 (**§4-ter 신설 + §4-bis의 "유지보수 작업 1건" 정정** — `server/run_auto_update.py`(`maybe_sweep_graph_orphans`·`run()`의 틱 4번 항목)·`server/graph_orphans.py`(`due`/`declaration_blockers`/`run_scheduled`·`CHECK_INTERVAL_SEC`·`SWEEP_INTERVAL_SEC`·`ENABLE_ENV`) 실측. `530fdfd`가 그래프 고아 노드 스윕을 이 데몬의 틱에 올렸으므로 유지보수 작업은 **2건**이다. 요점은 삭제가 아니라 **거절**(선언에 거부가 하나라도 있으면 `status: refused`로 전체 거절 — `min_population` 미만 라벨은 예산 가드가 못 막기 때문). 주기 상태의 출처가 config 백업과 다르다는 것(파일 vs 프로세스 monotonic → **재기동마다 1회 실행**)도 등재. 직전 2026-07-27) | **Owner:** Ingester | **Source-of-truth:** `server/run_auto_update.py` · `server/utils/auto_update_control.py` · `server/graph_orphans.py`(§4-ter) · 상위 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

본 디렉토리는 각 테이블별 실시간 인제션 파일 수집 및 백업 스케줄링을 독립적이고 완벽하게 관리할 수 있는 **하이브리드 동적 다중 감지 수집 시스템**입니다.

---

## 🚀 1. 디렉토리 설계 구조
각 테이블 하위에 `auto_update` 폴더를 생성하고, 파일 수집용 파이썬 스크립트(`*.py`)들을 배치하면 중앙 스케줄러(`server/run_auto_update.py`)가 이를 자동 감지(Auto-Discovery)하여 통합 기동합니다.

```
server/ingestion_workspace/
├── {table_name}/
│   ├── raws/                 # 최종 수집 파일이 안착할 폴더 (Watcher 감시 대상)
│   └── auto_update/          # 수집 자동화 스크립트 보관 폴더
│       ├── collect_sensor_a.py  # 기기 A 전용 수집기
│       └── fetch_web_data.py    # 외부 웹 API 전용 수집기
```

---

## 🔑 2. 주석 기반 제로설정 크론탭 스케줄링 (Comment-Driven Crontab)
별도의 설정 파일(`.json`)을 따로 구성할 필요 없이, 파이썬 파일(`.py`)의 **최상단 20줄 이내**에 주석으로 스케줄과 파일명 설정을 기재하면 작동합니다.

### 📝 설정 키워드 규격
* `# schedule: <cron_expression>`: 표준 크론탭 표현식으로 수집 실행 주기를 설정합니다.
  - 예: `# schedule: 0 * * * *` (매시 정각 실행)
  - 예: `# schedule: */5 * * * *` (5분마다 실행)
* `# filename_prefix: <prefix>`: `raws/` 폴더에 생성될 최종 CSV 파일의 접두사를 지정합니다.
  - 예: `# filename_prefix: sensor_a_data` -> 최종 생성 파일: `sensor_a_data_YYYYMMDD_HHMMSS.csv`

> [!NOTE]
> 만약 `# schedule:` 설정 주석이 생략되거나 누락된 스크립트의 경우, 기본 주기(매시 정각 `"0 * * * *"`)와 기본 접두사(스크립트 파일명)로 안전하게 자동 폴백(Fallback) 지정됩니다.

---

## 💾 3. 네임스페이스 `out` 변수 가로채기 (Variable Capture)
수집 스크립트 내부에서 복잡하게 파일 쓰기(I/O)를 하거나 표준 출력(`print`)으로 인한 로그 오염을 겪을 필요가 없습니다. 스크립트 마지막 시점에 **`out` 이라는 이름의 모듈 레벨 변수에 데이터를 대입**해 두기만 하면 스케줄러가 메모리에서 이를 자동으로 덤프 및 CSV 변환하여 적재합니다.

> [!IMPORTANT]
> `out`에 담을 값이 없을 때는 **`out = []` (또는 `out = ""`)** 를 쓰십시오. **`out = None`은 실패로 판정**되어 수집기가 `FAIL` 처리됩니다 — 자세한 이유는 아래 [실패 판정 규칙](#-실패-판정-규칙-failure-semantics-2026-07-27) 참조.

### 💡 지원 가능한 `out` 변수 데이터 타입
1. **문자열 (`str`)**: CSV로 변환할 문자열 데이터를 담아둡니다.
   ```python
   out = "pkg_id,base,x,y,leg\nCHIP_1,CHIP,10,20,LEFT"
   ```
2. **딕셔너리 리스트 (`list[dict]`)**: Key-Value가 매핑된 딕셔너리의 리스트입니다. **Key 리스트를 CSV 헤더로 자동 추출 및 매핑**하여 적재합니다. (권장)
   ```python
   out = [
       {"pkg_id": "CHIP_1", "base": "CHIP", "x": 10, "y": 20, "leg": "LEFT"},
       {"pkg_id": "CHIP_2", "base": "CHIP", "x": 30, "y": 40, "leg": "RIGHT"}
   ]
   ```
3. **2차원 리스트 (`list[list]`)**: 순수 행 리스트 구조입니다. 첫 행을 헤더로 기입하여 덤프합니다.
   ```python
   out = [
       ["pkg_id", "base", "x", "y", "leg"],
       ["CHIP_1", "CHIP", 10, 20, "LEFT"]
   ]
   ```
4. **Pandas DataFrame**: `to_csv` 메서드가 내장되어 있는 판다스 데이터프레임 등의 객체입니다. `to_csv(index=False)`를 자동 호출해 덤프합니다.
   ```python
   import pandas as pd
   out = pd.DataFrame(data_list)
   ```

### 🧩 스코프 보장 — 일반 파이썬 모듈과 동일 (2026-07-27 수정)
수집 스크립트는 **평범한 파이썬 모듈과 똑같은 이름 해석 규칙**으로 실행됩니다. 헬퍼 함수를 자유롭게 정의해 다른 함수 안에서 호출할 수 있고, 모듈 최상단 `import`를 함수 본문 안에서 사용할 수 있습니다.

```python
import json                     # 함수 안에서 그대로 보인다

def build_rows():
    return json.loads(fetch())  # 헬퍼 → 헬퍼 호출 OK

def fetch():
    return '[{"a": 1}]'

out = build_rows()
```

> [!WARNING]
> **과거 결함(2026-07-27 수정 전):** 러너가 `exec(code, globals, locals)`에 **서로 다른 두 네임스페이스**를 넘겨, 스크립트가 *클래스 본문(class body)* 스코프로 실행됐습니다. 모듈 레벨 `def`/`import`는 locals에 바인딩되는데 함수 본문은 `LOAD_GLOBAL`로 이름을 찾으므로 그것들을 보지 못해, **함수 안에서 헬퍼나 import를 참조하는 순간 `NameError`**가 났습니다. 그 예외는 warning으로 삼켜지고 stdout 폴백으로 넘어가는데, 해당 스크립트는 `print` 대신 `out`을 쓰므로 stdout이 비어 **"수집 0건 + 에러 0건"으로 조용히 끝났습니다.** 지금은 네임스페이스를 하나만 넘깁니다. (모듈 레벨에서 헬퍼를 호출한 스크립트는 `LOAD_NAME`이라 영향을 받지 않았습니다 — 그래서 일부만 고장 나 보였습니다.)

### 🛡️ 완충 폴백 (Stdout Capture Fallback)
스크립트에 `out` 변수가 **한 번도 선언되지 않았다면**, 자동으로 **자식 프로세스 표준 출력(stdout, print) 캡처 모드**로 전환하여 `print(...)`로 출력한 텍스트 전체를 낚아채 CSV로 저장해 줍니다.

> [!CAUTION]
> **폴백은 스크립트를 자식 프로세스로 한 번 더 실행합니다 — 부작용도 두 번 일어납니다.**
> 폴백이 걸리는 경우는 두 가지뿐입니다: ① `out`을 아예 선언하지 않은 stdout 수집기, ② 실행 중 예외 발생. 두 경우 모두 **in-memory 1회 + subprocess 1회, 총 2회** 실행됩니다.
> * 수집 외에 **외부 부작용**(ack POST, 소스 커서 전진, 메일 발송, 카운터 증가)이 있는 스크립트는 반드시 `out` 방식을 쓰십시오. 특히 **커서를 전진시키는 수집기는 매 주기 배치를 하나씩 건너뜁니다.**
> * ⚠️ **2026-07-27 스코프 수정으로 이 위험이 새로 생긴 부류가 있습니다.** 이전에는 헬퍼 함수를 쓰는 print 수집기가 첫 `LOAD_GLOBAL`에서 `NameError`로 즉사해 in-memory 실행이 부작용을 남기지 못했습니다. 이제는 끝까지 실행되고 자식 프로세스가 이를 반복합니다(측정: 1회 → 2회).
> * `out = None`은 **폴백을 타지 않습니다**(아래 실패 판정 참조) — 실패한 fetch를 두 번 호출하지 않기 위함입니다.

### 🚨 실패 판정 규칙 (Failure Semantics, 2026-07-27)
"확인 불가"가 "이상 없음"으로 보고되지 않도록, 러너는 아래를 **엄격히 구분**합니다.

| 상황 | 로그 | 결과 |
|---|---|---|
| `out` 있음 · 내용 있음 | INFO | CSV 적재, `SUCCESS` |
| `out` 있음 · 내용 비어 있음 (`[]`, `""`) | WARNING | 파일 미생성, `SUCCESS` (이번 주기 수집 0건 = 정상) |
| **`out = None` 대입** | **ERROR** | **`FAIL`** — 스크립트가 "줄 데이터가 없다"고 선언한 것. **폴백 없음**(외부 호출 재실행 방지) |
| `out` 있음 · **CSV 변환 실패** | (호출부 traceback) | **`FAIL`** — 폴백 **없음**. stdout 사본이 있어도 쓰지 않는다 |
| `out` 없음 · 예외 없음 | INFO (`stdout collector`) | stdout 폴백 — **정상 경로** |
| `out` 없음 · stdout 비어 있음 | WARNING | 파일 미생성, `SUCCESS` (수집할 게 없었음) |
| **실행 중 예외** + 폴백 성공 | **ERROR + 트레이스백** | CSV 적재, `SUCCESS` (에러는 로그에 남음) |
| **실행 중 예외** + 폴백도 빈손 | **ERROR + 트레이스백** | **`FAIL`** — 예외를 던져 admin `last_error`에 근본 원인 노출 |
| 자식 프로세스 종료코드 ≠ 0 | ERROR | **`FAIL`** |

> [!IMPORTANT]
> **"이번 주기엔 수집할 게 없다"를 표현하려면 `out = []` 또는 `out = ""`를 쓰십시오. `out = None`은 실패입니다.**
> `out = None`은 `out`을 **아예 선언하지 않은 것과 구분되지 않아**(둘 다 `.get("out")`이 `None`) 과거에는 stdout 수집기로 오인됐습니다. 그 결과 fetch 실패 → 스크립트 재실행(외부 API 2차 호출) → stdout 비어 있음 → `"Skipping file generation"` → **`SUCCESS` / `last_error=None`**. 수집기 작성자들이 이미 "에러가 난다"고 믿고 쓰던 관용구(`ingestion_workspace/bonding_map/auto_update/fetch_data.py:28-32`)라 실제 판정을 그 기대에 맞췄습니다.

* **CSV 변환 실패는 폴백하지 않습니다.** 행을 `print`도 하고 `out = df`도 하는 하이브리드 수집기는, 혼합 dtype 등으로 `to_csv`가 깨지면 **stdout 사본이 있어도 실패로 끝납니다**(수정 전에는 폴백이 CSV를 만들어 `SUCCESS`였습니다). 두 출력이 조용히 어긋나는 것보다 시끄러운 실패가 낫다는 판단입니다.
* **`sys.exit(0)`으로 끝나는 수집기**는 정상 완료로 처리되어 `out`이 그대로 채택됩니다. (`SystemExit`은 `Exception`이 아니라 `BaseException`이라, 이전에는 `execute_collector`와 `check_and_run_schedules`의 `except Exception`을 모두 관통해 **스케줄러 데몬 자체를 종료**시켰습니다.) 종료코드가 0이 아니면 실패로 처리합니다.

### ⚠️ 알려진 한계 (Known Limits)

| 항목 | 동작 | 비고 |
|---|---|---|
| `sys.exit("메시지")` | 문자열 종료코드는 **실패**로 처리되며, 이미 만들어진 `out`도 **버려집니다** | 파이썬 자체 의미론(문자열 코드 = 종료코드 1)과 일치. 정상 종료는 `sys.exit(0)` |
| `os._exit()` | 스케줄러 데몬을 **즉시 종료**시킵니다 | 인터프리터를 우회하므로 잡을 수 없음. 수집기에서 사용 금지 |
| 수집기의 `KeyboardInterrupt` | 데몬이 종료되고 로그에는 **"terminated gracefully"** 로 남습니다(`run_auto_update.py:655-656`) | **의도적 미수정** — Ctrl+C 정상 종료가 우선. 수집기가 원인인 종료가 정상 종료처럼 보일 수 있음에 유의 |
| `sys.path.insert(0, script_dir)` | 수집기 디렉터리가 **`sys.path[0]`에 영구 고정**됩니다(제거하지 않음) | 형제 파일에 `paths.py`·`utils.py`·`config.py`가 있으면 **서버 자체 모듈을 가릴 수 있습니다.** 현재는 `server/paths.py`가 수집기 실행 전 이미 `sys.modules`에 올라와 있어 import 순서로만 보호됩니다 — 이 이름들을 수집기 폴더에 두지 마십시오 |

---

## ⚡ 4. 실시간 무설정 핫 리로드 (Zero-Interaction Hot-Reload)
* **즉시 코드 반영**: 스케줄러가 매 크론 실행 타이밍마다 디스크에서 최신 소스 코드를 새로 읽어 실행(`exec`)하므로, **파일을 수정하고 저장하면 어드민 버튼을 누르거나 재기동할 필요 없이 다음 실행 때 즉각 반영**됩니다.
* **즉시 스케줄 반영**: 메인 데몬 루프가 파일의 수정 시각(`mtime`)을 실시간 폴링 감시합니다. 파일 상단의 `# schedule: ` 크론 설정을 수정하는 즉시 스케줄러가 이를 감지하여 다음 실행 타이밍을 동적으로 갱신하고 로깅합니다.

---

## 🧰 4-bis. 이 프로세스가 하는 "수집기가 아닌 일" — 주간 config 스냅샷 (2026-07-28 추가)

> **⚠️ 2026-07-30: 유지보수 작업은 이제 2건입니다.** 이 절이 첫째(config 스냅샷)이고 **아래 §4-ter**가 둘째(그래프 고아 노드 스윕)입니다. 종전의 "**유지보수 작업 1건**" 서술은 `530fdfd` 이후 거짓이었습니다.

스케줄러 데몬은 수집기 외에 **유지보수 작업**을 함께 돌립니다. 첫째는 `server/config/*.json`의 주 1회 스냅샷(C3 백업)입니다. 구현은 `server/config_backup.py`, 호출부는 `MultiDiscoveryScheduler.maybe_backup_configs()`입니다.

**왜 수집기로 만들지 않았는가** — 수집기는 테이블 단위입니다. 산출물이 `ingestion_workspace/<table>/raws/`로 나가고 디렉터리 워처가 그것을 **그 테이블로 인제션**합니다. config 백업에는 대상 테이블이 없고 인제션되어서도 안 되므로 구조가 맞지 않습니다. 게다가 2026-07-27부터 **아무것도 내놓지 않은 수집기는 FAIL**이므로(§3 실패 판정 규칙), 백업 작업을 수집기로 등록하면 **정상 동작이 고장난 수집기와 구분되지 않습니다.**

재사용하는 것은 **이 데몬의 틱**뿐입니다. 시스템에서 시간 기반으로 도는 프로세스는 여기 하나뿐이고, 주 1회 파일 복사를 위해 여섯 번째 감시 프로세스를 늘리는 비용이 더 큽니다.

**주기가 크론 표현식이 아닌 이유** — `config_backup.due()`는 "일요일 03:00인가"가 아니라 **"디스크의 최신 스냅샷이 7일보다 오래됐는가"**를 봅니다. 크론 시각은 그 순간 PC가 꺼져 있으면 **그냥 건너뜁니다**. 재기동으로 한 주를 조용히 거르는 것이 바로 이 백업이 막아야 할 실패라, 상태를 메모리가 아닌 파일에서 유도합니다. 그래서 스케줄러가 재기동돼도 주기가 중복·유실되지 않고, 밀린 스냅샷은 **다음 기동 첫 틱**에 떠집니다.

* **감시 비용**: 매 틱이 아니라 30분에 한 번만 검사합니다(`CHECK_INTERVAL_SEC`). 첫 틱은 무조건 검사합니다.
* **실패 격리**: 백업 실패는 로그로만 나가고 수집기 실행을 막지 않습니다. 대신 **`/health`의 `checks.config_backup`**이 `missing`/`stale`을 보고합니다 — 판정 근거가 이 작업이 쓴 상태 파일이 아니라 **스냅샷 파일 자체**라, 이 작업이 죽어도 신호는 살아 있습니다.
* 규격·보관·복원 절차: [CONFIG_GUIDE §1](CONFIG_GUIDE.md) · [ROLLBACK_PROCEDURE §3.1-bis](ROLLBACK_PROCEDURE.md)

---

## 🧹 4-ter. 두 번째 유지보수 작업 — 그래프 고아 노드 스윕 (2026-07-30 `530fdfd`)

두 번째 유지보수 작업이 같은 틱에 올라탔습니다: **그래프 고아 노드 스윕**. 구현은 `server/graph_orphans.py`, 호출부는 `MultiDiscoveryScheduler.maybe_sweep_graph_orphans()` → `graph_orphans.run_scheduled()`이고, 매 틱 검사가 아니라 **30분에 한 번 "지금 할 때인가"만 묻고**(`CHECK_INTERVAL_SEC`) 주기는 **1일**(`SWEEP_INTERVAL_SEC`)입니다.

**왜 여기인가** — §4-bis와 **정확히 같은 근거**입니다: 시간으로 도는 프로세스가 시스템에 이것 하나이고, 대상 테이블이 없으며 인제션되어서도 안 되고, 2026-07-27부터 **아무것도 내놓지 않은 수집기는 FAIL**이라 정상 동작이 고장과 구별되지 않습니다. 형태를 `config_backup`에서 그대로 베꼈습니다.

**왜 스케줄이 필요했나** — `graph_materializer._retarget_stale_edges`는 **엣지**를 지우고, 엣지가 떠난 뒤의 **노드**를 지우는 코드는 어디에도 없었습니다. 라벨 폐기만의 문제가 아니라 **정체를 바꾸는 셀 편집마다 노드 한 개가 샙니다**(랏을 `LOT-A`→`LOT-B`로 교정하면 엣지는 충실히 재조준되고 `Core(LOT-A|05)`는 영원히 남습니다). 라이브 실측 2026-07-30: 재동기화를 반복해도 살아남는 degree-0 노드 **12,761개**.

> 🔴 **이 작업의 요점은 삭제가 아니라 거절입니다 — 선언이 깨끗하게 로드되지 않으면 스윕은 아무것도 하지 않습니다.**
> 고아 판정은 *"현재 어떤 매핑도 이 `(label, identity_key)`를 생산할 수 없다"*이므로, **컬럼 하나를 rename해 한 테이블 매핑이 조용히 스킵되면 그 테이블이 생산하던 모든 라벨이 생산 불가로 보입니다.** 라벨별 예산 가드(인구의 절반 초과를 잃는 라벨은 **거절**)는 큰 라벨을 막지만 `min_population`(10) 미만 라벨은 **막지 못합니다.** 그래서 의심스러운 선언은 결론 일부가 아니라 **판단 자격 자체**를 잃습니다 — `declaration_blockers`가 비어 있지 않으면 `status: "refused"`로 **전체를 거절**하고, 로그가 *"거부를 고치면(`GET /graph/mapping-summary`에서 보입니다) 다음 주기가 진행된다"*까지 말합니다. 매핑이 하나도 로드되지 않은 경우도 blocker입니다(빈 선언에서는 정의상 전 노드가 고아).
> 같은 규칙이 `GET /graph/chip-trace`의 `mapping_unavailable`에도 걸립니다 — **소비자는 둘, 규칙은 하나**입니다([ONTOLOGY_GRAPH_SPEC §7.5e](../spec/ONTOLOGY_GRAPH_SPEC.md)).

* **전량이 아니라 라벨별로.** 거절된 라벨이 나머지를 인질로 잡으면 안 됩니다 — 폐기된 `Chip` 노드 12,468개가 편집당 새는 노드를 영구히 막게 됩니다. 매 주기 **가져간 것과 거절한 것을 개수·비율과 함께** 로그에 남깁니다: 건너뛴 집합이 안 보이는 스윕은 "할 일 없음"으로 읽힙니다.
* **생산 가능성은 materializer가 쓰는 `compose_identity` 그대로** 판정합니다 — 정체 구현이 둘로 갈리는 것이 이 저장소가 좌표 변환에서 두 번 치른 값입니다. **"엣지 0개"만으로는 고아가 아닙니다**(`SplitCondition`은 평균 degree 0.2 — degree-0 스윕은 DOE 어휘를 통째로 지웁니다).
* **끄는 노브**: `GRAPH_ORPHAN_SWEEP_ENABLED=false`(형제 `GRAPH_MATERIALIZER_ENABLED`와 같은 표기). `status: "disabled"`로 보고합니다.
* **실패 격리**: §4-bis와 동일 — 스윕 예외는 로그로만 나가고 수집기 실행을 막지 않습니다.
* ⚠️ **주기 상태의 출처가 §4-bis와 다릅니다.** config 백업은 "디스크의 최신 스냅샷이 7일보다 오래됐는가"를 **파일에서** 유도하지만, 스윕은 **프로세스 메모리의 monotonic 시각**(`_last_orphan_sweep`)을 봅니다. `0.0`은 "첫 틱에 실행"이므로 **스케줄러 재기동마다 스윕이 한 번 돕니다.** 멱등하고 저렴한 유지보수라 문제가 되지 않지만, "하루 1회"를 재기동과 무관한 보장으로 읽지는 마십시오.
* 운영자 문(수동): `server/scripts/graph_orphan_sweep.py` — **dry run 기본**, `--apply`는 격리 밖에서 `--allow-production` 필요(dry run은 읽기 전용이라 어디서나 허용).

---

## 🎚️ 5. 수집기별 Active 토글 (2026-07-25 추가)

어드민 **AutoUpdate 탭**의 수집기별 Active 스위치로 개별 스크립트의 스케줄 실행을 켜고 끌 수 있습니다.

* **영속 제어 파일**: `server/config/auto_update_control.json` (`{"disabled": ["<workspace>/<script.py>", ...]}`, gitignored — `.sample` tracked). 공용 IO는 `server/utils/auto_update_control.py`(원자적 tmp+replace 쓰기).
* **핫 반영**: 스케줄러가 **매 사이클** 제어 파일을 읽으므로 재기동이 필요 없습니다. 비활성 수집기는 실행을 스킵하고 `last_status="SKIPPED"` 기록 + `next_run` 전진 — **재활성화해도 밀린 주기를 몰아 실행하지 않습니다**.
* **fail-open**: 제어 파일이 없거나 손상되면 전부 active로 간주합니다.
* **run-now 예외**: 어드민의 즉시 실행(run-now)은 active 여부와 **무관하게 항상 실행**됩니다(수동 실행은 명시적 의도).
* API: `GET /admin/auto-update/status`(항목별 `active` 부가) · `POST /admin/auto-update/toggle` (body `{"script": "<workspace>/<script.py>", "active": bool}`, 미존재 404·형식 오류 400).
