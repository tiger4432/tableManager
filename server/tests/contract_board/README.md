# 체인 계약판 도구 (응용 C, 10-21 → 10-22)

시험이 아니다 — pytest 가 모으지 않는다(`test_*` 파일 없음). 박스 도구다: 경로 `C:/Users/kk980/...` 와 conda env
`assy_manager` 가 박혀 있다(`e2e_launch.py` · `run_board.py` · `board_db.py`). 결과 표는
`task/APPLICATION_CONTRACT_BOARD_WRITE.md`.

| 파일 | 하는 일 |
|---|---|
| `board_gen.py` | 통합 선언 스켈레톤의 축 × 길 × 칸 타입 × 죽임 자리를 짝 전부(greedy all-pairs) 88 사례로 · 사례마다 판 하나 · 오라클 · 쌍둥이 견주기. `--list` · `--check` · `--run <사례…>` · `--compare a b` |
| `board_fixed.py` | 판 하나 = 제품 런처(`run_decoupled_app.py`)를 스크래치 스키마 하나에 · 씨앗 · 가라앉힘 · 죽음 기다림 |
| `e2e_launch.py` · `rr_precreate.py` | 런처 · 스키마 · 제품 표 미리 만들기 · 운영자 명령(`cli`) · public 전후 대조 |
| `check_board.py` | 판의 끝 상태(대상 행 · 껍데기 · 같은 키 · 고아 층 · 치워 둔 것 · 타입) — 제품 프로세스 안에서 |
| `pkg/sitecustomize.py` · `pkg/mappers/` | 죽이는 자리 훅(`<flag>.arm` 이 있을 때만) · 읽기 셈 훅(`BOARD_READ_LOG`) · 판의 맵퍼 넷 |
| `run_board.py` · `board_db.py` | 버리는 DB 의 URL 을 database.json 에서 짓고 찍지 않음 · DB 만들기 · 지우기 · public 대조 |
| `scratch_pin.patch` | 판을 돌릴 워크트리의 `database.py` 를 `ASSY_SCRATCH_SCHEMA` 에 묶음 — 제품 엔진은 URL 의 search_path 를 버린다 |
| `final.py` · `classify.py` · `make_report.py` · `fill_after.py` | 결과 모으기 · 무리 가르기 · 표 쓰기 · 「착지 뒤」 칸 채우기 |
| `fetch_report.py` | «받기» 열 표 쓰기 — 판이 본 것으로 판정을 다시 낸다 |

```
git worktree add --detach C:/wt-app-board <해시> && git -C C:/wt-app-board apply server/tests/contract_board/scratch_pin.patch
BOARD_DB_NAME=<버리는 DB> python board_db.py create
BOARD_DB=<버리는 DB> BOARD_PORT0=19800 BOARD_SCRIPT=board_gen.py BOARD_WT=C:/wt-app-board BOARD_RUNS=<결과 폴더> \
  BOARD_OUT=<줄 파일> python run_board.py --run <사례 번호…>
BOARD_DB_NAME=<버리는 DB> python board_db.py drop
```

«받기» 열(지시 78eec1ec1, 10-22): 위 줄에 `BOARD_COLUMN=fetch` — 규칙 꼴 다섯 × 경로 × (자기 맵 · 잡 · 값 표 / 떠난 맵 · 키)
46 사례, 죽임 없음. 판마다 `BOARD_READ_LOG`(판 루트의 `reads.txt`)가 판 표 SELECT 를 단계로 적는다 — R `run_rule` 안 ·
W `hold_commit` 쥔 동안 · D 그 밖. R · W(대상 표 말고)가 빨강, 맵퍼 자신의 `sql()` 판은 «reads outside the fetch» 줄로.
카나리 ATTACH · ENTER 가 0 이면 «계기 고장». 결과 표는 `task/APPLICATION_CONTRACT_BOARD_FETCH.md`.

밟은 덫: 판을 둘 겹쳐 돌릴 때는 `BOARD_PORT0` · `BOARD_RUNS` 를 따로 · 같은 결과 폴더에 판 둘이면 서로 덮음 ·
`--check` 는 `PYTHONPATH=pkg` · 쌍둥이 견주기는 행마다 층 이름의 행 id 를 접는다(`same_run`).
