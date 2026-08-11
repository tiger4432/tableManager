# ⏪ 롤백 절차 — 배포가 잘못됐을 때 되돌리는 법

> **Status:** 🟢 Living | **작성:** 2026-07-28 · Server PM | **Last-verified:** 2026-08-05
>
> **이번 라운드 (2026-08-05 · `f6406b1`)**: **단계 4에 `--preflight-only`를 앞세웠다** — 되돌린 코드가 지금 DB와 맞는지를 **화면이 500을 내기 전에** 답하는 유일한 자리다. **되돌리는 방향은 대개 안전**(옛 코드는 새 컬럼을 매핑하지 않으므로 `INFO`)하고 **위험한 것은 앞으로 가는 방향**이다(마이그레이션 없이 새 코드 → 그 테이블 통째로 죽음). 🔴 **§6에 「`/health`가 못 보는 것」 하나 추가 — 코드와 *DB 스키마*의 불일치.** 드리프트난 스택은 `/health`가 **정상 200**을 답한다.
>
> 이전: (**1초 디바운스 함정 해소** — 트레일링 엣지 디바운스로 연속 저장이 더는 버려지지 않는다(단계 2). 복사 방식 제약(`cp` 강제)도 해제. 직전 2026-07-28 **C3 주간 config 스냅샷 신설 + 복원 드릴 실행** — 단계 2가 이제 실재하는 원본을 가리킨다. §3.1-bis 신설, 단계 2 재작성, 1초 디바운스 함정 추가. 직전: 격리 스택 전 구간 드릴 — §7 타임라인)
> **대상:** 새벽 2시에 이 문서를 여는 운영자.
> **먼저 알아야 할 것:** 이 시스템은 **코드와 config가 서로 다른 시점에 반영된다.** 그 사실 하나가 이 문서 전체의 이유다.
> **관련:** 배포는 [DEPLOY_SETUP](DEPLOY_SETUP.md) · 설정 키는 [CONFIG_GUIDE](CONFIG_GUIDE.md) · 게이트 판정은 [PRODUCTION_READINESS](../process/PRODUCTION_READINESS.md)

---

## 0. 30초 요약 — 지금 당장 되돌려야 한다면

```
1. 증거 확보     로그·config 사본·git HEAD·스키마 리포트   (약 10초, 건너뛰지 마라)
2. config 되돌리기  백업에서 제자리 복사                    (즉시 반영, 재기동 불필요)
3. 코드 되돌리기    git checkout <good-sha> -- <경로>       (실행 중 프로세스엔 아직 영향 없음)
4. 런처 통째 재기동  run_decoupled_app.py                    (여기서 코드 롤백이 실제로 발효)
5. 검증          도메인 엔드포인트로 옛 동작 확인            (/health로는 못 잡는다 — §6)
```

**실측 총 소요 30초**(준비된 상태 기준). 사용자 체감 장애는 그중 **16초**. 마흔 시간짜리 작업이 아니다 — 하지만 **순서를 틀리면 끝나지 않는다**(§2).

> 데이터베이스는 되돌아가지 않는다. 스키마는 **한 방향**이다 — §5를 반드시 읽어라.

---

## 1. 무엇이 언제 반영되는가 (이 표가 전부다)

| 반영 대상 | 언제 반영되나 | 되돌리려면 |
|---|---|---|
| **코드**(`server/**`, `client2/dist/**`) | **프로세스 재기동까지 고정** | 파일 복원 + **재기동** |
| **계획 계열 config**(`transfer_plan_config`·`bonding_plan_config`·`map_overlay_config`) | **요청마다 디스크 재읽기** — 즉시 | 파일 복원 (재기동 불필요) |
| **`table_config.json`** (선언) | config watcher의 **제자리 쓰기 감지** 시 즉시 (싱글턴 핫스왑) | 파일 복원 → watcher가 선언만 되돌림 |
| **`table_config.json`** (물리 CREATE/ALTER) | 위와 **동시에** — 재기동 없이 DDL이 나간다 | ❌ **되돌아가지 않는다** → §5 |
| **매퍼·수집기 스크립트**(`server/mappers/`, `<workspace>/auto_update/*.py`) | `SYSTEM_RELOAD`가 모듈 캐시를 비움 | 파일 복원 + `SYSTEM_RELOAD`(또는 재기동) |

**드릴 실측**:

- 코드 파일을 디스크에서 v2로 바꾼 직후 API는 **여전히 v1을 서빙**했다. 재기동 전까지 코드는 고정이다.
- 계획 config를 되돌리자 **0.01초**(바로 다음 요청)에 반영됐다.
- `table_config.json` 제자리 쓰기 → 약 5초 뒤 watcher가 `CREATE TABLE` + `ALTER TABLE ... ADD COLUMN`을 **재기동 없이** 실행했다.

> ⚠️ `SYSTEM_RELOAD`는 **config와 사용자 소유 스크립트만** 다시 읽는다. **제품 코드(`server/**`)를 다시 불러오는 경로는 존재하지 않는다.** 어떤 리로드 버튼도 코드 롤백을 대신하지 못한다.

---

## 2. 왜 배포 순서와 롤백 순서가 "같은 목록 거꾸로"가 아닌가

