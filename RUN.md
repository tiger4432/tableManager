# 지금 돌리면 되는 것

> ## [10-06] **엔티티 label — 노드가 키 대신 선언한 이름으로 보인다 · 선언 초안의 «다시 도는 소스»가 지문으로 (총괄 03bc94b6b) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 선언           원장 선언 entities.<타입> 에 "label": ["step", ...] — 그 타입의 키 또는 attributes 이름
>                없는 이름이면 저장 · 로드가 그 이름을 대어 거절(unknown_id, bundle.entities.<타입>.label)
> 재기동 뒤        걷기(표 · 그래프 · 사실 상자)에서 그 타입의 노드 이름이 적힌 순서대로 값을 「 · 」로 이은 것
>                값이 없는 이름은 빠지고, 하나도 없거나 label 을 안 적으면 오늘처럼 키(「 / 」)
>                소스 지문은 안 움직인다 — 커서 · 원장 소급 0
> 초안 비용        엔티티 · 술어 초안 저장 버튼 옆 「Sources N · …」 의 N = 활성과 초안 사이에 커서 지문이 바뀌는 도는 소스
>                label · inverse_of 만 고친 초안은 「Sources 0 · Truly none」 (전에는 그 이름을 쓰는 소스를 다 셌다)
> 급할 때          label 을 지우면 오늘의 키 이름표 — 다른 것은 안 바뀐다
> ```

---

> ## [10-06] **이력 목록 — 접힌 줄은 사람이 쓴 로그가 대표, 세상마다 실패 수 (총괄 a40ec0283 · 클라 9cdbda108 제안) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        히스토리 사이드바 Global 탭(/audit_logs/recent)에서 고친 행과 그 원장 영수증이 한 트랜잭션인 줄을 본다
> 뜻             접힌 줄의 로그 하나가 «영수증이 아닌» 가장 새 로그 — 사람이 고친 값(옛 값 -> 새 값)과 그 사람
>                전에는 가장 새 로그라서, 영수증이 뒤에 쓰이니 사용자 칸이 [ledger] 였다
>                영수증만 있는 트랜잭션(백필 · 소급)은 전과 같이 가장 새 영수증
>                receipt_worlds 의 세상마다 failed = 그 세상 번역이 실패한 영수증 수 (화면 표시는 클라 착지 뒤)
> 급할 때          읽기만 하는 목록 — 이 커밋을 되돌리면 대표가 가장 새 로그로 돌아간다. 데이터는 안 바뀐다
> ```

---

> ## [10-06] **원장 선언 폼 — 엔티티 바인딩의 타입 칸이 «이름 · 칸» 둘 중 하나 (총괄 068c904a6 ② · 클라 먼저) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        원장 선언 화면에서 소스 문장의 subject/target 바인딩(kind entity)을 연다
> 뜻             Entity type 칸에 고르개 name / column — name 은 오늘의 이름 고르개, column 은 Type from · column 두 칸
>                이미 이름을 적은 바인딩은 name 으로, {"kind": "column", ...} 를 적은 바인딩은 column 으로 열린다
> 급할 때          이 커밋을 되돌리면 타입 칸이 이름 고르개만 — 칸 타입은 원문 편집기로 적는다(오늘 오전과 같음)
> ```

---

> ## [10-06] **설정 해석 보고서 — 소스 줄이 로더의 판정 그대로 (총괄 11d0b6b88) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        관리 화면 설정 해석 보고서(/admin/config/resolve) 원장 도메인의 소스 줄
> 뜻             fine = 로더가 세운 소스(「`<소스>` is read: …」, 은퇴한 것은 「is retired」)
>                rejected = 로더가 거절한 소스, 로더의 문장 그대로 · 선언이 컴파일 안 되면 파일 줄 하나
>                전에는 옛 문법 검증기로 재서, 지금 문법 소스를 전부 「failed validation」 으로 적었다
> 급할 때          읽기만 하는 보고 — 되돌릴 일 없음
> ```

---

> ## [10-06] **설정 해석 보고서 — 「No translator states …」 목록이 실제로 안 쓰는 술어만 (총괄 6142e81bc) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        관리 화면의 설정 해석 보고서(/admin/config/resolve) 원장 도메인
> 뜻             「No translator states the declared predicates …」 에 이제 «어느 소스 문장도 · 엔티티 참조도 안 쓰는» 낱말만
>                전에는 옛 문법만 읽어, bind.mappings 소스의 술어를 거의 다 「안 쓴다」고 적었다(샘플: 16 중 15, 참은 7)
> 급할 때          읽기만 하는 보고 — 되돌릴 일 없음
> ```

---

> ## [10-06] **칸에서 타입을 읽는 바인딩 — 표 머리의 emits 와 온톨로지 탐색기 선에도 (총괄 564a46193 ②) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        entity_type 을 {"kind": "column", ...} 로 적은 소스가 있으면
>                그리드 표 머리 「ledger source — <소스> · emits ...」 에 그 역할이 받는 타입들의 references 엣지가 같이 나온다
>                온톨로지 탐색기에서 그 바인딩에 받는 타입마다 선이 하나씩
> 뜻             원장이 실제로 받는 것(행마다 그 칸의 타입)과 화면의 목록이 같아졌다
>                칸 타입 바인딩이 없는 박스에서는 전과 같다
> 급할 때          읽기만 하는 화면 — 되돌릴 일 없음
> ```

---

> ## [10-06] **체인 규칙 run_in 을 목록에서 고른다 (총괄 ff60fe669 ② · 클라 4256feacb 뒤) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        관리 화면 체인 규칙 응답(/admin/chain/rules/raw)에 "run_in": ["chain", "operation"]
>                규칙 폼의 run_in 칸(평면 · 통합 limits 둘 다)이 chain / operation 고르개
> 오타            저장 때 bad_run_in: run_in must be one of chain, operation, got '<값>' — 파일은 안 바뀐다
> 급할 때          쓰는 값을 바꾸지 않는다 — 원문 편집기로도 적을 수 있다
> ```

---

> ## [10-06] **선언 고치기 미리보기 — 칸에서 타입을 읽는 소스도 센다 (총괄 564a46193 ②) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        온톨로지 탐색기에서 엔티티 타입을 고치는 초안 -> 미리보기 비용 줄 Sources N
> 뜻             N 에 그 타입을 칸에서 읽을 수 있는 소스(술어가 그 역할에 그 타입을 받는 것)가 들어간다
>                칸 타입 바인딩이 없는 박스에서는 전과 같은 수
> 급할 때          읽기만 하는 미리보기 — 되돌릴 일 없음
> ```

---

> ## [10-06] **🔴 합치기가 빈 층을 안 남긴다 · 이미 남은 빈 층을 센다 (총괄 c773b0fed) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬 · 수집기 · 스케줄러)**
>
> ```
> 재기동 뒤        새 합치기(쓰기 문 · 키 고치기 --apply · 표기 소급)는 넘어가는 행에 없던 칸의 층을 만들지 않는다
> 센다(읽기만)      python server/scripts/count_absent_null_layers.py
> 세 수의 뜻        ① 비울 수 없는 쓴 이(파일 등)의 빈 층 — 전부터 세던 그 수(S-243-b), 판정 405 이전에 쌓인 부재
>                ② 합치기가 남긴 빈 사본, 비울 수 없는 쓴 이 — 부재로 확정. 이번 결함이 남긴 것
>                ③ 합치기가 남긴 빈 사본, 사람 · 체인 — 부재이거나 사람이 일부러 비운 칸의 사본. 구별이 안 된다
>                수마다 「가림」 = 그 칸에 값이 있는 다른 층이 있다 — 다음에 그 칸을 다시 계산하면 그 값이 지워질 수 있다
> 그래서          지우기가 정해질 때까지 합치기가 있던 표에 표기 소급을 다시 돌리지 않는다 — 세 수는 총괄께
> 급할 때          이 커밋을 되돌리면 빈 층이 다시 생긴다 — 되돌리지 않는다. 스크립트는 아무것도 쓰지 않는다
> ```

---

> ## [10-06] **실패한 규칙 작업의 기록이 잘리지 않음 (총괄 ff60fe669 ①) — 이주 «불필요» · 재기동 «필요»(API · 스케줄러)**
>
> ```
> 실패한 규칙 작업   Retroactive 실행 목록의 그 줄 error 가 JSON 으로 읽힌다(failed_at · reason · rules · tables · rows · row)
>                reason 이 길면 가운데가 … — 머리에 [rules=<규칙> ...], 꼬리에 올라온 오류
> 급할 때          쓰는 값을 바꾸지 않는다 — 되돌릴 일 없음
> ```

---

> ## [10-06] **표기 소급 — 접은 키가 다른 행의 키면 그 행으로 «합친다» (총괄 5ffa48232 · 소유자 「예」) — 이주 «불필요» · 재기동 «필요»(API · 스케줄러)**
>
> ```
> 순서            1 관리 화면 Retroactive 의 Fold stored values into the declared spelling 를 표 하나로 count(dry run)
>                2 문장에 N row(s) fold onto another row's key - the run merges each into that row
>                  (e.g. <옛 키> -> row <그 행> (<접은 키>); ...) 가 있으면 견본 셋을 열어 같은 것인지 본다
>                3 맞으면 run. 아니면 별칭 행이나 규칙을 고치고 1 부터
> 되돌릴 수 없음     합쳐진 행은 지워진다. 값 · 층은 받는 행으로 옮겨지고 감사 줄(collision_merge)이 남는다
>                받는 행에 사람이 적은 값은 그대로 남는다. 그 키를 가진 행이 없으면 모인 행 중 row_id 가 가장 작은 행이 받는다
> 돌린 뒤          실행 목록의 그 줄 result 의 rows_merged = 합친 행 수
>                같은 표를 다시 count -> fold onto another row's key 문장이 없어야 한다
> 급할 때          run 을 누르지 않는다 — count 는 아무것도 쓰지 않는다. 이미 합친 것은 되돌리지 못한다
> ```

---

> ## [10-06] **표기 규칙 collapse_repeats — 연달아 같은 마디는 하나로 (총괄 c1ddec935) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬 · 수집기)**
>
> ```
> 선언           notation_rules.json 칸에 {"write": true, "rules": {"collapse_repeats": "."}}
> 먼저 볼 것      그 칸의 미리보기 — 병합군에 a.b.b · a.a.b · a.b 가 한 줄로, folds_again 0
> 저장된 값       관리 화면 Retroactive 의 Fold stored values into the declared spelling 으로 그 표를 접는다(먼저 dry run)
> 거절이면        해석 보고서의 그 칸 줄: 'collapse_repeats' folds a value when it is written ...
>                (write 없음) · must be the one character that splits segments (값) · 'time' is the only rule
> 급할 때         그 칸의 collapse_repeats 를 지운다 — 몇 초 안에 다시 읽힌다. 이미 접어 저장한 값은 그대로
> ```

---

> ## [10-06] **선언 화면 — 엔티티 바인딩 타입 칸을 이름 고르개로 되돌림 (f1238d6ef 의 either 되돌리기, 총괄 긴급) — 재기동 «필요»(API)**
>
> ```
> 재기동 뒤        원장 선언 화면에서 소스 · 문장의 subject/target 바인딩을 연다
> 뜻             Entity type 칸이 오늘처럼 이름 고르개로 그려진다(f1238d6ef 로 재기동했으면 그 칸이 비어 있었다)
> 칸에서 읽는 타입   선언 원본(JSON)에 {"kind": "column", "column": "<칸>"} 으로 적는다 — 폼은 아직 이름만
> 급할 때          이 커밋을 되돌리면 f1238d6ef 의 빈 칸이 다시 난다 — 되돌리지 않는다
> ```

---

> ## [10-06] **원장 — 엔티티 타입을 행의 칸에서 (총괄 b5b335f2e ④ · 7255b4918) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬)**
>
> ```
> 재기동 뒤        기존 소스는 다시 번역하지 않는다 — 지문이 그대로(견본 6 · 이 박스 5 전후 같음)
>                그래서 체인 데몬 로그에 [Ledger] re-stamped ... cursor(s) 줄이 이번엔 안 나온다
> 칸 타입 소스를 더하면   후보 표의 확정 칸을 채운 행만 원자. 받지 않는 타입의 행은 거절 목록에
>                type_not_admitted (그 행의 칸 · 값 · 받는 타입을 문장에), 다른 행은 들어간다
> 급할 때          그 소스의 entity_type 을 이름으로 되돌리거나 소스를 retired — 다른 소스는 영향 없음
> ```

---

> ## [10-06] **체인 규칙을 작업으로 · LLM 으로 후보 뽑기 (총괄 b5b335f2e · be0abe305 · 92d0483e5) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬 · 스케줄러)**
>
> ```
> 설치            LLM 을 쓸 때만: conda env assy_manager 에서 pip install openai
> 환경변수         ASSY_LLM_BASE_URL · ASSY_LLM_MODEL · ASSY_LLM_API_KEY · ASSY_LLM_TIMEOUT_S(초, 기본 60)
>                서버 트리를 띄우는 셸에 — 띄운 뒤에는 못 준다
> 재기동 뒤        run_in: operation 규칙의 트리거 표에 쓰면 체인 데몬 로그에
>                [Retroactive] queued run_id=<id> op=rule_rows params={'rule': '<규칙>', ...}
> 뜻              묶음이 맵퍼 대신 작업을 줄 세우고 다음 묶음으로 갔다. 스케줄러가 작업을 하나씩 돈다
>                관리 화면 Retroactive 의 Run a rule's queued rows 가 그 작업 — failed 면 error 의 reason 이
>                체인 격리와 같은 문장(LLM 답이 틀리면 LlmRefused: ...)
> 키 확인          로그에 키가 없어야 한다: 키 앞 여섯 글자로 grep -c -> 0
> 후보 표          extractor · evidence 두 칸을 table_config 에 더하기 전까지는 쓰기가 그 둘만 버리고 센다:
>                [Schema] Column 'extractor' is not declared in column_types for table '<후보 표>' ... DROPPED
>                (find_links 맵퍼도 같다 — 두 칸을 더하면 그 줄이 멎는다)
> 급할 때          규칙의 run_in 줄을 지우고 재적재 -> 체인 안에서 돈다(느린 맵퍼면 그 뒤 묶음이 기다린다)
> ```

---

> ## [10-06] **걷기 요청 이름을 한 자리에서 — 옛 철자 접고, group_by 는 키 이름도, 없는 이름 거절 (총괄 17b6337e4 · a588e5d80) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤     curl "http://<서버>:<포트>/api/ledger/subgraph?id=<노드 id>&group_by=type&measure=sum:inspected@1"
> 뜻           groups[].value 의 키가 "sum:inspected@1"(보낸 그대로)이고 값이 sum:inspected 와 같다
>             follow=processed_with@1 · collect=wafer@1 · seed_type=wafer@1 도 맨이름과 같은 걷기
>             없는 이름 -> 422, detail = {reason, argument(칸), unknown, declared, world}
>             group_by · measure 의 없는 이름은 전에 «빈 값»이었다 — 이제 422 value_name_not_declared
>             group_by=wafer -> 웨이퍼마다 무리(노드 keys 에서). value_sources 맨 앞이 "keys"
> 급할 때       git revert <이 커밋> -> 재기동 (옛 철자가 다시 빈 값, 없는 이름도 다시 빈 값, group_by=wafer 도 다시 빈 무리)
> ```

---

> ## [10-06] **서버와 화면은 함께 — 화면이 이름의 @ 를 더는 벗기지 않는다 (총괄 2c4093eac) — 화면 빌드 · 서버 재기동 «같이»**
>
> ```
> 무엇이 바뀌나  선언 화면 Version 줄 · 새 이름의 @1 제안 · 걷기 전선의 @ 벗기기가 없어졌다. 이름은 서버가 보낸 그대로
> 볼 것        pull 뒤 재기동 없이 화면만 쓰면 옛 서버와 이름 철자가 어긋난다 — 옛 서버는 선언을 x@1 로 보내고 follow=x@1 을 422
>             재기동 뒤(서버 f34f16892 이후) 걷기 화면에서 follow 를 골라 걸으면 200
> 급할 때       git revert <이 커밋> -> 화면 빌드 (화면이 다시 @ 를 벗긴다 — 옛 서버와도 맞음)
> ```

---

> ## [10-06] **노드 · 엣지 이름에서 @1 은퇴 · 세상마다 목록은 고른 순서 (총괄 4eb1fe98f · 5788bd81c · 4be010312) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬)**
>
> ```
> 재기동 뒤 체인 데몬 로그   [Ledger] re-stamped N cursor(s) whose declaration did not change: ...
> 뜻          N = 운영 세상에서 도는 소스 수. 줄마다 (position stays ...) — 위치 · 원자는 그대로, 다시 번역 없음
>             다른 켜진 세상의 도장은 낡은 채 남지만 아무것도 막지 않는다
>             (맞추려면 python scripts/ledger_restamp_cursor.py --world <세상> --apply)
> 패널         원장 인입의 소스마다 도장(translator_ver)이 바뀌고, 차이 · 새 행 · 지워진 행은 재기동 전과 같다
> 확인         python -m ledger census   -> 새 행 · 수정 누락 · 지워진 행이 재기동 전과 같다
>             curl "http://<서버>:<포트>/api/ledger/declaration"   -> entities[].type 이 wafer 모양 (@1 없음)
> 걷기         world=<가>&world=<나> 로 걸으면 엣지 worlds · by_world 와 노드 attributes_by_world 가 둘 다 <가>, <나> 순서
> 파일         ledger_config.json 은 다음 저장 때 맨이름으로 다시 쓰인다 (그 전에도 읽기는 맨이름)
> 급할 때       git revert <이 커밋> -> 재기동. ⚠️ 그 사이 저장이 있었으면 파일이 맨이름이라 옛 코드가 거절한다
>             -> ledger_config.json 옆 backup 폴더의 저장 직전 파일을 같이 돌려놓는다
> ```

---

> ## [10-04] **걷기 응답의 노드 속성이 세상마다 (총괄 4e1e49fe9) — 이주 «불필요» · 재기동 «필요»(API)**
>
> ```
> 재기동 뒤     curl "http://<서버>:<포트>/api/ledger/subgraph?id=<노드 id>&world=<세상1>&world=<세상2>&hops=1"
> 뜻           nodes[].attributes_by_world = 속성마다 [{world, value, occurred_at, source_who}] — 고른 순서, 세상마다 한 줄
>              값은 그 세상의 원자에서 · 이름이 many(목록)인지는 걷기가 합친 선언(처음 고른 세상 우선)
>              attributes · attribute_conflicts 는 전과 같다 (세상들 가운데 한 값 · 값이 갈린 이름 수)
>              occurred_at null = 그 원자의 시각이 사건 시각이 아니다 (관계 선과 같은 규칙)
>              칸이 없는 노드 = 이 걷기가 그 노드의 등록 원자에 안 닿았다 (전과 같은 뜻)
> 급할 때       git revert <이 커밋> -> 재기동 (그 칸만 없어지고 다른 칸은 그대로)
> ```

---

> ## [10-04] **원장 census 가 새 행 · 고친 행 · 지워진 행을 따로 센다 (총괄 6091a7ae3 ② · ca68c7c48) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬)**
>
> ```
> 재기동 뒤 (server 폴더에서)
>   python -m ledger census
> 뜻           줄마다 「표 … · 색인 … · 차이 … · 새 행 … · 수정 누락 … · 지워진 행 … · 지문 없음 …」
>              차이 = 표 행 − 색인 행(새 행과 지워진 행이 상쇄됨) — «남은 0» 이 아니다. 판단은 새 행 · 수정 누락 · 지워진 행으로
> 셋 중 하나라도 0 이 아니면 그 세상 따라잡기 (census 기록의 next_step 이 이 줄)
>   python -m ledger.backfill --world <세상> --catch-up
> 급할 때       git revert <이 커밋> -> 재기동 (census 가 다시 not_yet 한 칸 · 다음 걸음 --drifted)
> ```

---

> ## [10-04] **원장 배치 영수증이 세상을 댄다 (총괄 6091a7ae3 ③) — 이주 «불필요» · 재기동 «필요»(체인 데몬 · API)**
>
> ```
> 무엇이 바뀌나  후속 · backfill 이 남기는 영수증(감사 행, column_name = ledger_batch)의 new_value 에 "world" — 성공 · 실패 둘 다
> 볼 것        세상이 둘 이상 켜진 채 행 하나를 고치면 같은 트랜잭션에 영수증이 세상 수만큼, 줄마다 world 가 다름
>              (타임라인 줄에 세상이 보이는 것은 클라 착지 뒤 — 그 전에는 펼친 값에서)
> 급할 때       git revert <이 커밋> -> 재기동 (영수증에 world 칸만 빠짐)
> ```

---

> ## [10-04] **원장 후속의 고치기가 같은 행을 한 번만 번역한다 (총괄 6091a7ae3 ①) — 이주 «불필요» · 재기동 «필요»(체인 데몬)**
>
> ```
> 무엇이 바뀌나  고치기(EDIT)를 따라갈 때 거둘 것을 겨누려고 번역한 결과를 그대로 쓴다 — 전: 같은 행을 두 번 번역
> 잰 것        이 박스 시험 DB, 세상 하나 · 1,000 행 한 그룹 고치기 4.55~5.17 s -> 3.48~3.99 s (켜진 세상마다 그만큼)
> 볼 것        체인 데몬 재기동 뒤 원장 후속이 고치기에서 덜 밀림 — 쓰는 원자 내용은 그대로
> 급할 때       git revert <이 커밋> -> 체인 데몬 재기동
> ```

---

> ## [10-04] **세상은 따로 · 겹침은 걸을 때 · 실시간은 켜진 세상 전부 (총괄 092a6f9e5 · 71880678a · ee0f66e7b) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬)**
>
> ```
> 재기동 뒤 볼 것  GET /admin/ontology-explorer/worlds -> live: {세상: true|false} (가지는 모두 true 로 시작)
>              체인 데몬 로그 [LedgerFollowUp] ... failed in world <세상> — 실패가 있으면 어느 세상인지 붙음
> 후속 비용      켜진 세상 수만큼 후속이 한 벌씩 — 이 박스 1,000 행 한 그룹에 세상 하나 ≈ 만들기 2.8 s · 고치기 4.9 s
> 뜻           큐가 밀리면 쓰지 않는 세상을 끈다 (화면 Live 끄기 = PUT /admin/ontology-explorer/worlds/<세상>/live {"live": false})
> 켤 때         화면 Live 켜기 -> 응답 run_id = 따라잡기 작업(ledger_catch_up) — 관리 화면 소급 작업 줄에서 끝 확인
>              손으로 (server 폴더에서)  python -m ledger.backfill --world <세상> --catch-up
> 뜻           꺼진 동안 생긴 행 · 고친 행 · 지운 행을 맞춤 — 끝나면 python -m ledger census --world <세상> 이 남은 0 · 수정 누락 0
> 급할 때       git revert <이 커밋> -> 재기동 (live 칸은 읽히지 않고, 이 커밋 뒤 만든 가지는 기본 세상 위에 선 것으로 읽힘)
> ```

---

> ## [10-03] **새 소스 backfill 이 같은 표의 다른 소스 사실을 한 번 더 쓰지 않는다 (총괄 5fec118bb) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬)**
>
> ```
> 무엇이 바뀌나  python -m ledger.backfill --source X (와 화면의 다시 번역)가 X 만 번역 — 전: 그 표를 읽는 소스 전부를 거두지 않고 한 번 더
> 운영에 쌓인 것  먼저 센다 (PG · 원장 전체를 훑음 — 한가할 때)
>   SELECT source_who, sum(n - 1) AS extra FROM (
>     SELECT source_who, count(*) AS n FROM ledger_events WHERE supersedes IS NULL
>      GROUP BY source_who, source_raw_ref, occurred_at, predicate, subject_type, subject_keys,
>               coalesce(object_payload, '{}'::jsonb)
>     HAVING count(*) > 1) d GROUP BY source_who ORDER BY 2 DESC;
> 뜻           소스마다 «같은 행 · 같은 사실을 이미 말한 원자가 있는데 하나 더» 의 수 — 줄이 없으면 끝
> 고치기        센 소스마다 (server 폴더에서, 먼저 미리보기)
>   python -m ledger.backfill --source <소스> --whole-source
>   python -m ledger.backfill --source <소스> --whole-source --apply
> 뜻           그 소스의 원자를 거두고 행마다 한 번씩 다시 씀 — 위 SQL 을 다시 돌려 그 소스 줄이 사라지면 끝
> 급할 때       git revert <이 커밋> -> 재기동 (backfill 이 다시 표 단위 — 선언이 바뀐 뒤면 중복이 다시 생김)
> ```

---

> ## [10-03] **대조 저장의 빈 세상은 걸은 세상 이름으로 (총괄 71ecd8223 · 0c918c2eb) — 이주 «불필요» · 재기동 «필요»(체인 데몬)**
>
> ```
> 무엇이 바뀌나  world 를 비워 저장한 contrast_run 행 — 체인 맵퍼가 운영 세상을 «이름으로» 걷고 computed_at 과 같은 되쓰기에 world 를 적는다
>              world 를 적어 저장한 행은 그대로
> 재기동 뒤 볼 것 R&D 보드에서 Save contrast 한 번 -> 계산된 뒤 그 행의 world 칸 = 운영 세상 이름(GET /admin/ontology-explorer/worlds 의 operating)
> 뜻           빈 칸이면 체인 데몬이 재기동 전 코드로 돌고 있다
>              그 전에 빈 칸으로 남은 행은 그대로 — 다시 계산(리플레이)되면 그때의 운영 세상 이름이 적힌다
> 급할 때       git revert <이 커밋> -> 체인 데몬 재기동 (빈 칸으로 남고 걷기는 그때의 운영 세상)
> ```

---

> ## [10-03] **한 배치 안에서도 나중에 온 값이 이긴다 (총괄 9280922aa) — 이주 «불필요» · 재기동 «필요»(API · 체인 데몬 · 파일 감시)**
>
> ```
> 무엇이 바뀌나  층 시각(cell_sources.ingested_at)을 한 함수(crud.layer_instant)가 찍는다 — 한 프로세스 안에서 앞 찍기보다 반드시 뒤
>              한 배치에 같은 칸을 두 소스가 쓰면 뒤 항목이 칸 · 감사 · 아웃박스에 나간다(전: 같은 눈금이면 이름 순으로 앞 항목)
>              병합 사본은 사라지는 행 안의 원래 전달 순서대로 찍힌다 — 그 행이 보이던 값이 사본 사이에서도 이김
>              (같이) 모르는 세상을 물으면 거절 world_unknown 의 worlds 가 default 를 먼저 싣는다 (총괄 f1ad96964 ①)
> 재기동 뒤 볼 것 (스캔 — 한가할 때, PG)
>   SELECT count(*) FROM (SELECT 1 FROM cell_sources WHERE ingested_at >= '<재기동 시각>'
>    GROUP BY table_name, row_id, column_name, ingested_at HAVING count(*) > 1) t;
> 뜻           재기동 뒤 한 칸에서 시각이 같은 층의 묶음 수 — 0 이 정상(한 프로세스는 같은 시각을 두 번 안 줌)
>              0 이 아니면 두 프로세스가 같은 눈금에 같은 칸을 썼거나 재기동 전 코드가 돌고 있다
>              '<재기동 시각>' 없이 돌리면 지난날 동률이 남긴 묶음까지 센다 — 그 칸들은 이름 순 값을 보이고 있을 수 있다(고치지 않음)
> 급할 때       git revert <이 커밋> -> 재기동 (층마다 datetime.now() 로 돌아감 · 이미 찍힌 시각은 그대로)
> ```

---

> ## [10-03] **세상 목록은 어느 답에서나 한 모양 (총괄 e51e3e417) — 이주 «불필요» · 재기동 «필요»**
>
> ```
> 무엇이 바뀌나  걷기 선언 답(/api/ledger/declaration)의 worlds 가 default 를 먼저 품고 operating 을 같이 싣는다
>              /tables · GET /admin/ontology-explorer/worlds 와 같은 함수(schema.world_listing)에서 나옴
> 재기동 뒤 볼 것  curl -s http://localhost:8080/api/ledger/declaration | python -c "import json,sys; d=json.load(sys.stdin); print(d['worlds'], d['operating'])"
> 뜻           ['default', ...가지] 와 운영 세상 이름 — 세상 목록 라우트 · /tables 의 같은 두 칸과 같아야 한다
>              worlds 에 default 가 없으면 재기동 전 코드가 돌고 있다
> 급할 때       git revert <이 커밋> -> 재기동 (선언 답이 가지만 싣던 모양으로 돌아감)
> ```

---

> ## [10-03] **원장 세상 — 운영 세상 한 칸 (총괄 e1f54cd72 · e67ef53f3 · 86d5061a0 · 2bb20ff56) — 이주 «불필요» · 재기동 «필요»(서버 + 워커 — 위 절과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  세상 이름 없이 읽고 쓰는 자리 전부(원장 후속 · 걷기 · 그리드 원자 보기 · 선언 읽기 · census)가 «운영 세상»을 따른다
>              배치 파일 config/ontology_worlds/worlds.json 이 없으면 운영 = 기본 (오늘 그대로)
> 확인         GET /admin/ontology-explorer/worlds
> 뜻           "operating": "default" 이면 오늘과 같다 · "history" 는 누가 언제 바꿨나
> 운영 바꾸기   PUT /admin/ontology-explorer/worlds/operating   본문 {"world": "<이름>"}   (엄격 관리자 토큰 · X-User 머리가 이력의 by)
>              되돌리기 = 같은 PUT 에 "default"
> 급할 때       worlds.json 의 "operating" 을 "default" 로 고치거나 파일을 지운다 -> 다음 요청 · 다음 후속 배치부터 기본
> ```

---

