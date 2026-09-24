# 지금 돌리면 되는 것

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
> ⚠️ 짝(on) 은 두 번 누릅니다 — on 을 펴고, 그 안의 「0」 줄을 한 번 더
> ```
>
> ### 확인 — 답이 «무엇을 뜻하나»
>
> ```
> ㉠ 개발자도구 Network 에서 admin-*.js 의 «이름»을 보십시오
>    admin-Betkez0l.js  새 번들이 떴습니다
>    다른 이름    옛 번들이 캐시에 남았거나 배포가 안 된 것입니다 — 화면은 안 바뀝니다
> ㉡ Chain 탭 → inventory_confirmed → on 의 「접힘 · 2」 → 「0」 줄
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
> 되돌리려면  git revert aac2e1bac 2cdb1e74f  하고 다시 배포
>            (되돌리면 목록이 다시 «안 펴집니다» — 값은 원문 JSON 에서만 보입니다)
> ```
