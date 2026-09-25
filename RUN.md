# 지금 돌리면 되는 것

> ## 🔴 [09-25 밤 5] **소급 연산 «전부» 페이지 사이에서 취소 — ledger_rescope · enrichment_confirm 도 · 마이그레이션 «없음» · 재기동 API**
>
> ```
> 무엇     원장 재번역(rescope)은 범위를 1,000 행 페이지로 — 한 페이지의 걷어냄 + 다시 번역이 한 커밋, 묶음은 안 가름
>          강화 확정(confirm)은 큐를 1,000 개 페이지로 — 한 쓸기는 여전히 거래 id 하나
>          소급 카드 일곱이 모두 취소를 받음. 실행은 자식 프로세스가 매번 새로 떠서 새 코드를 읽음 — 카드(× 버튼)만 API 재기동
> 확인     Retroactive 탭에서 두 연산 중 하나를 긴 범위로 -> 도는 중 × -> 다음 페이지 경계에서 cancelled
> 답의 뜻   cancelled · 결과의 행 수 = 끝난 페이지의 행      정상 — 끝난 페이지는 온전, 나머지는 손 안 댐
>          × 가 안 보임                               API 가 옛 코드 (재기동 안 먹음)
>          누르고 한 페이지 더 돈 뒤 멈춤               정상 — 취소는 «다음» 경계에서 읽힘
>          다시 돌리면                               rescope 는 처음부터(이미 한 페이지는 deduped), confirm 은 남은 큐
> 되돌리기  git revert. 쓰는 모양 · 쓰는 값은 같고 «나눠서» 쓸 뿐
> ```

---

> ## 🔴 [09-25 밤 4] **「지금 도는 것」 한 문 — 대기열 응답에 now_running · 마이그레이션 «없음» · 재기동 API**
>
> ```
> 무엇     /admin/chain/queue 가 now_running 을 싣는다 — 체인 규칙 · 소급 실행 · 수집기 · 파일 적재, 한 모양
>          옛 running(체인 규칙만)은 화면이 now_running 을 읽을 때까지 그대로
> 확인     server 에서 (API 를 거치지 않고 같은 함수를 부름 — 파일 적재는 API 메모리에만 있어 여기선 안 보임)
> ```
> ```bash
> python -c "import main; from database.database import SessionLocal as S; print(main.get_chain_queue_depth(db=S())['now_running'])"
> ```
> ```
> 답의 뜻   []                                   지금 도는 것 없음
>          where=own_process · cancel={run_id}   소급 실행이 자기 프로세스에서 돎 — 화면 취소가 닿음
>          where=chain_worker · cancel={run_id}  체인 리플레이 (체인 워커 안)
>          where=scheduler                       수집기가 돎 (취소 문 없음)
>          where=chain_worker · cancel=null      체인 규칙 — 워커가 따로 돌면 lap 이 찍힌 순간에만 보임(짧은 규칙은 거의 안 잡힘)
>          KeyError 'now_running'                옛 코드 — git pull 안 됨
> 되돌리기  두 커밋에 걸쳐 있음 — 새 파일 둘은 다른 커밋에 먼저 실렸다. 한 줄로:
>          git revert d6f4b8bcc && git rm server/runtime/running.py server/tests/test_what_is_running_is_one_seat.py
>          쓰는 것 없음 — 응답에 칸 하나가 는 것뿐
> ```

---

> ## 🔴 [09-25 밤 3] **실패 재시도: 행이 지워진 줄은 «끝냄», 한 것이 없으면 refused · 「언제부터 실패」 는 마지막 실패 시각 — 마이그레이션 «없음» · 재기동 API 만**
>
> ```
> 확인     어드민 Chain 탭 실패 목록에서 Retry All
> 토스트    「Reset N failed event(s) to PENDING. …」 로 시작   -> 새 코드 (N 은 PENDING 으로 되돌린 줄 수)
>          「Ended N row event(s) whose row no longer exists」 -> 행이 지워진 줄 N 개를 끝냄 — 실패 목록에서 빠지고 payload 에 cancelled_by=retry · 사유
>          「Successfully reset …」 · 「Skipped … whose row …」 -> API 가 옛 코드 (재기동 안 먹음)
> 곁       끝낸 줄은 SUCCESS 라 통지 스윕이 그 표를 한 번 새로고침함 (triage 취소와 같음) — 결함 아님
> 되돌리기  git revert 하고 API 재기동. 끝낸 줄은 FAILED 로 안 돌아옴 — 행이 없어 다시 돌릴 것도 없음 · 7 일 청소가 지움
> ```

