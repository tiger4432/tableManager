# config→스키마→기동 경로의 조용한 실패 3종 수리 (#9 / #13 / #16ⓐ)

> 2026-07-29 · Server · 기준 `f5805f4`

세 결함 모두 **조용한 실패** 계급이다. 셋 다 "실패했다는 사실이 어디에도 남지 않아서, 증상을 본 사람이 엉뚱한 데를 파게 만드는" 유형이다.

---

## #9 — 원자적 저장을 못 알아채 ALTER가 조용히 누락

### 현상
`table_config.json`에 컬럼을 추가했는데 물리 컬럼이 생기지 않는다. 그런데 `GET /tables/{t}/schema`는 새 컬럼을 담아 **200**을 돌려준다.

### 근본 원인
`config_watcher.ConfigChangeHandler`가 `on_modified`만 처리했다. 그런데 파일을 저장하는 가장 흔한 방식 — **temp 파일에 쓰고 rename**(에디터·에이전트 Edit 도구) — 은 `modified`가 아니라 `moved`를 만든다. 이 플랫폼에서 실측한 `os.replace`의 이벤트 순서:

```
created (tmp) → modified (tmp) → deleted (target) → moved (tmp → target)
```

**대상 경로에 대한 `modified` 이벤트는 아예 없다.** watcher는 깨어나지 않았고, 기존 테이블 ALTER의 유일한 런타임 경로가 통째로 죽어 있었다.

진단이 어려웠던 이유는 스키마 API가 **config 싱글턴을 읽기 때문**이다. 200에 컬럼이 보이는 것은 물리 반영의 증거가 아닌데, 그것이 증거처럼 보였다.

### 해결
`on_moved`를 추가하고 **`dest_path`** 로 판정한다(`src_path`는 temp 파일이다). 판정·디바운스·리로드는 `_maybe_reload`/`_reload`로 묶어 두 이벤트가 같은 경로를 탄다.

```python
def on_moved(self, event):
    if event.is_directory:
        return
    # The config is the DESTINATION of the rename; src_path is the temp file.
    self._maybe_reload(getattr(event, "dest_path", None))
```

`on_created`는 **일부러 넣지 않았다**. 직접 쓰기(`open(w)`)는 잘림 시점에 `created`/`modified`를 먼저 만들 수 있고, 1초 리딩 디바운스가 그 빈 파일 이벤트를 대표로 채택하면 **뒤따르는 진짜 저장이 통째로 버려진다**. 원자적 저장은 대상 경로에 이벤트를 하나(`moved`)만 만들므로 이 위험이 없다 — 위 실측이 근거다.

### 검증
`inspect(engine).get_columns(...)` 로 **물리 컬럼**을 직접 본다. 스키마 API 200은 증거로 쓰지 않는다.
- 단위: 합성 `FileMovedEvent`를 `handler.dispatch()`로 흘려보낸다(직접 `on_moved` 호출이 아니라 watchdog이 실제로 쓰는 `event_type → on_<type>` 배선까지 덮는다).
- 통합: 진짜 `Observer` + 진짜 `os.replace` + 진짜 ALTER. 핸들러가 move에 반응한다는 것과 **OS가 정말 move를 준다**는 것은 다른 명제라서 둘 다 필요하다.

---

## #13 — 손상된 config로 재기동하면 전 테이블이 조용히 사라진다

### 현상
`table_config.json`에 문법 오류가 난 뒤 재기동하면 모든 테이블이 없는 것처럼 뜬다. 로그는 깨끗하다.

### 근본 원인
```python
def load_table_config():
    ...
    except Exception:
        return {}        # 로그 한 줄 없음
```
가동 중에는 `refresh_dynamic_models`의 빈-config 가드가 싱글턴을 지켜준다. 하지만 **기동 시점**에는 그 `{}`가 그대로 진실이 된다. 화면은 데이터 유실처럼 보이는데 로그에 실마리가 없다.

### 해결 — 로더를 둘로 나눈다
| 함수 | 용도 | 파싱 실패 시 |
|---|---|---|
| `load_table_config()` | 런타임(핫리로드) | `logger.error`(경로 + `line N column M`) 후 `{}` — 기존 싱글턴 보존 |
| `load_table_config_or_raise()` | 기동 | `TableConfigError` |

`main.py` 부팅부가 후자를 쓰고, 잡으면 `logger.critical("[Boot] Refusing to start - ...")` 후 재던진다. 빈 상태로 뜨느니 안 뜨는 편이 낫다.

⚠️ **범위**: fail-fast는 **파싱 실패에만** 적용한다. 파일 부재(신규 설치)·읽기 실패(락·권한)·"JSON은 맞는데 선언이 이상함"은 기동을 막지 않는다. 의미 수준 불만으로 운영 서버가 안 뜨면 그 불만보다 큰 사고다. 이 경계는 테스트 두 개(`missing_file_is_not_an_error`, `semantically_odd_config_still_boots`)로 고정했다.

---

## #16ⓐ — 테스트만 돌려도 운영 PostgreSQL에 DDL이 나간다

### 현상
`main.py` 모듈 레벨의 `Base.metadata.create_all(bind=engine)`가 **import 시점**에 실행된다. 앱을 import하기만 해도(pytest 수집 포함) 그때 해석된 `DATABASE_URL`로 DDL이 나간다 — 미설정이면 그 기본값은 운영 DB다.

### 해결 — 삭제가 아니라 이동
요구가 둘이고 뒤쪽이 더 어렵다.
- INV-16-1: import가 DDL을 내지 않는다.
- INV-16-2: **신규 설치는 여전히 자동으로 테이블을 얻는다.** 이 경로를 없애면 온보딩("config에 테이블 추가 → 기동 → 즉시 사용")이 깨진다.

