# v1 해결기가 여섯 라우트를 세우는 원인 — 전수 분석

> 소유자: 「너가 원인 분석하지 말고 응용 세션 시켜」 · 총괄 지시 15:2x
> 🔴 **읽기 전용.** 코드 0줄. 라이브 config 읽기만. 추측 없음 — 못 잰 것은 적었습니다.

---

# ① 「packs 를 아직 요구하는 곳」 — 이름을 댑니다

```
ledger_trace.load_resolver_config()
   -> _declared_inference_derivations()          ledger_trace.py  (얼음 A)
      -> ledger.config.load()                    ledger/config.py (얼음 A)
         live  server/config/ledger_config.json          «없음»
         -> sample 폴백  server/config/sample/ledger_config.json.sample
            -> ledger/source_profile.py  「pack '…' is not declared in packs」
```

**요구하는 자리는 `ledger/source_profile.py` 의 `unknown_pack` 판정이고,
샘플을 보게 만드는 자리는 `ledger/config.py` 의 «샘플 폴백»입니다.**
둘은 다른 파일입니다 — 하나만 고쳐도 안 섭니다.

📎 `load_resolver_config` 자신은 `ledger_resolver.json` 을 읽고 **없으면 그냥 넘어갑니다.**
거절은 그 함수가 아니라 그 함수가 «부르는» 번역기 설정 로더에서 납니다.

---

# ② 이게 «유일한» 원인입니까 — **아니오. 둘이고, 둘째가 더 큽니다**

직접 먹여 봤습니다.

```
ledger.config.load()        -> 샘플 폴백 -> 「pack … is not declared in packs」
ledger.config.load(v5 경로)  -> «다른 거절» ->
     「sources.dt_job.occurred_at_column is not declared」
```

**경로를 라이브 v5 로 돌려도 안 섭니다.** 형식이 다릅니다:

```
v1 이 찾는 것   sources.<이름>.occurred_at_column        «평평한 키»
v5 가 가진 것   sources.<이름>.read.occurred_at = {column, timezone}
```

그리고 이건 필드 하나가 아니라 **문법 전체**입니다:

```
v1 문법   소스 «종류»마다 정해진 컬럼 목록
          LINEAGE_REQUIRED_COLUMNS · OBSERVATION_REQUIRED_COLUMNS · TRANSFER_REQUIRED_COLUMNS
          + finding_kind · run.* · group.row_order_column · container.*
v5 문법   소스마다 relation · read · prepare · map · bind
          문장(bind.mappings)마다 주어·목적어·한정어를 «바인딩»
```

**원인은 「파일이 없다」가 아니라 「두 문법이 다르다」입니다.**

---

# ③ packs «말고» 또 있습니까 — **여섯입니다**

v5 최상위는 `entities · setup_version · sources · vocabulary` 넷뿐입니다.
v1 리더가 아직 이름을 대는 것:

```
섹션                v5 에      ledger/config.py   ledger/source_profile.py
packs               «없음»          0                   11      <- 실행으로 확인된 거절
claims              «없음»          2                    7
profiles            «없음»          6                    5      <- 거절문에 경로로 나옴
binding_origin      «없음»          0                    2      (2026-08-22 삭제)
approval_status     «없음»          0                    4      (같은 날 삭제)
suggestion_reason   «없음»          0                    2      (같은 날 삭제)
layer               «없음»          0                    0      ✅ 깨끗
```

⚠️ **숫자는 «등장 횟수»이고 주석·독스트링을 포함합니다** — 실행되는 자리 수가 아닙니다.
실행으로 «확인»된 것은 `packs` 하나(거절이 실제로 났음)와 `occurred_at_column` 하나입니다.
나머지 넷은 **「이름이 남아 있다」까지만 잰 것**입니다.

---

# ④ 고칠 것입니까, 은퇴시킬 것입니까 — **은퇴입니다**

소유자 지시(「v1 기반들은 다 은퇴시키는 방향으로」)에 ②가 근거를 댑니다.

```
「경로만 돌린다」   ✗ 안 됩니다 — ② 가 실측으로 보여 줍니다
「v5 를 읽게 한다」  = v1 리더를 «다른 문법으로 다시 쓰는 것».  수리가 아니라 재작성입니다
                   그리고 그 모듈은 ③(은퇴) 대상입니다 — 죽을 것을 다시 쓰는 셈입니다
```

**그리고 없앨 때 잃는 것은 이미 쟀습니다** (`ONTOLOGY_API_GUIDE.md` §8-bis):

```
바로 은퇴      trace · explore · explore_entity   subgraph 가 «사실»을 덮습니다 (실측)
               structure                          급하지 않습니다
v5 에 작게 다시  coverage                          번역기 커서·소스 현황
               journey                           웨이퍼 두 장 «서열» 대조
```

---

# 안 잰 것

```
selection/resolve 가 이 원인에 걸리는지    입력 형식을 못 만들어 «안 쟀습니다»
③ 의 넷(claims·profiles·binding_origin 외)이 «실행되는» 자리인지
                                          이름이 남은 것까지만 쟀습니다
샘플 파일을 «누가 언제» 깨뜨렸는지         이 분석의 범위 밖입니다
```