> ## [10-03] **합쳐져 사라진 행의 층 · 덮어쓰기 행도 같이 지운다 (소유자 10-03 · 총괄 a13fcf00c) — 이주 «불필요» · 재기동 «필요»(위 절과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  두 행이 한 키로 합쳐질 때(쓰기 · 핀 · rebuild_blank_business_keys --apply) 지워지는 행의 cell_sources · cell_overwrites 행도 지운다
>              전: 그 행의 층과 덮어쓰기가 행 없는 row_id 아래 남았다 — 아무도 안 읽음
> 운영에 쌓인 것  표마다, 먼저 센다 (PG)
>   SELECT 'cell_sources' AS side, count(*) FROM cell_sources m
>    WHERE m.table_name = '<표>' AND NOT EXISTS (SELECT 1 FROM "<표>" r WHERE r.row_id = m.row_id)
>   UNION ALL
>   SELECT 'cell_overwrites', count(*) FROM cell_overwrites m
>    WHERE m.table_name = '<표>' AND NOT EXISTS (SELECT 1 FROM "<표>" r WHERE r.row_id = m.row_id);
> 뜻           행이 없는 row_id 의 층 · 덮어쓰기 — 병합(7월부터)과 오늘 --apply 의 병합이 남긴 것. 값은 이미 임자 행에 있다
> 지우기        같은 조건으로 (센 뒤에)
>   DELETE FROM cell_sources m WHERE m.table_name = '<표>' AND NOT EXISTS (SELECT 1 FROM "<표>" r WHERE r.row_id = m.row_id);
>   DELETE FROM cell_overwrites m WHERE m.table_name = '<표>' AND NOT EXISTS (SELECT 1 FROM "<표>" r WHERE r.row_id = m.row_id);
> 급할 때       git revert <이 커밋> -> 재기동 (되돌리면 병합이 다시 층을 남긴다 · 지운 행은 돌아오지 않는다)
> ```

---

> ## [10-03] **같은 데이터를 다시 써도 행이 하나 더 생기거나 합쳐지지 않고, 합쳐진 껍데기 행은 표에 안 남는다 (총괄 e243d6abf ③ · d5cf3a954 · 829e3fe20 ④) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체 — 아래 절의 보류도 이것으로 풀린다)**
>
> ```
> 무엇이 바뀌나  ③ 조합키를 지을 때 각 조각을 그 칸이 저장하는 철자로 바꾼 뒤 잇는다
>                숫자 "1.0" · "01" · 1.0 -> 1   시각 -> 세션 존 벽시계 'YYYY-MM-DD HH:MM:SS'(마이크로초가 있으면 .ffffff)
>                전: 페이로드 철자로 지은 키와 저장된 값으로 다시 지은 키가 달라, 같은 행을 두 번 쓰면 껍데기 행이 생기고 합쳐졌다
>              ④ 이 배치에서 새로 만든 행이 병합되면 그 행은 표에 들어가지 않는다
>                전(fb9a0b649 만 재기동한 경우): 층이 하나도 없는 껍데기 행이 남았다
> 순서 (표마다)  ① 미리보기 — 읽기 전용, 아무것도 안 씀
>   python server/scripts/rebuild_blank_business_keys.py --table <표>
>              ② 재기동
>              ③ 고치기 — 키와 업무키 칸을 새 철자로 · 부딪히는 행은 그 키를 가진 행에 합침 · 행마다 감사 줄
>                 끝에 「고친 행 N / 미리보기 N · 합친 행 M / 부딪힘 M」 — 두 쌍이 같아야 한다
>   python server/scripts/rebuild_blank_business_keys.py --table <표> --apply --by <이름>
>              ④ 미리보기 다시 — rebuildable 0 · collides 0 이어야 한다
> 뜻           rebuildable  옛 철자 키를 가진 행 — 고치기 전에 같은 데이터가 오면 그 행을 못 찾고 «새 행이 하나 더» 생긴다
>              「키가 바뀌는 행 - 어느 조각」  number · datetime = 그 조각의 철자 때문 · not_iso = ISO 로 안 읽히는 시각 글자(그대로 둔다)
>                                            split = 저장 키가 조각 수대로 안 나뉨(구분자가 값 안에 있음)
>              collides     다시 지으면 다른 행과 같은 키 — --apply 가 그 키를 가진 행에 합친다 · 🔴 되돌릴 수 없다
>                           (견본 「이 행 -> 그 키를 가진 행 · 다시 지은 키」 · 셋 이상이면 row_id 순으로 하나로)
>                           앞 판(5416d3020)으로 ③ 을 이미 돌렸다면 남은 collides 가 있다 — 이 판에서 ③ 을 한 번 더 돌려 합친다
> 유령 행       fb9a0b649 로 이미 재기동했다면만 — 키가 있는데 층이 하나도 없는 행 (PG, 표마다)
>   SELECT count(*) FROM "<표>" r
>    WHERE r.business_key_val IS NOT NULL
>      AND NOT EXISTS (SELECT 1 FROM cell_sources s WHERE s.table_name = '<표>' AND s.row_id = r.row_id);
>              0 이 아니면 그 행의 값은 임자 행으로 이미 넘어가 있다 — 지울지는 총괄에게 올린다(이 착지는 지우지 않는다)
> 세션 존       psql 에서 SHOW TimeZone;  -> 'Asia/Seoul' 같은 이름이어야 한다
>              파이썬이 못 읽는 이름이면 시각 조각은 고쳐지지 않는다(naive 는 벽시계 그대로, offset 붙은 것은 UTC 로 적혀 둘이 갈린다)
> 급할 때       git revert <이 커밋> -> 재기동 (되돌리면 같은 행 두 번 쓰기가 다시 껍데기 · 합치기로 간다)
> ```

---

> ## [10-03] **병합과 쓰기가 한 배치에 섞여도 인제션이 터지지 않고, 층의 원천 행(origin_row_id)을 잃지 않는다 (총괄 1495534c9) — 이주 «불필요» · 🔴 재기동 «보류»**
>
> ```
> 🔴 지금 재기동하지 않는다 (총괄 829e3fe20) — 이 커밋만으로 재기동하면, 숫자 칸에 "1.0" 처럼 저장 철자와 다르게
>    온 같은 데이터를 두 번 쓸 때 인제션 오류 대신 «층이 하나도 없는 껍데기 행»이 표에 남는다
>    재기동은 키 철자(총괄 e243d6abf ③) + 껍데기 행 지우기(④)가 함께 착지한 뒤 한 번 — 그 절이 이 위에 올라온다
> 무엇이 바뀌나  키 조각이 다른 행의 키가 되어 병합이 나는 쓰기와 보통 쓰기가 한 배치에 있으면
>              전: CompileError「origin_row_id is explicitly rendered as a boundparameter」로 배치 실패, 또는
>                  오류 없이 그 청크 전부의 origin_row_id 가 NULL — 09-16 부터
>              뒤: 오류 0 · 쓰기의 origin 남음 · 병합이 넘겨받은 층은 껍데기 행 층의 origin 을 그대로 가짐
> 재기동 뒤     인제션 로그에 위 CompileError 가 더 안 나와야 한다
> 세는 SQL     조용히 잃었을 수 있는 체인 층 (PG, 표마다)
>   SELECT table_name,
>          count(*) FILTER (WHERE source_name = 'chain_ingestion') AS chain_layers,
>          count(*) FILTER (WHERE source_name LIKE 'chain_ingestion (%') AS merged_chain_layers
>     FROM cell_sources
>    WHERE origin_row_id IS NULL AND source_name LIKE 'chain_ingestion%'
>      AND ingested_at >= '2026-09-16'
>    GROUP BY table_name ORDER BY 2 DESC;
> 뜻           원천 행 하나를 못 대는 체인 쓰기도 NULL 이라, 이 수는 «잃었을 수 있는» 상한이다
>              NULL 인 칸은 원천 행이 지워져도 거둬지지 않는다(그 층이 남는다)
>              층 이름으로는 못 되살린다 — 병합 층의 괄호 속은 합쳐진 행의 키와 행 id 앞 6자이지 원천 행이 아니다
>              같은 값을 다시 써도 층은 다시 쓰이지 않아(값이 같으면 손대지 않음) 리플레이로도 안 채워진다
>              그 원천 행이 바뀌어 새 값이 오면 그때 채워진다
> 급할 때       git revert <이 커밋> -> 재기동 (되돌리면 섞인 배치가 다시 실패한다)
> ```

---

> ## [10-03] **table_config 를 다시 쓰는 스크립트 둘이 운영자가 적은 칸을 지우지 않는다 (총괄 338abb9f3) — 이주 «불필요» · 재기동 «불필요»(명령줄 도구)**
>
> ```
> 무엇이 바뀌나  install_product_tables.py --overwrite-drift — 제품이 말하는 칸만 되돌리고 group · kind · indexes · 더한 열은 남김
>              table_config_from_schema.py --merge     — 시트에 있는 표는 column_types · display_columns 만 바꾸고 나머지 칸은 그대로
>                                                        그 두 칸도 더하고 고칠 뿐 안 지움 — 시트에 없는 열은 남고(보고 「시트에 없음, 남겨 둠」) · 순서 · 숨긴 열 그대로 · 새 열은 끝에
> 확인         python server/scripts/install_product_tables.py            (드라이런, 아무것도 안 씀)
> 뜻           DRIFT 줄의 extra 는 현장이 더한 칸 — --overwrite-drift 로도 지워지지 않는다 · missing / changed 만 되돌아간다
> 급할 때       없음 — 두 스크립트 다 쓰기 전에 백업을 남긴다(install) · --merge 는 -o 초안 파일에만 쓴다
> ```

---

> ## [10-03] **두 행이 한 키로 합쳐질 때 — 핀은 터지지 않고, 사람 값은 사람이 쓴 칸에서만 이긴다 (총괄 6e041f4cb ①) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체, 위 절들과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  셀 핀이 키 조각의 보이는 값을 바꿔 키가 다른 행의 것과 같아지면 → 그 행에 합침(쓰기에서 부딪힐 때와 같은 한 병합)
>              전: 합칠 칸이 하나라도 있으면 오류(NameError: changed_cols) · 핀 전체가 되돌려짐 — 2026-07-17 부터
>              합칠 때 사람이 쓴 칸은 «이번에 쓴 칸»뿐(핀 = 핀 걸린 칸, 쓰기 = 그 항목의 칸) — 임자 행에 사람이 적은 값은 남는다
>              전: 사람이 키 조각만 고친 쓰기도 그 항목의 모든 칸을 사람 것으로 세어, 임자 행의 사람 값을 기계 값으로 덮을 수 있었다
> 확인         그리드에서 키 조각 칸의 숨은 층을 핀으로 골라 다른 행의 키와 같게 → 행이 하나로, 오류 없음
> 뜻           합쳐진 행: 핀 걸린 칸 = 핀이 고른 층 · 임자 행에 사람이 적은 값 = 그대로 · 지운 쪽 행에 사람이 적은 값 = 넘어옴
>              사람이 쓴 칸이 임자 행의 사람 값과 부딪히면 쓴 값이 보이고 옛 값은 그 칸의 user (old_exist_…) 층
>              그 전에 «먹지 않은» 핀이 있었을 수 있다 — 그 칸은 핀 전 층을 보이는 채. 다시 핀하면 이제 합쳐진다
> 급할 때       git revert <이 커밋> -> 재기동 (되돌리면 핀 충돌은 다시 오류로 되돌려짐)
> ```

---

> ## [10-03] **원장이 «소스가 안 읽는 칸»만 바뀐 수정을 다시 번역하지 않는다 (총괄 «소스가 안 읽는 칸» · 6e041f4cb ②) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체, 위 절들과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  그리드 · 체인 · 파서가 고친 칸을 사건에 싣는다(오늘도) — 그 칸 중 어느 것도 원장 소스가 읽는 칸이 아니면 그 소스를 건너뜀
>              다시 번역은 오늘처럼: 읽는 칸이 섞임 · 칸을 안 말하는 사건 · 새 행 · 지움 · 파이썬 맵퍼 소스
> 확인         python -m ledger followup        (server 폴더)
>              뜻: 「따라갈 일 N · 실패 M」 아래 「건너뜀 <소스> N 사건」 — 아웃박스가 지닌 동안(보관 7일) 그 소스가 건너뛴 사건 수
>              체인 워커 로그  [LedgerFollowUp] lap: … · skipped <소스>=<사건 수> (no column it reads changed)
> 뜻           원장에 있어야 할 값이 안 바뀌었는데 그 소스가 건너뜀에 있으면: 그 값의 칸을 선언(bind · read)이 이름 부르지 않는 것 — 선언을 고친 뒤
>                 python -m ledger.backfill --source <소스> --whole-source --apply     (server 폴더, 그 소스를 다시 번역)
> 급할 때       git revert <이 커밋> -> 재기동 (되돌릴 이주 없음 — 칸에 남은 «done · skipped» 는 «done» 과 같이 읽힌다)
> ```

---

> ## [10-03] **조합키만 선언한 표도 키 조각이 바뀌면 키를 다시 짓는다 (총괄 a3cd662d9 · a61d32f4f ㄱ) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체, 위 절들과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  business_key 칸 없이 composite_key_source 만 선언한 표 — 키 조각을 고치면 키를 다시 짓고 · 비우면 NULL · 남의 키와 부딪히면 병합
>              그리드 «행 추가» 빈 행에 키 칸을 채우면 키가 생긴다(전: 안 생겨서 다음 키 쓰기가 행을 하나 더 만듦)
> 확인         조합키만 선언한 표에서 «행 추가» -> 키 칸을 다 채움 -> 같은 키로 파일 · 체인이 한 번 쓰면 행이 하나 그대로
>              이 병이 남긴 행 수(읽기만):
>              SELECT count(*) FROM <표> WHERE business_key_val IS NULL AND <조각 칸마다 IS NOT NULL AND btrim(칸::text) <> ''>
>              박스 오늘: 키를 선언한 표 32 · 겹친 키 그룹 0 · 이 병의 행 0
> 뜻           0 이 아니면 그 행은 키 없이 남은 것 — 고치는 것은 소유자가 돌린다(지우거나 접는 명령, 기본은 읽기만):
>                 python server/scripts/rebuild_blank_business_keys.py --table <표>            (키를 다시 조립 — 부딪히는 키는 collides 로 냄)
>                 python server/scripts/dedupe_business_key_rows.py --table <표>               (그다음 겹친 행 접기 — 값이 다른 그룹은 건너뜀)
>              각각 --apply 를 붙여야 쓴다. 순서는 rebuild 먼저
> 급할 때       git revert <이 커밋> -> 재기동 (되돌릴 이주 없음)
> ```

---

> ## [10-03] **원천 행을 지우면 «가려진 값»이었어도 보류를 다시 센다 (총괄 e11bb4de0 (나)) — 이주 «불필요» · 재기동 «필요»(체인 워커 — 위 절들과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  지움 경로(원장 따라가기의 DELETE)가 층을 거둔 대상 행마다 EDIT 사건 하나 — 체인 채널 · 거둔 칸 이름
>              allow_chain_trigger 를 적은 규칙만 깬다(보류 다시 세기 규칙)
> 확인         같은 키에 값이 다른 원천 행 둘 -> 공식 행 hold 빈 값 -> «안 보이는» 쪽 원천 행을 지움 -> hold = agreed
>              체인 워커 로그  [ChainRetract] table=<원천 표> … rows_told=<행 수>
> 뜻           그 줄에 rows_told 가 없으면 이 판이 아님(체인 워커 재기동 안 됨)
>              rows_told 가 있는데 hold 가 그대로면 다시 세기 규칙이 꺼져 있음 — 다시 채우기 동안은 꺼 둔 것이 맞다(「공식 표 다시 채우기」 8 · 10)
> 급할 때       다시 세기 규칙 "enabled": false -> Reload Configs & Code (사건은 남고 그 규칙만 안 깬다)
>              코드는 git revert <이 커밋> -> 체인 워커 재기동
> ```

---

> ## [10-03] **쓰기 문 — 같은 묶음에서 만든 행을 다시 쓸 때 칸마다 묻지 않는다 (총괄 bce43236b) — 이주 «불필요» · 재기동 «필요»(위 절들과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  체인 · 그리드 · 파서 쓰기 문에서, 묶음이 방금 만든 행의 다음 항목(값 다음 보류)이 칸 이력을 칸마다 DB 에 묻지 않는다
>              결과(칸 값 · 층 · 출처 · 덮어쓰기 · 아웃박스 · 감사 줄)는 전과 같다 — 시험 스키마 비교
> 확인         재기동 뒤 체인 워커 로그의 그룹 줄에 쓰기 단계 시간이 찍힌다(write:<표> · row build …) — row build 가 전보다 짧다
>              시험 스키마 1,000 행 체인 그룹: 4.23 s -> 3.04 s (운영은 안 쟀다)
> 뜻           row build 가 그대로 길면 이 판이 아닌 것(재기동 안 됨) — 체인 워커 재기동 확인
> 급할 때       git revert <이 커밋> -> 재기동 (되돌릴 이주 없음)
> ```

---

> ## [10-03] **원장 읽기 — «표의 물리 칸» 은 한 함수가 답하고, 읽기마다 한 번 묻는다 (총괄 c8d6a8597) — 이주 «불필요» · 재기동 «필요»(위 절들과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  표의 실제 칸을 묻는 자리 셋(원장 선언 검사 · 칼럼 통계 · 원장 읽기)이 column_stats.physical_columns 하나로
>              원장 읽기는 그 물음을 페이지마다가 아니라 «읽기 한 번»(소스 · 배치)마다 한 번 (pg 시험의 한 읽기: 7 번 -> 1 번)
> 확인         할 일 없음 — 원자 · 지문은 그대로(박스 소스 다섯 · 샘플 소스 셋 전후 같음)
> 뜻           어느 소스가 「relation '…' does not exist in the current schema」 로 서면 그 표가 DB 에 없는 것(전에는 같은 경우 SELECT 오류)
> 급할 때       git revert <이 커밋> -> 재기동
> ```

---

> ## [10-03] **원장 census — 사람이 센 두 수가 주기 census 뒤에도 남고 · 기록이 다음 할 명령을 싣는다 (총괄 5baab7b8d · e1648e884) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체, 위 절과 같은 재기동이면 한 번)**
>
> ```
> 무엇이 바뀌나  주기 census 가 기록을 쓸 때 사람이 센 rows_drifted · rows_unprinted 를 그때 시각 그대로 잇는다(전엔 지워져 Not measured)
>              census 기록에 next_step — 누락 있음: python -m ledger.backfill --source <소스> --drifted
>                                        사람이 센 적 없음: python -m ledger census --source <소스>   · 누락 0: 없음
> 확인         python -m ledger census --source <소스>   (server 폴더) -> 몇 분 뒤(주기 census 한 바퀴) 대시보드 원장 소스 패널
>              Edited, not followed 의 수와 Measured 시각이 사람이 센 그대로 남아 있어야 한다
>              python -m ledger census --source <소스> --json 의 그 소스 기록에 next_step
> 뜻           주기 뒤 Not measured 로 돌아가면 이 판이 아닌 것(재기동 안 됨) — 체인 워커 재기동 확인
>              Measured 시각이 주기마다 바뀌면 주기 census 가 두 수를 «다시 센» 것 — 표를 훑는 일이라 그러면 안 된다(보고)
> 급할 때       git revert <이 커밋> -> 재기동 (되돌릴 이주 없음 · 기록은 다음 census 가 다시 쓴다)
> ```

---

> ## [10-03] **원장 — 맵퍼는 그 표의 칸을 전부 받는다 · `map.input_columns` 은퇴 (소유자 · 총괄 2a8d9073c · 멈춤 둘 닫음 164553a6f) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  원장 읽기가 소스 표의 칸 전부(table_config.json 의 그 표)를 가져와 맵퍼에 넘긴다
>              ledger_config.json 의 map.input_columns 는 읽고 무시(지우지 않아도 된다) · 탐색기 폼에서 그 칸이 사라짐
> 확인         재기동 뒤 체인 워커 로그에 [Ledger] re-stamped N cursor(s) 줄이 «없어야» 한다
>              (박스: 소스 다섯 · 샘플 소스 셋 모두 지문이 그대로 · 같은 2,000 행에서 원자가 같음)
>              python -m ledger census --source <소스>   (server 폴더) — 수가 재기동 전과 같다
> 뜻           re-stamped 줄이 나오면 지문이 움직인 것 — 원자는 같아도 그 소스 커서가 한 번 다시 찍힌다(자리 그대로, 다시 읽는 행 없음)
>              로그 [Ledger] <표>: table_config declares <칸>, the table has no such column - not read (프로세스마다 한 번)
>                 = table_config.json 에는 있는데 DB 표에 없는 칸. 그 칸만 안 읽고 소스는 돈다 — 맞추려면 둘 중 한쪽을 고친다
>                 「column ... does not exist」 로 서는 것은 바인딩이 그 칸을 부를 때뿐(전과 같다)
>              행 단위 소스의 행 순서는 선언이 부르는 칸과 row_id 로만 — 다른 칸의 NUMERIC · DATE 값이 소스를 세우지 않는다
>              원자의 번역 버전(선언 전체 해시)은 재기동 뒤 새 원자부터 한 번 바뀐다 — 선언을 고칠 때마다 생기는 것과 같다
> 급할 때       git revert <이 커밋> -> 재기동 (되돌릴 이주 없음 · 옛 코드는 안 적은 input_columns 를 [] 로 채운다)
> ```

---

> ## [10-03] **원장 — 원장이 못 본 수정을 센다 · 그 행만 다시 번역 (총괄 bb9b1c19c (나) · c21cba507) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  원장 행 색인 줄에 «번역할 때의 행 지문». 칸은 원장 쓰기가 처음 돌 때 스스로 더함(로그 [Ledger] adding ledger_source_row_ref.row_fingerprint 한 번)
> 확인         python -m ledger census --source <소스>   (server 폴더) — 「표 · 색인 · 남은 · 수정 누락 D · 지문 없음 U」
> 뜻           U = 이 착지 전에 적힌 줄. 채우는 것은 필수 아님(새 세상 번역이 처음부터 적음)
>                 기본 세상에서 채우려면 소스마다 python -m ledger.backfill --source <소스> --whole-source --apply
>                 (이 박스 색인 행 1,215,824 · 시간은 총괄 율 1,000 행당 5.85 s 로 어림, 운영은 안 쟀다)
>              D = 원장이 못 본 수정(그 소스가 읽는 칸이 바뀌었는데 원장은 옛 값). python -m ledger.backfill --source <소스> --drifted 로 보고 --apply 로 그 행만 다시
>              D 가 다시 늘면 따라가기가 무언가를 놓친 것 — python -m ledger followup 의 실패 목록부터
> 급할 때       git revert <이 커밋> -> 재기동 (칸은 남아도 옛 코드가 안 읽는다)
> ```

---

> ## 🔴 [10-03 아침 고침] **원장 따라가기 — 대기열이 아웃박스 행으로 (총괄 bb9b1c19c (가) · a3d19dc51) — 이주 «필요»(앱을 «끄고») · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 순서          1 앱 끔       run_app.bat 전체를 닫는다 — 앱이 도는 중에 이주하지 않는다(쓰다 쉬는 세션이 이주를 붙잡는다)
>              2 이주 보고   python server/migrations/add_outbox_ledger_state.py
>                 뜻: server_version (11 이상이어야 칸 추가가 빠름) · column=ledger_state exists=False 면 아직 · index … valid=None 이면 색인 없음
>              3 이주        python server/migrations/add_outbox_ledger_state.py --apply
>                 뜻: 「added ledger_state - existing events 'done', N unprocessed back to NULL」 · 「idx_outbox_ledger_pending ensured」
>                    끝에 다시 찍는 보고에 done 이 거의 전부, <null = yet to follow> 이 N · index … valid=True
>                    「STOPPED at <단계>: waited 30s … pid … 」 면 그 pid 들이 아웃박스를 쥐고 있다(대개 아직 안 꺼진 앱) —
>                    그 세션을 끝내고(앱을 끄고) 3 을 다시. 칸은 이미 더해졌으면 그대로, 끊긴 색인은 지우고 다시 세운다
>              4 앱 켬       run_app.bat 전체 — 이주 «없이» 켜면 아웃박스 쓰기가 「column ledger_state does not exist」 로 실패
> 확인          python -m ledger followup     (server 폴더) — 「따라갈 일 K · 실패 F」. K 는 체인이 돌면 줄어들고, 일이 없으면 0
>              체인 워커 로그 [LedgerFollowUp] lap: N item(s) … M left in the queue — M 이 그 순간의 따라갈 일 수
> 뜻           실패 F 가 0 이 아니면 아래 목록에 이유가 찍힘 — 원인을 고친 뒤 python -m ledger followup --requeue-failed
>              K 가 줄지 않고 늘기만 하면 따라가기 루프가 안 도는 것 — 체인 워커 로그에 [LedgerFollowUp] batch failed 가 있는지
>              색인이 valid=True 가 아니면 따라가기가 매번 아웃박스를 훑는다 — 앱을 끄고 3 을 다시
> 급할 때       git revert <이 커밋> -> 재기동 (칸은 남아도 옛 코드가 안 읽는다 — 되돌릴 이주 없음)
> ```

---

