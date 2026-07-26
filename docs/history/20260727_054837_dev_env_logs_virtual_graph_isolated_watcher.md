# 격리 환경의 구멍 둘 — 로그와 virtual graph가 새어 나가고 있었다 + 격리 워처 동사

> 커밋 `47c20f3` · 2026-07-27 05:48 · 도메인 Server / 개발환경·격리
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 선행: [격리 개발 환경](./20260727_000000_isolated_dev_environment.md)
> 관련 스펙: [DOE_STORAGE_MAP](../spec/DOE_STORAGE_MAP.md)(이 커밋에서 신설)

## 배경

격리 환경을 **처음 실제로 쓴 팀**이 구멍 둘을 찾았다. 설계 단계 검토가 아니라 사용이 찾았다는 점이 중요하다 —
`paths.py`는 `config/`와 `ingestion_workspace/`를 옮겼지만, **`__file__`에서 경로를 짓는 지점이 그 둘만은 아니었다.**

## 변경 내용

### 1) 로그가 격리를 벗어나 있었다

`utils/logger.py`가 자기 `__file__`에서 디렉터리를 지었다. 결과: **모든 격리 프로세스가 사용자의 live 로그에 append**했다.
실측 — `chain_worker.log`에 6줄, `server.log`에 207줄이 `assy_qa`에만 존재하는 트랜잭션 id를 달고 들어가 있었다.

인시던트를 재구성하려고 읽는 파일에 드릴의 줄이 섞이면, 그 파일은 증거로서 죽는다.

```python
# server/utils/logger.py — get_process_logger
# Routed through paths.py - the single ASSY_DATA_ROOT override point - so an
# isolated process cannot append to the user's live server/*.log. Unset,
# paths.DATA_ROOT is server/, i.e. production is byte-for-byte unchanged.
log_path = paths.log_path(log_filename)
```

import 순서 함정이 하나 있었다 — `utils/`는 엔트리포인트가 `server/`를 `sys.path`에 얹기 **전에** import될 수 있다
(`main.py`는 19행에서 `utils.logger`를, 34행에서 `import paths`를 한다). `database/crud.py`와 같은 방식으로 폴백했다.
**조용히 live 트리로 되돌아가는 대신** sys.path를 보정하고 다시 import한다.

### 2) 형제 지점을 훑다가 더 나쁜 것을 찾았다

`graph_sync_worker.py`가 `VIRTUAL_GRAPH_PATH`를 `__file__`에서 지었고, `save_virtual_graph()`는 **그 파일을 덮어쓴다.**
그리고 `run_graph_sync`는 `devenv`가 띄우는 프로세스 중 하나다 — 즉 격리 실행이
**사용자의 live virtual graph를 덮어썼을 것이다.**

```python
# server/graph_sync_worker.py
# Routed through paths.py like ONTOLOGY_PATH above: this file is *written*
# (save_virtual_graph), so an isolated graph worker building it from __file__
# would overwrite the user's live virtual graph.
VIRTUAL_GRAPH_PATH = os.path.abspath(os.path.join(paths.DATA_ROOT, "database", "virtual_graph.json"))
```

바로 한 줄 위에서 이미 `paths`를 쓰고 있었다. **읽는 경로는 옮겼고 쓰는 경로는 놓쳤다** —
훑기의 기준을 "`__file__`을 쓰는가"가 아니라 "**쓰기 대상인가**"로 잡아야 했다는 교훈.

### 3) `devenv watcher-up` / `watcher-down`

인제션 드릴마다 워처를 손으로 띄우고 있었다. 그리고 **운영을 가리킨 워처는 드릴 파일을 진짜 데이터로 인제션한다** —
이 설비 전체에서 단일 최악의 조작이다.

관문의 네 가지 성질이 이 파일의 설계다.

