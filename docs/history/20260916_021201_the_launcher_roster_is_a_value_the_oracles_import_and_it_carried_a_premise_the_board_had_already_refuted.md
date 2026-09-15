# 런처의 자식 명부는 «오라클이 import 하는 값»이다 — 텍스트 창을 자르던 시험 다섯이 함수 하나를 읽고, 그 함수의 docstring 은 보드가 «18 분 전에 반증한» 전제를 그대로 옮겨 들었다 (S-255, 판정 406 전제 정정)

> **커밋:** `8c824a1e` — test(launcher): the roster is a value the oracles import, not text they window (S-255) → main 병합(총괄, `64f58a1c` 보드)
> **일자:** 2026-09-16 02:12
> **레인:** «워크트리 서브에이전트» — 등급 4 큐 항목을 야간 목표대로 에이전트에 맡김 → 착지 → 총괄 닫힘 `64f58a1c`(「main 에서 런처·감독·스키마·데스크톱 모집단 초록」)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 변이 여섯(커밋 본문, `launcher_specs.py` 스크래치 사본): 체인 spec 안 주석 삽입 · API spec 안 주석 삽입 → **초록** / `log_file=` 제거 · `heartbeat=` 제거 · `ASSY_CHAIN_WORKER=0` 제거 · 두 자식이 한 로그 파일 → **빨강**. 총괄 확인 「변이 여섯 기대대로」.

## ① 왜 — 주석 «한 줄»에 옳은 런처가 빨개졌다

오라클 둘이 `run_decoupled_app.py` 를 «텍스트»로 읽었다: 하나는 `ChildSpec(` 뒤 «420 자 창» 안에 `log_file=` 이 있나, 다른 하나는 `run_chain_worker.py` 의 «첫 언급» 줄에 `heartbeat="chain"` 이 있나. 2026-09-15 판정 406 ① 을 착지시키며 spec «안»에 주석을 넣자 둘 다 빨개졌다(`86016d10`, 같은 날 `f7f89ab9` 가 주석을 spec «밖»으로 옮겨 풀었다) — 런처는 옳았다. 값의 «텍스트 대리»가 상설이 금지한 모양이고, 그날 큐에 S-255 로 올라갔다.

## ② 변경 — 명부를 «몸통이 아무것도 안 만지는 모듈»로

```python
# server/runtime/launcher_specs.py — 새 파일
def child_specs(python_exe, server_dir, server_cmd, api_host, api_port):
    return [
        ChildSpec("Backend FastAPI Server", server_cmd, server_dir,
                  env={"DECOUPLED": "True", "ASSY_CHAIN_WORKER": "0"},
                  ports=(int(api_port),), port_host=api_host,
                  log_file=paths.log_path("server_stdout.log")),
        ChildSpec("File Ingestion Watcher", [python_exe, "run_watcher.py"], server_dir,
                  heartbeat="watcher", start_delay=2.0, log_file=paths.log_path("watcher_stdout.log")),
        ChildSpec("Chained Ingestion Worker", [python_exe, "run_chain_worker.py"], server_dir,
                  heartbeat="chain", log_file=paths.log_path("chain_worker_stdout.log")),
        ChildSpec("Auto Update Scheduler", [python_exe, "run_auto_update.py"], server_dir,
                  heartbeat="scheduler", log_file=paths.log_path("auto_update_stdout.log")),
    ]
# run_decoupled_app.py — main() 의 나머지 줄은 그대로, 데스크톱 자식은 여전히 main() 이 덧붙인다
specs = child_specs(python_exe, server_dir, server_cmd, api_host, api_port)
```
왜 런처 파일 «안»에 함수로 두지 않았나: `run_decoupled_app.py` 는 «import 하는 순간» 라이브 `launcher.log` 를 열고 루트 로거를 옮긴다(자기 시험들이 그래서 텍스트로 읽는다고 적어 뒀다) — 그리고 저장소 «루트»에 있어 어느 런타임 프로세스의 `sys.path` 에도 없다. 「대상이 import 가 안 되면 그것이 결함이다 → 재려는 것을 import 되는 모듈로 뺀다」(상설 2026-09-02)의 서버 판.
```python
# server/tests/test_duplicate_launcher.py — 텍스트가 «못 보던» 단언 하나가 덤으로
captures = [s.log_file for s in _launcher_roster()]
assert len(set(captures)) == len(captures), captures        # 두 자식이 «한 파일»에 tee 하면 자식별로 못 읽는다
```
오라클 «둘»을 고치러 갔는데 같은 파일을 자르던 형제 «셋»이 더 있었다(`..._declares_the_ports_its_children_bind` · `test_the_chain_loop_runs_in_its_own_process.py` 의 ChildSpec 슬라이스 둘) — 다섯이 전부 값을 읽는다. 부류에서 판정하고 «구성원을 센» 결과다.

