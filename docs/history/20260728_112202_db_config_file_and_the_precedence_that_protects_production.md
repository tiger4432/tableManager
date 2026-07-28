# DB 접속이 파일로 내려왔다 — 그리고 env가 파일을 이겨야만 하는 이유

> 커밋 `2728bd9` · 2026-07-28 11:22 · 도메인 Server(config·부팅 경로)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 운영 가이드: [database.md](../guide/config/database.md)
> 이 커밋은 H-fix 라운드의 문서 사이클(MAP_EDITOR_SPEC 6.0-ter 등)도 함께 실었다 — 이 항목은 **DB config 코드 절반**만 다룬다.
> 스위트 834 green (+14, `test_database_url_config.py`).

## 배경 — 코드에 박힌 접속 문자열은 현장에 배포할 수 없다

이 커밋 시점까지 DB 접속은 env `DATABASE_URL` 아니면 코드 하드코딩 기본값
(`postgresql://postgres:admin@localhost:5432/assy_manager`)이었다. 현장 배포에서
접속 정보를 바꾸려면 프로세스 5개의 기동 환경마다 env를 심어야 했다 — 사이트가
소유하는 config 파일(`server/config/database.json`)이 필요했다. 다른 config들이
이미 쓰는 방식 그대로: `.sample`을 저장소에 두고, 실파일은 현장이 만든다.

## 우선순위는 편의가 아니라 안전 속성이다

```python
# server/paths.py — resolve_database_url docstring
Precedence (do NOT reorder): env DATABASE_URL > config/database.json > default.
The env var MUST outrank the file: the isolated dev stack redirects its DB via
the env var, while `devenv.py bootstrap` copies the config tree - including a
production-pointing database.json - into the isolated root. If the file won,
an isolated stack would silently write to the production database.
```

`devenv.py bootstrap`은 config 트리를 통째로 격리 루트에 복사한다 — 운영을
가리키는 `database.json`까지 함께 온다. 격리 스택은 env로 DB를 돌려놓는 구조이므로,
파일이 env를 이기는 순간 격리 스택이 **조용히 운영 DB에 쓴다**. 그래서 이 순서는
테스트(`test_env_beats_config_file`)로 못 박혔고, 빈 env 값은 미설정으로 친다.

## 어디에 두는가 — stdlib 전용 resolver를 paths.py에

resolver를 `database/database.py`가 아니라 `paths.py`에 둔 이유는 소비자가 둘이기
때문이다. `process_supervisor.py`의 DB 도달성 프로브는 **sqlalchemy 자체가 import
불가능한 상태**(잘못된 배포 후)를 살아남아야 하는 코드다 — stdlib만 쓰는 paths에
resolver가 있어야 프로브와 엔진이 한 구현을 공유한다. `database.py`는 import 시점에
**한 번만** 읽는다. 접속 문자열은 hot-swap 대상이 아니므로 핫리로드를 일부러 만들지
않았다 — `database.json` 변경은 전 프로세스 재기동이다.

세부 결정 둘:

- **분리 필드는 `quote_plus`로 조립한다.** `p@ss:w%rd` 같은 특수문자 비밀번호가
  URL 조립에서 살아남는다. 완성 `url` 키가 있으면 그대로(verbatim) 쓴다.
- **깨진 파일은 ERROR 로그 후 다음 순위로 폴백한다.** 선택적 파일이 부팅을 죽여선
  안 되지만, 운영자의 접속 config를 **조용히** 무시하는 것은 엉뚱한 DB에 쓰고도
  모르는 길이다 — 그래서 무시할 때는 반드시 파일명을 박은 ERROR를 남겼다.

## 부팅 로그는 어느 소스가 이겼는지 말하되, 비밀번호는 말하지 않는다

`main.py` 부팅 시 `[db] url source=env|config file|default target=user:***@host/db`
한 줄이 남는다. 이 마스킹 작업 중 기존 결함 하나가 같이 잡혔다 —
`paths.describe()`가 env URL을 **원문 그대로**(비밀번호 포함) server.log에 찍고
있었다. 마스킹된 형태로 교체하고 테스트(`test_describe_masks_env_password`)로
고정했다.

## 그때 남아 있던 것

- 저장소에는 `.sample`만 있었다 — 실 `database.json`은 현장이 복사해 만드는
  파일이고, 이 커밋 시점의 라이브 스택은 여전히 env/기본값으로 돌고 있었다.
- 코드 기본값(`postgres:admin@localhost`)은 최종 폴백으로 그대로 남았다 —
  파일도 env도 없는 개발 장비의 무설정 기동을 위한 것이다.
- supervisor 프로브는 종전대로 "아무것도 설정 안 됨 = 프로브할 것 없음"이었다 —
  코드 기본값까지 프로브하도록 확장하지는 않았다(원래도 안 했다).
- 핫리로드가 없으므로, 파일을 고친 뒤 재기동 전까지는 다섯 프로세스가 종전 접속으로
  계속 돌았다 — sample의 `_comment`가 그 사실을 운영자에게 직접 말한다.
