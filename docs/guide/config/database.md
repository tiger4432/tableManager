# `database.json` 세팅 — DB 접속 정보 (이름·비번·호스트)

> **Status:** 🟢 Living | **Last-verified:** 2026-07-28 (신설) | **Owner:** Backend / Ops
> 상위: [폴더 인덱스](./README.md) · 배포 절차는 [DEPLOY_SETUP §1-1](../DEPLOY_SETUP.md) · 우선순위 규율은 [CONFIG_GUIDE §1](../CONFIG_GUIDE.md)

<!-- Loader evidence (2026-07-28):
  resolve: server/paths.py resolve_database_url (env DATABASE_URL > config/database.json > default; empty env = unset)
  compose: server/paths.py _database_url_from_config ('url' wins; split fields via urllib quote_plus;
    malformed/keyless file -> logger "paths" ERROR naming the file, then fall through)
  consume: server/database/database.py (read ONCE at import -> SQLALCHEMY_DATABASE_URL, DB_URL_SOURCE; no hot reload)
  boot log: server/main.py right after "[paths]" line -> "[db] url source=... target=<password masked>"
  launcher probe: server/process_supervisor.py _database_endpoint (same precedence, stdlib-only)
-->

## 1. 언제 이 파일을 만지는가

- **운영 DB의 이름·계정·비밀번호가 코드 기본값과 다를 때** — 기본값은 `postgresql://postgres:admin@localhost:5432/assy_manager`
- 환경변수 `DATABASE_URL` 없이 **파일로 접속 정보를 관리**하고 싶을 때 (운영자 친화 경로)
- **파일이 없어도 정상입니다** — 환경변수 또는 기본값으로 동작합니다.
- 🚨 **우선순위는 `DATABASE_URL` 환경변수 > 이 파일 > 코드 기본값**입니다. 환경변수가 걸린 프로세스에서 이 파일은 **무시**됩니다 — 격리 개발환경(devenv)이 환경변수로 DB를 갈아타는 안전장치이므로, 이 순서는 바꾸면 안 됩니다(`server/tests/test_database_url_config.py`가 고정).

## 2. 세팅 절차

1. **스냅샷**(파일이 이미 있을 때만 의미 있음): `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. `database.json.sample`을 `database.json`으로 복사합니다.
3. 두 방식 중 하나로 적습니다 — **둘 다 있으면 `url`이 이깁니다**:

   ```json
   { "url": "postgresql://<user>:<password>@<host>:5432/<db명>" }
   ```

   또는 분리 필드(특수문자 `@` `:` `%` 등은 자동 URL 인코딩되므로 그대로 적습니다):

   ```json
   {
     "host": "localhost",
     "port": 5432,
     "database": "assy_manager",
     "user": "postgres",
     "password": "p@ss:word"
   }
   ```

   분리 필드 생략 시 기본값: `host=localhost` · `port=5432` · `database=assy_manager` · `user=postgres` · password 없음.
4. **전 프로세스 재기동** — 커넥션 문자열은 핫스왑이 불가능하므로 핫리로드가 **없습니다**. 기동 시 1회만 읽습니다.

## 3. 반영 확인

기동 직후 `server.log`(각 프로세스 로그)의 `[db]` 줄에서 **어느 소스가 이겼는지**를 확인합니다:

```
[db] url source=config file target=postgresql://postgres:***@localhost:5432/assy_manager
```

- `source=config file` — 이 파일이 적용된 상태.
- `source=env` — 환경변수 `DATABASE_URL`이 걸려 있어 파일이 무시되는 중(격리 환경이면 정상).
- `source=default` — 파일이 없거나 **읽을 수 없어** 기본값으로 동작 중. 파일을 만들었는데 이게 보이면 §4.
- 비밀번호는 항상 `***`로 마스킹됩니다 — 로그에 원문 URL은 찍히지 않습니다.

이어서 `GET /tables`가 200으로 테이블 목록을 돌려주면 접속까지 성공입니다.

## 4. 잘못됐을 때

- **JSON이 깨졌거나 인식 키가 하나도 없으면** 기동은 계속되지만(선택 파일이 부팅을 죽이지 않음) ERROR 로그가 파일 경로를 지목하고 **다음 순위(기본값)로 넘어갑니다** — 즉 조용히 엉뚱한 DB를 보게 될 수 있으니, 파일을 만졌으면 반드시 §3의 `source=` 줄을 확인하십시오.
- 파일을 지우면 환경변수/기본값으로 복귀합니다(재기동 필요). 스냅샷 복원:

  ```bash
  conda run -n assy_manager python server/scripts/backup_config.py restore database_<yymmdd>.json.bak --yes
  ```

- **devenv 스냅샷 주의**: `devenv.py bootstrap`은 config 트리를 통째로 복사하므로 이 파일(운영 DB를 가리키는)이 격리 루트에도 복제될 수 있습니다. **무해합니다** — 격리 스택은 `DATABASE_URL` 환경변수로 기동되고 환경변수가 파일을 이깁니다. 이것이 §1의 우선순위를 바꾸면 안 되는 이유입니다.

## 5. 키 참조

| 키 | 타입 / 기본값 | 의미 |
|---|---|---|
| `url` | 문자열 | 완성된 접속 URL — 있으면 아래 필드 전부 무시 |
| `host` | 문자열, 기본 `localhost` | DB 호스트 |
| `port` | 숫자, 기본 `5432` | DB 포트 |
| `database` | 문자열, 기본 `assy_manager` | DB 이름 |
| `user` | 문자열, 기본 `postgres` | 접속 계정 (URL 인코딩 자동) |
| `password` | 문자열, 기본 없음 | 비밀번호 (URL 인코딩 자동) |

(`_`로 시작하는 `_*_doc`/`_comment`/`_split_example` 키는 sample의 주석용 — 코드가 읽지 않습니다.)
