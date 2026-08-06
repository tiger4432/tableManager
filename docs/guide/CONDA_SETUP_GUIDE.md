# 🚀 AssyManager 환경 세팅 가이드 (conda)

> **Status:** 🟢 Living | **Last-verified:** 2026-08-06 | **Owner:** Ops
> 🔴 **[2026-08-06 전면 재작성] 이 문서는 아카이브 후보였는데 아카이브하지 않았습니다 — 이유가 반대이기 때문입니다.**
> 종전 본문은 **제거된 PySide6 클라이언트 앱**(`client/main.py`)을 실행하라 지시하고, **SQLite 파일**(`server/assy_manager.db`)을 지우면 DB가 초기화된다 하고, `uvicorn main:app --reload`(포트 8000)을 기동 절차로 안내했습니다. **셋 다 오늘 거짓입니다.**
> 🔴 **트리거가 없어서 낡은 문서가 아니라, *가리켜지면서* 낡은 문서였습니다** — [SYSTEM_OVERVIEW §7](../overview/SYSTEM_OVERVIEW.md)(SSOT) · [CONFIG_GUIDE](./CONFIG_GUIDE.md) · [SERVER_STARTUP_GUIDE](./SERVER_STARTUP_GUIDE.md) · [docs/README](../README.md)가 운영자를 여기로 보냅니다. 아카이브했다면 **SSOT가 없는 문서를 가리키게** 됩니다. 그래서 재작성입니다.
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · **기동 절차의 정본은 SSOT §7**이고 이 문서는 **환경 구성**을 다룹니다.

---

## 1. 전제 조건

- [Miniconda](https://docs.anaconda.com/miniconda/) 또는 [Anaconda](https://www.anaconda.com/download) 설치.
- 터미널(PowerShell·CMD·Git Bash)에서 `conda`가 동작할 것.
- **PostgreSQL**이 필요합니다 → [NATIVE_POSTGRES_SETUP_GUIDE](./NATIVE_POSTGRES_SETUP_GUIDE.md). ⚠️ **이 프로젝트는 SQLite로 굴러가지 않습니다** — 테스트 스위트 일부가 SQLite로 돌 뿐이고, 개발·운영 저장소는 PostgreSQL입니다.

## 2. 환경 생성

저장소 루트에서:

```bash
conda env create -f environment.yml   # 환경 이름은 environment.yml의 `name:` — 현재 assy_manager
conda activate assy_manager
```

> 🔴 **모든 파이썬 실행은 이 환경에서 합니다.** 시스템 파이썬으로 돌리면 `psycopg2` 부재 등으로 **거짓 실패**가 납니다. 활성화하지 않고 한 번만 돌릴 때는 `conda run -n assy_manager python <파일>`.
> ⚠️ **Windows 콘솔은 cp949라 한글 출력에서 인코딩 에러가 납니다** — 앞에 `PYTHONIOENCODING=utf-8`을 붙이십시오.

환경 갱신(`environment.yml`이 바뀌었을 때):

```bash
conda env update -f environment.yml --prune
```

## 3. 무엇이 들어 있나

`environment.yml`이 정본이고 **여기에 목록을 다시 적지 않습니다**(사본은 반드시 낡습니다). 성격만 적으면:

| 무엇 | 왜 필요한가 |
|---|---|
| FastAPI · Uvicorn | 웹 API + WebSocket 허브(`server/main.py`) |
| SQLAlchemy · psycopg2 | ORM + PostgreSQL 드라이버 |
| Watchdog | 파일 인제션 워처 |
| **PySide6** | 🔴 **데스크톱 *셸*에 여전히 필요합니다.** `client/desktop_wrapper.py`가 QtWebEngine으로 웹앱을 감쌉니다 — **「PySide6는 제거됐다」로 읽지 마십시오.** 없어진 것은 Qt 위젯으로 그리던 **클라이언트 앱**입니다 |
| Node.js / npm | ⚠️ **conda 환경 밖입니다.** 웹 클라(`client2/`) 빌드에 별도로 필요합니다 |

## 4. 실행

**기동 절차의 정본은 [SYSTEM_OVERVIEW §7](../overview/SYSTEM_OVERVIEW.md)입니다.** 여기서는 환경 활성화 이후의 최소 형태만 적습니다.

```bash
# 전체 스택(웹서버 + 워처 + 체인 워커 + 그래프 싱크 + 스케줄러 + 데스크톱 셸)
python run_decoupled_app.py

# 데스크톱 셸 없이 서버만
python run_decoupled_app.py --server-only
```

- 🔴 **런처가 띄우는 웹서버 포트는 `8080`입니다**(`ASSY_API_PORT`). 브라우저에서 `http://127.0.0.1:8080`.
- ⚠️ **`uvicorn main:app --reload`를 기동 절차로 쓰지 마십시오.** 종전 이 문서가 그렇게 안내했습니다 — 그 형태는 **워커를 하나도 안 띄우고**(인제션·체인·그래프·스케줄러 전부 죽은 채) 포트도 uvicorn 기본 `8000`이라, 문서를 따라간 운영자가 `:8080`에서 아무 응답도 못 받습니다.
- 웹 클라 개발(핫리로드): `cd client2 && npm run dev` → `:5173`, API/WS는 `127.0.0.1:8080`으로 자동 타겟팅.

## 5. 확인

```bash
conda run -n assy_manager python -c "import fastapi, sqlalchemy, psycopg2; print('ok')"
curl http://127.0.0.1:8080/health
```

`/health`는 **체크 하나만 실패해도 설계상 503**입니다 — 상태코드가 아니라 **응답 BODY**(`status` + dict `checks`)로 판별하십시오([DEPLOY_SETUP §1-5](./DEPLOY_SETUP.md)).

## 6. 함정

- ⚠️ **DB 초기화는 파일 삭제가 아닙니다.** 종전 이 문서의 「`server/assy_manager.db`를 지우고 재시작하면 초기화된다」는 **SQLite 시절의 문장**이고 오늘 거짓입니다. 저장소는 PostgreSQL이고, 초기화·마이그레이션은 [NATIVE_POSTGRES_SETUP_GUIDE](./NATIVE_POSTGRES_SETUP_GUIDE.md)와 [POSTGRES_OPERATIONS_GUIDE](./POSTGRES_OPERATIONS_GUIDE.md)가 다룹니다.
- ⚠️ **`client/main.py`는 없습니다.** 종전 이 문서의 3단계가 그것을 실행하라 했습니다. 데스크톱은 `run_decoupled_app.py`가 자식으로 띄우는 `client/desktop_wrapper.py` 하나입니다.
- ⚠️ **환경변수는 프로세스가 태어날 때의 사본을 쥡니다.** 편집기(원격이면 `vscode-server`)가 변경 *전에* 떠 있었다면 그 안에서 연 터미널은 옛 환경을 물려받습니다 → [DEPLOY_SETUP §1-4-A](./DEPLOY_SETUP.md).

## 관련 문서

- 기동·프로세스 구성의 정본: [SYSTEM_OVERVIEW §2·§7](../overview/SYSTEM_OVERVIEW.md)
- PostgreSQL 설치: [NATIVE_POSTGRES_SETUP_GUIDE](./NATIVE_POSTGRES_SETUP_GUIDE.md) · 운영: [POSTGRES_OPERATIONS_GUIDE](./POSTGRES_OPERATIONS_GUIDE.md)
- 배포·토큰·프록시: [DEPLOY_SETUP](./DEPLOY_SETUP.md)
- 설정 파일 지도: [CONFIG_GUIDE](./CONFIG_GUIDE.md)