그래서 두 문장을 `bootstrap_database_schema()`로 묶고 `startup_event`가 호출하게 했다. 자동인 것은 그대로고, **서버를 실제로 띄워야** 한다는 조건만 붙었다.

### 부작용 — 측정해서 잡은 것 둘
1. **DB 불통 시 여전히 시끄럽게 죽는가.** `CODE_MAP`은 "PostgreSQL 불통 콜드스타트에서 죽는 자식은 정확히 하나(import가 `create_all`을 도는 웹서버)"를 동료실패 판정의 근거로 쓴다. 그 근거가 startup으로 옮겨갔으므로 실측했다 → `Application startup failed. Exiting.` **exit 3**. 감시자는 종료 코드를 구분하지 않고 `poll() is not None`이면 실패로 등록하므로 §1.3 판정은 불변.
2. **테스트에서는 startup이 이 단계를 건너뛴다.** 초안은 startup에서 무조건 호출했는데 `test_api.py::test_file_ingestion_callback_direct`가 깨졌다. 원인은 `sqlite:///:memory:`의 풀이 `SingletonThreadPool`이라는 것 — TestClient의 startup은 **워커 스레드**에서 돌고, 스레드마다 **다른 인메모리 DB**를 받는다. 게다가 커넥션이 5개를 넘으면 오래된 것부터 닫으므로, 매 TestClient마다 커넥션을 하나씩 늘리면 **메인 스레드의 DB가 테이블째 닫혀 사라진다.**
   → 호출부에 `TESTING` 가드를 두고, `conftest.py`가 앱 import 직후 **메인 스레드에서 1회** `bootstrap_database_schema()`를 호출한다. 스위트가 이 단계에 의존한다는 사실이 우연이 아니라 명시가 됐다.

---

## 검증

### 결함 역주입 (7종) — 각 검사가 자기 결함에서만 빨개진다

| 뮤테이션 | 되돌린 것 | 결과 |
|---|---|---|
| m1 | `on_moved` 제거 | `atomic_save_event_applies_physical_alter`, `atomic_save_through_real_watchdog` 2건 실패 |
| m2 | 리로드 중단 로그를 `debug`로 강등 | `unusable_config_is_logged_not_skipped` 실패 |
| m3 | 파싱 실패를 다시 조용히 `{}` | `parse_failure_logs_path_and_position` 실패 |
| m4 | 기동 fail-fast를 다시 삼킴 | `corrupt_config_refuses_to_boot` 실패 |
| m5 | `create_all`을 모듈 레벨로 복귀 | `importing_the_app_issues_no_ddl` 실패 |
| m6 | startup에서 호출 제거 | `startup_event_invokes_the_bootstrap` 실패 |
| m7 | bootstrap을 no-op으로 | `boot_still_creates_tables_on_a_fresh_install` 실패 |

주입/복원은 바이트 단위로 하고(autocrlf가 조용히 줄끝을 바꾸는 함정 회피), 복원 후 **SHA256으로 원본 일치**를 확인했다.

### 스위트
`1103 passed` / 실패 10건은 전부 `test_map_seam_contract.py` — contract-keeper가 같은 트리에서 작업 중인 `contracts/map_seam/`의 신규 계약 벡터이며, 아직 없는 서버 심볼(`valid_die_chain_error`)을 참조한다. 이번 변경과 무관하고 이번 변경이 만지지 않은 도메인이다.

### 물리 반영 확인의 정본
```sql
SELECT column_name FROM information_schema.columns WHERE table_name = '<table>';
```
`GET /tables/{t}/schema`의 200은 config 싱글턴을 읽은 결과일 뿐이다. 이 함정은 CONFIG_GUIDE §6-D로 그대로 남아 있다.

---

## 수정 파일
| 파일 | 내용 |
|---|---|
| `server/database/config_watcher.py` | `on_moved` 추가(dest_path 판정), `_maybe_reload`/`_reload` 분리, 빈 config 시 `Config reload ABORTED` ERROR |
| `server/database/crud.py` | `TableConfigError`, `load_table_config_or_raise()` 신설, `load_table_config()`는 loud + `{}` |
| `server/main.py` | 부팅 config 로드 fail-fast, `bootstrap_database_schema()` 신설(모듈 레벨 DDL 이동), startup 배선, 죽은 전역 `config_path` 제거 |
| `server/tests/conftest.py` | 앱 import 직후 메인 스레드에서 boot 단계 1회 호출(+사유 주석) |
| `server/tests/test_config_reload_integrity.py` | 신규 12건 |
| `docs/guide/CONFIG_GUIDE.md` | 함정 A·B 해소 등재, §4.4 발화 조건, S1 체크리스트 2행 |
| `docs/guide/config/table_config.md` | 로더 evidence 주석, §2 저장 절차 |
| `docs/architecture/data_model.md` | §1.2 부팅 스키마 구축, §5 watcher 이벤트·fail-fast |
| `docs/architecture/backend.md` | §1 DDL 이동·기동 fail-fast |

## 남은 것
- `docs/architecture/CODE_MAP.md` 앵커 갱신(code-mapper 소관): `load_table_config` ~172 앵커 이동, 신규 심볼 `TableConfigError`·`load_table_config_or_raise`·`bootstrap_database_schema`, §5 config_watcher 설명(`on_modified`만) 문구, 439행의 "import가 `create_all`을 도는 웹서버" 서술.
- 워커 프로세스(`run_watcher` 등)는 손상 config에서 fail-fast하지 않는다(빈 config + ERROR 로그로 계속). 웹서버가 안 뜨면 스택 전체가 눈에 띄므로 이번 범위에서는 의도적으로 남겼다.