배포는 **코드 → 재기동 → config**다.
롤백은 **config → 코드 → 재기동**이다.

거꾸로 읽으면 `config → 재기동 → 코드`가 되는데, **그 재기동은 아직 새 코드로 올라간다.** 장애 시간만 쓰고 아무것도 되돌리지 못한 뒤, 코드를 고치고 **한 번 더** 재기동해야 한다. 즉 **재기동이 배포에서는 가운데, 롤백에서는 맨 마지막**이라는 것이 차이의 전부다.

**재기동을 마지막에 두는 이유** — 재기동은 롤백에서 유일하게 비싼 단계이고, 유일하게 되돌릴 수 없는 시점이다. 그 순간 **config가 이미 옛 형태여야** 시스템이 정확한 상태로 올라온다. config를 나중에 되돌리면 서버는 **깨진 채로 올라오고**, `table_config.json`의 경우 두 번째 재기동(또는 watcher 재발화)이 또 필요하다.

### 드릴로 관측한 잘못된 순서 (= 2026-07-27 M2.6 인시던트)

코드를 먼저 되돌리고 재기동했다. 결과:

```
00:30:00  재기동 완료 (v1 코드 + v2 config)
00:30:06  GET /api/transfer-plan/stages -> 200,  "target_map": {}     <-- 타깃 맵 바인딩 소실
00:30:06  GET /health                  -> 200,  status: ok, problems: []
```

**코드만 되돌려서는 복구되지 않는다.** 그리고 이 상태에서 `/health`는 **정상이라고 말한다**(§6). config를 되돌이자 **0.01초** 만에 복구됐다 — 재기동 없이.

### 배포(전진) 순서에도 창이 있다 — 솔직하게

"코드 먼저, config 나중"은 **새 코드가 옛 config를 읽을 수 있을 때만** 무중단이다. 드릴에서 쓴 변경은 그렇지 않았고, 재기동 직후 **새 코드 + 옛 config** 상태에서 같은 방식으로 깨졌다:

```
00:27:46  재기동 완료 (v2 코드 + v1 config)
00:27:51  "plan_shape": "v2" 는 뜨는데  "target_map" 은 비어 있음
00:28:28  config를 v2로 쓰자 0.14초 만에 정상
```

- **하위호환 배포**(새 코드가 옛 config도 읽음): 코드 → 재기동 → config. 창이 없다. **이게 기본이어야 한다.**
- **비하위호환 배포**: 창은 피할 수 없다. **config 파일을 미리 만들어 두고** 재기동 직후 즉시 복사해 창을 초 단위로 줄여라. 여유가 있으면 스택을 내리고 → 양쪽 바꾸고 → 올리는 **콜드 배포**가 더 정직하다.
- 롤백에서 **옛 코드가 새 config를 읽을 수 있는 경우는 사실상 없다**(옛 코드는 새 형태를 본 적이 없다). 그래서 **롤백은 항상 config 먼저**다. 선택지가 아니다.

---

## 3. `server/config/`는 git에 없다 — 그러면 무엇에서 복원하나

`server/config/`와 `server/ingestion_workspace/`는 **의도적으로** gitignored다(운영 서버 패치 시 현장 자산 오염 방지 — [PRODUCTION_READINESS C3](../process/PRODUCTION_READINESS.md)). 따라서:

> 🚨 **`git revert`는 config를 건드리지 않는다.** 코드만 되돌리고 "롤백했다"고 판단하는 것이 이 시스템에서 가장 쉬운 실수다.

### 3.1 `table_config.json.bak.<ts>` 백업으로 충분한가 — **아니다. 부분적이다**

`install_product_tables.py --apply`가 쓰기 직전에 타임스탬프 백업을 남긴다(`server/config/table_config.json.bak.20260727-225922` 형태). 그 백업의 **정확한 성격**을 알고 써야 한다:

| | |
|---|---|
| **덮는 범위** | **그 스크립트가 실행된 순간**의 파일 전체 스냅샷 |
| **덮지 않는 범위** | 어드민 UI·에디터·에이전트가 손으로 한 수정에는 **백업이 생기지 않는다.** 백업은 제품 테이블 설치 경로에만 있다 |
| **따라서** | 백업 목록은 **배포 이력이 아니라 "제품 테이블을 설치한 이력"**이다. 그 사이의 현장 수정은 어느 백업에도 없다 |

**올바른 백업을 고르는 법** — 파일명의 타임스탬프는 `YYYYMMDD-HHMMSS`(로컬 시각)다. 되돌리려는 **배포 직전**의 것을 고른다.

```bash
ls -t server/config/table_config.json.bak.*        # 최신순
diff <(python -m json.tool server/config/table_config.json.bak.20260727-225922) \
     <(python -m json.tool server/config/table_config.json)
```

**반드시 diff를 먼저 보라.** 백업이 되돌리려는 배포보다 **오래됐다면**, 그 사이의 정당한 현장 수정(새 공장 테이블 선언, 컬럼 추가)까지 함께 지워진다. 그 경우 **파일을 통째로 되돌리지 말고, 문제의 항목만 골라서 편집**하라 — `table_config.json`은 최상위가 테이블명 키인 평평한 객체이므로 한 항목만 되돌리는 것이 가능하다.