---

> ## 🔴 [09-25 밤 2] **어드민 소급이 자기 프로세스로 돕니다 — 마이그레이션 «없음» · 재기동 «필요» (런처까지)**
>
> 소유자 「어드민에서 백필도 별도 프로세스로 · 대기열만 잘 떠서 제어할 수 있으면 됨」 (bfbe8a525).
> 스케줄러가 집은 소급은 `python -m admin.retroactive_run <run_id>` 자식에서 돕니다. 체인 리플레이는 체인 워커 그대로.
>
> ```
> ① 마이그레이션   없습니다
> ② config        안 건드립니다
> ③ 재기동        스케줄러 · 체인 워커 · API (프로세스를 내리면 감독자가 새 코드로 띄움)
> ④ 확인          어드민 Retroactive 에서 아무 소급 하나 (쓰는 것 없는 값으로: 예 withdraw · 표 아무것 · 없는 source 이름)
> ```
>
> ### 확인 — 답이 «무엇을 뜻하나»
>
> ```
> 실행 목록의 그 줄 runner 가 retroactive/<호스트>/<pid> 이고 그 pid 가 스케줄러 pid 와 다름   -> 자식에서 돎
>    runner 가 scheduler/…     스케줄러가 옛 코드입니다 (재기동 안 먹음)
> auto_update.log 「[Retroactive] run_id=… runs in its own process pid=…」 한 줄
> retroactive.log                 자식의 START / DONE 줄 · 자식이 죽었으면 retroactive_stdout.log 에 traceback
> 둘을 연달아 누르면              둘째는 queued 로 기다렸다가 첫째가 끝난 뒤 뜸 (동시에 running 둘 = 결함)
> 도는 중 Cancel                  다음 페이지에서 멈추고 cancelled
> 자식이 강제로 죽었으면          기록이 cancel_requested / running 으로 남고 약 60 초 뒤 「주인 없음」 -> Cancel 한 번에 failed 로 풀림
> ```
>
> ### 되돌릴 수 있나
>
> ```
> 끄는 스위치는 없습니다. 코드: git revert bfbe8a525 하고 재기동 — 스케줄러가 다시 자기 스레드에서 돌림
> 지우는 것 없음 · 소급이 쓰는 일은 전과 같고 도는 «프로세스»만 다릅니다
> ```

---

> ## 🔴 [09-25 밤] **CLI 의 쓰기가 어드민 소급과 같은 기록 · 관문 · 취소로 + 실패 요약은 화면 zone 의 날 — 마이그레이션 «없음» · 재기동 «필요»**
>
> 소유자 「내가 백필을 따로 둔 이유가 대형 작업을 별도 프로세스로」. 일은 CLI 자기 프로세스에서 돌고, 기록 · 관문 · 취소 · 끝맺기는
> 어드민 소급과 같은 것을 지납니다 (9ca3633f1). 실패 목록은 표 · 종류 · 날 한 줄 요약을 싣고, 날은 화면이 보낸 zone 의 날입니다 (29711cace).
>
> ```
> ① 마이그레이션   없습니다
> ② config        안 건드립니다
> ③ 재기동        스케줄러 · 체인 워커 · API 셋 다 (프로세스를 내리면 감독자가 새 코드로 띄움)
> ④ 확인 한 번     원자를 안 쓰는 0 페이지 실행 — 소스 이름은 그 설치의 원장 소스
> ```
> ```bash
> python -m ledger.backfill --source lot_event --max-batches 0
> ```
>
> ### 확인 — 답이 «무엇을 뜻하나»
>
> ```
> 어드민 Retroactive 실행 목록에 ledger_backfill 한 줄 (done) · runner 가 cli/<호스트>/<pid>
>    안 뜨면   CLI 가 옛 코드이거나 문을 안 지났습니다
> 「REFUSED: run_id=… held by …」   다른 소급이 도는 중 — 관문이 CLI 도 막는 것이 정상입니다. 끝나거나 화면에서 취소한 뒤 다시
> 마지막 줄이 KeyError 'not_yet'    이 변경 «전부터» 있던 출력 줄 결함입니다 (보고함). 실행은 이미 done 으로 적혀 있습니다
> /health 의 cli 줄 off_roster      CLI 가 한 번 돌았다는 표시입니다. 경보 아님 — 끝난 뒤에도 남습니다
> CLI 를 강제로 죽였으면            60 초 뒤 실행 목록의 그 줄에서 Cancel -> 잠금이 풀립니다 (failed 로 적힘)
> ```
>
> ### 되돌릴 수 있나
>
> ```
> 끄는 스위치는 없습니다. 코드: git revert 9ca3633f1 29711cace e8d2f7519 (새것부터) 하고 재기동
> 지우는 것 없음 · 쓰는 모양이 바뀐 것 없음 — CLI 가 쓰는 일은 전과 같고, 실행 기록 한 줄씩이 더 남습니다
> ```

