# server/notebooks

소유자 2026-09-12: 「파서·맵퍼 개발을 주피터 노트북처럼」 ·
「이름만 걸면 맵퍼/파서 입력 모양으로 df 를 주고, 자유폼으로 개발하다 되면 함수폼으로 발행」.

| 노트북 | 두 줄 |
|---|---|
| `mapper_workbench.ipynb` | 표 이름(또는 샘플 파일)을 적으면 운영이 맵퍼에 넘기는 모양 그대로 DataFrame 이 온다. 자유폼 셀에서 만들고, 발행 셀이 `@mapper` 함수 파일을 만든다. |
| `parser_workbench.ipynb` | 파일 경로를 적으면 그 파일이 온다. 읽기·가공을 자유폼 셀에 쓰고, 발행 셀이 `BasePipelineParser` 파일을 만든다. |

## 🔴 규칙 하나 — 노트북은 운영 코드를 «부른다»

셀이 다시 구현하는 것은 «없다». 입력·클레임 훑기·세 단계 분리·발행 대조는 전부
`server/dev_bench.py` 의 함수이고, 그 함수들이 부르는 것은 `outbox_expand` ·
`mapper_sdk` · `pipeline_base` · `directory_watcher` — 운영이 부르는 그것들이다.
**여기서 되는 것이 운영에서 안 되면, 도구가 신뢰받는 바로 그 순간에 거짓말을 한 것이다.**

예외는 «자유폼» 셀 둘뿐이고, 그 셀이 사용자의 로직이라는 것이 이 도구의 요점이다 —
껍데기를 «안 씌우는» 것이 기능이다. `server/tests/test_the_workbench_notebooks_call_production.py`
가 그 경계를 «셀 태그»로 채점한다.

## 왜 `server/notebooks/` 인가

노트북 둘이 «같은» 모듈(`dev_bench`)을 부른다. 파서 것을 `parsers/` 밑에 두면 맵퍼 것과
갈라지고, 워크스페이스(`ingestion_workspace/`)에 두면 그 폴더가 통째로 gitignore 라 도구가
커밋되지 않는다. 뿌리 찾기는 셀이 «한다**(`server/dev_bench.py` 를 찾아 올라간다) — 이 박스의
절대경로는 어느 셀에도 없다.

## 여는 법

VS Code / Cursor 의 노트북 편집기, 커널 **conda `assy_manager`**.
이 박스에 `jupyter notebook` / `jupyterlab` 은 **없다**(`ipykernel` · `jupyter_client` 는 있다).
서버형으로 열려면 패키지를 새로 깔아야 하고 그건 소유자 판단이다.

🔴 **첫 셀이 `sys.executable` 을 찍는다.** env 가 아닌 python 으로 커널이 뜨면 `psycopg2` 가
없어 DB 셀이 조용히 못 연다 — 그 사고가 한 번 있었다.

## 명령줄로 같은 것을 하려면

`python scripts/try_core.py mapper|parser|folder ...` 가 **같은 `dev_bench` 함수**를 지난다.
두 껍데기가 각자 조립하면 「명령줄에서는 된다」와 「시험은 통과한다」가 다른 사실이 된다.