**백업이 아예 없다면**: 그것이 정상 상태다(대부분의 변경은 백업을 남기지 않는다). 이때 복원 경로는 **§3.1-bis 주간 스냅샷**이다.

### 3.1-bis `<이름>_<yymmdd>.json.bak` — 주간 스냅샷 (C3, 2026-07-28 신설)

이쪽이 **일반 배포의 정식 복원 원본**이다. 누가 어떻게 고쳤든(어드민 UI·에디터·에이전트) 주 1회 전량 스냅샷을 뜨므로, §3.1의 설치 이력과 달리 **수정 경로를 가리지 않는다.**

```
table_config_260728.json.bak          <- 주간 스냅샷 (날짜가 확장자 앞)
table_config.json.bak.20260727-225922 <- 설치 이력   (날짜가 확장자 뒤)
```

> **이 두 줄의 차이가 새벽 2시에 지켜야 할 전부다.** 날짜가 **앞**이면 주간 스냅샷, **뒤**면 설치 이력이다. 파일을 열지 않고 `ls`만으로 구분된다.

| | |
|---|---|
| **주기** | 7일. **크론 시각이 아니라 "디스크의 최신 스냅샷이 7일보다 오래됐는가"**로 판정하므로, 그 시각에 PC가 꺼져 있었어도 다음 기동 때 밀린 스냅샷을 뜬다 |
| **어디서 도나** | Auto-Update 스케줄러 프로세스(`run_auto_update.py`) 안의 유지보수 작업. 수집기가 **아니다** — raws/로 나가지도, 인제션되지도 않는다 |
| **범위** | `server/config/*.json` 전량(파일당 1개). `.sample`·`.bak` 계열·`scheduler_status.json`·`supervisor_status.json`은 제외 |
| **보관** | 1개월 FIFO. 오래된 것부터 밀려나되 **최신 4개는 나이와 무관하게 남는다**(장기간 중단 후 재개가 이력을 통째로 지우는 것을 막는다). 삭제는 로그에 파일명이 찍힌다 |
| **같은 날 두 번** | 내용이 같으면 **건너뛴다**. 다르면 `_260728b` → `c`로 글자가 붙는다. **덮어쓰지 않는다** |

**정렬은 파일명이 한다.** `yymmdd`가 사전순 = 시간순이고 `260728` < `260728b` < `260729`다. `ls`의 마지막 줄이 최신이다 — `mtime`을 볼 필요가 없다(도구도 `mtime`을 보지 않는다).

```bash
conda run -n assy_manager python server/scripts/backup_config.py list    # 무엇이 있나
conda run -n assy_manager python server/scripts/backup_config.py check   # 최신 것이 신선한가 (오래됐으면 exit 1)
conda run -n assy_manager python server/scripts/backup_config.py snapshot # 위험한 변경 전에 손으로 하나 더
```

> ⚠️ **백업이 멈춘 것은 `/health`가 말해 준다.** `checks.config_backup`이 `missing`/`stale`이면 `problems`에 한 줄이 뜨고 상태가 `degraded`가 된다(HTTP는 200 유지 — 백업 부재는 *다음* 사고를 어렵게 만들 뿐 지금 죽은 것이 아니다). 이 판정은 작업이 스스로 기록한 "마지막 실행" 필드가 아니라 **디스크의 파일 자체**를 읽는다. 3주 전에 조용히 죽은 작업은 자기 성공 기록을 그대로 들고 있기 때문이다.

### 3.2 되돌리기 전에 반드시 스스로 백업하라

```bash
cp server/config/table_config.json          server/config/table_config.json.prerollback.$(date +%Y%m%d-%H%M%S)
cp server/config/transfer_plan_config.json  server/config/transfer_plan_config.json.prerollback.$(date +%Y%m%d-%H%M%S)
```

**이유**: 롤백이 실패하면 되돌아올 곳이 필요하다. 그리고 사후에 "무엇이 문제였나"를 보려면 **깨진 config 자체가 증거**다. 되돌리면서 지우지 마라.

