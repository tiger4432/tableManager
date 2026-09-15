# 지금 돌리면 되는 것

> 이 파일은 **푸시할 때마다 갱신**됩니다. 지금 main 에 있는 것 기준입니다.
> 전부 `server/` 에서 돌립니다. 운영은 그 환경의 `python`, 박스는 `C:\Users\kk980\anaconda3\envs\assy_manager\python.exe`.

---

## 1. 지금 제일 급한 것 — 조인이 왜 안 서는지 «한 줄로» 가른다

```bash
python scripts/check_one_row_one_fact.py --db
```

읽기만 합니다. 답이 셋 중 하나이고 **수리가 전부 다릅니다**:

| 답 | 뜻 | 고칠 곳 |
|---|---|---|
| 키가 «신원보다 좁은» 조인 | 유일 인덱스가 «영원히» 못 섭니다 | 🔴 **선언** — 조인 키를 신원까지 넓히기 |
| 같은 키 행이 있음 (진짜 중복) | 사본이거나 다른 사실이거나 | 아래 2번으로 가름 |
| 키가 «비어 있는» 행 | 중복이 아니라 **부재** | 키를 채우거나 null 정책 선언 |

## 2. 접어도 되는지 가른다 (1번이 「진짜 중복」일 때만)

```bash
python -c "import sys;sys.path.insert(0,'.');sys.stdout.reconfigure(encoding='utf-8');from database.database import SessionLocal;from virtual_join import unique_key;db=SessionLocal();print(unique_key.describe_fold_plan(unique_key.fold_plan(db,'<표>',['<조인 키>'])));db.close()"
```

* 「접어도 되는 키 N」 → 진짜 사본. 접으면 됩니다
* 「접으면 데이터가 사라지는 키 N」 → **접지 마십시오.** 신원이 그 컬럼이 아니라는 뜻입니다

## 3. 급할 때 끄는 스위치 (환경변수, 재기동 필요)

```bash
ASSY_CHAIN_WORKER=0        # 체인 루프 자체를 안 띄움 (API·읽기는 그대로)
ASSY_CHAIN_SYNTHESIZE=0    # enrichment/가상조인에서 «파생되는» 규칙을 안 만듦
ASSY_VJOIN_AUTO_INDEX=0    # 제품이 유일 인덱스를 자동으로 세우지 않음 — 🔴 1497ea3e 부터 OFF 는 «DB 를 한 번도 안 만짐»(그 전엔 점검 SQL 이 여전히 돌아 안 멎었음)
```

## 4. 통합 뒤 모양 미리보기 (읽기 전용, 안 써도 됨)

```bash
python scripts/preview_unified_declarations.py --out ../unified_preview.json
```

왕복이 하나라도 깨지면 **아무것도 안 씁니다.**

---

## 부팅 로그에서 볼 것 (재기동 뒤)

```
[ChainRules] set(N): 이름[출처,방식] 표=값 ... (꺼진 건 OFF)   <- 무엇이 도는가. synt = 제품이 만든 규칙
[ChainRules] refused(N): 이름(사유)                          <- 무엇이 «안» 도는가
[ChainRules] 지난 적재와 다름 - 사라짐 1: ...                  <- 선언을 바꾼 뒤 무엇이 달라졌나
[VirtualJoin:이름] 조인 키 (...) 가 ... 의 «신원»(...)보다 좁습니다   <- 1번과 같은 진단
```

## 5. 통합 선언에 «join» 적기 (S-237 착지 — 가상 조인은 그대로, 이건 «체인»)

`chain_rules.json` 의 `rules` 에 이 모양 하나를 적으면 체인 규칙 **둘**이 섭니다(왼쪽 트리거 + 오른쪽 트리거는 페이싱). 값은 대상 표의 «진짜 컬럼»에 «자기 층»으로 써지고, 원장이 그대로 봅니다.

```jsonc
{
  "name": "inventory_confirmed",
  "on":     { "table": "dt_inventory" },                       // columns 는 적지 마십시오 — 왼쪽 키에서 유도됩니다(판정 398)
  "derive": { "kind": "join",
              "join": { "right_table": "dt_job_attribution",
                        "on":   [ { "left": "dt_job", "right": "dt_job" } ],
                        "take": [ "dt_lot_confirmed", "dt_slot_confirmed" ] } },
  "into":   { "table": "dt_inventory" },
  "key":    { "columns": ["dt_job"], "unique": true }          // 오른쪽 유일성 — 제품이 인덱스를 세웁니다(S-235)
}
```
* fold 는 적지 않습니다 — 두 표의 표기 선언에서 «계산»됩니다(판정 397). `max_rewrite_rows` 도 없습니다 — 페이싱(판정 396).
* 재기동 뒤 부팅 줄에서 확인: `[ChainRules] set(N): inventory_confirmed[decl,join] …` 가 «둘» 보여야 합니다.
* 오른쪽 값이 null 이면 «null 로» 써집니다. 오른쪽 행이 없으면 안 씁니다.
* 오른쪽 행이 «둘 이상» 이면 그 왼쪽 행은 안 씁니다(둘 다 답이 아님) — 나머지 행은 그대로 써집니다. 로그 한 줄:
  `[join_into:이름] N left row(s) matched MORE THAN ONE right row and are skipped by name ...`
  이 줄이 보이면 «오른쪽 표의 데이터»에 같은 키가 둘인 것입니다 — 2번(접기)으로 가십시오. 선언을 고칠 일이 아닙니다.
* ⚠️ 첫 실행은 왼쪽 표 «전체» 행을 씁니다(박스 실측: dt_inventory 488,429 행). 운영에서는 페이싱 창을 정하고 켜십시오.