## ③ 🔴 이 커밋이 옮겨 든 docstring 은 «보드가 이미 반증한» 전제를 들고 있다

01:54 보드 정정(`96c55f02`, `docs/process/PROJECT_STATUS.md` 「[02:1x 정정 — 제 주장 하나가 틀렸다]」): 총괄이 22:5x 에 「런처로 도는 운영은 체인 루프가 «둘»이고 그중 하나가 API 안」이라 적고 소유자께도 그렇게 말했는데, 리빙 문서 정비(`6c8d1d88`)가 코드로 반증했다 — `main.py` 의 startup 이 `DECOUPLED == "True"` 면 체인 워커 기동 «전»에 `return` 하고, 런처는 그 변수를 «이미» 넘기고 있었다. 즉 런처 운영에서 API 안 루프는 «없었다». 판정 406 ① 의 `ASSY_CHAIN_WORKER=0` 은 «둘째 명시 가드»이지 「그것으로 비로소 하나가 된」 것이 아니다. 판정의 «구조»(API 프로세스는 체인 루프를 안 돌린다)는 그대로 참이고, 틀린 것은 «전제의 실측»이었다 — 커밋 메시지의 「이전 상태」를 재지 않고 옮겼다. 부류: 「주석은 의도의 증거이지 동작의 증거가 아니다」의 커밋 메시지 판.

이 커밋(02:12)은 그 정정 «18 분 뒤»에 착지했고, 런처의 주석 블록을 `child_specs` 의 docstring 으로 «그대로» 옮겼다:
```
🔴 [판정 406] THE CHAIN LOOP RUNS IN ITS OWN PROCESS. ... without that, a launcher-run
deployment had TWO chain loops and one of them lived inside uvicorn ...
```
기록자 실측(이 커밋의 트리): `server/main.py` :497 `if os.getenv("DECOUPLED") == "True": ... return` 이 워처·체인 워커 기동 «앞»에 있다. 그러므로 새 모듈의 docstring 「without that ... had TWO chain loops」는 «착지 시점에 이미 거짓»이었다. 워크트리 에이전트는 보드를 읽지 않았고(입력이 큐 항목 하나였다), 총괄 닫힘 줄도 이 문장을 잡지 않았다. 코드는 옳고(`ASSY_CHAIN_WORKER=0` 은 둘째 가드로 유효), 낡은 것은 «왜»를 적은 산문이다.

## ④ 아키텍처 영향

- 런처의 «항상 뜨는 자식 넷»은 `runtime/launcher_specs.child_specs` 라는 «값»이다. 시험은 그 값을 import 하고, `run_decoupled_app.py` 는 그것을 «부른다».
- 「이 자식이 무엇을 선언하나」(`heartbeat` · `ports` · `log_file` · 판정 406 의 env)가 «한 자리»에 문서화돼 있다.
- 그대로인 것: `main()` 의 나머지 줄 전부 · 데스크톱 자식(server-only 가 아닐 때만 `main()` 이 덧붙임) · 런처 파일이 import 시 로그를 여는 성질.

## ⑤ 그때 남아 있던 것

- ③ 의 docstring — 반증된 전제가 «새 파일»에 산 채로 남았다. 보드의 정정은 보드에만 있고 코드 산문에는 닿지 않았다.
- `_launcher_roster()` 헬퍼가 «세 시험 파일»에 각자 있다(`test_duplicate_launcher` · `test_process_supervisor` 의 인라인 · `test_the_chain_loop_runs_in_its_own_process`) — 인자는 자리 표시자(`"::"`, `"18080"`)라 셋이 같은 값을 만들지만 철자는 셋이다.
- `run_decoupled_app.py` 자체는 여전히 import 하면 부작용이 있다 — 이 커밋은 그것을 고치지 않고 «명부만» 밖으로 냈다.

---
📎 이 항목의 수(변이 6 · 420 자)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다.
📎 판정 406 이 착지한 자리: `20260915_233809_the_launcher_stands_the_apis_chain_loop_down_and_the_off_switch_had_never_run.md`(그 항목의 「루프가 둘」 서술은 이 항목 ③ 의 보드 정정으로 읽을 것) · 정정의 정본: `docs/process/PROJECT_STATUS.md` 「[02:1x 정정 — 제 주장 하나가 틀렸다]」 · 「텍스트가 «대리»면 금지, «주어»면 밖」(상설 2026-09-03) · 「주석은 의도의 증거이지 동작의 증거가 아니다」(2026-09-04) · 「부류로 묶되 구성원은 센다」(2026-08-27).