> ## [10-02 밤] **원장 소스 선언 폼 — 기본값뿐인 read 는 접힌 한 줄 · exclude_when 칸 칩 · 비운 사건 시각은 Not an event (총괄 04cecc30f) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  탐색기 저작 계획(/admin/ontology-explorer/authoring/plan)에 read.exclude_when 줄이 선다
>              후보는 그 관계의 칸마다 {"column": <칸>, "blank": true}
>              매핑의 사건 시각 역할을 비우면 그 줄의 ground 가 not_an_event 「Not an event」
>              화면: read 가 Defaults · N 으로 접혀 시작 · Exclude when 은 칩만(마지막 칩을 빼면 키 지움)
>                    레코드 칩 글자는 후보마다 값이 다른 키만(read.occurred_at 칩도)
>              초안은 파일의 그 선언 그대로 연다(v5 파일은 로더의 v6 읽기 upgrade_setup 으로)
>              저장은 로더가 채우는 칸(read 기본값 · map.unit · map.input_columns)을 비워 둔다 — 계획이 채우는 다른 칸(implementation_version 등)은 전처럼 적힌다
>              map.unit 을 안 적은 소스의 Mapper unit 은 로더의 기본값(row, 묶는 소스는 group_by) — 빨간 칸 아님
>              이미 쓴 원장 · 원자는 안 바뀐다. 이미 적힌 선언은 다음 저장 때도 적힌 그대로
> 확인         관리자 화면 Ontology Explorer -> read 를 안 적은 소스 -> 초안 -> read 줄이 Defaults · N
>              펼쳐 Exclude when 줄을 열면 column · <칸> 칩
> 뜻           read 가 펼쳐져 있고 Exclude when 에 + Condition 만 있으면 재기동 전 서버(계획에 그 줄이 없음)
>              read 를 적은 소스는 펼쳐진 채 시작하는 것이 맞다(기본값이 아닌 칸이 있음)
>              read 를 안 적은 소스의 초안 편집기에 read 가 보이면 재기동 전 서버(초안이 기본값 채운 선언에서 열림)
> 급할 때       git revert <이 커밋> -> 재기동
> ```

---

> ## 🔴 [10-03 소유자] **공식 표를 제자리에서 비우고 다시 채우기 — 순서 전부 (총괄 35b76ba92 · 32bab7896 · 1472ec1cc · a3d19dc51) — 이주 «필요»(위 절, 앱을 끄고) · 재기동 «필요»(run_app.bat 전체, 한 번)**
>
> ```
> 0 코드        git pull — 복사 맵퍼 묶음(8990d408f) · 비우기 도구(81ffa8499) · 원장 따라가기 대기열(3bce75e88) · 이주 고침(이 커밋)
> 1 앱 끔       run_app.bat 전체를 닫는다
> 2 이주        python server/migrations/add_outbox_ledger_state.py --apply   (위 절의 2 · 3 — STOPPED 면 그 절대로)
> 3 표 설정      server/config/table_config.json 의 official_dt — composite_key_source 를 코어 칸으로 · column_types 에 "hold": "string"
> 4 원장 소스    config/ontology/ledger_config.json 에서 official_dt 를 읽는 소스의 read 에 "exclude_when": [{"column": "hold", "blank": true}]
> 5 앱 켬       run_app.bat 전체 — 3 · 4 를 한 번에 읽는다
>               확인: SELECT count(*) FROM information_schema.columns WHERE table_name = 'official_dt' AND column_name = 'hold'
>               뜻: 1 = hold 칸이 섰음 · 0 = 3 이 안 들어감(표 설정 파일 · 저장 위치를 다시 봄). 그리드 official_dt 에도 HOLD 칸이 보인다
> 6 비우기 보고   python server/scripts/empty_table.py official_dt
>               뜻: 행 · 칸 층 · 사람 층(비우면 사람이 고친 값도 같이 감) · 덮어쓰기 · 원장 소스와 원자 · 트리거 규칙. 아무것도 안 씀
> 7 비우기       python server/scripts/empty_table.py official_dt --apply --confirm-rows <6 의 행 수> --by <이름>
>               뜻: 「비움 … · 원자 N 거둠 · 아웃박스 이벤트 0」. 「거절: 지금 K 행」이면 그 사이 표가 움직임 — 6 부터 다시
>                  「비움」 줄 뒤 「원자 거둠」 전에 오류로 멈췄으면 표는 이미 빔 — 소스마다 python -m ledger.backfill --source <소스> --whole-source --apply (server 폴더)
>               시간: 시험 스키마 10,000 행(칸 층 80,000 · 원자 10,000) 1.03 s -> 100만 어림 103 s (운영은 안 쟀다)
> 8 체인 규칙 둘  config/chain_rules.json 에 RELEASE_LOG 「보류 포함 행 복사」의 두 규칙(둘 다 "is_batch": true) — 다시 세기 규칙 official_dt_hold_recount 에는 "enabled": false
>               까닭: 켜 두면 복사가 공식 행에 쓸 때마다 다시 세기가 한 번 더 돈다(세기 질의가 한 번씩 더) — 다시 채우기 내내
>               -> 어드민 Reload Configs & Code (체인 탭 편집기로 저장하면 그 자리에서 다시 읽음)
> 9 다시 채우기   python server/scripts/chain_replay_cli.py replay dt_log_to_official_dt --apply
>               뜻: 이벤트를 1,000 행씩 쌓고 바로 끝남. 복사는 체인 워커가 돈다 — 그동안 다른 체인 일은 그 뒤에 줄 선다
>               시간: 시험 스키마 10,000 행에 체인 64.89 s · 원장 21.59 s((가) 위, 운영 같은 연결 풀) -> 100만 어림 약 2.4 시간 (운영은 안 쟀다)
> 10 다시 세기 켬  체인 대기열에서 9 의 줄이 사라지면 official_dt_hold_recount 의 "enabled": false 를 지우고 Reload Configs & Code
> 11 확인        체인 대기열 화면 — 9 는 «한 줄»(잡 하나), 다 돌면 없음
>               SELECT count(*) FROM official_dt WHERE hold IS NULL OR hold = ''    -- 같은 키 원천 행들의 값이 갈린(또는 원천이 없는) 공식 행 수
>               python -m ledger census --source <official_dt 를 읽는 소스>        (server 폴더) — 「표 N · 색인 N · 남은 0」이어야
>                  남은 이 0 이 아니면   python -m ledger.backfill --source <그 소스>   (색인에 없는 행만 번역)
>                  색인이 표보다 크면    그만큼 «표엔 없고 색인엔 있는 행» — python -m ledger.backfill --source <그 소스> --whole-source --apply
>               python -m ledger followup (server 폴더) — 「따라갈 일 0 · 실패 0」이어야. 실패가 있으면 이유를 고치고 --requeue-failed
> 급할 때       9 를 멈춤: python server/scripts/chain_pause_cli.py pause --reason "다시 채우기 멈춤" (다시: ... resume)
>               규칙 둘을 "enabled": false -> Reload Configs & Code
> ```

---

> ## [10-02 밤] **표 통째로 비우기 — server/scripts/empty_table.py (총괄 35b76ba92) — 이주 «불필요» · 재기동 «불필요»(새 명령)**
>
> ```
> 무엇          표 하나의 행 · 그 표의 칸 층 · 덮어쓰기를 한 트랜잭션에 지우고, 그 표를 읽는 원장 소스의 원자를 거둔다. 아웃박스 이벤트 0
>              내일 공식 표 다시 채우기의 «순서 전부»는 다음 착지(복사 맵퍼 묶음)의 RUN.md 에 들어간다
> 보고          python server/scripts/empty_table.py <표>
>              뜻: 행 · 칸 층 · 사람 층(비우면 사람이 고친 값도 감) · 덮어쓰기 · 원장 소스와 원자 · 트리거 규칙. 아무것도 안 씀
> 비우기        python server/scripts/empty_table.py <표> --apply --confirm-rows <보고의 행 수> --by <이름>
>              뜻: 「비움 … · 원자 N 거둠 · 아웃박스 이벤트 0」. 「거절: 지금 K 행」이면 그 사이 표가 움직임 — 보고부터 다시
>                 「비움」 줄 뒤 「원자 거둠」 전에 오류로 멈췄으면 표는 이미 빔 — 소스마다 python -m ledger.backfill --source <소스> --whole-source --apply (server 폴더)
>              시간: 시험 스키마 10,000 행(칸 층 80,000 · 원자 10,000) 0.99 s -> 100만 어림 99 s
> 급할 때       없음 — --apply 전에는 아무것도 안 쓴다
> ```

---

> ## [10-02 밤] **보류 포함 행 복사 맵퍼 copy_rows_with_hold (총괄 3211e9000 · 3ba1d1dd4) — 이주 «불필요» · 재기동 «필요»(체인 워커)**
>
> ```
> 무엇이 바뀌나  제품 맵퍼 하나(server/mappers/hold_copy.py, 추적됨). 제품 코드는 그대로
> 쓰는 법       RELEASE_LOG 「보류 포함 행 복사」 예시 — 대상 표에 hold 칸 · 규칙 둘(복사 · 보류 다시 세기) · 원장 소스 exclude_when 한 줄
>              내일 공식 표 다시 채우기 순서는 다음 착지(빠른 비우기)의 RUN.md 에 «전부» 명령으로 들어간다
> 확인         재기동 뒤 체인 규칙 화면에서 두 규칙에 거절이 없는지 · 원천 행 하나 저장 -> 공식 행 hold = agreed
>              같은 키에 값이 다른 원천 행 하나 더 -> hold 빈 값 · 원장에서 그 행 원자가 거둬짐
> 뜻           hold 빈 값 = 같은 키 원천 행들이 다른 값 묶음 둘 이상
>              원천 행을 지운 뒤에도 빈 값이면: 남은 원천 행들이 아직 갈린 것(가려진 값을 지운 경우는 10-03 e11bb4de0 착지로 다시 셈)
>              그 착지 «전»에 지운 행이면 다시 세기 규칙을 그 행에 리플레이
>              python server/scripts/chain_replay_cli.py replay official_dt_hold_recount --row-ids <공식 행 row_id> --apply
> 급할 때       두 규칙을 enabled: false (또는 chain_rules.json 에서 지움) -> 체인 워커 재기동
> ```

---

> ## [10-02 저녁] **메인 그리드 — row_id 가 있는 표 끝에 ROW_ID 칸 · 그 칸으로 거르기 (총괄 e67ef53f3 · d692af408) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  GET /tables/{표}/schema 의 columns 가 created_at · updated_at 뒤에 row_id 로 끝난다 — 그 관계의 모델에 row_id 가 있을 때만
>              (모든 표 · row_id 를 선언한 보기. display_columns 에 이미 적은 표는 그 자리)
>              row_id 없는 보기에 row_id/id 거르기 -> 422 「'<표>' has no row_id, so it cannot be filtered by 'row_id'」
>              화면: 메인 그리드 맨 오른쪽 ROW_ID 칸, 머리 아래 거르기 칸. 맵 편집기 X · Y · Val 고르기에는 시스템 칸이 안 나옴
> 확인         curl -s http://localhost:8080/tables/<표>/schema  -> columns 의 마지막이 "row_id"
> 뜻           표에서 마지막이 updated_at 이면 재기동 전 서버. row_id 를 선언 안 한 보기는 updated_at 으로 끝나는 것이 맞다
>              화면에 ROW_ID 칸이 없으면(표에서) 화면 새로 받기 전
> 급할 때       git revert <이 커밋> -> 재기동. 화면은 row_id 가 안 오면 그 칸을 안 그린다
> ```

---

> ## [10-02 밤] **원장 소스 — 시각은 사건 엣지에만 · read 는 안 적어도 됨 (총괄 0c9b6e3c0) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  bind.occurred_at 을 안 적은 매핑 = 사건 엣지 아님(원자 basis 'ingested', 저장 시각은 같은 행의 사건 시각 — 사건 id 하나)
>              read 칸을 안 적으면 제품이 채움(unit · identity · order_by · group_by · occurred_at · registration_probe · map.unit · input_columns)
>              적은 선언은 그대로 — 박스 미리보기 5 소스 · 원자 1,198 가 전후 같음(사건 id · 시각 · basis · 번역 버전), 묶음 해시 같음
> 확인         재기동 뒤  python -m scripts.migrate_ledger_slim_sources   (미리보기, 아무것도 안 씀 — server 폴더에서)
> 뜻           「movable - atoms unchanged」 옮겨도 원자가 같다 · 「movable - atoms change」 옮기면 시각 · 사건 id 가 바뀐다
>              이 박스 선언은 setup_version 5 라 미리보기만 된다 — 옮기려면 먼저 v6 이주
> 옮기기       --apply --source <소스>  (고른 소스만)
>              박스에서 `dt_job` 을 옮기면 원자 866,192 개의 시각과 사건 id 가 바뀌고, 다시 번역은 원천 행 535,559 × 1,000 행당 5.85 s(박스에서 잰 율) ≈ 52 분입니다.
>              그 소스는 --change-atoms 를 같이 주고, 뒤에 python -m ledger.backfill --source dt_job --whole-source --apply
>              --drop-retired  아무도 안 읽는 옛 바인딩 칸(approval_status) 지우기 — 묶음 해시가 한 번 바뀜(새 원자만 새 번역 버전)
> 급할 때       git revert <이 커밋> -> 재기동
> ```

---

> ## [10-02 저녁] **메인 그리드 표 드롭다운 — table_config 의 group 으로 묶기 + 검색 (총괄 685f236d7) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  GET /tables 에 groups 가 붙는다 — {표: 묶음}, group 을 안 적은 표는 없음. tables 목록은 그대로
>              화면: 표 드롭다운이 그 묶음 이름 아래로 묶이고(Other 맨 아래), 앞에 검색 칸(Search tables)
> 확인         curl -s http://localhost:8080/tables  -> 키에 groups 가 있다
> 뜻           groups 가 {} 이면 아직 아무 표도 group 을 안 적은 것 — 드롭다운은 오늘처럼 묶음 없는 목록(정상)
>              묶으려면 server/config/table_config.json 의 그 표 항목에 "group": "이름" 한 줄 -> 재기동(어드민 Reload Configs & Code 로도 되는지는 안 쟀음)
>              groups 키 자체가 없으면 재기동 전 서버
> 급할 때       git revert <이 커밋> -> 재기동. 화면은 groups 가 없으면 오늘 모양이라 서버만 되돌려도 된다
> ```

---

> ## [10-02 저녁] **원장 — 시각 값 문장이 사건 시각 대신 바인딩한 칸 값을 싣는다 (총괄 0c9b6e3c0 ③) — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  value_type "timestamp" 술어를 declarative-role 로 번역하면 값 = bind.value 의 칸(전에는 사건 시각)
>              폼: basis 소스의 그 값 칸에서 「This square is not read」가 빠진다(occurred_at 칸은 그대로)
> 확인         grep -n '"value_type": "timestamp"' server/config/ontology/ledger_config.json
> 뜻           안 나오면 할 일 없음(이 박스는 0 — 걸린 소스 · 매핑 · 원자 0)
>              나오면 그 술어를 매핑하는 소스 중 map.implementation_id 가 declarative-role 인 소스의 원자가 사건 시각을 값으로 들고 있다
>              그 소스만 다시 번역(아래) — 돌리기는 소유자
>                python -m ledger.backfill --source <소스> --whole-source            (미리보기 — relation_rows 가 행 수, 안 씀)
>                python -m ledger.backfill --source <소스> --whole-source --apply
>                시간 어림  행 수 × 5.85 s / 1,000 (박스 다이 소스에서 잰 율)
> 급할 때       git revert <이 커밋> -> 재기동
> ```

---

> ## [10-02 저녁] **체인 대기열 — 소급 잡 하나는 한 줄 (run_id) · 접기는 자르기 전 — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  소급 잡이 도는 동안 낸 이벤트와 그것이 깨운 체인 쓰기가 payload 에 run_id 를 싣는다
>              GET /admin/chain/queue 의 waiting_transactions = «줄»: 잡(run_id · op) · 트랜잭션 · 그 행 하나 중 하나
>                 한 줄 = run_id · op · transaction_id · events(남은 이벤트) · rows(그 이벤트가 싣는 행) · 가장 오래 기다림
>              🔴 rows 의 뜻이 바뀜: 전에는 «이벤트 수», 이제 «행 수». 이벤트 수는 events
>              listed = {lines, lines_total, cap, capped} — 상한은 «줄» 200(전에는 «이벤트» 200, rows_scanned 은 없어짐)
> 확인         재기동 뒤 소급 잡 하나(어드민 Retroactive 탭) -> 체인 대기열 화면에 그 잡이 한 줄
>              curl -s -H "X-Admin-Token: <토큰>" http://localhost:8080/admin/chain/queue  -> waiting_transactions[].run_id · op
> 뜻           같은 잡이 두 줄이면: 재기동 전에 큐에 들어간 이벤트(run_id 없음) — 다 빠지면 한 줄
>              op 가 비어 있고 run_id 만 있으면 retroactive_runs 에 그 실행 행이 없는 것
> 급할 때       git revert <이 커밋> -> 재기동. 이벤트의 run_id 키는 읽는 쪽이 없으면 무해
> 화면         클라 레인이 이 줄 모양으로 대기열 화면을 바꾼다(그 전까지 화면의 rows 칸은 «행 수»를 보이고, 잡 줄의 tx 칸은 빈다)
> ```

---

> ## [10-02 오후] **배포 뒤 운영 순서 — 다이 references · 키 철자 하나 (총괄 6736254fd) — 이주 «불필요» · 재기동 «필요»**
>
> ```
> 1 선언     config/ontology/ledger_config.json 의 die@1 에 references 목록 하나(아래 references 절의 예시) — 재기동 «전»에 적어도 된다
> 2 재기동   run_app.bat 전체. 로그 [Ledger] re-stamped N cursor(s) … — 다이를 부르는 소스들의 지문이 새로 찍힘(자리 그대로)
> 3 다이를 부르는 소스 전부 다시 번역 — 키 철자 하나(7.0 -> '7', 7350027a6) 와 references 원자가 같이 들어온다
>     소스 목록   GET /api/ledger/declaration 의 sources[].emits 에 in_container@1 이 있는 소스
>     소스마다    python -m ledger.backfill --source <소스> --whole-source            (미리보기 — relation_rows 가 행 수, 안 씀)
>                python -m ledger.backfill --source <소스> --whole-source --apply
>     시간 어림   행 수 × 5.85 s / 1,000 (박스 die_inspection 117,742 행 = 11분 28초) — 1,000 행당 5 s 규격을 넘는다
> 뜻           3 을 다 돌리기 전에는 같은 다이가 두 철자로 갈려 걷기에서 두 노드로 보인다 — 다 돌리면 하나
>              한 소스만 돌리고 멈추면 그 소스의 다이만 새 철자 — 나머지를 이어서 돌린다
> 급할 때       선언에서 references 를 지우고 재기동(이미 쓴 원자는 3 을 다시 돌리면 거둬진다)
> ```

---

> ## [10-02 오후] **그리드 행 지우기 — 답은 지운 수 · 트랜잭션만 — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  POST /tables/<표>/rows/batch_delete 의 답 = {status, deleted_count, transaction_id} — created_logs 가 빠짐
>              행마다 이력은 그대로 audit_logs 에, 다른 화면은 그대로 batch_row_delete 방송으로 받음(500 행 묶음마다 그 행들의 이력)
> 확인         재기동 뒤 그리드에서 행 몇 개 고르고 🗑️ Row -> 아래 줄 Deleting … · N s 가 오르다 Deleted N rows · S s
>              다른 탭에 같은 표를 열어 두면 그 행들이 그쪽에서도 빠짐(방송)
> 뜻           Deleted 가 뜨는데 다른 탭에서 안 빠지면 방송이 안 간 것 — 서버 로그의 웹소켓 줄을 본다. 답 자체가 늦으면 지우기 본체(DB) 시간
> 급할 때       git revert <이 커밋> -> 재기동(화면은 deleted_count 만 읽으므로 되돌려도 화면 변화 없음)
> ```

---

> ## [10-02 오후] **원장 펼친 보기에 occurred_at_basis 칸 · references 예시는 목록 모양 — 이주 «필요»(보기만) · 재기동 «불필요»**
>
> ```
> 무엇이 바뀌나  ledger_atom_rows 보기 맨 끝에 occurred_at_basis(빈 값 = 사건 시각, ingested = 아님)
>              RELEASE_LOG · 아래 references 절의 선언 예시가 «목록 하나» 모양 — 재기동 전 옛 코드도 받아들인다
> 돌릴 명령     python server/migrations/add_ledger_atom_rows.py --report    (보기 있음 확인)
>              python server/migrations/add_ledger_atom_rows.py             (보기를 그 자리에서 다시 만듦 — 원장 · 원천 표 그대로)
>              config/table_config.json 의 ledger_atom_rows.column_types 맨 끝에 "occurred_at_basis": "string" (샘플 그대로)
> 뜻           메인 그리드의 ledger_atom_rows 에 그 칸이 보이면 끝. 칸만 비어 보이면 표 선언은 됐고 이주를 안 돌린 것
>              이주가 「cannot change name of view column」으로 거절하면 보기를 손으로 바꾼 설치 — 보기를 지우고(DROP VIEW ledger_atom_rows) 다시 돌린다
> 급할 때       표 선언에서 그 한 줄을 지우면 그리드에서 사라진다(보기는 그대로 둬도 됨)
> ```

---

> ## [10-02 오후] **바인딩 · 묶음 · when 칸은 맵퍼 입력 칸에 다시 안 적는다 — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  검증기가 바인딩(bind.mappings 의 칸 · bind.entities 속성 칸) · map.unit.columns 를 map.input_columns 에 다시 적으라고 안 한다
>              그 칸은 읽기가 저절로 싣는다 — bind.entities 속성 칸도(전에는 안 실려 번역에서 missing_binding_column)
>              ⚰️ 10-03 2a8d9073c 로 Mapper input_columns 칸째 사라짐 — 아래 확인은 할 수 없다
> 확인         (⚰️) 재기동 뒤 탐색기에서 소스를 열어 Mapper input_columns — 바인딩한 칸이 눌린 채 잠겨 있다
>              입력 칸에서 바인딩한 칸을 빼고 저장 · 적용 -> 거절 없음(전에는 「Profile column 'X' at … is missing」)
> 뜻           체인 데몬이 뜰 때 [Ledger] re-stamped N cursor(s) … 줄 — bind.entities 속성이 있는 소스(박스: dt_job)의 지문만 새로 찍힘.
>              자리 그대로, 다시 읽는 행 없음. [Ledger] N cursor(s) were NOT re-stamped 줄이 나오면 그 소스가 멈춘 것 — 줄 뒤 사유를 본다
> 급할 때       git revert <이 커밋> -> 재기동. 단 이 커밋 뒤에 입력 칸을 비워 저장한 선언은 되돌리면 다시 거절된다
> 재기동 뒤 로그 위 re-stamped 줄
> ```

---

> ## [10-02 오후] **엔티티 references 가 원자를 쓴다(다이 → 웨이퍼) · 사건 시각 아닌 원자는 창을 늘 지난다 — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  entities.<타입>.references(하나 또는 목록)를 적으면 그 엔티티를 부르는 소스마다 그 엣지 원자를 하나 더 쓴다(분자당 하나)
>              그 원자의 occurred_at_basis = ingested(사건 시각 아님). 새 칸 · 새 값 · CHECK 교체 없음
>              사건 시각 아닌 원자(이것 · 원래 ingested 인 dt_job)는 걷기 시간 창이 늘 지나보내고 · 창 밖 수에 안 세고 ·
>              응답 엣지 occurred_at 이 null · 처음 본 시각(gaps)에 안 든다. 최신값 · 가져오기 순서는 그대로
> 선언(운영자가)  config/ontology/ledger_config.json 의 entities 에서, 예:
>                "die@1": {"keys": [...그대로...], "references": [{"edge": "in_container@1",
>                  "to": {"entity": "wafer@1", "keys": {"wafer": "mat_id"}}, "from": {"when": {"mat_type": "Wafer"}}}]}
>              목록 모양으로 — 재기동 전 옛 코드도 받아들인다(한 개 객체면 옛 코드가 die@1 을 거절해 다이 소스가 멈춘다)
> 확인 명령     재기동 뒤 로그에 [Ledger] entity|die@1 is NOT read: … 줄이 없어야 한다(있으면 그 줄 뒤가 거절 사유 — 술어 · 키 대응 · when)
>              다이를 부르는 소스를 소스마다 다시 번역:  python -m ledger.backfill --source <소스> --whole-source --apply
>              확인:  SELECT count(*) FROM ledger_events WHERE predicate = 'in_container' AND occurred_at_basis = 'ingested'
> 뜻           그 수가 늘면 references 원자가 쓰인 것
>              체인 데몬이 뜰 때 [Ledger] re-stamped N cursor(s) … 줄 — 선언이 바뀐 소스의 커서 지문을 새로 찍음(자리 그대로), 그 뒤 새 행부터 references 원자
>              이미 번역된 옛 행은 위 다시 번역으로만 생긴다
> 급할 때       선언에서 references 를 지우면 새 원자는 안 생긴다(이미 쓴 것은 남음 — 그 소스를 다시 번역하면 거둬진다). 코드는 git revert -> 재기동
> 재기동 뒤 로그 위 두 줄
> ```

---

> ## [10-02 낮] **정적 «씨앗»의 첫 걸음은 동적 노드로 간다 — 걷기 — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  씨앗이 정적 타입(선언 class: static)이면 그 씨앗에서 나가는 첫 걸음이 동적 노드로 간다
>              예: 레시피 씨앗 + follow=processed_with -> 그 레시피를 쓴 웨이퍼들. 전에는 노드 1 · 엣지 0
>              걷는 도중 만난 정적 노드는 오늘과 같다(웨이퍼 -> 레시피 -> 다른 웨이퍼 0)
>              씨앗이 동적인 걷기 · 대조는 답이 그대로
> 확인 명령     curl "http://<서버>:<포트>/api/ledger/subgraph?id=<레시피 노드 id>&follow=processed_with&hops=2&fanout_limit=20"
> 뜻           nodes 에 웨이퍼가 있다                       새 코드
>              bundles 에 {far_type: wafer, count: N}       웨이퍼가 fanout_limit 을 넘었다 — 그리지 않고 수로 답했다
>                 truncated.claims 가 true 면 그 N 은 «읽은 만큼»이다(전체 수가 아니다)
>              nodes 에 레시피 하나뿐 · edges 0              서버가 옛 코드 — 재기동이 안 됐다
>              ⚠️ 걷기 화면의 경로 목록은 이 첫 걸음을 아직 안 내놓는다 — 클라 착지 뒤에 화면에서 고를 수 있다
> 급할 때       이 커밋을 되돌린다(git revert) -> 재기동. 데이터는 안 바뀐다
> 재기동 뒤 로그 새 로그 줄 없음
> ```

---

> ## [10-02 낮] **걷기 시작점 목록이 노드를 «두 쪽»에서 읽는다 — /api/ledger/key-values — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체) + 브라우저 강력 새로고침**
>
> ```
> 무엇이 바뀌나  목록의 노드를 주어 쪽 «과» 목적어 쪽에서 읽는다(gaps._nodes_of_type_sql). 목적어로만 나오던 타입(이 박스 recipe · defect_kind)이 이제 목록에 나온다
>              타입은 같은 이름만 — 전에는 lot 목록에 lot_slot 의 lot 키가 섞였다
>              순서는 «값 오름차순»(전: 빈도 내림차순). count 는 그 값의 노드를 두 쪽에서 부르는 원자 수
>              전선 칸 subjects -> nodes · limits.scan_rows -> limits.scan_nodes · scanned 는 «읽은 노드 수»
>              client2/dist 를 같이 다시 빌드했다 — 화면이 nodes 를 읽는다
> 확인 명령     curl "http://<서버>:<포트>/api/ledger/key-values?type=recipe"
> 뜻           "nodes": [...] · "order": "value_asc"        새 코드
>              "subjects": [...]                             서버가 옛 코드 — 재기동이 안 됐다
>              걷기 화면 목록이 «모든 타입»에서 비고 「원장에 주어로 없습니다」     서버 · 번들 중 하나만 새것(둘 다 같은 증상)
>                                                           -> 서버 재기동 «그리고» 브라우저 강력 새로고침(Ctrl+F5)
>              "nodes": [] · "scan_truncated": false          그 타입은 원장 어느 쪽에도 노드가 없다
> 급할 때       이 커밋을 되돌린다(git revert) -> 재기동 + 새로고침. 데이터는 안 바뀐다
> 재기동 뒤 로그 새 로그 줄 없음
> ```

---