---

> ## 🔴 [09-25 저녁] **대기열 — 끝난 줄이 제 상태로 빠집니다 · 체인 대기열이 워커를 봅니다 — 마이그레이션 «없음» · 재기동 «필요» · 한 번 도는 명령 «하나»**
>
> 소유자 「ㄴ 으로」 · 「같은 문하고 옛 줄 치워」. 스케줄러가 줄을 뺄 때 상태와 시각을 같이 찍고(c28ab7ad9),
> 체인 대기열이 따로 도는 체인 워커를 그 워커의 heartbeat 로 봅니다(191c0b54a).
>
> ```
> ① 마이그레이션   없습니다
> ② config        안 건드립니다
> ③ 재기동        스케줄러 · 체인 워커 · API 셋 다 (run_app.bat 은 떠 있으면 아무것도 안 합니다 — 프로세스를 내리면 감독자가 새 코드로 띄움)
>                확인: /health 의 workers.chain.pid 와 workers.scheduler.pid 가 바뀌었나
> ④ 한 번         재기동 «뒤»에 옛 줄을 치웁니다 — 먼저 드라이런, 수를 보고 나서 --apply
> ```
> ```bash
> python scripts/outbox_triage.py --finish-stranded
> ```
> ```bash
> python scripts/outbox_triage.py --finish-stranded --apply
> ```
>
> ### 확인 — 답이 «무엇을 뜻하나»
>
> ```
> ④ 드라이런   「finished but PENDING: N」 과 종류별 줄 — 스케줄러가 예전에 상태 없이 빼 둔 줄입니다
>             N 이 0   치울 것이 없습니다. --apply 를 안 돌려도 됩니다
>             N > 0    --apply 가 그 N 줄을 SUCCESS + 지금 시각으로 찍고, 알림 청소가 곧 가져갑니다 (이 박스: 24 줄, 몇 초 안에)
> ⑤ 어드민 Chain 대기열 머리   「Loop Unknown · Mapper never reloaded · No loop in this process」 가 «안» 나와야 합니다
>             나오면   체인 워커가 옛 코드이거나(재기동 안 먹음) 워커 heartbeat 가 60 초 넘게 멎었습니다
>             Log 줄은 체인 워커의 로그 이름(chain_worker.log)입니다 — API 의 server.log 가 아닙니다
> ```
>
> ### 되돌릴 수 있나
>
> ```
> ④ --apply 는 «되돌릴 수 없습니다» — 그 줄들의 PENDING 이 SUCCESS 로 바뀌고, 처리 시각은 «이 명령을 돌린 때»입니다
>    (실제로 끝난 시각은 처음부터 안 적혀 있었습니다). 지우는 것은 없습니다. 그 줄들은 7일 청소로 원래대로 사라집니다
> 코드  git revert 00c0bad6a 191c0b54a c28ab7ad9  (새것부터) 하고 재기동
> ```

---

