# parsers/notebooks

**왜 여기인가:** 이 노트북이 «부르는» 코드(`pipeline_base.py` · `directory_watcher.py`)가 바로 옆에
있다 — 저장소 뿌리에 두면 부트스트랩이 경로 추측이 되고, 워크스페이스(`ingestion_workspace/`)에
두면 그 폴더가 통째로 gitignore라 도구가 커밋되지 않는다.

- `parser_workbench.ipynb` — 샘플 파일 하나로 `BasePipelineParser` 파서를 개발·검증·내보내기.
  초안 파서의 모양은 `../custom_parser.py.sample`(클래스형)을 그대로 따른다 — 예시가 둘로
  갈라지면 둘 다 낡는다. 함수형(`parse_file()`)은 다른 방식이고 `../custom_parser_template.py`다.

**여는 법:** VS Code/Cursor의 노트북 편집기 + 커널 `assy_manager`(conda). 이 박스에는
`jupyter notebook`/`jupyterlab`이 설치돼 있지 않다(`ipykernel`·`jupyter_client`는 있어서 IDE
편집기로는 그대로 돈다). 서버형으로 열려면 패키지를 새로 깔아야 하고, 그건 소유자 판단이다.

🔴 **규칙 하나:** 노트북은 운영 코드를 **부른다**. 읽기·정리·파서 탐색·컬럼 검사 중 어느 것도 다시
구현하지 않는다. 여기서 되는 것이 운영에서 안 되면, 도구가 신뢰받는 바로 그 순간에 거짓말을 한
것이다.