> ## [10-01 밤] **이미지 참조 — 이미지는 «전부» 서버가 받아서 보낸다 · 브라우저가 답을 3600 초 든다 — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  칸 값 하나로 이미지를 가리킨다 — https://… 그대로, 또는 <출처 이름>:<경로 또는 키>. 칼럼 타입 낱말은 "image"(저장은 글자)
>              출처는 server/config/image_sources.json 한 파일 — 샘플 server/config/sample/image_sources.json.sample 에 셋:
>                 folder  {"kind": "folder", "root": "D:/shared/photos"}                         photos:2026/10/a.png
>                 db      {"kind": "db", "connection": {dialect · host · port · database · user · password_env},
>                          "query": "SELECT image FROM images WHERE image_id = :key"}             inspection_db:IMG-001
>                 url     {"kind": "url", "base": "https://vendor.example.com/images/"}         vendor:a.png
>              🔴 비밀번호는 파일에 0 — password_env 에 «환경변수 이름»만. db 출처는 «읽기 전용 사용자»를 권한다
>              🆕 url 출처도 https:// 칸도 서버가 받아서 보낸다 — 브라우저를 그 주소로 보내는 답은 없다
>                 -> 사용자 PC 가 이미지 호스트에 못 닿아도 보인다. 그만큼 서버가 바깥 주소를 대신 읽는다(부하)
>                 받은 답은 image/* · 20,971,520 바이트 이하 · 리다이렉트 아님 — 넘으면 다 받기 전에 끊는다
>              옛 선언의 "proxy" 칸은 읽지 않는다 — 있어도 거절 안 함, 지워도 된다
>              🆕 답(파일 · 바이트)에 Cache-Control: private, max-age=3600 — 거절에는 안 붙는다
> 확인 명령     curl -i "http://<서버>:<포트>/api/image?ref=photos:a.png"
>              curl -sI "http://<서버>:<포트>/api/image?ref=photos:a.png" | findstr /i cache-control
> 뜻           200 + 이미지                                   읽힘
>              400 "… outside the root …"                     folder 경로가 root 밖(.. · 절대경로)
>              400 "… leaves the host of image source …"      url 출처에서 칸 값이 호스트를 바꾸려 했다(base 가 / 로 안 끝날 때 @ · . · :포트) — base 를 / 로 끝내면 그 값은 경로
>              404 "no file … / no image for key …"           파일 · 키가 없다
>              404 "image source … is not declared"           선언에 없는 출처 이름
>              500 "… must bind :key and nothing else"        db 출처의 query 가 :key 하나만 묶지 않는다
>              500 "… reads its password from X, which is not set"   그 환경변수가 서버 프로세스에 없다
>              500 "… another reference twice"                db 값이 글자면 참조로 «한 번 더» 푸는데 두 번째도 글자였다
>              502 "image source '<이름>' could not be read: …"   db 연결 · 질의 실패 — 뒤의 첫 줄이 사유
>              502 "… could not be fetched: …"                바깥 주소에 못 닿음(이름 · 연결 · 시간 초과)
>              502 "… answered a redirect (3xx) - not followed"   바깥이 다른 곳으로 넘기려 했다 — 넘겨진 주소로 고친다
>              502 "… answered '<type>', not an image"        바깥 답이 그림이 아니다(사내 페이지 · JSON)
>              502 "… is larger than … bytes - not read further"   상한(image_sources.MAX_BYTES)을 넘었다
>              🔴 배포 뒤 이미지를 «같은 참조»로 바꿔 놓으면 이미 본 화면은 최대 3600 초 옛 그림을 보인다
> 급할 때       image_sources.json 을 지우면 출처 참조가 전부 404(https:// 칸은 여전히 받아 옴). 캐시는 image_sources.CACHE_SECONDS 를 0 으로 -> 재기동
> 재기동 뒤 로그 새 로그 줄 없음 — 거절은 응답의 detail 로 말한다
> ```

---

> ## [10-01 밤] **잡 단위 거둠으로 지운 행이 이력 · 원장 후속에 간다 + 맵퍼 표면에 find_links · unknown_words — 이주 «불필요» · 재기동 «필요»(run_app.bat 전체)**
>
> ```
> 무엇이 바뀌나  allow_retraction 이 행을 지우는 길이 맵 퍼지와 «같은 문»(crud.purge_map_rows — 그리드 지우기는 따로)
>              -> 거둠으로 지운 행마다 DELETE 이벤트 · 행 지움 이력. 원장 후속이 그 행에서 나온 원자를 거두고, 체인 거둠 바퀴가 그 행이 먹인(도장 있는) 칸을 거둔다
>              맵퍼는 from mapper_sdk import find_links, unknown_words 로 부른다 (from utils import text_links 도 계속 된다)
> 뜻           `🔄 [DtMapRetraction] … retracted N stale row(s)` 뒤에 같은 표의 `[ChainRetract] table=<표> deleted_rows=N …` 가 따라 나오면 이 변경이 돈 것
>              그 표를 지켜보는 규칙 중 «되돌릴 수 없는» 종류가 있으면 거둠마다 `[ChainRetract] <규칙>: …` 경고 한 줄씩 — 이 박스는 dt_map 를 지켜보는 규칙 0 · 경고할 것 0
>              이미 거둠으로 지운 행에서 나온 원자(소급) — 이 박스 원자 0 (거둠 표 dt_map 는 원장 참조 0)
>              운영에서 세기: SELECT count(*) FROM ledger_source_row_ref r WHERE r.relation = '<거둠 표>'
>                             AND NOT EXISTS (SELECT 1 FROM <거둠 표> x WHERE x.row_id = r.row_id)
> 급할 때       이 커밋을 되돌린다(git revert) -> 거둠이 다시 손으로 지우고 이벤트 · 이력이 안 남는다. 이미 남은 이력 · 거둬진 원자는 그대로
> 재기동 뒤 로그 위 두 줄 — 거둠이 일어날 때만
> ```

---

> ## [10-01 밤] **글에서 원인 -> 현상 후보 — server/utils/text_links.py — 이주 «불필요» · 재기동 «불필요»(새 파일)**
>
> ```
> 무엇이 바뀌나  소유자 @mapper 가 import 해 쓰는 순수 함수 둘 — find_links(text, names, links) · unknown_words(texts, names, links). 다른 코드 무변
> 가이드        docs/guide/TEXT_LINKS_GUIDE.md — 표 넷 · 짝짓는 규칙 두 줄 · 맵퍼 예 · 규칙 선언(allow_retraction) · 사전 고친 뒤 다시 돌리기 · 남는 것 둘
> import 한 줄  from utils import text_links
> 뜻           글에 말이 있는데 후보 0 -> 연결 말 사전에 cause 행(side 포함)이 없거나, 그 side 쪽에 노드가 없다. unknown_words 로 사전이 못 덮은 낱말을 본다
>              연결 말 행의 meaning 이 다섯 밖이거나 cause 행에 side 가 없으면 그 행 번호를 대고 ValueError -> 그 규칙의 실패 로그로 보인다
>              속도(박스, 합성 naming phrases 1000 · link phrases 7 · texts 1000 x 20 sentences (seeded synthetic)): 글 하나 9.7 ms 중 사전 짓기 8.3 ms — 글 1,000 건 10.56 s
> 급할 때       그 규칙을 끈다(enabled false). 이 모듈은 부르는 맵퍼가 없으면 안 돈다
> 재기동 뒤 로그 새 줄 없음. 이 모듈을 고친 «뒤»에는 체인 워커 재기동 — 이미 읽힌 모듈은 다시 안 읽는다
> ```

---

> ## [10-01 밤] **원장 «펼친 보기» ledger_atom_rows — 그리드에서 원자를 평문으로 · 원천 row_id 로 — 이주 «필요» · 재기동 «필요»**
>
> ```
> 무엇이 바뀌나  읽기 전용 보기 ledger_atom_rows: 한 행 = (원자, 원천 행). 주어 · 목적 · 수식어는 저장 철자 그대로의 평문(키=값 / …)
>              source_row_id 로 거르면 그 행이 낳은 원자가 전부 나온다. 원천 행이 없는 원자(뷰를 읽던 소스)는 원천 칸이 빈 한 줄
>              원천 행 참조 표에 색인 둘(이음 · row_id). 원장 표는 무변
> 돌릴 명령     python server/migrations/add_ledger_atom_rows.py --report     (있고 없음 · 크기)
>              python server/migrations/add_ledger_atom_rows.py              (색인 둘 CONCURRENTLY + 보기 — 쓰기 계속됨, IF NOT EXISTS 라 다시 돌려도 같음)
>              table_config.json 에 "ledger_atom_rows" 항목을 출고 샘플에서 그대로 복사 -> 재기동(run_app.bat 전체) -> 그리드 표 목록에 뜸
>              ⚠️ 이 박스는 이주가 «이미» 돌았다(보기 · 색인 둘 있음) — table_config 항목만 남음
> 뜻           이 박스: 색인 79 MB + 67 MB
>              첫 쪽 100 행 0.03 s · row_id 하나 1.85 s · 주어 평문 일부 10.9 s · 전체 행 수 10.5 s (2,334,076 행)
>              전체 행 수는 그리드의 미뤄 세기(defer_total -> /data/count, 캐시)로 — 첫 쪽을 막지 않는다
>              row_id · 주어 거르기는 원장 표에 색인을 안 넣어 원장 전체를 훑는다(총괄 판정 — 원장 표에는 색인을 안 넣기로)
>              참조 표 쓰기 비용: 1,000 행당 44.5 / 47.1 ms -> 62.5 / 65.5 ms (시험 DB, 참조 길이 882 · 지우고 다시 넣기)
> 급할 때       table_config 의 그 항목을 지우면 그리드에서 사라진다. 보기 · 색인은 DROP VIEW ledger_atom_rows · DROP INDEX CONCURRENTLY 두 색인
> 재기동 뒤 로그 새 로그 줄 없음
> ```

---

> ## [10-01 밤] **걷기 «도로 내려가지 않기» — 역 술어 칸 `inverse_of` · 같은 타입 형제만 막음 — 마이그레이션 «없음» · 재기동 «필요»**
>
> ```
> 무엇이 바뀌나  걷기가 형제로 퍼지지 않는다: 같은 술어를 반대 방향으로(또는 선언된 역 술어를 같은 방향으로) 되밟아
>              «출발한 노드와 같은 타입»으로 가는 걸음을 막는다 — 다이 -> 웨이퍼 <- 다이. 다른 타입으로 가는 길은 걷는다
>              어휘 술어에 칸 하나 inverse_of — 걷기만 읽는다(소스 지문 · 원장 무변, 소급 0)
> 운영자가 적을 것  ledger_config.json 의 vocabulary 에 짝 하나 (한쪽만 적어도 양쪽으로 읽힘):
>                "inspected@1": { …, "inverse_of": "in_container@1" }
>              적지 않은 짝은 그 두 술어로 형제가 «오늘처럼» 퍼진다(같은 술어 되밟기만 막힘)
> 돌릴 명령     재기동 — run_app.bat 전체 (짝을 적은 뒤에도 재기동이 걷기에 읽힘을 보장)
> 뜻           이 박스 다이 씨앗(라우트 기본): 오늘 노드 400 · 엣지 892(잘림) -> 짝 없음 노드 400 · 엣지 795 -> 짝 적은 사본 노드 15 · 엣지 25(잘림 없음)
>              짝 없이 빠지는 것은 같은 술어 형제 걸음뿐 — hops 3 비교에서 빠진 노드 65 개 전부 «형제 걸음으로만 닿던» 노드
>              검증 거절: unknown_id(없는 술어) · invalid_predicate(두 끝이 뒤집혀 안 맞음 / 역이 둘)
> 급할 때       짝을 지우면 그 두 술어는 다시 따로 걸린다. 규칙 자체를 되돌리려면 커밋 되돌리기
> 재기동 뒤 로그 새 로그 줄 없음 · 짝이 틀리면 선언 적재가 그 이름으로 거절
> ```

---

> ## [10-01 밤] **걷기 노드 이름표 — 선언 키 전부 · 키 철자 — 마이그레이션 «없음» · 재기동 «필요»**
>
> ```
> 무엇이 바뀌나  걷기 응답 노드의 label = 그 타입 «선언»의 키 순서 전부(앞 두 값이 아니라). 수는 원장 키 접기와 같은 철자(1 · 1.0 -> 1)
>              선언에 없는 타입은 오늘 모양 그대로 · 키 하나짜리(웨이퍼 · 랏)는 오늘과 같음
> 돌릴 명령     재기동 — run_app.bat 전체
> 뜻           이 박스 웨이퍼 SYN-CX-BW-001 걷기: 다이 278 개의 이름표 42 가지 -> 278 가지 · 다이 아닌 노드 122 개 이름표는 그대로
> 급할 때       커밋 되돌리기 (데이터 · 선언 변경 없음)
> 재기동 뒤 로그 새 로그 줄 없음
> ```

---

> ## [10-01 밤] **걷기 펼침 묶음 — `fanout_limit` · `expand` · `bundles` — 마이그레이션 «없음» · 재기동 «필요»**
>
> ```
> 무엇이 바뀌나  걷기(GET /api/ledger/subgraph)에 요청 칸 둘: fanout_limit=<정수> · expand=<노드 id>|<술어>|<방향>
>              한 노드에서 한 술어 · 한 방향으로 먼 노드가 fanout_limit 을 «넘으면» 그리지 않고 응답 bundles 에 한 줄
>              칸이 없으면 오늘과 같음(bundles 키도 없음)
> 돌릴 명령     재기동 — run_app.bat 전체 (라우트 인자)
>              확인: GET /api/ledger/subgraph?id=<다이 id>&fanout_limit=20  -> 응답에 bundles
> 뜻           bundles 의 count = 그 묶음을 펼치면 그려지는 먼 노드 수(이미 그린 노드 포함). 묶음은 노드가 아니고 truncated 와 별개
>              이 박스 다이 씨앗: 칸 없으면 노드 400(잘림 nodes) · fanout_limit=20 이면 노드 15 · 묶음 13 · 잘림 None
>              원자는 오늘처럼 읽는다 — 묶음은 «그리는 수»를 줄이지 원자 예산을 아끼지 않는다
> 급할 때       요청에서 fanout_limit 를 빼면 오늘과 같음(서버 스위치 없음)
> 재기동 뒤 로그 새 로그 줄 없음
> ```

---

> ## [10-01 저녁] **원장 선언 v6 — prepare 절 은퇴 · lot_event 은퇴(계보는 체인) · 맵퍼 칼럼 이름은 규칙 칸 — 이주 «필요»(v6 --apply) · 재기동 «필요»**
>
> ```
> 무엇이 바뀌나  ① 원장 선언 setup_version 6 — 소스의 prepare 절 은퇴. 옛(5) 파일은 메모리에서 6 으로 읽힘:
>                 direct-join prepare 는 버리고 적재 노트 한 줄, 일하는 준비기를 든 lot_event 만 이름 거절(Next: 아래 이주)
>              ② lot_event 소스 은퇴(원자는 남음) — 계보 derived_from 은 체인 규칙 lot_event_to_lot_lineage -> 표 lot_lineage -> 원장 소스 lot_lineage
>                 웨이퍼·랏 등록(register)은 끊김 · 갭 질문 「등록되지 않은 웨이퍼 · 랏」 은퇴 · 어휘 register@1 의 주어에서 lot@1 · wafer@1 빠짐
>              ③ 체인 맵퍼 lot_slot_wafer · lot_lineage 는 칼럼 이름 전부를 규칙 params 에서 읽음 — 기본값 없음, 빠지면 이름 거절
>              ④ 걷기 타입 목록(seed_type) = 원자가 이름 댄 노드 전부(등록 여부 무관) · 예산만큼 «키 순서 앞쪽». 갭 측정도 같은 질의
> 돌릴 명령     git pull 전에 server/mappers/lot_slot_wafer_mapper.py 를 옆으로 옮김 (추적 안 된 박스 사본 — 같은 경로에 추적판이 들어옴)
>              python server/scripts/migrate_ledger_config_to_v6.py                 (미리보기 — 바꿀 것을 줄마다, 아무것도 안 씀)
>              python server/scripts/migrate_ledger_config_to_v6.py --apply         (ledger_config · table_config · chain_rules 셋, 백업 남김)
>              재기동 — run_app.bat 전체 (lot_lineage 표 생성 · 규칙 적재)
>              python server/scripts/chain_replay_cli.py replay lot_event_to_lot_lineage --apply
> 뜻           --apply 전(재기동 사이)에 멈추는 것 셋: lot_event 소스(이름 거절) · lot_slot_wafer 규칙(돌 때마다 「빠진 칸」 거절) · 갭 화면(「이름 없는 질문」 거절)
>                 셋 다 같은 Next(위 이주)이고 --apply 로 풀림. 나머지 소스는 그대로 돎
>              미리보기 정상 줄: vocabulary.register@1.subjects: - lot@1, wafer@1 · chain_rules.lot_event_to_lot_slot_wafer.params: + target_* 다섯
>              옛 계보 원자는 남는다 — lot_event 가 쓴 derived_from 과 lot_lineage 가 쓸 derived_from 은 걷기에서 엣지 «하나»(근거는 둘 중 하나만 보임)
>              이 박스(사본 · 메모리, 쓰기 0): 이주 뒤 prepare_retired 0 · lot_slot_wafer 36525행 전후 같음 · 계보 쌍 1986 원장과 같음
> 급할 때       커밋 되돌리기 + --apply 가 남긴 백업 세 파일 복원
> 재기동 뒤 로그 --apply 전: [Ledger] setup_version 5 read as 6: … - Next: run scripts/migrate_ledger_config_to_v6.py to write it
>                         [Ledger] source lot_event is NOT planned: bundle.sources.lot_event.prepare …
>              --apply 뒤: 그 두 줄이 없어야 함
> ```

---

> ## [10-01 오후] **숫자의 신원 철자는 하나 — 문자 칸 숫자 · 저장된 칸 소급 · 원장 엔티티 키 — 마이그레이션 «없음» · 재기동 «필요» · 소급/다시 번역은 운영자가 표·소스마다**
>
> ```
> 무엇이 바뀌나  ① 문자 칸(number · datetime 아닌 칸)에 숫자가 오면 clean_str_value 의 철자로 저장 — 1.0 -> '1', 3 -> '3', 1.5 -> '1.5'
>                 층과 보이는 칸이 같은 글자(전엔 층 숫자 1.0 · 칸 PG 글자 '1.0' — 파이썬 '1' · PG ->> '1.0' 로 답이 둘). bool · NaN · inf · 글자 '1.0' · number 칸은 그대로
>              ② 소급 "Fold stored values into the declared spelling" 이 write 칸만이 아니라 «글자 칸 전부»를 쓰기 접기 그대로 지남
>                 층이 접힌 칸은 보이는 값을 접힌 층에서 다시 정함. 키는 접기가 키 부품 칸을 바꾼 행만, 그 행의 안 접은 칸이 저장 키를 그대로 짓는 때만 바뀜
>              ③ 원장 엔티티 키 — 선언 바인딩의 키 칸이 그 칸의 «선언 타입»으로 정규화(map_overlay.canonical_key_value):
>                 number 칸의 1 · 1.0 · '01' 은 키 '1'(글자) 하나. 문자 칸의 '1.0' 은 '1.0' 그대로 — 접고 싶으면 그 칸을 table_config 에서 number 로 선언
>                 저장된 원장 키는 «다시 번역할 때까지» 옛 꼴(7.0) 그대로 — 새로 번역되는 원자부터 '7'
> 돌릴 명령     재기동 — run_app.bat 전체
>              ② 표마다: 어드민 Retroactive 탭 "Fold stored values into the declared spelling" -> table -> Count 먼저, 그다음 Run
>              ③ 소스마다 (whole_source 는 화면 폼에 없어 명령줄):
>                 python server/ledger/backfill.py --source <소스> --whole-source              (미리보기 — 행 · 잃은 행 · 그 원자, 안 씀)
>                 python server/ledger/backfill.py --source <소스> --whole-source --apply --pace slow
>                 대상 = number 칸을 엔티티 키에 묶는 소스: bonded_from · bw_dt_seat · die_inspection · dt_transfer · transfer_event · void_observation
> 뜻           ② Count: affected = 보이는 값이 바뀌는 칸 · layers_folded = 바뀌는 층 · keys_not_rebuilt = 키가 저장 키와 이미 어긋나 건너뛰는 행(그 행은 한 칸도 안 접음, 신원 그대로)
>              ③ 다시 번역 전에는 같은 다이가 옛 꼴(7.0)과 새 꼴('7')로 갈려 걷기에서 둘로 보일 수 있음 — 소스를 다시 번역하면 옛 꼴이 빠지고 새 꼴만 남음
>              저장된 마킹의 옛 다이 id 는 다시 번역 뒤 안 맞음 — 마킹은 브라우저에 저장돼 서버에서 셀 수 없음. 저장된 대조(contrast_run)는 이 박스엔 표가 없음(0)
>              이 박스(미리보기만, 실행 안 함): dt_map.value 층 1,000,400 · 보이는 칸 1,000,399 · wafer_map_metadata 층 1 / 다시 번역: die_inspection 숫자 키 0 · transfer_event 숫자 키 0 (뷰를 읽는 넷은 오늘 로드 거절 — 미리보기 없음)
> 급할 때       커밋 되돌리기. 소급·다시 번역은 실행 전이면 안 돌리면 됨 — ② 는 돌린 뒤 되돌릴 수 없음(옛 철자는 칸마다 이력 줄), ③ 은 되돌린 코드로 다시 번역하면 옛 꼴로 돌아감
> ```

---

> ## [10-01 오후] **sample 의 decide 넷 복원 — 마이그레이션 «없음» · 재기동 «없음» (sample 만)**
>
> ```
> 무엇이 바뀌나  server/config/sample/chain_rules.json.sample 에 derive.decide 넷이 돌아옴 — 09-24 은퇴 때 옮겨지지 않고 지워졌던 것
>              dt_job_lot_slot_attribution · dt_frame_confrimation · core_frame_review · dt_lot_slot_from_log (이름 철자 그대로)
>              sample 의 alignment_rule 둘이 다시 있는 선언을 가리킴. 넷 다 꺼진 채 출하 — DT 체인을 켤 때 같이 켬
> 돌릴 명령     없음
> 뜻           박스·운영 설정은 한 줄도 안 바뀜. 새 설치가 sample 을 복사할 때만 닿음
> 급할 때       커밋 되돌리기
> ```

---

> ## [10-01 오후] **표 선언 엑셀 붙여넣기 · 복사 — 화면만 · 마이그레이션 «없음» · 재기동 «없음» (git pull 뒤 페이지 새로고침)**
>
> ```
> 어디         Admin -> Tables -> 표 고르기 -> 「Paste columns · names / types / key」 칸과 「Copy columns」 버튼
> 붙여넣기      엑셀 가로 세 줄: 1 줄 컬럼 이름 · 2 줄 타입(string · number · datetime, 대소문자 무관) · 3 줄(있으면) 키 컬럼에 key
>              -> column_types · display_columns(붙인 순서 전부) · 키(하나면 business_key, 둘 이상이면 composite_key_source)를 채움
>              있는 표는 통째로 바뀜 — 저장 전에 Dropped · Type · Key · Shown · Existing rows change identity 줄과 확인창
> 복사          지금 컬럼을 같은 세 줄로 클립보드에 — 엑셀에서 고쳐 다시 붙여넣기. 키를 세 줄로 못 적는 표는 3 줄을 빼고 그렇다고 한 줄
> 뜻           칸 · 버튼이 안 보이면 = 옛 화면이 캐시됨 -> Ctrl+F5
> 급할 때       저장 전 확인창에서 No — 아무것도 안 보냄
> ```

---

> ## [10-01 오후] **(선택) HTTPS — nginx 앞단 · 제품 코드 무변 · 마이그레이션 «없음» · 재기동 «없음»**
>
> ```
> 무엇이 바뀌나  가이드만 — docs/guide/HTTPS_PROXY_GUIDE.md (pfx + p7b -> fullchain · nginx.conf · 방화벽 · 부팅 시 자동)
> 돌릴 명령     가이드 2~7 단계 (관리자 PowerShell 한 창)
> 뜻           curl.exe https://<호스트명>/health 가 200 = 프록시가 8080 에 닿음
>              다른 PC 브라우저에서 자물쇠 + 실시간 갱신 = 웹소켓까지 통함
> 급할 때       C:\nginx 에서 .\nginx.exe -s stop — http://<서버>:8080 은 그대로 살아 있다(8 단계를 안 했으면)
> ```

---

> ## [10-01 오후] **체인 규칙 이름 바꾸기 = 제자리 · 이름을 붙든 기록이 있으면 거절 · 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  체인 편집기에서 규칙 이름을 바꿔 저장하면 «그 자리의 그 규칙»이 바뀜(켜짐 그대로) — 전엔 꺼진 새 규칙이 덧붙고 옛 것이 계속 돌았음
>              서버는 POST /admin/chain/rules/raw 의 from(연 이름)을 읽음 — 클라가 from 을 보내야 화면에서 동작(클라 레인)
> 돌릴 명령     없음
> 뜻           저장이 rule_name_held 로 거절되면 = 옛 이름으로 찾는 기록이 있음(확정 · 미처리 리플레이 · 다른 규칙의 alignment_rule · 안 끝난 소급) — 이름 유지, 새 이름이 꼭 필요하면 새 규칙을 추가하고 이것을 끔
>              바꾸기가 되면 = 그 규칙이 쓴 칸은 그 행이 다음에 올 때 새 이름으로 다시 쓰임
> 급할 때       커밋 되돌리기
> ```

---

> ## [10-01 오전] **걷기 — 아무도 안 부르던 claims_by_ids 둘 은퇴 · 동작 같음 · 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  코드 정리만 — 걷기 룩업의 claims_by_ids(SQL · 메모리 둘) 지움. 호출자 0
> 돌릴 명령     없음
> 뜻           걷기 응답은 전과 같음
> 급할 때       커밋 되돌리기
> ```

---

> ## [10-01 오전] **탐색기 — 가지 뷰 다시 짓기를 세 문이 함수 하나로 부름 · 동작 같음 · 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  코드 정리만 — bootstrap · 초안 반영 · 선언 삭제 뒤의 뷰 다시 짓기가 함수 하나(_world_after_write)
> 돌릴 명령     없음
> 뜻           가지 걷기가 503 「ledger_relation_absent」 면 = 전과 같이 그 가지를 한 번 반영하거나 backfill --world 로 번역
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 오전] **원장 `cardinality: one` — 지금 값은 가장 늦은 occurred_at, 걷기가 읽을 때 정함 · 쓰기에서는 아무것도 안 함 · 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  one 으로 적으면 걷기가 지금 것만 그린다(옛 값은 include_superseded)
>              지금 것 = 같은 주어·술어 중 occurred_at 이 가장 늦은 사실. 늦게 «도착한» 옛 사실은 지금 것이 아님
>              옛 값을 그리면 엣지에 not_current · 가장 늦은 시각에 목적어가 둘이면 둘 다 그리고 노드의 current_conflicts 가 셈
>              원자를 쓸 때는 one 이 아무것도 안 함 — 한 배치 거절(cardinality_one_violated)·supersedes 찍기 은퇴
> 돌릴 명령     없음 (이미 쓰인 원자에도 바로 걸림 — 재번역 불필요)
> 뜻           걷기 응답에 walk.superseded_dropped 가 없어짐 — 그 칸을 읽던 화면은 없음(클라 검색 0)
>              one 술어에서 한 주어에 엣지가 둘 이상 보이면 = 같은 가장 늦은 시각의 두 사실(current_conflicts 로 확인)
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 오전] **원장 가지 — 기본에 거절 소스가 있어도 새 가지를 만듦 · 없는 가지는 이름 대어 거절 · 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  가지 만들기(bootstrap?world=)가 기본 선언을 그대로 복사하고 기본과 같은 잣대로 잼 — 거절 소스는 기본처럼 이름 대어 빠짐
>              전: 기본에 거절 소스가 하나라도 있으면 400 bootstrap_invalid 「the starting file did not validate and was not written」
>              폴더 없는 가지를 열면 400 world_not_created 「Next: create the branch first」 (전: 500)
> 돌릴 명령     없음
> 뜻           가지 만들기가 아직 400 bootstrap_invalid 면 = 기본 선언 파일 «전체»의 문제(선언 하나의 문제가 아님) — 그 응답의 details 를 봄
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 아침] **원장 가지 — 만들 때 · 선언을 저장(반영)·삭제할 때 걷기 뷰를 다시 지음 · static 만 바꾼 가지도 걷힘 · 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  탐색기의 가지 만들기(bootstrap?world=) · 초안 반영 · 선언 삭제 뒤에 그 가지의 걷기 뷰를 다시 지음
>              전: 번역(backfill --world)만 뷰를 지어서 static 처럼 소스를 안 움직이는 바꿈만 한 가지는 걷기 503 · 저장 뒤 뷰의 제외 목록이 옛것
> 돌릴 명령     없음 (이미 있는 가지는 다음 반영·삭제 때 다시 지어짐)
> 뜻           가지 걷기가 503 「ledger_relation_absent」 면 = 그 가지를 한 번 반영하거나 backfill --world 로 번역
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 아침] **원장 가지 번역 — 가지가 바꾼 소스만 씀 · 같은 표를 읽는 안 바뀐 소스는 기본 원자로 보임 · 마이그레이션 «없음» · 재기동 없음 (backfill --world 는 CLI 한 번)**
>
> ```
> 무엇이 바뀌나  backfill --world <가지> --source <소스> 가 그 가지의 «바뀐 소스»만 번역. 전엔 같은 표를 읽는 다른 소스도 가지에 들어가 걷기에서 기본 원자가 가려짐
> 돌릴 명령     없음 (가지를 쓰는 중이면: 그 가지를 지우고 다시 만들어 번역하면 곁 소스가 빠짐)
> 뜻           가지 걷기에서 안 바꾼 소스의 엣지가 기본과 같으면 = 됨
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 아침] **수를 세어 로그 한 줄 찍는 다섯 자리 — 같은 문턱(1·10·…·10^18) · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 · 워처 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  키 게이트 거절 · VOID/SAT 파일 거절 · 원장 거절 · 안 말한 단위 · 미선언 컬럼 드롭 — 넷은 100 만 뒤로 줄을 안 냈는데 이제 1000 만 · 1 억 … 에서도 냄
>              미선언 컬럼 드롭 줄은 전과 같음
> 돌릴 명령     없음
> 뜻           그 줄들 뒤로 조용하면 = 그 수가 더 안 늘었음 (다섯 자리 모두)
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 아침] **작성 화면 — 못 읽는 설정 파일은 계획과 view 가 같은 낱말 · unreadable_config 은퇴 · draft_required 문장 · 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  ledger_config.json 이 JSON 으로 안 읽히면 작성 계획도 view 와 같이 400 invalid_json (전: unreadable_config)
>              뿌리가 객체가 아니면 둘 다 400 invalid_type at ledger_config
>              draft_id 없는 요청의 문장: 「Next: open a draft first - this request needs a draft id」
>              받는 파일은 그대로 — 같은 키가 두 번인 파일도 전처럼 읽힘
> 돌릴 명령     없음
> 뜻           「Next: restore or fix ledger_config.json ...」 = 그 파일을 고치기. 문장 끝에 줄·칸 위치
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 아침] **어느 문장도 안 말한 행 — 배치마다 경고 대신 값마다 세어 하트비트 노트 · 1·10·100… 단위에서 한 줄 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  전: 배치마다 「[Ledger] <소스>: N unit(s) said no sentence - mat_type='WF' (N). Next: …」
>              후: 하트비트 ledger 노트에 「units no sentence said: units=N | <소스>:mat_type='WF'=N, …」(상위 5 + (+k more))
>                  값 하나가 1 · 10 · 100 … 단위에 닿을 때만 「[Ledger] Next: correct the value … <소스>: mat_type='WF' said no sentence … | units so far in this process: N」
> 돌릴 명령     없음
> 뜻           노트의 수가 늘면 = 그 값의 행이 계속 아무 문장도 안 말함 -> 그 값을 표에서 고치거나 그 값을 when 에 적은 문장을 선언
>              수는 프로세스 집계 — 재기동이면 0 부터
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 아침] **작성 화면 — 저장 전 계획이 저장과 같은 입력으로 채움 · 초안 없는 POST 는 draft_required · 설정 파일 없음/못 읽음은 500 대신 이름 붙은 거절 · 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  POST /admin/ontology-explorer/authoring/plan (초안 있음): 채우기가 저장과 같은 활성 셋업·카탈로그로
>              같은 라우트에 draft_id 없음: 400 draft_required (전: invalid_draft_id)
>              ledger_config.json 이 없거나 객체로 못 읽힘: view·초안·저장 등 400 + 코드(missing_config_file · invalid_json · invalid_type) (전: 500)
> 돌릴 명령     없음
> 뜻           「Next: restore or fix ledger_config.json ...」 거절 = 그 파일을 되살리거나 고치기. 파일이 없으면 작성 화면의 Create starting file
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 아침] **걷기 응답의 증거 길 — 홉마다 predicates · 대조 저장은 그 길 그대로 · 참거짓 글 칸은 "true"/"false" 만 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  /api/ledger/subgraph 의 propagation.ranked[].evidence[].hops[i](i ≥ 1)에 predicates 가 붙음 — 응답 edges 중 앞 홉과 그 홉 사이 술어 전부
>              대조 저장(contrast_factor.evidence)은 전과 같은 글(시험 픽스처에서 byte 같음)
>              contrast_run.include_superseded 칸: "true"/"false" 만 읽음. 전엔 "1" 도 참, "yes" 는 거짓 — 이제 둘 다 그 run 거절
>              소급 작업의 참거짓 인자도 같은 읽기 · 같은 거절 문장
> 돌릴 명령     없음
> 뜻           대조 run 이 「include_superseded must be true or false, got "yes" - write true or false」 로 안 돌면 = 그 칸에 true 나 false 를 적기
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 새벽] **작성 폼 감사 스크립트가 제품의 스켈레톤 해석기를 부름 · 출력 같음 · 재기동 «없음»**
>
> ```
> 돌릴 명령     (필요할 때) python server/scripts/audit_authoring_form.py --help 대로 — 결과는 전과 같음(추적 표본 311 경로 전후 byte 같음)
> 뜻           폼 감사가 제품 해석기(config_authoring._skeleton_node)와 다른 답을 낼 수 없게 됨
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 새벽] **파일의 «내놓았는데 안 써진 칸» — 한 문장 · 다음 행동 먼저 · 모델이 못 받는 칸만 든 파일도 FAILED · 마이그레이션 «없음» · 재기동 워처 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  파일 기록 · 워처 줄이 한 문장: 「Next: declare the undeclared columns in table_config.json; reload or restart so this process holds the
>              unmapped columns, then Retry the file. Not written: undeclared_column a=3; unmapped_column c=5 over N row(s).」(있는 사유만)
>              전엔 「Dropped N undeclared column(s) ...」 과 「Not written (unmapped_column): ...」 두 문장
>              선언됐지만 이 프로세스 모델이 못 받는 칸만 든 파일(쓴 행 0) -> 이제 FAILED 「... Nothing was written to '<표>' - dropped: unmapped_column <칸>.」
> 돌릴 명령     없음
> 뜻           undeclared_column = 표 선언(table_config.json)에 없는 칸 -> 선언하거나 그대로(옛 필드면 버리는 게 맞음)
>             unmapped_column = 선언엔 있는데 이 프로세스가 아직 모름 -> 리로드/재기동 뒤 그 파일 Retry
>             WARNING 은 (사유, 칸) 이 이 프로세스에서 처음 보일 때 한 번, 그 뒤엔 파일마다 INFO
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 새벽] **체인 범위 배치 — 권한(allow_replace_map / allow_retraction)을 봉투 독자가 묻음 · 동작 같음 · 마이그레이션 «없음» · 재기동 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  «되쓰기가 아닌» 배치의 권한 검사를 dt_map_derivation.normalize_scoped_batch 가 함(워커가 두 번 묻던 것을 뺌)
>              한 가지 다름: 권한도 없고 봉투도 틀린 배치는 이제 권한 문장이 먼저 나옴(격리 사유 글)
> 돌릴 명령     없음
> 뜻           격리 사유 「returned scoped batches without allow_replace_map or allow_retraction」 = 그 규칙에 두 권한 중 하나를 줘야 함(되쓰기만 하는 규칙은 필요 없음)
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 새벽] **가지 — 기본과 가지 «둘 다» 거절한 소스는 «안 바뀜» · 가지 걷기에 기본 원자가 보임 · 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  가지가 말하는 소스 = 선언 지문이 기본과 다른 소스. 이제 양쪽 선언이 다 그 소스를 거절하면(예: 뷰를 읽는 소스) 가지는 새로 말할 것이 없으니
>              가지 뷰가 그 소스의 기본 원자를 그대로 보임. 한쪽만 거절하면 여전히 «바뀜»(가지 뷰에서 기본 원자 빠짐)
> 돌릴 명령     없음. 이미 만든 가지는 다음 --world 번역이나 가지 선언 저장 때 뷰가 다시 지어짐
> 뜻           가지 걷기에서 어떤 소스가 통째로 안 보이면 = 그 소스가 가지 쪽에서만 거절됨(가지 선언을 고치거나 --world 번역)
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 새벽] **--whole-source 가 표가 잃은 행의 원자도 거둠 (모든 세상) · --apply 없이 미리보기 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  --whole-source 는 페이지로 다시 번역한 뒤, 색인엔 있고 표엔 없는 행(따라가기가 놓친 삭제 · 가지는 따라가기가 없음)의 원자를 삭제처럼 거둠
>              기본 세상에서도 같음 — 따라가기가 이미 거뒀으면 0
> 미리보기       python -m ledger.backfill --source <소스> [--world <이름>] --whole-source   (--apply 없이 · server/ 에서)
>              -> relation_rows(표 행) · gone_rows(표가 잃은 행) · gone_atoms(거둘 원자). 번역은 안 함
>              관리 화면의 소급 작업(ledger_rescope, whole_source) 미리보기도 같은 셋
> 거두기        같은 명령에 --apply -> gone_rows · gone_withdrawn
> 뜻           gone_rows > 0 인데 기본 세상 = 따라가기가 그 삭제를 못 봄(큐가 비었거나 워커가 꺼져 있던 동안) — 거두는 게 맞음
>             가지는 늘 따라가기가 없으니 기본 표에서 지운 행은 여기서만 거둬짐
> 가지 속도(박스 수)  lot_slot_wafer 37,325 행 -> 원자 37,325 · 88.7 초 (421 행/초 · 2.38 ms/행) · 19 배치 — 임시 가지로 한 번 잼
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 새벽] **원장 프레임은 NaN 을 만들지 않음 — DB 의 NULL 이 None 으로 끝까지 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  DB 행 -> 원장 소스 프레임(backfill._v2_frame) · 준비기 출력 -> 프레임 칸(_assemble_prepared_frame) 을 object 로 지음
>              pandas 3 은 NULL 이 섞인 글자 칸을 str 로 잡아 None 을 NaN 으로 바꿨음 — 이제 None 그대로
>              그래서 when 비교(_when_value) · 정본 JSON 의 NaN 갈래가 빠짐. 번역 결과는 같아야 함(NULL 이 든 글자 칸 = 빈 칸으로 견줌)
> 돌릴 명령     없음. 재기동 뒤 따라가기가 평소처럼 도는지만
> 뜻           로그 「value is not deterministic JSON ... NaN」 으로 배치가 거절되면 = 어딘가 프레임이 아직 NaN 을 만듦(원장 밖에서 지은 프레임) -> 그 소스 이름과 보고
>             「mat_type='nan' said no sentence」 처럼 nan 글자가 보이면 = 같은 원인
> 급할 때       커밋 되돌리기
> ```

---

> ## 🔴 [10-01 새벽] **row 소스의 group_by — 폼에 안 그림 · 저장하면 파일에서 빠짐 · 없음은 빈 목록으로 읽음 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  선언 폼: unit=row 소스엔 group_by 칸이 없음(스켈레톤 when {unit: group}). 「Filled: unit=row -> no group_by」 줄들이 사라짐
>              저장: row 소스 파일에서 "group_by": [] 가 빠짐. 검증·컴파일은 없음을 빈 목록으로 읽음(setup_bundle.read_group_by)
>              라이브 파일에 [] 가 남아 있어도 그대로 유효 — 폼은 빈 목록이면 안 그림(클라 92ad06716). 한 번 저장하면 파일에서도 빠짐
> 돌릴 명령     없음. 재기동 뒤 탐색기에서 row 소스(dt_job 등) 하나 열기 -> group_by 칸 없음 · group 소스(lot_event) -> 지금과 같음
> 뜻           row 소스를 저장한 뒤 그 소스 커서가 cursor_snapshot_reset_required 로 서면 = 소스 지문이 움직인 것(추적 표본 여섯에선 [] 든 파일 · 저장한 파일이 같음을 잼) -> 보고
>             group 소스에서 group_by 를 지우면 「field is required」 거절 — 정상
> 급할 때       커밋 되돌리기(되돌린 코드는 group_by 를 모든 소스에 요구 — 저장으로 빠진 row 소스엔 "group_by": [] 한 줄 다시)
> ```

---

> ## 🔴 [09-30 밤] **원장 가지 — 선언을 바꿔 시험하는 세상 · 가지 없는 설치는 그대로 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  가지 <이름> = 선언 파일 하나(config/ontology_worlds/<이름>/ledger_config.json) + PG 스키마 하나(w_<이름>)
>              가지에는 «기본과 선언이 다른 소스»의 원자만. 걷기는 가지 뷰 = 가지 원자 + 기본 원자(그 소스 빼고)
>              따라가기(체인)는 기본만 — 가지는 사람이 명령으로 다시 번역
> 만들기        탐색기 Bootstrap 에 world=<이름> — 기본 선언을 복사해 시작. 그 세상의 선언을 탐색기에서 고침(요청마다 world=<이름>)
> 번역          python -m ledger.backfill --source <바꾼 소스> --world <이름> --whole-source --apply   (server/ 에서 · 가지 스키마·표·뷰도 이 명령이 만듦)
> 걷기 · 보드    /api/ledger/subgraph · /key-values · /gaps · /declaration 에 world=<이름> · /declaration 의 worlds 칸 = 가지 목록
>              대조 저장 행(contrast_run)의 world 칸 — 라이브 table_config 의 contrast_run 에 "world": "string" 한 줄(표본대로. 저장하면 감시가 칸을 더함)
> 병합          탐색기 기본 세상(world 없음)에서 그 소스 선언을 가지 것으로 저장·활성화
>              → python server/scripts/ledger_restamp_cursor.py --apply
>              → python -m ledger.backfill --source <소스> --whole-source --apply   (옛 선언 원자는 페이지마다 걷히고 새로 씀 · 한 페이지 한 커밋)
>              → 가지 지움
> 지우기        DELETE /admin/ontology-explorer/worlds/<이름> → 미리보기(스키마 · 원자 수 · 파일). 같은 요청에 ?confirm_atoms=<그 수> → 지움(되돌릴 수 없음)
> 은퇴          backfill · ledger_restamp_cursor 의 --ontology-root → --world. 저장된 작업의 ontology_root 칸: 기본 뿌리면 기본으로, 다른 경로면 이름 대어 거절
> ASSY_DATA_ROOT 세운 설치는 원장 선언을 <DATA_ROOT>/config/ontology 에서 읽음 — 전과 다른 파일이면 커서가 선다(위 restamp)
> 뜻           404 「world_unknown」 = 그 이름의 가지 선언 파일이 없음. 503 「ledger_relation_absent」 relation w_<이름>.ledger_view = 가지를 아직 번역 안 함(위 번역)
>             가지 선언을 손으로 고치면 «가지가 말하는 소스»는 다음 --world 번역 때 다시 정해짐(그 전까지 뷰는 전 번역 기준)
>             기본 원천 행이 지워지면 가지 원자는 다음 --whole-source --apply 가 거둠(가지엔 따라가기가 없음 · --apply 없이 돌리면 몇 행 · 몇 원자인지 먼저 보임)
> 급할 때       가지만 끄기 = 가지 지우기. 가지 없는 설치는 이름 · 원장 · 커서가 전과 byte 같음. 코드는 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 밤] **nokey 로 적은 키 칸이 «아예 없는» 파일도 적재 — 마이그레이션 «없음» · 재기동 워처 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  표준 파서 헤더 검사: null_policy 에 nokey 로 적은 키 칸은 헤더에 없어도 통과 — 그 칸은 쓰기 문이 nokey_… 로 채움
>              전: 그 칸이 헤더에 없으면 「required key column(s) missing from header」 로 파일째 거절(err/ 로)
> 누가          null_policy 에 nokey 를 적은 표만. 안 적은 표는 전처럼 거절
> 확인          그 파일의 줄 「N row(s) keyed nokey_... (<칸>).」
> 뜻           전에 err/ 로 간 그런 파일은 다시 넣으면 적재됨
> 급할 때       null_policy 에서 nokey 를 지움 — 그 칸이 없는 파일은 다시 거절
> ```

---

> ## 🔴 [09-30 밤] **원장 커서 칸이 빈 행 — 그 행이 든 분자만 이름 대어 거절, 배치는 계속 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  원장 번역: 커서 칸(read.order_by)이 빈 행이 든 분자를 no_raw_ref 로 거절 1 건 — 같은 배치의 나머지 분자는 번역됨
>              전: 그런 행 하나가 배치 전체를 멈춤 「cursor number must be finite」 — 이 박스 dt_log 에서 작업 3 개(144 행), 그 작업을 따라갈 때마다
>              묶음 소스(group_by 가 있는 소스, 예 dt_job)는 그 분자를 «통째로» 거절 — 남은 행으로 작은 사건을 짓지 않음
> 확인          서버·체인 워커 로그에 「cursor number must be finite」가 더는 안 남
>              대신 거절 표본: 사유 no_raw_ref · 주소 bundle.sources.<소스>.read.order_by.<칸>
>              문장 「molecule …: row … leaves its cursor column <칸> empty - … fill <칸>」
> 뜻           그 줄 = 원천 표의 그 행 커서 칸이 비어 있음. 할 일은 그 칸을 채우는 것 — 채우면 다음 따라가기가 그 분자를 번역
>             그 분자에 전에 적힌 원자는 거절되는 동안 원장에서 걷힘 — 편집으로 칸을 비우면 걷히고 채우면 돌아옴(PG 에서 잼)
>             거절 수는 그 작업을 따라갈 때마다 늘어남 — 채울 때까지
>             identity · group_by 칸이 빈 행은 전처럼 페이지째 멈춤 — 문장만 「driver identity/group_by value is missing」 으로
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 밤] **DT 스텝 뒤 공정 행은 dtwafer 로 — 표본 선언 셋을 라이브에 옮기면 켜짐 · 마이그레이션 «없음» · 재기동 서버 · 체인 워커(번역 ①②) · 선언 ③ 은 리로드 + 커서 지문**
>
> ```
> 무엇이 바뀌나  ① 원장 번역: 어느 문장의 when 에도 안 맞은 행을 값마다 세어 — 「[Ledger] Next: … <소스>: mat_type='WF' said no sentence …」 (10-01 부터 1·10·100… 단위에서 한 줄, 수는 하트비트 노트)
>              ② 원장 번역: 문자열 칸의 NULL(pandas 3 에선 NaN)이 배치 전체를 멈추던 것이 멈추지 않음 — 09-10 박스 로그의 「not deterministic JSON … nan」
>              ③ 표본 선언(추적 파일)에 스텝 가르기 — 라이브 선언에는 «운영자가 옮길 때» 켜짐. 옮기기 전엔 동작 그대로
> 옮기기        표본 server/config/sample 의 세 파일에서 그대로:
>              table_config   step_phase 표(business_key · composite_key_source = step, 칸 step · mat_type) · wafer_process 에 mat_type 칸
>                             저장하면 웹 서버의 설정 감시가 표를 만들고 칸을 더함 — 서버 로그 「Physical database schema synced successfully.」
>              chain_rules    step_phase_to_wafer_process 조인(체인 탭 저장 — 리로드 불필요)
>              ledger_config  dtwafer@1 · processed_with@1 subjects 에 dtwafer@1 · wafer_process_recipe 문장 둘(when mat_type "" / "DT") · input_columns 에 mat_type
>              curl -X POST "http://<host>:8080/admin/reload-configs" -H "X-Admin-Token: <토큰>"
>              python server/scripts/ledger_restamp_cursor.py --apply     (선언이 바뀌어 커서가 선 것을 풀기 — 위치는 안 움직임)
> 운영자 두 줄   「운영에서는 step_phase 표에 DT 스텝을 한 줄씩 적으면 됩니다(스텝 · DT).」
>              「결함 계측 표에도 같은 조인 한 줄, 다이 문장을 when 으로 둘(빈 칸 -> mat_type Wafer · DT -> DT).」
> 확인          DT 스텝을 적으면 그 스텝의 공정 행 mat_type 이 DT 가 되고, 원장의 그 행 원자가 wafer -> dtwafer 로 옮겨감(옛 원자는 지워짐)
> 뜻           「mat_type='WF' said no sentence」 = 단계표에 DT 가 아닌 값(WF · 오타)을 적은 스텝 — 그 행은 원장에 안 감. 그 칸을 비우거나 DT 로
>             스텝을 빼려면 단계표 행을 지우지 말고 mat_type 칸을 비울 것 — 지운 행은 채웠던 공정 행에 닿지 않아 DT 가 남음(잰 것)
>             「cursor number must be finite」 = 이제 안 남 — 바로 위 절(커서 칸이 빈 행)
> 놓친 따라가기  원장 따라가기 줄은 메모리라 워커가 죽으면 잃음 — 그때만: python -m ledger.backfill --source wafer_process_recipe --scope-column mat_type --scope-values DT --apply (server/ 에서)
> 급할 때       스텝 가르기만 끄기: 단계표를 비움(행의 mat_type 을 비우면 원자가 wafer 로 돌아감) · 코드 되돌리기는 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 저녁] **HTML 토폴로지 파서 — 한 헤더 경로에 값 칸 둘이면 이름 대어 거절 · 옆 그룹 헤더가 안 섞임 · 마이그레이션 «없음» · 재기동 «없음»**
>
> ```
> 무엇이 바뀌나  HTMLTableGraphParser.extract_semantic_tuples — 두 값 칸의 헤더 경로가 같으면 ValueError (전: 뒤 칸만 남고 앞 칸이 말없이 사라짐)
>              같은 줄에 나란히 선 그룹 헤더(A · B)는 자기 열 아래 칸에만 붙음 (전: B 가 A 의 칸에도 붙어 값 하나가 사라짐)
> 누가 부르나     이 박스: 추적 코드 0 · ingestion_workspace 파이썬 18 개 중 0 (bonding_map 은 HTMLMatrixTableParser — 안 바뀜)
> 확인          이 함수를 부르는 커스텀 파서가 있으면, 헤더 경로가 겹치는 파일은 그 파일 줄에
>              「Next: mark the cell that tells these rows apart as a header (is_header_fn) … N value cells share one header path … The path: (…)」 — 다음 행동이 맨 앞(파일 상태 칸이 500 자만 남겨도 안 잘림, 09-30 f7738d7a4)
> 뜻           그 줄 = 전에는 값 일부를 조용히 잃던 파일. 할 일은 행을 가르는 칸(예: 웨이퍼 열)을 is_header_fn 에서 헤더로 — 그 뒤 다시 올리기
>             위아래로 쌓인 표는 거절이 아니라 가이드 §3.1-bis(먼저 나눠 읽기)
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 저녁] **원장 선언 폼 — column 바인딩의 Time zone 칸이 글자 상자로 · 마이그레이션 «없음» · 재기동 «없음» (리로드 한 번)**
>
> ```
> 무엇이 바뀌나  원장 선언 폼에서 Binding 이 column 인 칸마다 뜨던 「Time zone … No shape · broken」 줄이 글자 상자로 뜸
>              값은 시간대 이름(예 Asia/Seoul) — 목록에서 고르는 칸이 아니라 적는 칸 (read.occurred_at 의 Time zone 과 같은 모양)
> 할 일         curl -X POST "http://<host>:8080/admin/reload-configs" -H "X-Admin-Token: <토큰>"   (스켈레톤 캐시를 비움 — 서버 재기동 불필요)
> 확인          원장 선언 폼 · 어느 소스의 bind · column 바인딩 하나 → Time zone 칸이 상자, 「No shape · broken」 없음
> 뜻           리로드 뒤에도 그 줄이 남으면 화면이 옛 응답을 들고 있는 것 — 폼 새로고침
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 저녁] **nokey 값의 시각이 마이크로초까지 — 마이그레이션 «없음» · 재기동 서버 · 워처 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  nokey_<첫 적재 시각 UTC, 마이크로초까지 — 20260930T051503.123456Z>_<6 hex> (전: 초까지)
>              같은 초에 처음 적재된 두 파일의 행이 우연히 같은 6 hex 여도 안 합쳐짐
> 확인          nokey 칸 값에 소수점 여섯 자리
> 뜻           ⚠️ 바로 앞 절(nokey)을 운영에 올려 이미 채운 파일이 있으면, 그 파일을 Retry 할 때 값 모양이 달라 새 행이 생김 — 안 올렸으면 영향 0
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 오후] **행마다 부르는 체인 규칙의 batches · 맵 메타데이터도 씀 — 마이그레이션 «없음» · 재기동 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  "is_batch" 가 없는(행마다 부르는) 규칙이 돌려준 batches · map_metadata_updates 를 워커가 버리던 것을 이제 읽음 — 배치 규칙과 같은 한 길
>              허락 칸 검사도 같음: 맵 메타데이터는 allow_map_metadata_upsert, 봉투는 그 규칙의 허락 · trigger 표 되쓰기는 덮어쓰기만
> 이 박스 · 표본  불러오는 규칙이 전부 "is_batch": true 라 동작이 바뀌는 규칙 0 (박스 15 · 표본 11)
> 확인          행마다 규칙이 되쓰기 · 봉투를 돌려주면 그 표에 써짐 · 허락 없는 맵 메타데이터는 이름 대어 실패
> 뜻           @mapper 규칙의 allow_retraction · allow_replace_map 은 여전히 "is_batch": true 가 필요 — 문장이 바뀜:
>             「called row by row, each row's call removes what the other rows of its job or map made」
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 오후] **키 칸이 빈 파일 행을 nokey_… 로 채움 — 선언한 표만 · 마이그레이션 «없음» · 재기동 서버 · 워처 (run_app.bat 로 전체)**
>
> ```
> 선언          표 선언 null_policy 에 키 칸마다 "nokey" — 예 "null_policy": {"slot": "nokey"} (표 편집기 저장). 안 적은 표는 그대로
> 값            nokey_<그 파일의 첫 적재 시각 UTC, 20260930T051503Z>_<6 hex>
>              6 hex = (파일 내용 시그니처의 해시 + 행 번호) mod 16^6 — 같은 파일이면 Retry 에도 같은 값(옛 행을 찾음), 한 파일 안에서는 안 겹침
> 누가 채우나     파일에서 온 행만(워처 — 표준 파서 · 파이프라인). 그리드 입력 · 체인 쓰기는 안 채움
>              표준 파서는 nokey 칸이 빈 행을 더는 안 버림(전에는 「키 컬럼 공백/결측으로 스킵」)
> 확인          파일 줄 「N row(s) keyed nokey_... (<칸>).」 · 표의 그 칸에 nokey_… 값
> 뜻           「N row(s) not keyed nokey (<칸>) - the file has no content signature …」 = 파일 내용을 못 읽어 안 채움, 그 행은 전처럼 키 없이
>             ⚠️ 이어쓰는 로그 파일은 내용이 바뀌면 시그니처가 바뀌어 앞 행들이 «새 nokey» 를 받고 행이 겹침(잰 것: 3 행 파일에 1 행 더해 다시 올리면 7 행)
> 급할 때       표 선언에서 "nokey" 를 지우고 저장 — 그 뒤 파일부터 채우지 않음(이미 채운 행은 그대로)
> ```

---

> ## 🔴 [09-30 오후] **원장 선언 계획에 «물려받은 속성» 행 — 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  역할이 entity 이고 자기 attributes 를 안 적었으면, 계획(GET/POST /admin/ontology-explorer/authoring/plan)에
>              그 역할의 attributes 자리에 읽기 전용 행 하나 — 값 = 번역이 묶는 속성 · ground.rule "inherited_from_source" ·
>              근거 = 그 소스의 bind.entities.<타입>.attributes
>              저장은 그 행을 역할에 «안 씀»(쓰면 역할이 덮어써서 소스 쪽 고침이 안 따라감)
> 확인          속성을 소스에 적은 소스의 계획에서 그 타입을 쓰는 역할마다 그 행
> 뜻           역할이 자기 attributes 를 적었으면 그 행이 없음 — 그 역할은 소스 것을 안 씀
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 오후] **표 스키마 응답에 smart_paste — 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  GET /tables/<표>/schema 에 "smart_paste" — 표 선언(table_config.<표>.smart_paste)을 그대로. 안 적은 표는 null
> 확인          선언한 표의 스키마 응답에 그 목록 · 안 적은 표는 null
> 뜻           null = 순서를 안 적음(클라가 묻는 쪽) · [] 는 오지 않음
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 오후] **원장 선언 저장이 꺼진 갈래의 칸을 걷음 — 마이그레이션 «없음» · 재기동 서버 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  바인딩을 column -> constant 로 바꾸면 남던 "column": "" 같은 칸을 저장이 걷음(스켈레톤의 when)
>              저장(PUT drafts/<id>)과 저장 없는 계획(POST authoring/plan)이 같은 자리를 지남
>              응답에 dropped_fields: [{path, value}] — 걷은 칸과 그 값
>              kind 를 아직 안 고른 바인딩은 아무것도 안 걷음(저장이 이름 대어 거절)
> 확인          원장 선언 창에서 역할 하나를 column -> constant 로 바꿔 저장 -> 저장됨 · dropped_fields 에 그 column
> 뜻           dropped_fields 가 비었는데 unknown_field 로 거절되면 when 이 없는 칸이 남은 것 — 그 경로를 적어 올릴 것
>             엔티티 · 키 · 속성 · 술어 · 한정어 · 컬럼 이름을 바꾸거나 지운 흔적은 이 변경이 안 걷음 — 저장이 이름 대어 거절(보고의 표)
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 오후] **시각 칸은 같은 순간이면 같은 값 · 빈 글은 None — 마이그레이션 «없음» · 재기동 서버 · 워처 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  「칸 값이 바뀌었나」를 묻는 자리(AST 로 센 것 — 보고에 표)가 한 함수(crud.value_key)를 지남
>              datetime 칸 = 순간으로 견줌(「…T08:00:00+09:00」 = 「… 08:00:00+09:00」 = 「…T23:00:00Z」 전날)
>              꼬리 없는 시각 = PG 세션 시간대로 읽음(쓰기 문이 PG 에 넘길 때와 같음 — 연결마다 PG 가 알려 줌, 질의 없음)
>              빈 글('' · 공백만) = None (판정 284)
> 운영에서 보일 것 같은 순간을 다른 철자로 다시 보낸 파일 · 체인이 같은 순간을 다시 옮긴 것 -> 칸 안 씀 · ROW_UPDATE 이력 줄 0 · 체인 사건 0
>              파일 줄의 「바뀐 칸」 수가 그만큼 줄어듦 · R3 dry-run 이 철자만 다른 칸을 안 셈
>              옛 행의 '' 칸 위에 이긴 층이 None 이면 안 다시 씀(전에는 매번 None 으로 씀)
>              버전 게이트의 「같은 판 다른 내용」 경고가 철자만 다른 시각에는 안 뜸
>              셀 원천 삭제 · 우선순위 지정의 이력 줄이 같은 값이면 안 남음
> 확인          같은 파일을 다시 떨어뜨려 파일 줄의 바뀐 칸이 0 인지 · 다른 순간을 넣으면 전처럼 씀
> 뜻           다른 순간인데 안 써지면 이 변경이 원인일 수 있음 — 그 칸의 두 값과 PG 의 SHOW TimeZone 을 같이 적어 올릴 것
> 급할 때       끄는 스위치 없음 — 커밋 되돌리기
> ```

---

> ## 🔴 [09-30 오후] **대조 run 행이 스스로 말함 — computed_at · candidates · contrast · complete — 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 준비          운영 table_config 의 contrast_run 에 칸 넷: computed_at(datetime) · candidates(number) · contrast · complete(string) — 표 편집기 저장
>              운영 chain_rules 의 contrast_factor_from_run 에 "is_batch": true 한 칸 — Chain 탭 저장 (표본 server/config/sample/chain_rules.json.sample 과 같게)
>              둘 중 하나라도 빠지면: 칸이 없으면 그 칸은 버린 칸(unmapped/undeclared)으로 셈 · is_batch 가 없으면 run 행에 아무것도 안 씀
> 무엇이 바뀌나  체인이 대조를 계산한 같은 호출에서 그 run 행에 넷을 되씀. factor 행은 contrast · complete 를 더는 안 씀(옛 행의 값은 남음)
>              규칙은 읽은 표(trigger)에만, 덮어쓰기로만 되쓸 수 있음 — 다른 표는 「cannot redirect a scoped batch … only the rule's trigger table」 로 거절
> 확인          체인 워커 로그 「Executing chained batch updates to 'contrast_run' …」 · 그 run 행의 computed_at 이 참
> 뜻           넷 다 빔 = 아직 안 돎(또는 until 이 비어 거절) · computed_at 있고 candidates 0 = 돌았고 후보 0
>             [ChainRule] 줄의 rows_out 은 이제 factor 행 수 + run 행 수(run 하나면 N+1)
> 급할 때       Chain 탭에서 contrast_factor_from_run 의 enabled 를 false 로 저장
> ```

---

> ## 🔴 [09-30 오전 4] **조인이 시각 칸 값을 옮겨도 쓰기가 안 깨짐 — 층 · 표 · 다시 읽은 값이 같은 순간 — 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  조인의 take 가 datetime 칸이면 전에는 그 규칙의 쓰기 묶음이 통째로 TypeError(층 JSON 이 파이썬 시각을 못 씀)
>              이제 쓰기 문 경계가 시각 값을 시간대 꼬리 있는 ISO 글로 바꿔 층 · 표에 씀 — 같은 순간
>              파일에서 오는 글 값은 한 글자도 안 바뀜
> 확인          그 조인이 돈 뒤 체인 로그에 TypeError 줄이 없고, 그리드 그 칸 · 소스 관리의 chain_ingestion 층에 값
> 뜻           같은 순간을 다시 옮기면 표 칸을 매번 다시 씀(값 비교가 글자라 철자만 달라도 «바뀜») — 사건이 그만큼 남음
>             행 방송의 시각 TypeError(동결 09-29)는 그대로 — 방송은 커밋 뒤 표에서 다시 읽은 시각을 실음
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-30 오전 3] **설정엔 있는데 떠 있는 프로세스의 모델이 모르는 칸은 층도 표도 안 씀 — 버린 칸으로 세고 파일 줄에 이름 — 마이그레이션 «없음» · 재기동 서버 · 워처 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  Reload 실패 · 설정과 모델이 갈리는 순간 · 모델이 건너뛰는 칸 이름(is_graph_synced · needs_graph_rollback ·
>              graph_synced_at) — 전에는 층엔 값을 쓰고 표 값은 조용히 안 써서 「층엔 값 · 표엔 빈칸」이 됐음
>              이제 그 칸은 층도 표도 안 쓰고 버린 칸(unmapped_column)으로 셈 — 층과 표가 어긋나지 않음
> 확인          파일 처리 줄(워처 로그 · 파일 기록)의 「Next: reload or restart so this process holds the unmapped columns, then Retry the file. Not written: unmapped_column <칸>=<값 수> over N row(s)」(10-01 d4a949a8c ③ 에서 이 모양으로 — 옛 글: declared, but this
>              process's model does not hold the column; reload or restart, then Retry the file.」
> 뜻           그 줄이 뜨면 그 칸 값은 «어디에도» 안 들어감 — Reload(안 되면 재기동) 뒤 그 파일을 Retry 하면 들어감
>             칸 이름이 위 셋 중 하나면 Reload · 재기동으로도 안 됨 — 표 편집기에서 칸 이름을 바꿔야 함
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-30 오전 2] **기존 표에 칸을 더하고 저장 · Reload 만 해도 그리드가 그 칸을 보여 줌 (재기동 없이) — 마이그레이션 «없음» · 재기동 서버 · 워처 · 체인 워커 (run_app.bat 로 전체)**
>
> ```
> 무엇이 바뀌나  표 편집기로 칸을 더해 저장하거나 Reload 해서 떠 있는 프로세스가 그 칸을 모델에 붙이면, 그 프로세스의
>              SQL 컴파일 캐시를 비움 -> 전에 쓰던 질의도 새 칸을 실어 읽음
>              전에는 표와 층엔 값이 있는데 그리드가 그 칸을 모든 행에서 빈칸으로 보였고, 재기동해야 떴음
>              칸이 안 바뀐 저장 · Reload 는 캐시를 안 비움
> 확인          칸을 더해 저장 -> 파일 한 번 적재 -> 새로고침 없이도(다음 페이지 요청에서) 그리드에 그 칸 값
> 뜻           이 수리는 재기동 «뒤»부터 들어감 — 지금 떠 있는 프로세스는 옛 코드라 이번 재기동 한 번은 필요
>             저장 순간 표가 바쁘면(누가 읽는 중) 칸을 만드는 ALTER 가 20초 잠금에 밀려 칸이 안 생길 수 있음 — 서버 로그
>             「[Schema Sync] column '…' was not added to '…' - another session held the table past 20s」 가 뜨면 그 칸은
>             다음 저장이나 재기동 때 생김(이 수리와 별개)
> 급할 때       스위치 없음 — 재기동이 옛 방법 그대로 풀어 줌
> ```

---

> ## 🔴 [09-30 오전] **원장 선언 창: 역할을 엔티티로 고르고 키 없이 저장해도 500 없음 · 저장 없이 키 칸을 받는 읽기 — 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  역할을 entity 로 고르고 키를 아직 안 적은 채 Save -> 전엔 500(KeyError 'keys'), 이제 저장되고 그 칸의 거절 이름이 뜸
>              POST /admin/ontology-explorer/authoring/plan  {selection, draft_id, raw} -> 저장 없이 그 본문의 폼(키 칸 포함)
>              GET plan 과 같은 답 모양 · 쓰는 것 0 · 화면이 이 길을 부르는 것은 클라 몫
>              plan 의 행마다 "reshapes" — true 인 잎(entity_type · kind · predicate …)이 바뀌면 화면이 다시 물음
> 확인          그 Save 가 200 이고 화면에 「Saved but not applied」 와 그 칸의 거절 줄
> 뜻           「Saved but not applied」 인 채 파일에 남은 소스는 재기동 뒤 원장이 «그 소스만» 안 읽음 —
>             서버 로그 「[Ledger] source <id> is NOT planned: …」(다른 소스는 읽음). 키를 채워 다시 저장하면 풀림
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-30 아침] **대조 저장 — contrast_run 한 줄 -> 체인 -> contrast_factor (걷기의 순위 그대로) — 마이그레이션 «없음» · 재기동 서버 · 체인 워커 (run_app.bat 로 전체를 다시 띄우면 둘 다 됨)**
>
> ```
> 준비          표 둘: server/config/sample/table_config.json.sample 끝의 contrast_run · contrast_factor 를 운영 table_config 에 (표 편집기 저장)
>              규칙 하나: server/config/sample/chain_rules.json.sample 끝의 contrast_factor_from_run 을 운영 chain_rules 에 (Chain 탭 저장)
>              맵퍼는 추적 파일 server/mappers/contrast_walk.py — Chain 탭 맵퍼 고르개에 소유자 맵퍼와 같이 «mappers.contrast_walk / contrast_walk» 로 뜸
> 무엇이 바뀌나  contrast_run 에 행이 들어오면 체인이 그 행의 인자로 걷기 라우트(GET /api/ledger/subgraph)를 부르고
>              propagation.ranked 를 contrast_factor 행으로 씀 — 키 run_id + node_id. until 이 걷기를 묶음
> 확인          체인 워커 로그 「[ChainRule] rule=contrast_factor_from_run kind=mappers.contrast_walk.contrast_walk target=contrast_factor rows_in=1 rows_out=<N> …」
>              같은 인자로 부른 걷기의 propagation.ranked 수 = <N> = contrast_factor 에서 그 run_id 의 행 수
> 뜻           contrast=unexamined -> 양품(negative) 씨앗이 없었음 · complete=false -> 걷기가 잘림(node_limit) — 순위는 잠정
>             「[ContrastWalk] … until is empty - …」 -> until 이 빈 run 이라 안 씀 (걷기를 묶을 수 없어서)
>             until 은 시간대를 붙여 적는다 — 안 붙이면 DB 세션 시간대로 읽힘(보드는 Z 를 붙여 보냄, 그리드에 손으로 적을 때만 해당)
>             행 0 -> 후보 0 이거나 아직 안 돎 — 둘을 가를 자리는 아직 없음(보고의 제안)
>             contrast_run 행을 지우면 -> 그 run 의 factor 행은 «남고» 칸이 전부 비워짐(맵퍼가 찍은 도장으로 걷힘, 키 R1|<노드> 만 남음)
>             그때 「[ChainRetract] … 파일 맵퍼는 … 적는지는 제품이 모릅니다」 줄이 나와도 이 규칙엔 해당 없음 — 이 맵퍼는 도장을 찍음
> 급할 때       Chain 탭에서 contrast_factor_from_run 의 enabled 를 false 로 저장
> ```

---

> ## 🔴 [09-29 밤 4] **체인 규칙을 저장하면 체인 워커가 «규칙만» 다시 읽음 — 마이그레이션 «없음» · 재기동 run_app.bat 전체(서버 · 체인 워커 · 워처 · 스케줄러)**
>
> ```
> 무엇이 바뀌나  Chain 탭 저장 · 문법 변환 -> 범위(chain_rules)를 실은 SYSTEM_RELOAD 한 행
>              체인 워커: 규칙 파일만 다시 읽음 — 매퍼 다시 불러오기 · 표 모양 맞추기 · 웜업 없음
>              워처 · 스케줄러: 그 행은 지나감. Reload 버튼(범위 없음)은 전과 같이 전부
> 확인          체인 워커 로그 「[Reload] SYSTEM_RELOAD chain_rules (Event ID: N) - re-reading the chain rules only」
>              바로 다음 「[Reload] Loaded N active chain ingestion rules.」 — 저장 뒤 보통 1 초 안, 길어도 3 초
>              GET /admin/chain/queue 의 rules_base 가 저장 답의 base 와 같으면 워커가 그 저장을 읽은 것
>              rules_loaded_age_seconds 는 그 뒤 지난 초
> 뜻           rules_base 가 저장 답의 base 와 다르면 워커가 아직 안 읽음 — 3 초 넘게 다르면 워커 로그를 봄
>             서버 로그 「saved, but the chain worker was NOT told」 -> 워커는 모름. Reload 를 누름
>             규칙이 새 맵퍼 이름을 가리키면 그 이름을 못 찾을 때만 맵퍼 폴더를 한 번 더 훑음
>                새 «파일»은 찾음 · 이미 불러온 파일에 새로 적은 함수는 못 찾음(「unresolvable」) -> Reload
> 급할 때       스위치 없음 — Reload 버튼이 전과 같이 전부 다시 읽음
> ```

---

> ## 🔴 [09-29 밤 3] **유일 인덱스 보고의 「빈 키」가 조인과 같은 판정 — 마이그레이션 «없음» · 재기동 체인 워커 · 서버 (run_app.bat 로 전체를 다시 띄우면 둘 다 됨)**
>
> ```
> 무엇이 바뀌나  인덱스 보고(키가 «비어 있습니다» — 중복이 아니라 부재)의 빈 판정이 조인의 것(crud.is_blank_key_part)과 하나
> 확인          보고 문장은 그대로 — PostgreSQL 에선 키 식이 텍스트라 NaN 키는 'NaN' 으로 와서 전처럼 «중복», NULL·빈 값은 전처럼 «부재»
> 뜻           갈리던 값은 실수 nan · inf · -inf 셋뿐이고 PostgreSQL 보고엔 그 값이 실수로 들어오지 않음
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-29 밤 2] **조인 선언 한 칸 `derive.join.blank: "skip"` — 짝이 된 빈 값은 안 씀(파일 값이 섬) — 마이그레이션 «없음» · 재기동 체인 워커 · 서버 (run_app.bat 로 전체를 다시 띄우면 둘 다 됨)**
>
> ```
> 무엇이 바뀌나  적은 조인: 짝이 된 원천 행의 take 값이 비면 그 칸을 안 씀 — 층 없음, 파일 값이 그대로 보임
>              값이 있는 take 는 전처럼 덮음 · 안 적은 조인은 전처럼 빈 값을 씀
>              "skip" 말고 다른 낱말은 저장·로드에서 거절: 「derive.join.blank 'yes' - one of skip」
> 확인          서버 로그 「<규칙>: N blank answer(s) not written (blank: skip) - core_wafer_id=<n>」 (한 번 돌 때 한 줄)
> 뜻           이 칸을 켜도 그 조인이 «전에» 쓴 빈 층은 남아 파일 값을 계속 가림 — 아래로 걷음
> 이미 덮인 것  ① 수만 보기   python server/scripts/chain_replay_cli.py withdraw dt_log chain_ingestion --columns core_wafer_id
>             ② 걷기       같은 줄 끝에 --apply
>             ③ 다시 쓰기   python server/scripts/chain_replay_cli.py replay <조인 이름>:target   (수만 · 끝에 --apply 로 씀)
>             ⚠️ chain_ingestion 층은 칸당 «하나» — ② 는 빈 층만이 아니라 그 칸에 체인이 쓴 값 «전부»를 걷음
>                같은 칸을 쓰는 다른 규칙이 있으면 ③ 을 그 규칙들에도. ③ 이 끝날 때까지 그 칸은 파일 값(없으면 빈 칸)
>             같은 ①~③ 이 [09-29 밤] 의 것도 걷음 — 조인 키가 모두 빈 행끼리 전에 짝지어 쓴 값은 남아 있는데,
>                ② 가 그 칸의 체인 값을 걷고 ③ 은 이제 그 행을 짝짓지 않으므로 다시 안 씀. 칸은 그 조인의 take 칸들(--columns a,b)
> 급할 때       선언에서 blank 칸을 지우면 전처럼(빈 값을 씀)
> ```

---

> ## 🔴 [09-29 밤] **조인 키 칸이 «모두» 빈 행은 짝이 아님 — «일부»만 비면 그대로 — 마이그레이션 «없음» · 재기동 체인 워커 · 서버 (run_app.bat 로 전체를 다시 띄우면 둘 다 됨)**
>
> ```
> 무엇이 바뀌나  선언한 조인(derive.join)의 짝 키 칸이 모두 빈 행
>              into 표 행이면 답을 찾지 않음 · 원천(on.table) 행이면 누구의 답도 아님
>              키가 둘 이상이고 일부만 비면 전과 같이 빈 칸끼리 같음
> 확인          서버 로그 「<규칙>: N row(s) with every join key empty - not matched (target side)」
>              또는 「(value side)」 — 그 규칙이 한 번 돌 때 쪽마다 한 줄, N 이 0 이면 안 나옴
> 뜻           전에 빈 키끼리 짝지어 쓴 값은 «남음» — 이제 조인이 그 행에 대해 말하지 않으므로 지우지 않음
>             원천에 빈 키 행이 여럿이라 「둘 이상과 맞아 건너뜁니다」 가 나던 행은 이제 그 줄 대신 위 줄이 나옴
>             유일 인덱스는 안 바뀜 — 원천에 키가 모두 빈 행이 둘 이상이면 인덱스는 여전히 안 섬
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-29 저녁 3] **실패한 파일을 폴더째 재시도 — 먼저 보기(수 · 바로 아래 폴더별) — 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  POST /admin/file-ingestion/retry-failed?folder=<폴더>  -> 그 폴더 «아래»(하위 전부) FAILED 만 PENDING_RETRY
>              ...&preview=true  -> 쓰지 않고 count · by_folder(바로 아래 폴더별 수, 폴더에 바로 있는 파일은 ".")
>              폴더 경계로만(C:\a\A 가 C:\a\AB 를 물지 않음) · 대소문자 · 구분자는 파일 시스템대로 · 외부 루트든 관리 폴더든 같은 판정
>              화면의 폴더 고르기 · 버튼은 클라 몫(총괄이 넘김)
> 확인          같은 폴더로 preview 의 count 가 곧 누른 뒤 PENDING_RETRY 가 되는 수
> 뜻           count 0 이면 「No failed file under <폴더>」 — 쓴 것 없음. preview 는 폴더가 없어도 아무것도 안 씀
>             외부 경로 판정도 같은 함수라 이제 대소문자를 파일 시스템처럼 봄(Windows 에서 경로 대소문자가 달라도 같은 루트)
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-29 저녁 2] **웹소켓 연결을 두 번 빼던 ValueError — 대기열 방송이 멈추지 않음 — 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  끊긴 연결을 방송의 보내기 실패와 /ws 끊김이 둘 다 빼도 둘째는 조용히 넘어감 — list.remove ValueError 없음
>              방송은 연결 목록의 사본을 돎 — 도중에 한 명이 나가도 다음 사람을 건너뛰지 않음
> 확인          서버 로그의 「Client disconnected. Total clients: N」 이 「list.remove(x): x not in list」 없이 나옴
>              「Error sending to a client」 가 난 뒤에도 대기열 탭이 계속 새로고침됨
> 뜻           전에는 그 ValueError 하나로 대기열 방송 루프가 끝나 재기동까지 대기열 화면이 안 바뀌었음
> 급할 때       스위치 없음 — 서버 재기동이 그 루프를 다시 세움
> ```

---

> ## 🔴 [09-29 저녁] **외부 경로 파일의 재시도가 워처의 «그 표 처리기»로 돔 — 폴더의 웨이퍼·시각·options 그대로 — 마이그레이션 «없음» · 재기동 워처**
>
> ```
> 무엇이 바뀌나  Retry(파일 인제션) -> PENDING_RETRY -> 워처의 재처리 폴러가 «그 표를 감시하는 처리기»로 다시 읽음
>              전에는 새 처리기를 만들어 외부 경로를 몰랐음 -> 외부 파일 재시도가 「No custom pipeline parser matched」로 다시 실패
>              워처가 처리기를 다 세우기 전엔 PENDING_RETRY 를 집지 않음(다음 바퀴에 집음)
>              워처가 감시하지 않는 표의 기록은 「the watcher runs no handler for table …」 로 FAILED
> 확인          외부 파일 하나가 FAILED 면 원인(예: unit 없음)을 external_sources[].options 로 고치고 워처 재기동 -> Retry
>              -> 인입 기록 SUCCESS · 행에 폴더의 웨이퍼 · cell source 이름 external:<parser>:<경로>
> 뜻           관리 raws/ 파일 재시도는 전과 같음(파일을 옮기지 않고 그 자리에서 읽음)
>             options 를 바꾼 것은 워처 재기동 뒤에만 처리기에 실림 — 재기동 없이 Retry 하면 옛 options 로 읽음
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-29 오후 3] **수집기 백필이 «다음 시작일»을 말함 — 지난 실행이 멈춘 자리 — 마이그레이션 «없음» · 재기동 서버 · 스케줄러(auto update) · 체인 워커**
>
> ```
> 무엇이 바뀌나  /admin/retroactive/runs 의 collector_backfill 실행마다 next_start (KST, backfill Start 칸이 받는 모양)
>              끝까지 돔 -> 마지막 창이 잘린 그 시각 · 취소 -> 끝낸 다음 날 00:00 · 실패 -> 실패한 날 · 도는 중 -> null
>              실행 결과에 done_until 이 실리고, 결과 문장에 「collected up to (KST) <날짜>」 가 붙음
>              화면의 Start 칸 미리 채우기는 클라 몫(총괄이 넘김) — 이 착지만으로는 칸이 안 바뀜
> 확인          백필을 한 번 돌리고 끝난 뒤 GET /admin/retroactive/runs 에서 그 실행의 next_start 를 봄
>              그 값을 Start 로 다시 돌리면 창이 이어짐(겹침 · 빈틈 없음)
> 뜻           null 이면 이어 누를 자리가 없음 — 도는 중이거나, 이 착지 «전»에 끝까지 돈 기록(잘린 자리가 안 적혀 있음)
>             재기동 전 스케줄러 · 체인 워커가 돌린 실행은 done_until 이 없음 — 끝까지 돈 것은 null, 취소 · 실패는 날 수로 답함
> 급할 때       스위치 없음 — next_start 는 제안일 뿐, Start 칸에 아무 날이나 적어 돌릴 수 있음
> ```

---

> ## 🔴 [09-29 오후 2] **저장 뒤 로드에서 빠진 선언이 탐색기 목록에 남음 — 같이 빠진 것까지 · 저장 답도 댐 — 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  원장 선언이 저장된 뒤 로드가 그 선언을 빼고 읽으면, 탐색기 목록(스냅숏 invalid)에 그 선언과 «같이 빠진» 선언이 남음
>              전에는 로드가 통째로 실패할 때만 목록이 찼음 — 하나만 빼고 읽으면 목록이 비었음
>              같이 빠진 것의 사유 = "entity <x> left out" · "predicate <x> left out" (전에는 한국어 문장)
>              저장 답(validation_errors)도 같이 빠진 것을 댐 — 같은 판정 자리(resolve_declarations)
>              빠진 것이 하나라도 있으면 스냅숏의 active_snapshot.valid 가 false
> 확인          서버 로그의 「[Ledger] <선언> is NOT read」 줄이 있으면, 탐색기 목록에도 그 선언이 사유와 함께 있어야 함
> 뜻           목록에 남은 것 = 파일에는 있는데 로드가 안 읽은 것. 같이 빠진 것은 앞의 것을 고치면 같이 돌아옴
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-29 오후] **체인 규칙은 «바뀔 때만» 읽음 — 대기열 새로고침이 규칙을 다시 읽지 않음 — 마이그레이션 «없음» · 재기동 서버 · 체인 워커**
>
> ```
> 무엇이 바뀌나  서버는 규칙을 한 번 읽어 두고 씀. 다시 읽는 때: 체인 규칙 저장(체인 탭 raw 편집기 · 문법 바꾸기) 직후 · Reload Configs
>              체인 워커는 전과 같음(부팅 · SYSTEM_RELOAD 때 읽음). 워커의 DELETE 그룹 경로도 읽어 둔 것을 씀
>              [ChainRules] set(N) 줄 = 실제로 다시 읽은 횟수. 대기열 탭이 방송마다 새로고침해도 줄이 안 늘어남
> 확인          grep -c "\[ChainRules\] set(" server/chain_worker.log   를 대기열 탭을 연 채 체인이 도는 동안 두 번 — 수가 그대로여야 함
> 뜻           저장하거나 Reload 를 누를 때만 한 줄씩 늚. 그 밖에 늘면 규칙을 요청마다 읽는 자리가 아직 있다는 뜻
>             ⚠️ 서버를 안 거친 파일 수정(손 편집 · 스크립트 · 복원)은 Reload Configs 를 눌러야 서버 화면에 보임 — 워커는 원래 그랬음
> 급할 때       스위치 없음 — 화면이 옛 규칙을 보이면 Reload Configs
>             Reload 뒤 서버 로그에 「[Reload] chain rules NOT forgotten」 줄이 있으면 서버가 옛 규칙을 들고 있음 — 서버 재기동
> ```

---

> ## 🔴 [09-29 낮] **체인 묶음이 실패하면 «쪼개지 않음» — 재시도 한도에서 통째 FAILED · 새 사건 0 — 마이그레이션 «없음» · 재기동 체인 워커**
>
> ```
> 무엇이 바뀌나  재시도 한도(max_group_attempts, 기본 1)에 닿은 묶음은 반으로 나뉘지 않고 통째로 FAILED. 새 사건을 안 만듦
>              그 묶음의 사건마다 error_log = failed_at · reason(원문 그대로) · rules · tables · rows · row
>              rules · tables = 사유 머리 [rules=.. target=..] 를 쓴 «실패한 자리»의 값. 그 자리가 모르면 null — 그룹이 깨운 규칙으로 안 채움
>              row = 오류 문장이 대는 행 id(최대 10). 안 대면 null — 행을 찾으려고 다시 돌리지 않음
>              맵퍼 실패의 사유 머리가 [rule=X target=Y] 에서 [rules=X target=Y] 로 — 쓰기 실패와 같은 모양
> 돌릴 명령     python server/scripts/outbox_triage.py --count      큐를 모양·원인별로 셈 (드라이런, 아무것도 안 바꿈)
> 확인          재기동 뒤 실패 줄이 묶음마다 «한 줄»:
>              Transaction <tx> permanently failed: <n> event(s), <m> row(s) -> FAILED [rules=<규칙> tables=<표> row=<...>]. 원인: <마지막 줄>
>              그 뒤 같은 tx 에 #half# 가 붙은 사건이 새로 생기지 않아야 함
>              rules=(unknown) 이면 실패한 자리가 규칙을 모름(예: 행이 안 읽혀 규칙이 돌기 전에 거절). row=not given by the error 는 로그 줄에만
> 뜻           한 행이 틀려도 그 묶음 전부(최대 1,000 행)가 FAILED — 의도된 답. 어느 행인지는 사유 원문(어드민 실패 목록의 traceback)
>             재시도 버튼 = 그 묶음을 한 번 다시 PENDING · 새 사건 0
>             이미 큐에 있던 #half# 사건도 한도에 닿으면 통째 FAILED 로 끝남(더 안 나뉨)
> 급할 때       어드민 체인 Pause -> 체인 워커 로그 「under tx 'chain_replay_<run>'」 에서 그 리플레이의 <run> 을 봄
>             -> python server/scripts/outbox_triage.py --set-aside --transactions replay_<run>,chain_replay_<run> --reason "<왜>"
>                (드라이런, 수만 봄) -> 같은 명령에 --apply -> Resume
>             ⚠️ 한 홉 더 번진 사건은 tx 앞에 chain_ 이 하나씩 더 붙음(chain_chain_replay_<run>) — 그 이름을 같이 적거나 --tables <표>
>                --rules <규칙> 은 «그 규칙이 깨울» 대기 사건을 고름 — 리플레이 것만이 아님
> ```

---

> ## 🔴 [09-29 오전 4] **조인의 on.columns 를 «키 + take» 와 집합으로 견줌 — 마이그레이션 «없음» · 재기동 체인 워커 · 서버**
>
> ```
> 무엇이 바뀌나  조인 선언에 on.columns 를 적었으면 그 칸 = 조인을 실제로 깨우는 칸(키 + take) 이어야 함 · 순서 무관
>              다른 칸이 섞이면 그 선언만 로드에서 빠짐 — 로그 [ChainRules] join_trigger_conflict: ... wakes on ['<키>', '<take>'] ...
>              키만 적은 옛 모양은 로드되고 한 줄로 이름 불림 — [ChainRules] '<선언>' writes on.columns [...] - the join key only; ...
> 확인          재기동 뒤 체인 워커 로그에 join_trigger_conflict 줄이 없어야 함. 있으면 그 줄이 보이는 칸 목록을 on.columns 에 그대로 적거나 on.columns 를 지움
> 뜻           on.columns 를 안 적는 것이 기본 — 조인이 스스로 적음. 적었다면 설명일 뿐 깨우는 칸을 바꾸지 않음
> 급할 때       스위치 없음 — 그 선언의 on.columns 를 지우면 됨
> ```

---

> ## 🔴 [09-29 오전 3] **엔터티 class 도 운영자의 낱말 — ["static","probe"] 저장 뒤 엔터티가 선언에서 빠지던 결함 — 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  엔터티 class 에 static · dynamic 밖의 낱말을 적어도 받음(술어와 같음). 빈 낱말은 「없음」으로 접힘
>              코드가 읽는 낱말은 여전히 엔터티 static 하나 — probe 같은 낱말은 행동 없음
> 확인          선언창에서 엔터티 class 에 낱말 하나를 더해 저장 -> GET /api/ledger/declaration 의 entities 에 그 엔터티가 그대로 있고
>              class 가 적은 목록 그대로. 서버 로그에 「[Ledger] entity|… is NOT read」 줄이 없어야 함
> 뜻           「Saved」 뒤 엔터티가 사라지면 그 엔터티의 선언이 문법에서 떨어진 것 — 서버 로그의 NOT read 줄에 칸 이름이 있음
>              (저장은 문법이 틀려도 파일에 씀 — 소유자 판정 「지금은 안읽히면 저장도 안하네」. 읽는 쪽이 그 선언만 뺌)
> 급할 때       스위치 없음 — 그 class 칸을 지우거나 낱말 하나로 되돌리면 오늘 그대로
> ```

---

> ## 🔴 [09-29 오전 2] **class = 낱말 하나 또는 목록 (엔터티 · 술어) · follow=class:<낱말> — 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 선언 예      "vocabulary": {"measures@1": {..., "class": ["model"]}, "inspected@1": {..., "class": "context"}}
>             엔터티는 "class": "static" 도 ["static"] 도 됨. 낱말은 엔터티든 술어든 운영자가 지음 — 코드가 읽는 것은 엔터티 static 하나(위 [09-29 오전 3])
> 걷기         /api/ledger/subgraph?...&follow=class:model   -> 부류 model 을 든 술어 전부를 밟음
>             모르는 낱말 -> 422 · reason predicate_class_not_declared · unknown · declared(선언에 쓰인 낱말)
> 선언 라우트   /api/ledger/declaration 의 entities[].class · predicates[].class 가 «목록»(없으면 null)
>             전에는 엔터티 class 가 낱말 하나("static")였음 — 이 칸을 읽는 서버 밖 소비자가 있으면 모양이 바뀜
> 선언창       술어마다 class 칸(낱말 목록) — 적고 저장하면 파일에 목록 그대로, 다시 열면 그대로
>             ⚠️ 엔터티 class 를 낱말 하나로 적은 선언(이 박스 3 · 샘플 3)은 창에서 그 값을 «보여만» 주고 편집 칸을 안 냄
>                파일은 그대로 맞게 읽힘 — 창에서 고치려면 지우고 목록으로 다시 적음. 창이 낱말 하나를 목록으로 그리는 것은 클라 몫
> 뜻           class 는 운영자가 붙이는 낱말. 제품 동작이 부류 이름으로 갈리지 않음 — 엔터티 static 만 걷기가 읽음(전과 같음)
> 급할 때       스위치 없음 — class 칸을 지우면 오늘 그대로
> ```

---

> ## 🔴 [09-29 오전] **걷기 라우트의 화면 문장이 영어 — reason 낱말은 그대로 — 마이그레이션 «없음» · 재기동 서버**
>
> ```
> 무엇이 바뀌나  /api/ledger/subgraph · key-values · gaps · declaration 의 거절과 빈 응답 message 가 영어. 문장 모양은 「무엇 - 다음 행동」
>              detail.reason 과 나머지 칸(unknown · declared · state …)은 그대로
> 확인          curl -s "http://127.0.0.1:8080/api/ledger/subgraph?seed_type=wafer&seed_limit=1&collect=banana"
>              -> 422 · reason node_type_not_declared · message "Not a declared node type: banana - pick one from 'declared'"
> 뜻           message 는 사람이 읽는 문장이라 바뀜. 코드로 가르는 쪽은 reason 을 읽을 것 — reason 은 안 바뀜
> 급할 때       스위치 없음
> ```

---

> ## 🔴 [09-29 아침] **trigger_columns 가 «막는 칸» — 적힌 칸 밖의 변경에 규칙이 안 돎 — 마이그레이션 «없음» · 재기동 체인 워커 · 서버**
>
> ```
> 재기동 «전»   pull 한 뒤 이 목록을 소유자께 — 적힌 칸 밖의 변경에 이제 안 도는 규칙들
>              conda run --no-capture-output -n assy_manager python -c "import sys; sys.path.insert(0,'server'); from chain import ingestion_worker as w; [print('WAKES', r.get('name'), w.wake_columns(r)) for r in w.load_chain_rules() if w.wake_columns(r)]"
>              WAKES 로 시작하는 줄 하나 = 규칙 하나와 그 규칙을 깨우는 칸. 넓히려면 그 규칙의 trigger_columns(통합 선언은 on.columns)에 칸을 더함
>              조인과 그 :target 짝은 스스로 적으므로 손댈 것 없음
> 무엇이 바뀌나  trigger_columns(∪ require)와 겹치지 않는 사건에 규칙이 안 돎
>              칸 목록이 없는 사건(행 하나씩 쓴 변경 · 옛 사건 · 리플레이)에는 오늘처럼 돎
>              조인 값 표 쪽의 깨우는 칸에 take 칸이 더해짐(전에는 키만) — 값만 바뀌어도 조인이 돎
> 재기동 뒤      로드 때 규칙마다 한 줄   [ChainRules] <규칙> wakes only on: [..]
>              안 돈 묶음마다 한 줄     [Chain] rule <규칙> skipped: none of [..] changed   <- 이제 참: 그 규칙은 실제로 안 돎
> 뜻           값이 안 옮겨지고 skipped 줄이 찍히면 — 그 값을 바꾸는 칸이 깨우는 칸에 없음. 그 칸을 trigger_columns 에 더함
> 급할 때       스위치 없음 — 그 규칙의 trigger_columns 를 지우면 표의 어떤 변경에도 다시 돎
> ```

---

> ## 🔴 [09-28 밤 3] **require 가 조인 양쪽 · 전부 막힌 묶음 · 보강 백필까지 — 마이그레이션 «없음» · 재기동 서버 · 체인 워커**
>
> ```
> 무엇이 바뀌나  조인: 값 표 행의 require 칸이 비면 그 행은 답이 아님 — :target 짝(채워지는 표가 바뀔 때)도 그 값을 안 옮김
>              묶음의 행이 전부 막히면 맵퍼를 부르지 않음. 처음부터 행이 없던 묶음은 오늘처럼 부름
>              보강 백필(어드민 소급 · scripts/backfill_enrichment.py)도 같은 판정으로 거름
> 로그 줄       [Chain] <규칙 또는 선언 이름>: <N> row(s) not handed over - required column(s) empty: <칸>=<N>  — 백필도 같은 줄
> 뜻           아래 [밤 2] 절의 뜻 그대로. 그 절의 「조인은 값 표 쪽만」 줄은 이 착지로 지움
> 조인 오타     손으로 고친 파일에서 on.require 이름이 틀리면 값 표 쪽 규칙은 로드 거절,
>              :target 짝은 돌 때 「require column '<칸>' does not exist on '<표>'」로 거절하고 아무것도 안 씀
> 급할 때       스위치 없음 — 그 선언의 require 칸을 지우면 오늘 그대로
> ```

---

> ## 🔴 [09-28 밤 2] **규칙의 require — 이 칸이 다 찬 트리거 행만 규칙에 넘어감 — 마이그레이션 «없음» · 재기동 서버 · 체인 워커**
>
> ```
> 예시 선언   평평  {"name": "<복사 규칙>", "trigger_table": "dt_log", "target_table": "<정답맵 표>",
>                  "require": ["<키 칸>", "<키 칸>"], "allow_chain_trigger": true, ...}
>            통합  "on": {"table": "dt_log", "require": ["<키 칸>", "<키 칸>"]}
>            allow_chain_trigger 가 있어야 함 — 키를 채우는 것이 inventory 조인(체인 쓰기)이라 이 칸이 없으면 채워져도 안 깨어남
> 로그 줄     [Chain] <규칙 이름>: <N> row(s) not handed over - required column(s) empty: <칸>=<N>, <칸>=<N>
> 뜻         그 행들은 맵퍼에 안 넘어감. 묶음마다 한 줄, 막힌 행이 없으면 줄 없음
>            나중에 그 칸이 채워지는 쓰기에 다시 깨어나 넘어감
>            같은 칸 이름이 계속 찍히면 그 칸을 «채우는 쪽»이 안 채우고 있는 것 — 조인·원천을 볼 것
>            이미 넘어가 쓴 행은 칸이 다시 비어도 안 거둠
> 로드 거절   [ChainRules] <규칙> refused (1): unknown_require_column ... requires ['<칸>'] that '<표>' does not have ...
>            그 규칙 하나만 빠짐(파일 전체 아님). 저장 화면도 같은 문장으로 거절
> 급할 때     스위치 없음 — 그 규칙의 require 칸을 지우면 오늘 그대로
> ```

---

> ## 🔴 [09-28 밤 1] **선언은 자기가 쓴 것에 안 깨어남 — allow_chain_trigger 는 «다른» 선언이 쓴 것만 받음 — 마이그레이션 «없음» · 재기동 체인 워커 · 스케줄러**
>
> ```
> 무엇이 바뀌나  체인이 쓴 사건에 쓴 선언 이름이 실림(payload 의 "written_by")
>              그 선언의 규칙(조인의 원천 규칙 · :target 짝 · 자기 트리거 표에 쓰는 맵퍼)은 그 사건에 안 깨어남 — allow_chain_trigger 가 있어도
> 뜻           오늘 사건의 조인 선언에 allow_chain_trigger 를 다시 적어도 자기 순환은 안 남
>              다른 선언이 쓴 것엔 그대로 깨어남(옵트인) · 같은 쓰기에 다른 선언이 섞였으면 깨어남(그쪽 변화 때문)
>              decide 의 자동 확정 반쪽은 dedup 반쪽의 쓰기에 그대로 깨어남(둘은 다른 규칙)
> 재기동 뒤     재기동 «전»에 쌓인 사건은 "written_by" 가 없어 옛 규칙대로 읽힘 — 대기열이 비면 끝
>              확인: 조인이 쓴 뒤 database_outbox 의 그 사건 payload 에 "written_by": ["<선언 이름>"]
> 급할 때       스위치 없음. 되돌리기는 git revert 뒤 둘 재기동 — 되돌리면 allow_chain_trigger 가 적힌 조인은 다시 자기에 깨어나니 그 칸을 지운 채로
> ```

---

> ## [09-27 아침 6] **예/아니오 칸 셋 더 — 파일명 규칙 required · finding kind active · bypass_proxy — 동작 같음, 문장만 하나로 · 재기동 워처 · 스케줄러**
>
> ```
> 무엇이 바뀌나  세 칸 다 오늘도 true/false 아니면 거절(규칙 · 종류) 또는 기본 true(bypass_proxy) — 로그 문장만
>              「<칸> must be true or false, got <값> - write true or false」로 (bypass_proxy 의 한국어 경고 줄은 사라짐)
> 재기동 뒤     scheduler 로그 "auto_update_control.json: bypass_proxy must be true or false, got … - falling back to true" — 뜨면 그 칸을 true/false 로
> 되돌리기      git revert
> ```

---

> ## [09-27 아침 5] **스크립트 리플레이는 연쇄를 청하지 못함 — chain_replay_cli.py 의 --cascade 없음 — 마이그레이션 «없음» · 재기동 없음(CLI) · API(소급 탭 안내 줄)**
>
> ```
> 무엇이 바뀌나  python server/scripts/chain_replay_cli.py replay <규칙> ... --cascade  ->  "unrecognized arguments: --cascade" 로 거절(아무것도 안 돎)
>              --cascade 없이 돌리면 오늘과 같음 — 리플레이의 쓰기는 하류 규칙을 안 깨움
> 연쇄가 필요하면  그리드에서 행을 찍어 리플레이(그 클릭만 연쇄를 청함 — 옵트인 규칙만)
> 되돌리기      git revert
> ```

---

> ## [09-27 아침 4] **페인트 잠금 기본 문장 영어 — 마이그레이션 «없음» · 재기동 API**
>
> ```
> 무엇이 바뀌나  map_overlay_config.json 의 paint_lock 에 message 를 안 적은 표 -> 화면 문장이 "This cell holds a locked value - it cannot be painted"
> 운영 설정     paint_lock 의 message 칸에 문장을 적어 두었으면 그건 운영자 값 — 그대로 그려짐. 바꾸려면 그 칸을 고침(저장하면 다음 요청부터)
>              찾기: findstr /n "message" server\config\map_overlay_config.json
> 되돌리기      git revert 뒤 API 재기동
> ```

---

> ## 🔴 [09-27 아침 3] **표에 새 칸을 붙이는 스키마 동기화 — 20 s 넘게 막히면 포기하고 프로세스는 계속 — 마이그레이션 «없음» · 재기동 API · 워처 · 체인**
>
> ```
> 무엇이 바뀌나  선언에 새 칸이 생겨 기동 · 설정 저장 때 ALTER TABLE ... ADD COLUMN 을 걸 때, 그 표를 잡은 세션이 있으면 20 s 뒤 포기
>              (전: 끝없이 기다림 — 기동이 거기서 멈추고, 그 표의 읽기 · 쓰기가 ALTER 뒤에 줄 섬)
> 재기동 뒤     각 프로세스 로그 "[Schema Sync] column '<칸>' was not added to '<표>' - another session held the table past 20s. …"
> 뜻           그 표는 칸이 붙을 때까지 읽기 · 쓰기가 실패(「column "<칸>" does not exist」) · 기동과 다른 표는 돎
> 뜨면         conda run --no-capture-output -n assy_manager python server/scripts/diagnose_db_health.py — 그 표를 잡은 pid 확인
>              그 트랜잭션을 끝낸 뒤 설정 저장(리로드가 다시 붙임) 또는 재기동
> 같이 바뀜     원장 파티션 DDL 의 「락을 못 잡음」 판정이 같은 함수 — statement timeout 은 더 이상 「락」이라 말하지 않음
> 급할 때       스위치 없음. 되돌리기는 git revert 뒤 셋 재기동
> ```

---

> ## 🔴 [09-27 아침 2] **예/아니오 칸은 true/false 만 — 체인 규칙 · 수집기 · 원장 묶음 · 표기 · 맵 · 자동 확정 — 마이그레이션 «없음» · 재기동 넷 다(API · 워처 · 체인 · 스케줄러)**
>
> ```
> 재기동 «전»   운영 설정에 true/false 아닌 예/아니오 값이 있나 — 둘 다 저장소 루트에서
>              conda run --no-capture-output -n assy_manager python -c "import sys; sys.path.insert(0,'server'); import chain_bindings; from chain import ingestion_worker as w; rules=w.read_rules_document()['rules']; bad=[(r.get('name'), f) for r in rules for f in chain_bindings.flag_refusals(r)]; [print(*b) for b in bad]; print('chain rules checked:', len(rules), '| not true/false:', len(bad))"
>              conda run --no-capture-output -n assy_manager python -c "import sys; sys.path.insert(0,'server'); import map_overlay; from maps import preset_routing as p; c=map_overlay.load_overlay_config(); t=list(c.get('preset_routing') or {}); [p.resolve_routing_config(c,x) for x in t]; l=list(c.get('paint_lock') or {}); [map_overlay.get_paint_rules(c,x) for x in l]; print('map routing tables checked:', len(t), '| paint lock entries checked:', len(l))"
>              뜻: 줄마다 「<규칙> <칸> must be true or false, got <값> - write true or false」 · 맵은 「… ignored: …」 경고 줄
>              뜨면 그 칸을 true 또는 false 로 고친 뒤 재기동. 안 고치면 — 체인 규칙은 «안 섬»(오늘 1 · "true" 로 돌던 규칙도 멈춤),
>              맵 라우팅 · 페인트 잠금 항목은 «안 씀»(오늘 0 · "false" 가 켜짐으로 읽히던 것)
>              끝 줄의 checked 수가 0 이면 파일을 못 읽은 것 — 경로부터
> 바뀌는 것     체인 규칙: 예/아니오 칸(enabled · is_batch · allow_* · idempotent · key.unique · decide 의 auto_confirm · alignment)이
>              true/false 아니면 로드 · 저장에서 그 선언이 안 섬 — 전에는 "false" 글자가 켜짐(allow_retraction 이면 지우기가 켜짐)
>              맵: 라우팅 · 페인트 잠금의 enabled 도 같음 — 그 항목을 안 쓰고 경고 한 줄
>              나머지(수집기 · 원장 묶음 · 표기 · 자동 확정 · map_push_ok · 수집 설정 여섯 · std_parse)는 전에도 거절/기본값 — «문장»만 하나로
> 재기동 뒤     chain_worker.log "[ChainRules] <규칙>: <칸> must be true or false, got …" — 그런 규칙마다 한 줄
> 급할 때       스위치 없음. 그 칸을 true/false 로 고치면 다음 리로드부터 섬. 되돌리기는 git revert 뒤 넷 재기동
> ```

---

> ## 🔴 [09-27 아침 1] **치워 둔 사건 다시 돌리기 — 규칙마다 한 번 · 연쇄 없음 — 마이그레이션 «없음» · 재기동 API · 스케줄러**
>
> ```
> 무엇이 바뀌나  소급 탭 "Run set-aside events again" · outbox_triage.py --rerun-set-aside · --replay-cancelled
>              치운 사건이 가리키던 행을 그 표의 규칙마다 «한 번» 리플레이 — 그 쓰기는 하류 규칙을 «안 깨움»(옵트인이어도)
>              (전에는 체인처럼 연쇄 — 소유자 09-27 「큰 소급 치워둔거니 한번만」)
> 그대로        그리드에서 행을 찍어 리플레이하면 오늘처럼 연쇄(옵트인 규칙만)
> 확인          소급 탭 그 연산의 안내 줄 "It replays the rows those events named, each rule once - nothing downstream runs; …"
>              옛 문장 "… cascades like the chain would have" 가 보이면 API 가 옛 코드 — 재기동
> 뜻           다시 돌린 뒤 하류 표가 옛 값이면 정상 — 하류가 필요하면 하류 규칙을 소급 탭 "Replay chain rules over old data (R1)" 로 따로, 또는 그리드에서 행 리플레이
> 급할 때       스위치 없음. 되돌리기는 git revert 뒤 API · 스케줄러 재기동
> ```

---

> ## 🔴 [09-27 새벽 1] **@mapper 규칙도 지운다 — allow_retraction(잡마다) · allow_replace_map(맵마다) — 마이그레이션 «없음» · 재기동 체인 워커 · API**
>
> ```
> 무엇이 바뀌나  @mapper 맵퍼를 쓰는 규칙에 allow_retraction / allow_replace_map 이 적혀 있으면 착지 «뒤 첫 실행부터» 지움
>              (전에는 그 칸이 아무 일도 안 했음 — 덮어쓰기만)
> 재기동 뒤     chain_worker.log "[ChainRules] <규칙>: @mapper removes by job - …" 또는 "… map by map - …" — 그런 규칙마다 한 줄
>              거절 "[ChainRules] <규칙> refused …: sdk_two_removals · sdk_removal_needs_batch · sdk_map_key_not_on_trigger · sdk_job_column"
>              뜻: 그 규칙은 안 돎 — 문장이 다음 행동을 적음("is_batch": true 등)
> 절반 가드     이번에 한 행도 안 낸 잡이 가진 행이 20 이상이면 "[DtMapRetraction] … DECLINED … Next, to remove them on purpose: …"
>              뜻: 아무것도 안 지움. 정말 지우려면 그 줄이 적은 대로 그리드에서 그 잡의 행을 지움
> replace_map   맵을 통째로 — 사람이 고친 값(CellOverwrite)도 같이 지움(소유자 판정). retract 는 살림
> 급할 때       그 규칙의 allow_* 칸을 지우고 설정 저장(리로드) — 덮어쓰기만으로 돌아감
> 되돌리기      git revert 뒤 체인 워커 · API 재기동
> ```

---

> ## 🔴 [09-26 밤 8] **넓은 조인은 쪽으로 — 1,000 행씩 답하고 · 쓰고 · 커밋 · 왼쪽 조회 인덱스 · 두 칸 키가 만 개를 넘어도 섬 — 마이그레이션 «없음» · 재기동 체인 워커**
>
> ```
> 재기동 뒤     chain_worker.log "[Join] 조회 인덱스 ix_vjoin_<표>_<칸>… 를 세웠습니다 (<초> s)" — 조인마다 처음 한 번(이미 있으면 줄 없음)
>              미뤄지면 "… 세우지 못했습니다 — … 다음 기동/리로드로 미룹니다. 그동안 이 조인은 왼쪽 행을 인덱스 없이 고릅니다(느림)"
> 조인 줄       "[Chain] <규칙> -> <표>: page <N>, <M> row(s)" — 둘째 쪽부터 쪽마다 한 줄
>              [ChainRule] 줄의 rows_out 은 «모든 쪽»의 행 수 — 조인이 첫 부름에 한 번 읽은 것으로 셈
> 읽는 때       조인은 답에 필요한 것(왼쪽 키 · 맞는 오른쪽 행)을 첫 부름에 «한 번» 읽음 — 같은 묶음의 앞 규칙이 쓴 값은
>              이 조인이 안 봄(한 번에 쓰던 때와 같음)
> 뜻           쪽마다 커밋 — 도는 동안 왼쪽 표가 반만 붙은 채 보일 수 있음
>              중간에 실패하면 앞 쪽은 남고 그 묶음은 FAILED(시도 1) — 리플레이가 같은 값은 헛쓰기로 지나며 나머지를 채움
> 급할 때       그 조인만 끄기: chain_rules.json 의 그 선언에 enabled: false + 설정 저장(리로드) · 나중에 리플레이
> 되돌리기      git revert 뒤 체인 워커 재기동. 남은 ix_vjoin_* 인덱스는 되돌린 코드가 모름 — 필요 없으면 손으로 DROP INDEX CONCURRENTLY
> ```

---

> ## 🔴 [09-26 밤 7] **기동 인덱스 작업은 첫 박동 «뒤», 체인 루프 «옆»에서, 20 s 시한 — 마이그레이션 «없음» · 재기동 체인 워커**
>
> ```
> 재기동 뒤      체인 워커가 첫 박동부터 냄 — 선언된 유일 인덱스 세우기 · 걷기는 그 «뒤» 옆 작업(루프는 안 기다림)
> 미뤄진 줄      chain_worker.log
>   "[Join:<규칙>] 유일 인덱스를 세우지 못했습니다 — 다른 세션이 표 <표> 를 20s 넘게 잡고 있습니다. 다음 기동/리로드로 미룹니다 ..."
>       뜻: 그동안 그 조인은 행 단위 그물만(오른쪽 행이 둘인 왼쪽 행은 거절). 급하지 않음 — 다음 설정 저장이나 재기동에 다시
>   "[Join] 인덱스 <이름> 를 걷지 못했습니다 — ... 그동안 이 인덱스가 그 표의 쓰기에 23505 를 낼 수 있습니다(S-248)"
>       뜻: 그 표 쓰기가 23505 로 실패하면 이것이 이유 — diagnose_db_health.py §3 로 표를 잡은 pid 를 찾아 끝낸 뒤 설정 저장(리로드)
> 리로드         설정 저장(리로드)마다 인덱스 작업이 다시 돎 — 전에는 기동 때만 돌았음(주석은 「리로드마다」라 적혀 있었음)
> foreign_beat   이 착지 뒤엔 인덱스 작업 때문에는 안 생김(첫 박동이 먼저). 그래도 보이면 첫 박동 앞에 남은 것:
>                import 때 스키마 동기화(run_chain_worker.py · 설정에 새 컬럼이 있을 때 ALTER TABLE · 시한 없음) — 소유자 물음으로 올라가 있음
> 시한 값        server/db_safety.py 의 DDL_LOCK_TIMEOUT = "20s" — 원장 파티션 DDL 과 같은 상수 하나
> 스위치         없음. 되돌리기는 git revert 뒤 체인 워커 재기동
> ```

---

> ## 🔴 [09-26 밤 6] **표기 3 단계 — 선언 전에 저장된 값을 선언한 철자로(제자리) — 마이그레이션 «없음» · 재기동 API**
>
> ```
> 언제          notation_rules.json 에 "write": true 칸을 선언한 «그날». 선언이 없으면 할 일 없음
> 순서          ① 소급 탭 "Fold stored values into the declared spelling" — table · 드라이런(Count) 먼저
>              ② 같은 표에 "Fold file layers that repeat a newer one" — 철자만 달랐던 파일 층이 이제 같은 값
>              ③ python server/scripts/tune_layer_tables.py --table cell_sources --vacuum
> 드라이런 뜻    "... row(s) would take another row's key and are skipped" — 두 옛 철자가 한 키가 됨. 병합 안 함 — 별칭 행이나 규칙을 고치고 다시
>              "... value(s) change again on a second fold - the run stops there" — 선언부터 고침. 실행은 그 페이지 앞에서 멈춤
> 사실 둘        맵 키 칸(map_key_columns)을 write 로 선언하면 소급을 같은 날 — 첫 replace_map 푸시가 옛 철자 행의 뺀 칸을 못 지움
>              별칭 표: python server/scripts/install_product_tables.py --apply -> POST /admin/reload-configs -> 선언
> 되돌리기       불가 — 저장돼 있던 철자는 칸마다 이력 줄(notation_backfill)의 옛 값. 코드는 git log --oneline --grep "feat(notation): notation stage three" 를 revert
> ```

---

> ## 🔴 [09-26 밤 6] **문 가르기 복기 넷 — 켜짐 판정 하나 · 재시도 집계 · 파일 마무리 단계 · 리플레이 기록 전 판정 — 마이그레이션 «없음» · 재기동 넷 다(API · 워처 · 체인 · 스케줄러)**
>
> ```
> 돌릴 것      없음. 재기동만
> 재기동 뒤     chain_worker.log  "[ChainRules] set(N): ..." — 규칙 옆 " OFF" 는 enabled 가 false · 0 · null 인 규칙
>              뜻: 0·null 은 전에도 워커가 안 깨웠고 명단도 OFF 였다. 이제 파생 표 집계도 같은 답(도는 규칙은 하나도 안 바뀜)
>              통합 선언에 enabled 0·null 을 적었으면 이제 «규칙을 안 세움» + 노트 "enabled=false - no rule stands for it"
> 워처 로그     "[BK Conflict Recovered]" 다음 그 파일의 FILE 줄 — side-table rows · row build 칸 수가 커밋된 시도 것만
>              뜻: 되감긴 시도의 초는 그 쓰기 단계의 «이름 없는 나머지»로 감. 나머지가 굵으면 위 경고 줄이 이유
> 헬스         마지막 청크 뒤에 멈추면 워처 박동 단계가 "finish" (전엔 마지막 청크의 commit 으로 읽힘)
> 소급 탭       chain_replay 에 멱등 아닌 규칙 · 등록 안 된 트리거 표 -> 요청 자리에서 거절, 실행 행이 안 생김
> 스위치        없음. 되돌리기는 git revert 뒤 재기동
> ```

---

> ## 🔴 [09-26 밤 5] **표기 2 단계 — "write": true 칸은 쓸 때 접혀 저장 — 마이그레이션 «없음» · 재기동 넷 다(API · 워처 · 체인 · 스케줄러)**
>
> ```
> 무엇이 바뀌나  server\config\notation_rules.json 에서 "write": true 인 칸만 — 파일 · 격자 · 체인 쓰기가 접힌 값을 저장
>              그 파일이 없거나 write 칸이 없으면 아무것도 안 바뀜
>              키 칸을 write 로 선언해도 새 행 없음 — 옛 철자로 저장된 행을 찾아 그 행의 키를 접힌 키로 바꿈
> 이력          접기가 철자를 바꾸고 그 칸이 쓰일 때 칸마다 한 줄(old = 들어온 철자, new = 저장값). 같은 철자를 다시 보낸 파일은 줄 없음
> 확인          watcher.log "[Ingest] <표> FILE <파일>: ... · time rule left as written: no matching format N, time zone written M"
>              time 칸이 그대로 둔 값의 수 — 0 이면 이 칸이 안 나옴. N 이 크면 그 칸의 "from" 모양을 더 적음
>              GET /admin/config/notation/preview?table=<표>&column=<칸> 의 folds_again 이 0 이 아니면 선언부터 고침(소급이 거기서 멈춤)
> 별칭 표        notation_alias 라이브 설치는 총괄이 소유자께(1 단계 항목의 install_product_tables.py)
> 스위치        그 칸의 "write": true 를 지우면 5 초 안에 다음 쓰기부터 안 접음. 이미 접혀 저장된 값은 그대로
> 되돌리기       git log --oneline --grep "feat(notation): notation stage two" 의 커밋을 git revert 뒤 네 프로세스 재기동
> ```

---

> ## 🔴 [09-26 밤 4] **비상 정지 — 체인 일시정지 · 대기열 치워 두기 · 다시 돌리기 — 마이그레이션 «없음» · 재기동 넷 다(API · 워처 · 체인 · 스케줄러)**
>
> ```
> 사고 때 순서   ① Pause          어드민 POST /admin/chain/pause {reason}  ·  또는 conda run --no-capture-output -n assy_manager python server/scripts/chain_pause_cli.py pause --reason "왜"
>                                 새 묶음을 안 잡고 · 도는 묶음은 다음 단계에서 되감고 · 도는 쿼리는 그 자리에서 끊음. 대기열은 그대로(잃는 것 0 · 재시도 횟수 안 올림)
>               ② 치워 두기       소급 탭 "Set queued chain events aside" — 표 · 규칙 · 트랜잭션 중 하나 이상 + 사유. 드라이런이 사건 수 · 행 수를 먼저 보여 줌
>                                 CLI: python server/scripts/outbox_triage.py --set-aside --tables 표 --reason "왜" (--apply 로 실제로)
>               ③ Resume          POST /admin/chain/resume  ·  chain_pause_cli.py resume — 남은 대기열이 다시 흐름
>               ④ 나중에           소급 탭 "Run set-aside events again"(같은 범위) — 치운 사건이 가리키던 행을 리플레이, 규칙마다 한 번 · 연쇄 없음(09-27 아침 1 절)
>                                 CLI: outbox_triage.py --rerun-set-aside --tables 표 --apply
> 확인          GET /admin/chain/pause 가 요청 상태 · /health 의 chain 이 paused(degraded) 면 워커가 멈춤을 지킴
>               chain_worker.log "[Chain] paused - tx '...' was rewound at a stage boundary" — 되감긴 묶음마다
> 재기동        멈춤은 재기동해도 유지 — 풀려면 Resume. 상태 파일: server\config\chain_control.json
> 뜻           치운 사건은 지워지지 않음 — cancelled_by = operator · cancel_reason 이 사건에 남음
> 스위치        이것 자체가 스위치. 되돌리기는 git revert 뒤 재기동 — 남은 상태 파일은 읽는 코드가 없어 아무 일도 안 함
> ```

---

> ## 🔴 [09-26 밤 3] **쓰기의 경로(channel) — 자동 확정이 옵트인을 지나고 · 소급의 쓰기는 체인을 안 깨움 — 마이그레이션 «없음» · 재기동 넷 다(API · 워처 · 체인 · 스케줄러)**
>
> ```
> 무엇이 바뀌나   outbox 사건에 경로 칸 — chain · api · file · retroactive. 층 이름(source_name)은 그대로
>               chain        체인이 쓴 것(자동 확정 포함) — 옵트인한 규칙만 깨움 · 깊이 상한이 셈
>               api · file   사람 · 다른 클라이언트 · 파일 적재 — 오늘처럼 모든 규칙을 깨움
>               retroactive  소급 탭 · CLI 의 모든 소급 실행이 쓴 것 — 옵트인이어도 «아무 규칙도» 안 깨움. 하류는 하류를 따로 소급
>               그리드 클릭 리플레이만 연쇄(cascade) — 옵트인 규칙만 깨움. 클라는 d3659ec09 부터 cascade: true 를 보냄(빌드 포함 — 브라우저 새로고침 뒤)
> 재기동 뒤      server\config\ingestion_settings.json 의 "enrichment_auto_confirm_enabled" 를 true 로 되돌려도 됨 — 자동 확정 쓰기가 이제 옵트인을 지남
> 확인          chain 박동 note 에 "N event(s) read by source name (no channel)" — 착지 전에 쌓인 체인 사건을 옛 방식(source_name)으로 읽은 수
>               대기열이 비면 더 안 늘어남. 늘어나면 경로를 안 세우는 체인 쓰기가 남아 있다는 뜻 — 보고
> 소급 폼        모든 연산에 "Downstream chain rules are not triggered by a retroactive run - run them too if they read what this changed"
>               수집기 날짜별 소급만 "The files it collects are ingested as usual, and the chain runs on them"
> 스위치        없음. 되돌리기는 git revert 뒤 네 프로세스 재기동(경로 칸이 없는 사건은 옛 방식으로 읽히므로 섞여도 안전)
> ```

---

> ## 🔴 [09-26 밤 3] **같은 값의 파일 층 — 쓰기에서 안 쌓고, 쌓인 것은 소급 한 번 — 마이그레이션 «없음» · 재기동 워처 · 체인 워커 · API**
>
> ```
> 보이는 것   헤비 레인 청크 줄 · 파일 줄의 INSIDE THE WRITE — cell sources <초> / N rows · folded layers <초> / N rows
>            값이 그대로인 행을 다시 가져온 파일이면 cell sources 0 rows · folded layers 0 rows = 층이 안 쌓임
>            값이 바뀐 파일이면 cell sources 는 바뀐 칸 수 · folded layers 는 그 값을 말했던 옛 파일 층 수
> 쌓인 것     드라이런: 어드민 Retroactive -> "Fold file layers that repeat a newer one" -> table -> Count
>            문장 "layers N -> M, the deepest cell A -> B" — N-M 이 지울 수
>            (이 박스 1,000 행 x 5 칸 x 9 겹 픽스처: 46,000 -> 6,000 · 9 -> 1 · 1.2 s — 운영 규모는 안 쟀음)
>            실행: 같은 화면 Run  또는  python -c "from admin import retroactive; retroactive.run_here('fold_file_layers', {'table': '<표>'})"
>            끝나면: python server/scripts/tune_layer_tables.py --table cell_sources --vacuum
> 뜻         되돌릴 수 없음 — 사라지는 것은 「같은 값을 말한 옛 파일 이름」 기록뿐. 칸 값 · 이력 · 이기는 층은 그대로
> 되돌리기    코드: git log --oneline -1 --grep "file layer that repeats" 의 커밋을 git revert 뒤 워처 · 체인 워커 · API 재기동. 지운 층은 안 돌아옴
> ```

---

> ## 🔴 [09-26 밤 2] **지금 운영 — 자동 확정이 옵트인을 건너뛰어 번지는 것을 멈추는 스위치 (코드 착지 전 · 재기동 «없음»)**
>
> ```
> 끄기        server\config\ingestion_settings.json 에 "enrichment_auto_confirm_enabled": false
>             파일을 매 작업마다 다시 읽음 — 재기동 없이 다음 묶음부터 자동 확정이 멈춤
> 뜻          판정 규칙이 값을 «자동으로» 채우는 쓰기만 멈춤. 판정 목록(대기열)은 그대로 쌓이고 사람이 확정하는 길은 그대로
> 확인        어드민 설정 해석 화면(/admin/config/resolve 가 답하는 것)에 enrichment_auto_confirm_enabled 가 false 로 나오는지
>             ⚠️ 꺼져 있을 때 체인 로그에 따로 찍히는 줄은 없음
> 다시 켜기    ⓪(자동 확정 쓰기가 체인 경로로 읽히게 하는 착지) 뒤에 true 로 — 그 착지의 RUN.md 절이 알림
> ```

---

> ## 🔴 [09-26 밤 1] **체인 멈춤 증거 — 연결 이름 · 멈춤 줄 · 이전 체인 워커가 남긴 쿼리 끊기 — 마이그레이션 «없음» · 재기동 넷 다(API · 워처 · 체인 · 스케줄러 — 연결 이름은 프로세스를 새로 띄워야 붙음)**
>
> ```
> 연결 이름    pg_stat_activity 의 application_name — assy_server · assy_watcher · assy_chain · assy_scheduler · assy_retroactive · 스크립트는 assy_<스크립트>
>             체인이 멈춤을 물을 때 여는 짧은 연결은 assy_chain_probe
> 찾기        Select-String -Path server\chain_worker.log -Pattern ": stalled \d+ s in "        <- 멈춘 묶음마다 한 번
>             Select-String -Path server\chain_worker.log -Pattern "left by a chain worker"       <- 기동 때 끊은 남은 쿼리
>             conda run --no-capture-output -n assy_manager python server/scripts/diagnose_db_health.py   <- §3 이 같은 문장
> 멈춤 줄     [Chain] tx <id> · <행> row(s) of <표>: stalled <초> s in <단계> (rule <규칙> · db pid <pid>) - <그 pid 가 하고 있는 것>
>             어드민 health 의 chain: 단계가 300 s 넘게 안 움직이면 stalled + 같은 문장. 움직이는 긴 묶음은 ok (예전엔 60 s 넘으면 wedged)
> 문장의 뜻과 할 일
>   waiting Lock:… on pid N (assy_watcher, active …)                   워처 청크가 같은 행을 쓰는 중 — 기다림(청크가 커밋하면 풀림)
>   waiting Lock:… on pid N (assy_<무엇>, idle in transaction <긴 시간>)  그 프로세스가 트랜잭션을 연 채 멈춤 — 그 프로세스 재기동
>   waiting Lock:… on pid N (assy_chain, …)                            체인 자기 프로세스의 리플레이 · 소급이 같은 행을 씀 — 청크 커밋마다 풀림. 안 풀리면 그 소급을 멈춤
>   waiting Lock:… on pid N (assy_ 로 시작하지 않는 이름)                 사람 · 외부 도구의 연결
>   its own query active <초> (no lock…): SELECT …                      그 쿼리 자체가 느림 — 오늘 운영의 조인 답 SELECT 가 이 모양. 급하면 그 규칙 enabled:false + 리로드, 나중에 리플레이
>   idle in transaction <초> - the time is not in the database          DB 가 아니라 파이썬(맵퍼 계산)이 오래 걸림
>   not probed (…)                                                      묻기가 실패 — diagnose_db_health 로 직접
> 남은 쿼리    체인 워커가 기동할 때 «이미 없는» 이전 체인 워커의 연결(이름 assy_chain · 이 프로세스보다 먼저 열림)을 끊고 하나마다 한 줄
>             assy_retroactive · 스크립트 · 다른 프로세스 이름은 안 건드림. 다른 체인 루프가 살아 있으면 아무것도 안 끊음
>             ⚠️ 이 착지 «뒤 첫 재기동»에는 못 끊음 — 이전 코드의 연결은 이름이 없음(diagnose 의 app=-). 두 번째 재기동부터 스스로 풂
> foreign_beat 박동 파일의 pid 가 감독자가 띄운 pid 가 아님 — 새 워커가 첫 박동 전에 막혀 있고(기동 인덱스 작업이 남은 쿼리 뒤에서 기다림) 파일엔 옛 pid 가 남은 것
> 워처 청크 줄  " | blocked by pid N: …" 가 " | waiting Lock:… on pid N (<이름>, <state> <시간>): …" 로 바뀜 — 같은 함수의 문장
> 스위치      없음(로그 · health 문장만). 멈춤 문턱은 워처와 같은 300 s
> 되돌리기    git revert 뒤 네 프로세스 재기동
> ```

---

> ## 🔴 [09-26 저녁 2] **표기 값 규칙 1 단계 — join · pad_last_number · replace · time 의 선언 점검과 미리 보기 — 마이그레이션 «없음» · 재기동 API (notation_rules.json 에 선언이 있을 때)**
>
> ```
> 총괄 한 번   python server/scripts/install_product_tables.py --apply     <- 라이브 table_config 에 notation_alias 표(비어 있음)
>            인자 없이 돌린 dry run 이 "1 to add" 면 아직 안 한 것 · "0 to add" 면 된 것
> 확인        GET /admin/config/resolve?domain=notation  -> 선언마다 effective / rejected
>            rejected 에 "Refused: the join character is the one this column's key is joined with" 이면 그 칸의 join 을 다른 글자로
>            GET /admin/config/notation/preview?table=<표>&column=<칸>  -> write 칸은 "write": true · time 칸은 time_left_as_is
> 뜻         저장은 2 단계([09-26 밤 5] 항목)부터 — 이 단계의 몫은 선언 점검과 미리 보기
>            write 칸은 «적은» 규칙만 돎(기본값 separator · case 안 옴) — {"join": "-", "pad_last_number": 2} 면 wafer.1 -> wafer-01
>            미리 보기 folds_again 이 0 이 아니면 한 번 더 접을 때 또 바뀌는 값 — 소급 전에 규칙이나 별칭 행을 고침
> 되돌리기    git log --oneline --grep "written spelling" --grep "written column runs only" 의 커밋을 새것부터 git revert 뒤 API 재기동
>            쓰는 것 없음(notation_alias 표는 남음 — 비어 있음)
> ```

---

> ## 🔴 [09-26 저녁 1] **헤비 레인 쓰기 로그 — 청크 줄의 곁표 넷 · 파일마다 한 줄 — 마이그레이션 «없음» · 재기동 감시자(워처) · 체인 워커**
>
> ```
> 찾기       Select-String -Path server\watcher.log -Pattern "\[Ingest\] .* FILE "            <- 파일이 끝날 때 한 줄 (두 레인 같은 줄)
>            Select-String -Path server\watcher.log -Pattern "\[Ingest\] .* chunk \d+:"       <- 청크마다 한 줄
>            체인 쪽 같은 쓰기 단계는 chain_worker.log 의 "[Chain] group" 줄 INSIDE THE WRITE 에 같은 모양으로 — 그 줄은 뷰를 지은 묶음에만 찍힘(보통 묶음엔 안 나옴)
> 파일 줄     <표> FILE <파일>: 행 수 · 걸린 초 · 분당 행 · <레인> · waited <초> (<무엇을 기다렸나>)
>            · sent: new · changed · unchanged · cells changed · side-table rows · STAGES(parse · apply · commit) · INSIDE THE WRITE · DB wait samples (Lock)
> 비교하는 법  같은 표의 느린 파일 줄과 안 느린 파일 줄을 위아래로 놓고 칸마다 견줌
>            waited 가 크면 쓰기가 아니라 «차례»가 느린 것 — heavy 는 (queue + table lock) · normal 은 (table lock) · 레인 없이 들어온 파일은 not measured
>            changed · cells changed 가 크면 고칠 게 많은 파일 — audit logs · cell sources 행 수가 같이 큼
>            같은 행 수인데 한 쓰기의 초만 크면 그 곁표 쪽(색인 · 부풀음). Lock 표본이 있으면 다른 쓰기에 막힌 것
> 청크 줄     side tables 한 덩어리가 넷 — audit logs · cell sources · cell overwrites · overwrite deletes, 각각 «초 / 행 수». row build 에 «바뀐 셀 수»
> 스위치      이 두 줄을 끄는 칸은 없음. ingestion_settings 의 chunk_wait_sampling=false 는 DB 대기 표본(청크 줄 waits · 파일 줄 DB wait samples)만 끔
> 되돌리기    git revert 뒤 워처 · 체인 워커 재기동. 쓰는 것 없음(로그만 — 새 질의 0)
> ```

---

> ## 🔴 [09-26 오후 7] **수집기 하루 단위 소급 — 소급 연산 «Backfill a collector day by day» — 마이그레이션 «없음» · 재기동 API · 스케줄러**
>
> ```
> 쓰는 법    Admin -> 소급 -> "Backfill a collector day by day" · collector = <표>/<스크립트.py> (# window: 를 적은 수집기) · start = YYYY-MM-DD (KST)
>            CLI: python -c "from admin import retroactive; retroactive.run_here('collector_backfill', {'collector': '<표>/<스크립트.py>', 'start': 'YYYY-MM-DD'})"
> 도는 모습   start(날짜면 그날 00:00 KST)부터 24h 씩, 마지막은 지금에서 자름 — 하루 = 스크립트 한 번(그 날 구간이 마커에 채워짐)
>            그 날 파일이 적재 대기열을 지날 때까지(파일 체크포인트가 DONE) 기다린 뒤 다음 날. 진행 N/M 일 · 날 사이에서 취소
> 멈춤       그 날 파일이 FAILED 면 run 이 실패로 끝나고 사유에 그 날짜 — "…failed to ingest (…) - fix it, then start again from <날짜>"
>            고친 뒤 start 를 그 날짜로 다시 걸면 거기서부터 끝까지
> ⚠️ 기다림   시간 상한 없음 — 워처가 멈췄거나 체크포인트 기록이 실패한 파일이면 그 날에서 계속 기다림(진행이 안 움직임). 취소로 끝냄
> 확인       소급 목록에서 N/M 일 · 끝나면 done · days_done
> 되돌리기    git revert 뒤 API · 스케줄러 재기동. 이미 적재된 날의 행은 남음(일반 적재와 같음)
> ```

---

> ## 🔴 [09-26 오후 6] **수집기 선언 점검 — Declarations 에 collector 영역 · 짝이 안 맞는 스크립트는 로드 거절 — 마이그레이션 «없음» · 재기동 스케줄러 · API**
>
> ```
> 거절       # window: 는 있는데 {{WINDOW_START}} · {{WINDOW_END}} 가 없음 / 마커는 있는데 # window: 가 없음 / window 가 <n>d · <n>h 가 아님
>            {{LIST:표.칸}} 의 칸이 table_config 에 없음 · 날짜 칸임
>            -> 그 수집기는 스케줄러에 안 올라감(Auto Update 탭 목록에서 빠짐)
> 볼 곳      스케줄러 로그  "[Collector] '<표>/<스크립트>' is not loaded - <문장>"
>            Declarations -> "Auto update collectors (script markers)" 영역의 rejected — 같은 문장
> 이 박스    착지 전 잼: 수집기 10 개 전부 fine · rejected 0 (마커를 쓰는 스크립트가 없음)
> 줄이 나오면  스크립트 머리 · 마커를 짝으로 맞추거나, 목록 칸을 table_config 에 선언(글자 · 숫자 칸)
> 되돌리기    git revert 뒤 스케줄러 · API 재기동. 쓰는 것 없음(판정만)
> ```

---

> ## 🔴 [09-26 오후 5] **수집기 스크립트의 목록 마커 {{LIST:표.칸}} — 마이그레이션 «없음» · 재기동 스케줄러(run_auto_update)**
>
> ```
> 쓰는 법    스크립트 본문에  AND b.part IN ({{LIST:part_filter.part_id}})
>            실행마다 그 표 그 칸의 그리드 값(빈칸 뺌 · 한 번씩 · 값 순서)이 'a','b' 로 들어감. 값 속 ' 는 '' 로
> 거절       목록이 비었거나 · 1,000 값을 넘거나 · 못 읽었거나 · 표·칸이 선언 안 됐으면 그 실행은 «시작 안 함» (FAIL)
>            Auto Update 탭 서랍에 그 한 문장(트레이스백 아님) — 예 "{{LIST:…}} has no value in '…'. The run did not start."
> 재기동 까닭  스케줄러가 시작할 때 동적 모델을 만들어야 목록을 읽을 수 있음(이번에 넣음). 재기동 전에는 목록 마커 스크립트가 거절됨
> 확인       목록 마커를 적은 스크립트를 즉시 실행 -> raws 의 새 CSV(또는 스크립트가 보낸 쿼리)에 값 목록이 들어 있음
> 되돌리기    git revert 뒤 스케줄러 재기동. 쓰는 것 없음(그리드를 읽기만)
> ```

---

> ## 🔴 [09-26 오후 4] **수집기 스크립트의 시간 구간 마커 — 마이그레이션 «없음» · 재기동 스케줄러(run_auto_update)**
>
> ```
> 쓰는 법    스크립트 머리(위 20 줄)에  # window: 1d   (또는 <n>h)   · 선택  # window_format: %Y-%m-%d %H:%M:%S (없으면 이 모양)
>            본문 어디든  {{WINDOW_START}} · {{WINDOW_END}}
> 도는 모습   크론 · 즉시 실행 모두 — 실행 시각(KST)에서 window 만큼 앞 ~ 실행 시각을 채워 돌림. 원본 파일은 안 바뀜
>            out 을 안 쓰는 스크립트는 채운 사본(<스크립트>.<pid>.filled, 같은 폴더)을 자식 프로세스로 돌리고 끝나면 지움 — 수집기로 안 잡힘
> 그대로     # window: 가 없는 스크립트는 전과 같음(마커를 안 채움) — 이 박스 수집기 10 개가 전부 그렇다
> 거절       # window: 가 <n>d · <n>h 가 아니면 그 실행이 FAIL, 사유 "'# window: …' is not a length - write it as <n>d or <n>h"
> 확인       머리를 적은 스크립트를 즉시 실행 -> raws 의 새 CSV 에 마커 대신 날짜 · 시각이 들어 있음
> 되돌리기    git revert 뒤 스케줄러 재기동. 쓰는 것 없음(사본은 실행마다 지움)
> ```

---

> ## 🔴 [09-26 오후 3] **파생 표를 대상으로 한 조인은 그 표의 키를 조인 키 안에서 — 마이그레이션 «없음» · 재기동 API · 체인 워커**
>
> ```
> 규칙       조인 대상이 «켜진 파생행 규칙»의 파생 표이면, 그 표의 composite_key_source(없으면 business_key) ⊆ 조인의 on[].left
>            아니면 로드 거절 · 저장 400(code join_key_contract) · 선언 점검(Declarations) 거절 줄 — 세 곳이 한 문장
>            문장은 파생행 키 계약 그대로, 키 이름만 조인 것: "derived table composite_key_source must be a subset of the join's on[].left columns (violation: [...])"
> 그대로     파생 표가 아닌 표로 가는 조인(찾아보기 조인)은 키가 넓어도 섬 · 꺼진 파생행 규칙의 표는 파생 표로 안 셈
> 확인       재기동 뒤 체인 워커 로그에 "[ChainRules] <이름> refused (1): join_key_contract" 줄이 없으면 이 박스는 영향 0
>            (착지 전 잼: 켜진 조인 inventory_confirmed · test 둘 다 dt_log 대상, 파생 표는 dt_inventory 하나 -> 새로 거절 0)
> 줄이 나오면  그 조인은 안 돎 — 파생 표의 키 칸을 조인의 on 에 더하거나, 파생 표의 composite_key_source 를 조인 키 안으로 줄임
> 되돌리기    git revert 뒤 API · 체인 워커 재기동. 쓰는 것 없음(판정만)
> ```

---

> ## 🔴 [09-26 오후 2] **파생행 집계에 unique_concat — 마이그레이션 «없음» · 재기동 체인 워커 · API**
>
> ```
> 선언       파생행 규칙의 aggregations 에 한 줄  "wafer_ids": {"fn": "unique_concat", "column": "wafer_id", "separator": ", "}
>            파생 표(table_config)에 그 이름의 text 칸이 있어야 함(없으면 로드 거절 — 전과 같음)
> 값         그 판단키의 커밋된 소스 행 전체에서 — 빈 값 빼고 · 중복 없이 · 값 순서 · separator 로 이음. 값이 하나도 없으면 비움
> 거절       count · min · max 에 separator 를 적으면 규칙이 이름과 함께 거절됨 · separator 가 글자가 아니면 거절
> ⚠️ 채워지는 때  그 키에 새 소스 행이 올 때(체인). enrichment backfill 은 «없는 파생행만» 만들고 기존 행은 안 건드림 —
>            기존 파생행에 새 집계를 채우는 문은 아직 안 정함(총괄께 여쭘)
> 되돌리기    git revert 뒤 체인 워커 · API 재기동. 선언에 unique_concat 을 적었으면 그 줄을 먼저 지움(되돌린 코드는 모르는 fn 으로 거절)
> ```

---

> ## 🔴 [09-26 오후 1] **같은 내용의 실패 파일이 워처 기동마다 다시 읽히지 않음 — 마이그레이션 «없음» · 재기동 감시자(워처)**
>
> ```
> 무엇       raws 에 남은 실패 파일(아카이브 끔)이 같은 내용의 사본을 가지면 기동마다 하나씩 다시 파싱 · FAILED 기록 +1 이었음
>            이제 «그 내용이 FAILED» + «이 경로에서 실패한 뒤로 파일이 안 바뀜»이면 조용히 건너뜀(기록 없음 — tier-1 과 같이)
> 그대로     같은 내용이 새 이름으로 오면 읽음 · 실패 뒤 고쳐 저장하면(mtime 이 뒤) 읽음 · Retry 는 늘 읽음
> 확인       재기동 뒤 워처 로그 기동 스윕 줄의 dispatched 수 — 같은 내용 실패 파일만 남아 있으면 0
> 되돌리기   git revert 뒤 워처 재기동. 쓰는 것 없음(읽기만: 체크포인트 한 줄 · 파일 기록 FAILED 줄)
> ```

---

> ## 🔴 [09-26 아침 3] **PG 시험은 자기 DB assy_test 에서 — 분리 환경(assy_qa)을 켜든 말든 같은 답 · 운영 무관 · 재기동 «없음»**
>
> ```
> 무엇       시험의 PostgreSQL 되돌이가 assy_qa 가 아니라 같은 서버의 assy_test (빈 DB + pg_trgm). 이름은 tests/support/isolated_pg.PG_TEST_DATABASE 한 자리
> 처음 한 번  시험이 postgres 관리 DB 에서 CREATE DATABASE assy_test · pg_trgm 설치. 사람이 할 일 없음
> 그대로     분리 환경(devenv)은 assy_qa. ASSY_PG_TEST_DATABASE_URL 로 다른 DB 를 주면 그것이 먼저
> 되돌리기   git revert. assy_test 는 남음 — 지울 때 DROP DATABASE assy_test (시험 말고 쓰는 것 없음)
> ```

---

> ## 🔴 [09-26 아침 2] **쓴 값이 하나도 없는 파일은 FAILED + 한 문장 · 일부만 버린 파일은 기록에 버린 칸 문장 — 파서 길 둘이 같은 답 · 마이그레이션 «없음» · 재기동 감시자(워처)**
>
> ```
> 전부 버림   선언된 칸이 하나도 없는 파일 -> FAILED · 파일 기록(error_message) 한 줄:
>            No column of this file is declared on '<표>', so nothing was written - dropped <칸들>. Declare the columns on the table, or send the file to the table that declares them.
>            표준 파서(헤더에서) · 커스텀 파서(쓰기 고리에서) 같은 문장. 전: 커스텀은 SUCCESS · 기록 없음, 표준은 FAILED · 트레이스백
> 일부 버림   SUCCESS 그대로 + 기록에 Next: declare the undeclared columns in table_config.json. Not written: undeclared_column <칸>=<값 수> over M row(s). (10-01 d4a949a8c ③)
>            전: 표준 파서 길은 기록 없음(표준 파서가 스스로 빼고 WARNING 만)
> 로그       버린 칸은 워처의 한 자리가 적음 — 칸마다 처음 한 번 WARNING · 파일마다 INFO(기록과 같은 문장). 표준 파서의 "ignoring unknown column(s)" WARNING 은 없어짐
> 아카이브 끔  FAILED 파일은 raws 에 남음. 내용이 같은 실패 파일이 둘 이상이면 워처 기동마다 하나 빼고 다시 읽혀 FAILED 기록이 늘어남(보고만 · 958d57347)
> 되돌리기    git revert 뒤 워처 재기동. 쓰는 것 없음(파일 기록 · 체크포인트의 상태 낱말만 달라짐)
> ```

---

> ## 🔴 [09-26 아침 1] **스케줄러 재기동을 넘어 수집기의 마지막 실행이 남음 · 끊긴 실행은 FAIL + 사유 — 마이그레이션 «없음» · 재기동 스케줄러**
>
> ```
> 재기동 뒤   Auto Update 탭의 last_run · last_status · last_error 가 재기동 전 그대로 (전: PENDING · last_run 없음)
> 끊긴 실행   수집 도중 스케줄러가 죽고 되살아나면 그 수집기는 FAIL
>            last_error = The scheduler running this collector stopped before it finished - run it again.
>            last_run = 끊긴 실행의 시작 시각 · 대기열(지금 도는 것)에는 안 나옴
> 로그       auto_update.log — [Collector] '<표>/<스크립트>' was RUNNING under scheduler/<host>/<pid>, which is gone - recorded as FAIL
> 되살림 없이 스케줄러가 죽은 채면 지금처럼 탭 · 대기열 state 가 orphaned (그걸 적는 프로세스가 없음)
> 도장 없는 옛 RUNNING   이 코드 전의 줄 — unknown 그대로, 다음 실행이 덮음
> 되돌리기    git revert. 쓰는 것은 상태 파일 server/config/scheduler_status.json 뿐 (지금도 스케줄러가 쓰는 파일)
> ```

---

> ## 🔴 [09-26 새벽 2] **수집기·소급의 «누가 돌리나» — 대기열 항목에 state · Auto Update 탭 낱말 · 재적재 도중 끝난 수집이 RUNNING 으로 안 남음 — 마이그레이션 «없음» · 재기동 API · 스케줄러 · 체인 워커**
>
> ```
> 대기열    /admin/chain/queue 의 now_running 항목마다 "state": running · orphaned · unknown
>           orphaned = 그 일을 시작한 프로세스의 심박이 없거나 다른 pid 가 뜀 — 시작한 프로세스가 죽음
>           unknown  = 도장이 없는 옛 줄 (이 코드 전에 시작된 수집 · 소급)
> 탭        Auto Update 의 상태 낱말 — RUNNING 인데 그 스케줄러가 없으면 orphaned (unknown 은 옛 줄)
> 수집 도중  설정 재적재(SYSTEM_RELOAD)가 와도 끝나면 SUCCESS · FAIL — 전: 끝나도 RUNNING 으로 남음
> 확인      상태 파일 server/config/scheduler_status.json 의 줄마다 "runner": scheduler/<host>/<pid>
>           없으면 스케줄러가 옛 코드
> 재기동     스케줄러 재기동 뒤의 수집기 상태는 [09-26 아침 1]
> 되돌리기  git revert. 쓰는 것은 상태 파일의 runner 칸뿐
> ```

---

> ## 🔴 [09-26 새벽 1] **표·원장 소급도 없는 이름은 기록 «전»에 거절 · 거절된 소스의 rescope 는 이름 있는 거절 — 마이그레이션 «없음» · 재기동 API · 스케줄러 · 체인 워커**
>
> ```
> 확인      어드민 소급에서 resolve · withdraw · ledger_backfill · ledger_rescope 에 없는 표·칸·소스 이름
> 답의 뜻   400 한 문장(영어), 실행 목록에 줄 없음                                 새 코드
>           실행 목록에 줄이 생기고 queued -> failed                                API 가 옛 코드
>           건수 400 이 「이 연산의 건수를 계산할 수 없습니다: …」 로 시작              API 가 옛 코드
> 거절된 소스  rescope -> 「source 'X' was refused by the loader, so it has no plan to run: …」 (전: 자식이 AttributeError)
>           ledger_backfill 의 건수는 그대로 not_applicable (있는 이름이라 문에서 안 막음)
> 빈 표 설정  CLI · 데몬이 「table_config.json is empty or missing」 을 이름 판정보다 먼저 말함
> 되돌리기   git revert. 쓰는 것 없음
> ```

---

> ## 🔴 [09-25 밤 10] **대형 레인 워커 N — 한 표는 한 워커가 차례대로, 다른 표끼리 동시 · 칸 heavy_lane_workers(기본 1) · 마이그레이션 «없음» · 재기동 감시자**
>
> ```
> 칸        server/config/ingestion_settings.json 의 "heavy_lane_workers" — 1 이상 정수, 없으면 1 (= 전과 같음)
>           감시자 재기동 때 읽음. 값은 운영자가 적음 (박스 설정에 아무도 안 채움)
> 확인      다른 표의 큰 파일 둘을 거의 같이 올림 -> 감시자 로그의 「📥 New file detected: <파일>」 (처리 시작) 두 줄의 시각
> 답의 뜻   워커 1: 둘째 표는 첫째가 끝난 뒤 시작                          그대로 (칸이 없거나 1)
>           워커 N>1: 둘째 표가 첫째가 도는 동안 시작 · 같은 표 둘째 파일은 첫째 뒤   새 코드 + 칸 읽음
>           N>1 인데 둘째 표가 기다림                                    감시자가 옛 코드이거나 재기동 전
> 잘못 적음  「Ignoring invalid 'heavy_lane_workers' …」 경고 한 줄 뒤 1 로 돔
> 주의      쓰기가 적재 시간의 거의 전부 — 워커를 늘리면 DB 부하가 같이 늘어남
> 되돌리기  칸을 1 로(재기동) — 또는 git revert
> ```

---

> ## 🔴 [09-25 밤 9] **업로드한 큰 파일이 대형 레인을 탑니다 — 업로드가 raws/ 옆에 다 쓴 뒤 옮김 · 마이그레이션 «없음» · 재기동 API**
>
> ```
> 확인      문턱(ingestion_settings 의 heavy_file_mb, 기본 10 MB) 이상인 파일을 화면에서 업로드 -> 감시자 로그
> 답의 뜻   「🐘 Routed to heavy lane queue (… B): user(…)_…」            새 코드
>           그 줄 없이 「New file detected」 뒤 바로 처리                    API 가 옛 코드 (재기동 안 먹음)
> 남는 것   표 작업공간 폴더(raws/ 의 부모)에 「.upload.<hex>」 파일이 남아 있으면 — 쓰다가 프로세스가 죽은 것. 지워도 됨(감시자는 안 봄)
> 그대로    탐색기·네트워크 복사로 raws/ 에 직접 넣는 큰 파일은 지금처럼 크기를 생긴 순간에 재서 인라인으로 갈 수 있음 (내용은 맞게 들어감)
> 되돌리기  git revert. 쓰는 것 없음 — 파일이 raws/ 에 «나타나는 방식»만 바뀜
> ```

---

> ## 🔴 [09-25 밤 8] **로더가 거절한 원장 소스도 셈 바퀴가 잽니다 — 셈이 거절 문장으로 · 마이그레이션 «없음» · 재기동 체인 워커**
>
> ```
> 확인      /api/ledger/declaration 의 소스별 셈 — 로더가 거절한 소스
> 답의 뜻   「Refused by the loader」 + 로더의 지금 문장              새 코드, 그 소스 차례가 지남
>           옛 남은 행 수 · 「뷰에 row_id 를 선언하라」 처방           체인 워커가 옛 코드, 또는 아직 차례 전 (바퀴 = 소스 수 × 쉼)
> 바퀴 줄    [LedgerCensus] lap: N source(s) — N 에 거절 소스가 들어감. 「retired」 뒤에는 운영자가 은퇴시킨 것만
>           거절 소스마다 매 바퀴 「[LedgerCensus] X failed」 — 지문을 부르는 옛 갈래 (이 수리가 안 들어감)
> 행 없음    거절 소스인데 등록 행이 없으면 계속 없음 — 돈 적이 없다는 뜻
> 되돌리기   git revert. 쓰는 것은 셈 칸뿐 — 다음 바퀴가 다시 씀
> ```

---

> ## 🔴 [09-25 밤 7] **없는 규칙 이름은 기록 «전»에 거절 — 어드민 · 건수 · CLI 같은 문장 · 마이그레이션 «없음» · 재기동 API · 스케줄러 · 체인 워커**
>
> ```
> 확인      어드민 소급에서 없는 규칙 이름으로 실행
> 답의 뜻   400 「chain rule 'X' not found or disabled; available: …」, 실행 목록에 줄 없음   새 코드
>           실행 목록에 줄이 생기고 queued -> failed                                        API 가 옛 코드
>           건수 400 이 「이 연산의 건수를 계산할 수 없습니다: …」 로 시작                    API 가 옛 코드
> 관문 문장  「op=X is progressing, last progress Ns ago」 · 진행 보고가 없으면 「no progress reported yet」
>           「progressing for Ns」 가 보이면 그 프로세스가 옛 코드
> CLI 실행  실행 목록의 요청자 칸 = OS 계정 이름 (전: 빈칸)
> 매퍼 로그  「… decision key(s) built for 'T'」 (전: upserted into — 건수만 셀 때도 그렇게 적었음)
> 되돌리기  git revert. 쓰는 것 없음
> ```

---

> ## 🔴 [09-25 밤 6] **숫자 칸에 글자가 오면 «한 문장» — 그리드 · 파일 · 체인 같은 말 · 마이그레이션 «없음» · 재기동 API · 감시자 · 체인 워커**
>
> ```
> 문장     Row N: column 'C' does not take 'V' - a number is expected.
>          그리드  N = 보낸 묶음에서 몇 번째          파일  N = 파일의 몇 번째 데이터 행 (머리줄 빼고)
>          체인    [rules=그 규칙 target=그 표] 뒤에 같은 문장 — N 은 그 규칙이 쓴 묶음에서 몇 번째
> 확인     파일 탭의 실패 사유 · 그리드 붙여넣기 거절 토스트 · 체인 실패 목록의 사유
> 답의 뜻   그 문장                         새 코드
>          한국어 「올바른 숫자 형식이 아닙니다」   그 프로세스가 옛 코드 (재기동 안 먹음)
>          파일 사유가 여러 줄 Traceback        이름 붙은 거절이 아닌 다른 실패 — 지금처럼 전체를 남김
>          체인 사유 머리가 (unknown)           규칙 이름을 모르는 실패 (쓰기 전 단계) — 쓰기에서 난 거절은 이제 규칙을 적음
> 되돌리기  git revert. 쓰는 것 없음 — 거절 문장과 사유 머리만 바뀜
> ```

---

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
>          옛 running(체인 규칙만)은 은퇴 — 화면이 now_running 을 읽음 (총괄 c1dc16fdd)
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