> ## 🔴 [09-25 오후] **원장 소스는 «뷰»를 안 읽습니다 + 그리드에 Ledger 열 — 마이그레이션 «없음» · 소급 «없음» · 재기동 «필요»**
>
> 소유자 「소급은 하지 말고 그냥 걷어내 · 운영에서는 뷰 안 써」. 원장 소스는 `row_id` 가 있는 «표»만 읽습니다.
> 뷰를 읽는 소스는 로드 때 «그 소스 하나만» 빠지고 나머지는 섭니다.
>
> ```
> ① 마이그레이션   없습니다. 소급도 없습니다 — 이미 뷰 소스로 들어간 원자는 그대로 둡니다
> ② config        제품은 안 건드립니다
> ③ 재기동        API 와 워커 둘 다. 메인 그리드는 새로고침 — 새 번들 main-DWdsueZG.js
> ```
>
> ### 확인 — 답이 «무엇을 뜻하나»
>
> ```
> ㉠ 재기동 뒤 로그에서 이 두 줄이 «0 줄»이어야 합니다
>      ERROR [Ledger] source <이름> is NOT planned: bundle.sources.<이름>.relation source '<이름>' reads '<관계>',
>        which is not a table that has row_id (view); a ledger source must read a table that has row_id
>      ERROR [Ledger] <이름> is NOT read: ...
>    있으면   그 소스가 뷰를 읽고 있습니다. 그 소스 «하나만» 빠졌고 나머지는 섭니다
>            고치려면 그 소스의 relation 을 row_id 가 있는 표로 (소유자 config)
>    🔴 소스가 «전부» 거절되면 원장 전체가 서지 않습니다 — 「every declared source was refused, so nothing would be read」
> ㉡ 메인 그리드 열 목록 «맨 끝»의 Ledger 칸
>      소스 이름   그 소스가 이 행을 원장에 올렸습니다
>      Not yet    아직 안 올렸습니다 — 원장이 따라오면 이름으로 바뀝니다
>      Refused    이 표를 읽는 소스가 «전부» 로더에서 거절됐습니다 — 사유는 ㉠ 의 줄
>      Unknown    소스인지 · 올라갔는지 알 수 없습니다 (선언이나 색인을 못 읽음)
>    원장 소스가 아닌 표에는 Ledger 열이 없습니다
> ```
>
> ### 급할 때 끄는 스위치
>
> ```
> 토글이 없습니다 — 갈래를 «지운» 것이라 켜고 끌 축이 없습니다
> 되돌리려면  git revert 8def5f28e 2fbe12b3f 9653f3e6b c193986a8  하고 재기동 + 그리드 새로고침
>            임시 복제본에서 쟀습니다: 새것부터 · 옛것부터 둘 다 충돌 0
> ```

---

> ## 🔴 [09-25] **조인 선언의 `on` 이 «원천»으로 — 배포 직후 옛 모양 조인은 거절됩니다 · Chain 탭에서 조인마다 버튼 한 번**
>
> 소유자 「붙일 값을 고쳐야 트리거 시켜서 그걸 붙이지」. 조인도 mapper·decide 와 같은 문장입니다 —
> `on` = 값이 바뀌는 표(원천), `into` = 붙는 표. `derive.join.right_table` 은 없어졌습니다.
>
> ```
> ① 마이그레이션   없습니다
> ② config        제품은 안 건드립니다. 다만 derive.join.right_table 이 적힌 조인은 재기동 «직후» 거절됩니다
>                 (그 규칙 하나만 빠지고 나머지 규칙은 섭니다)
> ③ 재기동        API 와 체인 워커 둘 다 (API: 선언창 · 변환 문 / 워커: 로더). 어드민은 새로고침 — 새 번들
> ④ 할 일         재기동 «바로 뒤», 조인마다:
>                   Chain 탭 → 그 조인 열기 → 「To new join shape」 한 번 → 확인창에서 확인
>                 재기동과 ④ «사이»에 원천 표를 고쳤다면, 변환 뒤 원천 표 그리드에서 «선언 이름»으로 소급 한 번
>                   (거절된 동안의 수정은 into 표에 안 붙었습니다 — 소급이 붙입니다)
> ```
>
> ### 거절 문장 — 체인 워커 로그 `ERROR [ChainRules] …`
>
> ```
> <이름>: derive.join.right_table is retired - on names the table whose value changes.
>   Set on.table to "<원천>" and delete right_table (the Chain tab's convert does both)
>    뜻   옛 모양입니다 — ④ 의 버튼 한 번이 두 칸을 다 고칩니다
> <이름>: a join needs on.table - the table whose value changes
>    뜻   on 이 비었습니다 — 원천 표 이름을 on.table 에
> ```
>
> ### 확인 — 답이 «무엇을 뜻하나»
>
> ```
> ㉠ Chain 탭에서 조인을 열었을 때 변환 버튼의 글자
>    To new join shape   옛 모양입니다 — 누르십시오
>    To flat             이미 새 모양입니다. 🔴 누르지 마십시오 — 평면 규칙이 되고 :target 짝이 사라집니다
>    통합으로 · 평면으로   옛 번들입니다 — 새로고침
> ㉡ 체인 워커 부팅 줄 [ChainRules] set(N): 에 조인마다 «둘»
>      <이름>[decl,join] target_table=<붙는 표> trigger_table=<원천>
>      <이름>:target[decl,join] target_table=<붙는 표> trigger_table=<붙는 표>
>    하나뿐이면  짝이 없습니다 — on 과 into 가 같은 표면 정상, 아니면 「To flat」 으로 평면이 된 것입니다
>    없으면     거절된 것입니다 — 같은 로그의 ERROR [ChainRules] <이름>: 줄
> ㉢ 원천 행 하나의 값을 고치면 붙는 표의 같은 키 행이 그 값이 됩니다
> ```
>
> ### 급할 때 끄는 스위치
>
> ```
> 토글이 없습니다
> 되돌리려면  git revert 2a9d8e18c 7c94fdc65 f4300aa19 244d825dc  하고 재기동 — «이 순서로» (새것부터)
>            임시 복제본에서 쟀습니다: 이 넷을 새것부터 충돌 0 · (문서 커밋 뺀) 셋을 옛것부터 충돌 1
>            🔴 이미 변환한 조인은 옛 코드가 «거절하지 않고» 세웁니다 — 다만 원천을 모르는 채로
>               (엔진이 읽는 right_table 이 비어 있음 · 돌 때 무엇이 되는지는 안 쟀습니다)
>               되돌리면 변환한 조인마다 원문을 손으로: on.table <- 붙는 표 · derive.join.right_table <- 원천
> ```