> 복사 방식은 무관하다(2026-07-29 #9/H3). watcher가 `on_modified`·`on_moved`·`on_created`를 모두 처리하므로 `cp`든 `mv`든 `os.replace`든 반영된다. 2026-07-28 드릴 시점에는 `on_modified`만 처리해서 **원자적 rename이 조용히 누락**됐고, 그래서 이 문서가 `cp`를 지정했다.

---

## 4. 절차

### 단계 1 — 증거 확보 (약 8초, 건너뛰지 마라)

되돌리고 나면 왜 깨졌는지 알아낼 재료가 사라진다. 특히 **로그는 재기동으로 계속 덮이고**, 깨진 config는 복원으로 사라진다.

```bash
mkdir -p rollback_evidence/$(date +%Y%m%d-%H%M%S) && cd $_
cp ../../server/config/*.json .                       # 깨진 config 그대로
cp ../../server/server.log ../../server/watcher.log ../../server/launcher.log . 2>/dev/null
git rev-parse HEAD > git_head.txt
git status --short  > git_status.txt
curl -s http://localhost:8080/health > health.json
conda run -n assy_manager python server/scripts/list_undeclared_tables.py > schema_before.txt
```

`server/scripts/dev_env/manifest.py capture`를 쓰면 DB 행수·config 파일 해시를 한 번에 뜰 수 있다(롤백 전후 대조용):

```bash
conda run -n assy_manager python server/scripts/dev_env/manifest.py capture rollback_evidence/before.json
```

**⚠️ 로그에 없는 것**: `table_config.json` 변경이 유발한 `ALTER TABLE`은 `sync_dynamic_tables_schema`가 **`print()`로만** 내보낸다. 런처는 자식 프로세스의 stdout을 리다이렉트하지 않으므로(`process_supervisor.py`의 `Popen`에 `stdout=` 없음) 그 줄은 **운영자 콘솔에만** 뜨고 어느 로그 파일에도 남지 않는다. 드릴에서 확인한 결과, `server.log`에는 `Physical database schema synced successfully.`라는 **어느 테이블의 어느 컬럼인지 없는 한 줄**만 남는다. 콘솔 스크롤백이 살아 있다면 **지금 복사해 두라. 재기동하면 사라진다.**

### 단계 2 — config 되돌리기 (즉시 반영, 재기동 불필요)

되돌릴 config가 **있는지 없는지 먼저 확인**한다. 이번 배포가 config를 건드리지 않았다면 이 단계는 건너뛴다.

```bash
# 이번 배포에서 손댄 config가 무엇인지 (수정 시각으로 좁힌다)
ls -lt server/config/*.json | head

# 되돌아갈 스냅샷 고르기 — 날짜가 확장자 앞이면 주간 스냅샷이다 (§3.1-bis)
conda run -n assy_manager python server/scripts/backup_config.py list
```

**배포 직전 날짜의 것을 고른다.** 고른 뒤 반드시 diff를 본다 — 스냅샷이 배포보다 오래됐다면 그 사이의 정당한 현장 수정까지 함께 지워진다(§3.1).

```bash
diff <(python -m json.tool server/config/table_config_260728.json.bak) \
     <(python -m json.tool server/config/table_config.json)
```

되돌린다. **깨진 파일은 자동으로 `.prerollback.<ts>`로 남으므로 증거를 잃지 않는다.**

```bash
# 먼저 --yes 없이 → 무엇을 덮어쓰는지만 보여주고 쓰지 않는다
conda run -n assy_manager python server/scripts/backup_config.py restore table_config_260728.json.bak
conda run -n assy_manager python server/scripts/backup_config.py restore table_config_260728.json.bak --yes
```

> 손으로 할 때 저장 방식은 이제 상관없다(2026-07-29 #9/H3) — `cp`·`mv`·`os.replace` 전부 watcher를 발화시킨다. 2026-07-28 드릴 시점에는 원자적 rename이 누락돼 `table_config.json`이 **디스크에는 옳고 시스템은 옛 상태인 채로** 남았고, `restore`가 제자리 쓰기를 하는 이유가 그것이었다(그 선택 자체는 여전히 무해하다).

**실측**(2026-07-28 격리 스택 드릴, §8):

| | 명령 반환 | 시스템이 옛 동작을 서빙하기까지 | 총계 |
|---|---|---|---|
| `transfer_plan_config.json` (계획 계열) | 0.16초 | **0.005초** (다음 요청) | **0.17초** |
| `table_config.json` (watcher 경유) | 0.20초 | **0.13초** (watcher 재읽기) | **0.33초** |

`table_config.json`은 watcher가 **선언만** 핫스왑한다 — **물리 스키마는 따라오지 않는다**(§5).

#### ✅ 1초 디바운스 함정 — 해소 (2026-07-29, H2)

2026-07-28 드릴이 찾아낸 함정이다. **파일은 옳은데 시스템이 옛 선언을 계속 서빙했고, 로그에는 아무 줄도 남지 않았다.** 원인은 `config_watcher.py`의 **리딩 엣지** 디바운스였다:

```python
if now - self.last_triggered < 1.0:
    return          # 1초 안에 들어온 두 번째 쓰기는 통째로 버려진다
```

배포(쓰기 1)와 롤백(쓰기 2)이 1초 안에 일어나거나, **연달아 두 번 되돌리면**(잘못 골라서 다시 고름) 두 번째가 삼켜졌다.

지금은 **트레일링 엣지**다 — 이벤트마다 타이머를 재무장하고 **마지막 이벤트 후 1초**에 1회 발화한다. 연속 쓰기 중 버려지는 것이 없고, 여러 번 써도 리로드는 마지막 상태 기준 1회다. 느린 비원자적 쓰기(첫 이벤트가 잘린 파일을 보는 경우)도 같은 수정으로 닫혔다.

**남은 것은 지연뿐이다**: 반영은 **마지막 쓰기로부터 약 1초 뒤**다. 되돌린 직후 즉시 확인하면 아직 옛 값일 수 있으니 1초 기다렸다가 다시 본다.

**그래도 안 바뀌면** — `restore`가 `the snapshot is byte-identical to the current file`이라고 말하는데 동작이 안 돌아왔다면 파일은 이미 옳다. 즉 **복원 실패가 아니라 재읽기 실패**이고, 이제는 그 경우 **watcher 로그에 줄이 남는다**(`Configuration change detected ...` 또는 `Config reload ABORTED: ...`). 로그가 완전히 비어 있다면 watcher 프로세스 자체를 의심하고, `POST /admin/reload-configs`(신규 CREATE 전용) 또는 재기동으로 간다.

### 단계 3 — 코드 되돌리기 (아직 실행 중 프로세스에는 영향 없음)

```bash
git log --oneline -10                       # 되돌릴 지점 찾기
git checkout <good-sha> -- server/ client2/dist/     # 파일만 되돌린다
#  또는
git revert --no-commit <bad-sha> && git status
```

`client2/dist/`를 **반드시 포함**한다 — 서버가 서빙하는 것은 소스가 아니라 빌드 산출물이고, 그 산출물은 git에 올라간다.

이 시점에는 디스크만 바뀐다. **드릴에서 확인**: 코드 파일을 바꾼 뒤 재기동 전 API는 여전히 옛(=당시 실행 중) 동작을 서빙했다.

### 단계 4 — 재기동: 대상은 **하나가 아니라 다섯**이다

```bash
# 런처를 통째로 내렸다가 다시 올린다 (Ctrl+C 후 재실행)
conda activate assy_manager
python run_decoupled_app.py --preflight-only   # ← 2026-08-05 신설: 올리기 전에 물어본다
python run_decoupled_app.py
```

> 🔴 **`--preflight-only`가 되돌린 뒤에 특히 값싸다**(`f6406b1`). **아무것도 띄우지 않고** 포트와 **스키마 드리프트**를 점검합니다 — 되돌린 코드가 지금 DB와 맞는지를 **화면이 500을 내기 전에** 답하는 유일한 자리입니다.
> - **되돌리는 방향은 대개 안전합니다** — 옛 코드는 새 컬럼을 매핑하지 않으므로 그 컬럼은 `INFO`(무해, §5의 잔여물)로 보고됩니다.
> - **위험한 것은 앞으로 가는 방향입니다** — 마이그레이션을 안 돌린 DB에 새 코드를 올리면 **그 테이블이 통째로 죽습니다**(그 컬럼을 읽지 않는 코드까지). 배너의 `TABLE-DOWN`이 그것이고, 평결이 **어느 마이그레이션을 돌려라**까지 말합니다.
> - ⚠️ **종료 코드는 포트만 봅니다** — 드리프트는 종료 코드를 안 바꿉니다(무인 재기동이 컬럼 하나로 스택 전체를 막지 못하게). **스크립트로 감싸지 말고 배너를 읽으십시오.**

**웹서버만 재기동하지 마라.** 코드는 프로세스마다 고정되므로, 웹서버만 다시 띄우면 **워처·체인 워커·그래프 워커·스케줄러 4개가 옛 코드를 든 채 남는다.**

특히 걸리는 두 가지:

| | |
|---|---|
| **Auto-Update 스케줄러** | `SYSTEM_RELOAD`를 구독하긴 하지만 하는 일은 **수집기 스크립트 재스캔**(`dynamic_collector_*` 모듈 캐시 비우기)뿐이다. `run_auto_update.py` 자신과 `server/**` 모듈은 **다시 로드되지 않는다.** 리로드로는 롤백되지 않는다 |
| **`ASSY_ADMIN_TOKEN`이 설정된 환경** | 워커는 런처 기동 시점의 환경을 복사해 물려받는다. 부분 재기동으로 워커가 옛 토큰을 든 채 남으면 `/internal/events/*`가 **401**(헤더 없음) 또는 **403**(양쪽 토큰 불일치)을 돌려주고 **실시간 동기화가 조용히 멈춘다** — 화면은 멀쩡하고 데이터만 안 들어온다. **[F8 2026-07-30] 진단이 로그 한 줄로 끝난다**: 실패 줄의 `admin-gate=yes`면 우리 게이트(토큰 문제 — 조치까지 같은 줄에 있다), `admin-gate=no`면 **우리가 아니다**(앞단 프록시·방화벽 — [DEPLOY_SETUP §1-5](./DEPLOY_SETUP.md), 재기동으로 절대 안 고쳐진다). 토큰이 갈렸는지는 웹서버·워커 기동 배너의 `token fingerprint`를 눈으로 비교하면 된다 |

**실측 재기동 시간**: 정지 2.5초 + 기동 후 `/health` 응답까지 3.2초 = **약 5.6~5.7초**. 사용자에게는 그 구간이 연결 거부로 보인다.

### 단계 5 — 검증: `/health`로는 부족하다

```bash
curl -s http://localhost:8080/health | python -m json.tool      # 프로세스·워커·DB만 본다
curl -s http://localhost:8080/api/transfer-plan/stages          # 도메인 동작 — 이쪽이 진짜 판정
```

**반드시 "옛 동작이 실제로 나오는지"를 눈으로 확인**하라. 파일이 바뀐 것은 증거가 아니다. 드릴의 판정 기준은 `target_map.table`이 다시 값을 갖는지였다.

### 복원 불가일 때 — 인정하고 멈춰라

설치 이력(§3.1)도 없고 주간 스냅샷(§3.1-bis)도 없다면 **롤백은 불가능하다.**

> 주간 스냅샷이 도입된 2026-07-28 이후로 이 분기에 빠지는 경우는 **스케줄러가 한 번도 안 돌았을 때뿐**이고, 그때는 `/health`가 이미 `config backup: no config snapshot has ever been taken`이라고 말하고 있었을 것이다. 사고가 나서야 그 줄을 읽게 됐다면, 그 줄이 **몇 주 전부터 떠 있었다는 뜻**이다.

이때 옳은 행동은 즉흥적으로 config를 손으로 재구성하는 것이 아니라:

1. 현재 상태를 **그대로 동결**하고 증거를 뜬다(단계 1).
2. **앞으로 고치는 쪽**(roll-forward)을 택한다 — 깨진 바인딩 하나를 새 코드에 맞추는 편이, 기억으로 config를 복원하는 것보다 안전하다.
3. 사용자에게 **복원 경로가 없다는 사실**을 먼저 알린다.

---

## 5. 스키마는 한 방향이다 — "이미 CREATE된 테이블은 어떻게 하나"

**선언을 되돌려도 물리 객체는 남는다.** 만드는 경로는 있고(`create_missing_dynamic_tables`, `sync_dynamic_tables_schema`) **지우는 경로는 없다.**

**드릴로 재현**: `table_config.json`에 테이블 하나와 기존 테이블의 컬럼 하나를 선언 → watcher가 약 5초 만에 `CREATE TABLE` + `ALTER TABLE ADD COLUMN` 실행 → **선언을 되돌린 뒤에도 둘 다 그대로 남아 있었다.**

**실제 사례 (2026-07-27)**: 폐기된 밴드 모델을 만들다가 `map_band_registry`를 라이브 `table_config.json`에 넣었고 watcher가 1초 안에 물리 테이블을 만들었다. 선언은 깨끗이 되돌렸는데 **빈 테이블은 남았다** — 어디에도 선언되지 않은 채. (사용자가 직접 `DROP`해 2026-07-28 기준으로는 없다.)

> **이것은 한 번의 사고가 아니라 축적이다.** 2026-07-28에 라이브 DB를 이 리포트로 훑었더니 **미선언 테이블 7개**(빈 것 3 — `data_rows`·`hvy_drill_big`·`hvy_drill_small`, 행이 있는 것 4 — M2.6에서 선언이 빠진 `transfer_plan`·`transfer_plan_doe`·`transfer_plan_doe_layer`·`transfer_plan_map`)와 **미선언 컬럼 2개**(`bonding_map.grid_metadata`, `inventory_master.M22N`)가 나왔다. 어느 것도 화면·인제션에 나타나지 않는다. **아무도 세고 있지 않으면 계속 늘어난다.**

### 잔여물을 찾는 법

```bash
conda run -n assy_manager python server/scripts/list_undeclared_tables.py
```

읽기 전용이다. DDL을 내지 않고, `DROP` 문을 **출력만** 한다. 세 가지를 보고한다:

| 보고 항목 | 뜻 |
|---|---|
| **UNDECLARED TABLE** | 선언에도 없고 제품 시스템 테이블도 아닌 물리 테이블. **비어 있으면** 되돌린 선언의 잔여물일 가능성이 높다. **행이 있으면** config 이전의 레거시 테이블일 가능성이 높으니 **감으로 지우지 마라** |
| **UNDECLARED COLUMN** | 선언된 테이블에 남은, 선언에 없는 물리 컬럼. 되돌린 컬럼 추가가 쌓이는 자리다. 인제션은 값을 버리고 그리드는 보여주지 않으므로 **무해하지만 계속 쌓인다** |
| **DECLARED BUT MISSING** | 반대 방향 — 선언은 있는데 물리 테이블이 없다. 대개 원자적 쓰기라 watcher가 발화하지 않은 경우다. `POST /admin/reload-configs` 또는 재기동으로 생성된다 |

### 지우는 것은 사람이 한다

이 스크립트는 **절대 DROP하지 않는다.** 새벽 2시에 스크립트가 내릴 결정이 아니다. 확인한 뒤에만, 출력된 문장을 직접 실행하라.

```sql
DROP TABLE "map_band_registry";                    -- 비어 있음을 확인한 뒤에만
ALTER TABLE "test" DROP COLUMN "drill_note";
```

> 드릴에서 이 문장들을 **격리 DB에 실제로 실행해** 검출 → 제거 → 재검출(깨끗함)까지 왕복을 확인했다.
> ⚠️ 행이 있는 테이블은 지우지 마라. 격리 스냅샷에서도 `map_split_registry.updated_by`처럼 **정체를 모르는 잔여 컬럼**이 이미 하나 있었다 — 출처를 모르는 것은 남겨 두는 편이 낫다.

### "롤백됐다"의 정확한 뜻

코드와 config는 **이전 상태로 돌아간다.** 데이터베이스는 **앞으로 간 채로 남는다.** 남은 컬럼·테이블은 선언되지 않았으므로 조회·인제션·화면 어디에도 나타나지 않는다 — **동작은 완전히 롤백되지만 스키마는 아니다.** 이것이 이 시스템에서 롤백이 의미할 수 있는 최대치다.

---

## 6. `/health`가 잡지 못하는 것

`GET /health`는 **DB·워커 박동·outbox 나이·감시자**를 본다. **코드와 config의 형태 불일치는 보지 않는다.**

**드릴 실측** — 코드만 되돌린 깨진 상태에서:

```
GET /api/transfer-plan/stages -> 200   "target_map": {}      <-- 바인딩 소실
GET /health                   -> 200   status: ok  problems: []
```

즉 **롤백의 성공 판정을 `/health`로 하면 안 된다.** 이번 배포가 건드린 기능의 **도메인 엔드포인트**를 직접 호출해 옛 응답 형태가 나오는지 보라.

> 🔴 **`/health`가 못 보는 것이 하나 더 있다: 코드와 *DB 스키마*의 불일치**(2026-08-05 `f6406b1`). 모델에 컬럼이 늘어도 `create_all`은 **이미 있는 테이블을 ALTER하지 않으므로**, 마이그레이션이 안 돈 DB에서는 그 테이블의 **모든 full-entity SELECT와 모든 ORM INSERT**가 실패한다 — 그런데 `/health`는 **정상 200**을 답한다(2026-08-05 하루에 3건, 전부 제품 소유자가 제품을 쓰다가 발견). 이 축의 관측 지점은 **`--preflight-only`의 배너와 기동 로그뿐**이고, 폴링으로는 절대 안 잡힌다. 계약은 [backend §1.3 ①-ter](../architecture/backend.md).

---

## 7. 브라우저는 즉시 따라오지 않는다

`client2/dist/`가 git에 올라가므로 코드 롤백은 **브라우저 번들도 함께 되돌린다.** 그런데 이미 페이지를 열어 둔 사용자는 **옛(=롤백 직전) 번들을 들고 있다.**

번들 파일명에는 내용 해시가 박힌다(`main-ZMT8OkhI.js`). 롤백으로 해시가 바뀌면, 열려 있던 탭이 요청하는 파일은 **더 이상 존재하지 않는다.**

**실측** (드릴 서버):

```
GET /assets/main-ZMT8OkhI.js   -> 200 text/javascript      (현재 번들)
GET /assets/main-OLDHASH1.js   -> 404 application/json     (없는 해시)
GET /                          -> 200 text/html
```

`/assets`는 `StaticFiles` 마운트라 **진짜 404**를 낸다(정적 catch-all의 HTML 200 함정에 걸리지 않는다). 결과적으로 **탭이 조용히 오작동하지는 않고, 대신 죽는다.**

**따라서**:

- **API 계약을 바꾸는 롤백이라면** 사용자에게 **새로고침(Ctrl+Shift+R)을 반드시 알려라.** 옛 번들은 새(=옛) 서버 계약과 맞지 않는다.
- 진행 중이던 편집은 **새로고침으로 날아간다.** 롤백을 알리고 잠깐 기다리는 편이 낫다.
- `admin.html`·`map_editor.html`은 `no-store`로 서빙되므로 새로고침 한 번이면 새 해시를 집는다. **루트 `index.html`에는 그 헤더가 없다** — 강제 새로고침이 필요할 수 있다. (⚠️ **[2026-08-11] `enrichment.html`은 삭제됐다** — 이 목록에서 제외. 남은 정적 페이지: `admin.html`·`map_editor.html`·`map_editor2.html`·`graph.html`·`trace.html`.)

---

## 8. 드릴 — 이 절차는 실제로 실행됐다 (2026-07-28)

운영이 아니라 **격리 스택**에서 돌렸다: 전용 데이터 루트(`ASSY_DATA_ROOT`), `assy_qa` 스냅샷 DB, API :8082, 그래프 :8092, 런처(`run_decoupled_app.py --server-only`)로 **5개 프로세스 전부** 기동.

**시나리오** — 계획 config의 바인딩 키를 새 형태로 바꾸고 그 형태만 읽는 코드를 함께 배포(비하위호환), 동시에 `table_config.json`에 테이블 1개 + 기존 테이블 컬럼 1개 추가. 그다음 되돌렸다.

| 단계 | 결과 | 실측 |
|---|---|---|
| 코드 파일만 v2로 교체 | API는 **여전히 v1** 서빙 | — |
| 런처 통째 재기동 | v2 코드 발효 | **5.7초** (정지 2.5 + 기동 3.2) |
| v2 코드 + v1 config | `target_map` 비어 있음 — **전진 배포의 창** | 창 지속 42초(내 조작 속도) |
| 계획 config → v2 | 정상 | **0.14초** 만에 반영 |
| `table_config` → v2 | `CREATE TABLE` + `ALTER TABLE` 실행 | 제자리 쓰기 후 **약 5초** |
| **잘못된 순서**: 코드만 되돌리고 재기동 | `target_map: {}` — **여전히 깨짐**. `/health`는 `ok` | 5.7초 |
| 이어서 config 되돌리기 | 즉시 복구, **재기동 불필요** | **0.01초** |
| **올바른 순서** 전 구간 | 증거 8초 → config 10초 → 코드 0초 → 재기동 11초 | **총 30초** |
| 사용자 체감 장애(폴링 관측) | 응답 저하 13초 + 연결 거부 3초 | **16초** |
| 롤백 후 검증 | `target_map.table` 복귀, `/health` ok | — |
| 잔여물 | 테이블·컬럼 **둘 다 그대로 남음** → 리포트가 검출 | — |
| 잔여물 제거 문장 실행 | 검출 → 제거 → 재검출 깨끗 | — |

**폴링으로 본 롤백 타임라인** (0.25초 간격):

```
00:32:38  200  target_table='dt_map'  shape=v2     ← 나쁜 버전이 정상 동작 중
00:33:00  200  target_table=None      shape=v2     ← config 되돌림 (v2 코드가 v1 config를 못 읽음)
00:33:13  연결 거부                                 ← 재기동
00:33:16  200  target_table='dt_map'  shape=v1     ← 복구 완료
```

00:33:00→00:33:13의 13초는 **내가 코드를 되돌리고 재기동 명령을 치는 데 걸린 시간**이다. 재기동 명령을 **미리 준비해 두면** 이 구간은 재기동 자체(약 6초)로 줄어든다.

### 이 문서에서 **드릴로 실행되지 않은** 부분 (추론으로 쓴 것)

정직하게 구분한다.

| 항목 | 상태 |
|---|---|
| `git checkout <sha> -- <경로>` / `git revert` **커밋 객체** 조작 | ❌ **미실행.** 드릴은 작업 트리 편집 후 `git checkout -- <파일>`로 파일을 복원했다. 파일 복원의 효과는 동일하나 **커밋 이력을 다루는 부분은 검증되지 않았다** |
| `client2/dist/` 롤백에 따른 **실제 해시 변경** | ❌ **부분.** 없는 해시가 404를 낸다는 것만 실측했다. 실제 롤백으로 해시가 바뀌는 왕복은 안 했다(map-pm이 `client2/**`를 동시 작업 중이라 접근 금지) |
| `ASSY_ADMIN_TOKEN` 부분 재기동 → `/internal` 401 | ⚠️ **절반 실측 (2026-07-28).** **토큰 상속은 실측됐다** — 토큰을 설정하고 런처를 통째로 재기동한 결과, `/internal/events/*` 4개 라우트 전부 토큰 없이 **401**, 워커 4종은 정상 하트비트, 아웃박스 pending 0, 워커 로그에 `401` 없음. 즉 `os.environ.copy()` 상속 경로는 동작한다. **아직 미실측인 것은 "부분" 재기동** — 워커만 옛 토큰을 든 채 남겨 401을 유발하는 시나리오는 재현하지 않았다 |
| `table_config.json.bak.<ts>` 백업에서의 복원 | ⚠️ **동등물로 실행.** 드릴은 같은 형식의 사전 사본에서 **제자리 복사**로 복원했다. `install_product_tables.py`가 만든 백업 파일 자체를 쓰지는 않았다 |
| C3 주간 config 스냅샷에서의 복원 | ✅ **실행됨 (2026-07-28, 별도 드릴).** 격리 스택에서 스냅샷 → config 파손 → 복원 → **옛 동작 서빙 확인**까지 왕복. 계획 계열 0.17초 / `table_config` 0.33초. 디바운스 함정도 이 드릴에서 나왔다(단계 2) |
| C3 PostgreSQL 백업에서의 복원 | ❌ **미실행 — DB 백업은 아직 없다.** config만 해결됐다. [PRODUCTION_READINESS C3](../process/PRODUCTION_READINESS.md) |
| 운영 환경에서의 실행 | ❌ **의도적으로 안 함.** 운영은 읽기 전용이었다 |

### 드릴이 드러낸 인접 사실 2건

- **유령 워커**: 어제 격리 세션에서 남은 워커 5개가 아직 떠 있었고, 그중 하나가 :8091을 점유해 드릴의 그래프 워커가 6회 연속 실패 → `FAILED` 확정됐다. 감시자·박동 판정은 **설계대로** 이것을 `foreign_beat`으로 잡아냈다. 드릴은 이들을 **죽이지 않고** 전용 포트·전용 데이터 루트로 비켜 갔다.
- **`[Schema Sync]`는 로그 파일에 없다**: 런처가 자식 stdout을 리다이렉트하지 않아, `ALTER TABLE` 문장은 콘솔에만 뜬다. `server.log`에는 어느 컬럼인지 없는 `Physical database schema synced successfully.` 한 줄만 남는다.

---

## 9. 사전 준비 — 롤백을 30초짜리로 만드는 것들

배포 **전에** 해 두면 새벽 2시가 짧아진다.

- [ ] 배포 직전 config 전체를 복사해 둔다 (`server/config/*.json` → 타임스탬프 디렉터리).
- [ ] 되돌아갈 커밋 SHA를 적어 둔다 (`git rev-parse HEAD`).
- [ ] **이번 배포가 config를 건드리는가**를 명시적으로 답한다. 답이 "예"면 롤백 목록에 config가 들어간다.
- [ ] **새 코드가 옛 config를 읽을 수 있는가**를 답한다. 답이 "아니오"면 창이 생긴다 — 콜드 배포를 검토하라.
- [ ] `table_config.json`을 건드린다면 **되돌려도 스키마는 남는다**는 것을 미리 인지한다.
- [ ] 재기동 명령을 **미리 터미널에 준비**해 둔다(붙여넣기만 하면 되게).
- [ ] **위험한 변경이면 손으로 스냅샷 하나 더 뜬다** — `backup_config.py snapshot`. 주간 주기를 기다리지 마라(같은 날 두 번은 글자가 붙어 안전하다, §3.1-bis).
- [ ] `backup_config.py check`가 `ok`인지 본다 — 오래됐으면 배포 전에 지금 하나 뜬다.