```python
# server/scripts/dev_env/iso_watcher.py
# 1. 관문은 순수 함수다 — check_static_isolation / check_live_isolation은 확정된 사실을 받아
#    위반 목록을 반환한다. 프로세스·커넥션·파일시스템 없이 "이 설정이면 거절되는가"를 물을 수 있다.
# 2. 로그·연결·파일을 여는 모든 것보다 먼저 돈다 — `import run_watcher`만으로도
#    로그 핸들러가 서고 DDL이 나가므로, 그 import는 두 관문이 통과한 뒤에만 일어난다.
# 3. live 검사는 방금 자기가 읽은 환경변수가 아니라 **실제로 연 세션**에 묻는다:
#    SessionLocal()에서 SELECT current_database().
# 4. 실패 모드는 "뜨지 않는다"다. 격리를 *증명할 수 없는 것* — 도달 불가 DB, 파싱 불가 URL — 도 거절이다.
```

세 번째가 특히 중요하다. `assy_qa`라고 적혀 있으나 실제로는 다른 곳으로 해석되는 URL은
환경변수를 다시 읽어서는 잡히지 않는다.

### 4) DOE 패널이 어디에 쓰는지 문서화 — `docs/spec/DOE_STORAGE_MAP.md`

사용자가 "`map_doe`는 안 쓰는 테이블 아니냐"고 물은 데서 나왔다. 답: **사용자 본인이 손으로 입력한 데이터가 들어 있다.**
테이블 드롭다운에 안 보이는 이유는 맵이 아니라 **계획 저장소**이기 때문이다.

패널 하나를 편집하면 **세 곳 + 맵 테이블**에 떨어진다.

| 테이블 | 무엇이 |
|---|---|
| `map_split_registry` | 값의 색·설명 |
| `map_doe` | 구간(band) 계획 |
| `map_doe_source` | 그 구간의 자재 |
| (맵 테이블 자신) | 칠해진 셀 |

이 지도가 다음 커밋의 DOE 삭제 수정에서 결정적으로 쓰였다.

### 5) 백업에 관한 준비도 체크리스트 정정

`config/`와 `ingestion_workspace/`가 gitignore인 것은 **실수가 아니라 의도**다 —
운영 서버를 패치하는 행위가 현장 자산을 오염시키지 못하게 하는 선이다.
문서에 그 이유와 함께 "커밋해서 '고치지' 말 것" 경고를 넣었다.

대가는 **git이 복구 경로가 아니라는 것**이고, 그것이 오늘 잃은 자산 두 개를 되살리지 못한 이유다.

## 아키텍처 영향

- `paths.py`의 관할이 `config/`·`ingestion_workspace/`에서 **프로세스 로그**까지 넓어졌다(`paths.log_path`).
  `ASSY_DATA_ROOT` 미설정 시 위치는 종전과 바이트 단위로 동일하다.
- 격리 워처가 **드릴의 표준 동사**가 됐다 — 에이전트마다 손으로 만들던 가장 위험한 단계가 사라졌다.

## 검증

- 운영 스택을 **띄운 채로** 측정 — 15초 동안 live 로그 5개가 바이트·mtime 동일한 반면 dev_env 로그는 생성됐다.
  이어서 live 크론을 가로지르는 4.5분 창에서 **같은 5개 파일이 249 KB 증가**했다 →
  계측기가 "무변화"라고 주장한 바로 그 파일들에서 깨어 있음이 증명된다.
  증가한 바이트 안에 `dev_env`·`assy_qa`·격리 포트 문자열은 **0건**.
- 관문의 거절 3종(각각 운영 벡터 하나씩 격리)이 **핸들러가 서기 전에** 종료함을 확인. 도달 불가 DB 포함.
- 스위트 **498 passed / 0 failed**.

## 다음 단계

- `__file__`에서 경로를 짓는 지점의 훑기는 **이번 두 건으로 끝났다는 보장이 없다.**
  이번에 찾은 기준(“쓰기 대상인가”)으로 재훑기를 한 범위가 어디까지였는지는 보고서에만 있다.
- gitignore된 자산의 복구 경로는 **여전히 없다.** 스냅샷/매니페스트는 계측 도구이지 백업이 아니다.