---

> ## 🔴 [09-24 밤] **`enrichment_rules.json` 은퇴 — 마이그레이션 «없음» · 재기동 «필요» · 🔴 재기동 «전» 확인 하나**
>
> 인리치(결손 보정) 선언의 집이 «하나»가 됐습니다 — `server/config/chain_rules.json` 의 `derive: {kind: "decide"}`.
> 제품은 `server/config/enrichment_rules.json` 을 «어디서도» 읽지 않습니다. 다시 놓아도 아무 일도 안 일어납니다.
>
> ```
> ① 마이그레이션   없습니다
> ② 재기동        필요합니다 — 로더·소급·설정 보고가 바뀌었습니다 (위 09-23 절의 «먹는 방법» 그대로)
> ```
>
> ### 🔴 재기동 «전»에 — 이 설치에 `server/config/enrichment_rules.json` 이 있습니까
>
> ```
> 없다       할 일 없습니다. 이 박스가 그렇습니다 (소유자 박스엔 그 이름의 파일이 없고,
>           enrichment_rules2.json 은 제품이 원래 안 읽던 이름입니다)
> 있다       🔴 재기동하면 그 안의 규칙은 «오류 없이» 멈춥니다. 재기동 «전»에 규칙마다
>           chain_rules.json 의 "rules" 에 한 항목으로 옮기십시오:
>              source_table  -> "on":   {"table": ...}
>              derived_table -> "into": {"table": ...}
>              decision_key  -> "derive": {"kind": "decide", "decide": {"key": [...],
>              target_fields ->                                    "fields": [...],
>              나머지 칸(list_columns · aggregations · reference_views · auto_confirm · alignment)
>                             -> 같은 이름으로 "decide" 안에
>              enabled       -> 항목의 최상위
>           키 표: docs/guide/config/chain_rules.md §5-B-bis
> ```
>
> ### 확인 셋 — 답이 «무엇을 뜻하나»
>
> ```
> ㉠ 체인 워커 부팅 줄 [ChainRules] set(N): ... 에 옮긴 규칙이 «둘씩» 보여야 합니다
>      enrichment_dedup:<이름>[decl,decide] · enrichment_auto_confirm:<이름>[decl,decide]
>    없으면   그 선언이 거절된 것입니다 — 같은 로그의 ERROR [ChainRules] <이름>: ... 가 사유입니다
> ㉡ 어드민 설정 해석 보고의 Enrichment 칸 출처가 chain_rules.json 이어야 합니다
>    (전에는 enrichment_rules.json 을 들고, 그 파일이 없으면 「규칙이 하나도 없습니다」라고 말했습니다)
> ㉢ 소급(backfill) 이 규칙을 못 찾으면 이제 이렇게 말합니다:
>      rule '<이름>' is not declared in chain_rules.json; available rules: ...
>    뜻   그 이름의 derive.decide 선언이 없습니다. «파일이 없다»는 말은 더 이상 안 나옵니다
>    대신 rule '<이름>' cannot be looked up: chain_rules.json could not be read (...) 가 나오면
>    뜻   선언이 없는 게 아니라 chain_rules.json 이 «깨져» 있습니다 — 파일부터 고치십시오 (09-25 추가)
> ```
>
> ### 급할 때 끄는 스위치
>
> ```
> 토글이 없습니다 — 두 번째 문을 «지운» 것이라 켜고 끌 축이 없습니다
> 되돌리려면  이 착지 커밋을 git revert 하고 재기동
> ```

---

> ## 🔴 [09-23 저녁] **운영 장애 수리 — 마이그레이션 «없음» · config 변경 «없음» · 재기동 «필요»**
>
> 「선언은 섰고 체인은 돌았는데 행 추가만 안 되던」 것을 고쳤습니다.
> 판단키 한 칸이 비면 파생 행을 «안 만들고» 넘어가던 갈래를 지웠습니다.
>
> ```
> ① 마이그레이션   없습니다
> ② 소유자 config  안 건드렸습니다. 한 줄도 고치실 것 없습니다
> ③ 재기동        🔴 `run_app.bat` 은 «이미 떠 있으면 아무것도 안 합니다» (총괄 실측:
>                두 번 돌렸는데 다섯 프로세스 전부 옛 코드 그대로였습니다)
>                먹는 방법: 체인 워커 프로세스를 «내리면» 감독자가 새 코드로 띄웁니다
>                확인: `/health` 의 `workers.chain.pid` 가 «바뀌었나` · `restarts` 가 늘었나
>                🔴 체인 워커가 «옛 코드»로 돌고 있습니다 — 재기동 전에는 안 고쳐집니다
> ```
>
> ### 무엇이 달라지나 — 세 줄
>
> ```
> 전   판단키가 일부 빈 소스 행 -> 파생 행이 «안 생김». 경고는 로그에만
> 후   그 행도 파생됨. 정체성은 «표가 선언한 컴포짓키»로 지어집니다 (전과 같은 철자)
> ⚠️  빈 성분은 «키를 짓는 데»만 씁니다 — 기존 행의 «값을 덮지 않습니다»
> ```
>
> ### 🔵 소급 «없습니다» — 이미 있는 파생 행은 안 움직입니다
>
> ```
> 정체성 철자가 한 글자도 안 바뀌므로 옛 이름 행이 «두 벌»이 되는 일은 없습니다
> 새로 생기는 것은 «전에 거절당하던» 행뿐입니다
> ```
>
> ### 확인 셋 — 답이 «무엇을 뜻하나»까지
>
> ```
> ㉠ 재기동 뒤 체인 워커 로그에서 «이 줄이 더는 안 나와야» 합니다
>    server/chain_worker.log
>      「row(s) with a PARTIAL decision key were NOT derived」
>    나오면   재기동이 안 먹은 것입니다 (옛 프로세스가 살아 있습니다)
>    안 나오면 고쳐진 것입니다
>
> ㉡ 그리고 대신 이 줄의 «뒤 숫자»를 보십시오 — 같은 줄에 있습니다
>      「N source row(s) -> M unique decision key(s) upserted into '<표>'
>        (K of them on a PARTIAL decision key)」
>    K 가 «0보다 크면» 전에 버려지던 행이 지금 들어가고 있는 것입니다
>
> ㉢ 🔴 새로 생긴 줄 하나 — 이것이 나오면 «선언을 보셔야» 합니다
>      「N decision key(s) were NOT derived: every column that BUILDS the identity of
>        '<표>' is blank on them」
>    뜻   그 행들은 파생 표에서 «주소가 없습니다». 만들면 나중에 갱신도 회수도 못 합니다
>    할 일 그 표의 composite_key_source (없으면 business_key) 가 가리키는 «그 컬럼»이
>          소스에서 왜 비는지 보십시오. 코드가 대신 정해 줄 수 없는 자리입니다
> ```
>
> ### 급할 때 끄는 스위치
>
> ```
> 이 수리에는 토글이 없습니다 — 갈래를 «지운» 것이라 켜고 끌 축이 없습니다
> 되돌리려면  git revert 2b37dcbd  하고 재기동
> ⚠️ 되돌리면 「행 추가가 안 되는」 증상이 그대로 돌아옵니다
> ```
>
> ```
> 착지  2b37dcbd  (시험 포함 7 파일 · 회귀 309 통과 · 변이 증명 있음)
> ```

---

> ## [09-24 · 서버] 체인 스켈레톤이 목록은 «목록», 참거짓은 «체크박스»라고 말합니다 — `90b9f4437` · API 재기동 필요
>
> ```
> ① 마이그레이션   없습니다
> ② config        안 건드렸습니다
> ③ 재기동        API 프로세스 — 선언창의 모양(스켈레톤)은 API 가 «돌면서» 냅니다. 새로고침만으로는 안 바뀝니다
> ```
>
> ### Chain 탭에서 inventory_confirmed 의 on · take 가 어떻게 보이나 — 그 답의 뜻
>
> ```
> 빈 입력칸                 옛 번들입니다 — 아래 [09-24 · 화면] 의 ㉠ 부터
> [{"left":…}] 같은 글자     새 번들 · «옛 API» 입니다 — API 재기동 전
> 「접힘 · N」 목록           새 번들 · 새 API 입니다 — 눌러서 펴지고 「+」·「−」로 고칩니다 (aac2e1bac)
> key.unique 가 체크박스     새 API 입니다
> into 드롭다운에 table 만     새 API 입니다 (09-25) — read 가 보이면 옛 API, 재기동 전입니다
> ```
>
> ### 급할 때 끄는 스위치
>
> ```
> git revert 90b9f4437  -> API 재기동   목록이 다시 «글자»로 보입니다(값은 보이되 폼에서 못 고침)
> ```
>
> ## [09-24 · 화면] 체인 선언창의 목록이 «펴지고» 고쳐집니다 — 마이그레이션 없음 · 새 번들
>
> ```
> ① 마이그레이션   없습니다
> ② config        안 건드렸습니다
> ③ 돌릴 것        없습니다. 어드민 페이지를 «새로고침» 하십시오 — 번들 파일 이름이 바뀌었습니다
> ```
>
> ### 무엇이 달라지나
>
> ```
> 전   on · take 가 「접힘 · 2」 · 「접힘 · 3」 으로 그려지고 눌러도 안 펴졌습니다. 「+ pair」 도 무반응
> 후   누르면 펴지고, 항목을 고치고 · 「+」 로 더하고 · 「−」 로 뺄 수 있습니다
> 덤  「+」 뒤 「−」 로 원래대로 돌리면 초안이 안 남습니다 — 다음에 열어도 「복원」이 안 뜹니다
> ```
>
> ### 확인 — 답이 «무엇을 뜻하나»
>
> ```
> ㉠ 개발자도구 Network 에서 admin-*.js 의 «이름»을 보십시오
>    admin-WsUDTkwl.js  새 번들이 떴습니다
>    다른 이름    옛 번들이 캐시에 남았거나 배포가 안 된 것입니다 — 화면은 안 바뀝니다
> ㉡ Chain 탭 → inventory_confirmed → on 의 「접힘 · 2」 «한 번»
>    left · right 칸에 dt_job 이 보이면  고쳐진 것입니다
>    눌러도 안 펴지면                  옛 번들입니다 (㉠ 부터)
> ㉢ 같은 번들에 09-23 수리도 실려 있습니다 — 끝난 enrichment backfill 줄에
>    「not created - no decision key N」 같은 칩이 보이면 그 수만큼 «안 만든» 것입니다 (0 도 그대로)
> ㉣ 인리치 목록 아래 메모가 「Edit rules in the Chain tab (derive.decide)」 이면 은퇴한 파일 안내가 빠진 번들입니다
>    「server/config/enrichment_rules.json 수기 편집」 이 보이면 옛 번들 — 그 파일은 이제 아무도 안 읽습니다
> ```
>
> ### 급할 때 끄는 스위치
>
> ```
> 없습니다 — 화면이 «받는» 클릭만 늘었고 토글할 축이 없습니다
> 되돌리려면  git revert 4335f209c 2cdb1e74f aac2e1bac  하고 다시 배포 — 셋을 «이 순서로» (새것부터)
>            ⚠️ 옛것부터 돌리면 첫 단계에서 충돌합니다 — 임시 트리에서 둘 다 돌려 봤습니다:
>               옛것부터 충돌 파일 4 · 새것부터 0
>            되돌리면  목록이 다시 «안 펴집니다»(값은 원문 JSON 에서만) · 은퇴한 파일 안내 문장도 «다시» 나옵니다
> ```
