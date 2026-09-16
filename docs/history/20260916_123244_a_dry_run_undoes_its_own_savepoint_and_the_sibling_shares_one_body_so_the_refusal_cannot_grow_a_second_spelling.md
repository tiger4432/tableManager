# 건식 실행은 «자기» SAVEPOINT 를 되돌린다 — 호출자의 트랜잭션이 아니라. 그리고 형제 둘이 «한 몸»이라 거절이 두 철자가 될 수 없다 (S-274 1단계, 판정 415)

> **커밋:** `4c4744f7` — fix(enrichment): a dry run undoes its own savepoint, not the caller's transaction (S-274 stage 1, ruling 415)
> **일자:** 2026-09-16 12:32
> **레인:** 구현자 · 응용/구현자 census(D-41) → 판정 415 → 착지 → 총괄이 «직접 A/B 로» 검증
> **측정 상자:** 이 워크스테이션 + 이 박스의 PostgreSQL. **운영이 아니다.**
> **스위트:** `run_auto_confirm_sweep` · `session_contract` · `enrichment.analysis` · `retroactive` 를 이름으로 드는 평범 스위트 **668 passed / 1 skipped** · `scripts/run_pg_tests.py` **91 passed / 0 failed** · `pytest tests --collect-only -q` **6,812 · 0 errors**. 총괄이 따로 잰 것 **135 passed / 2 skipped**.
> **파일:** `server/session_contract.py` · `server/enrichment/analysis.py` · `server/tests/test_a_dry_run_undoes_only_what_it_wrote.py`(신규 230줄) (+284 / −8)

---

## ① 왜 — 「belt and braces」 한 줄이 «남의» 작업을 지우고 있었다

`run_auto_confirm_sweep(apply=False)` 의 끝줄:

```python
if not apply:
    db.rollback()  # belt and braces: a dry-run holds no writes, make it structural
```

**좌석 «안»에서는 옳다** — 건식은 아무것도 남기면 안 된다. **좌석 «밖»에서는 파괴적이다** — 그 세션은 «호출자»의 것이고, 호출자는 자기 미커밋 작업을 쥐고 있을 수 있다. 이 팔에 실제로 닿는 호출자가 셋이었다(`_count_chain_replay` · `_run_chain_replay` · 건식 라우트).

🔴 **저장소가 이 모양의 값을 «이미 한 번 치렀다».** `enrichment/config._isolated_execute` 의 docstring 이 기록하고 있었다 — 오염된 세션이 `process_pending_groups` 로 새어 그 `processed_chain=True` 커밋이 롤백으로 바뀌었고, 그룹이 안 찍혀 **배치 루프가 영원히 재실행**했다.

---

## ② 판정 415 의 핵심 — 「롤백을 지운다」가 «아니다»

```
❌ 롤백을 지운다        건식이 자기가 쓴 것을 남긴다. 다른 결함으로 바꾸는 것일 뿐이다
✅ 되돌릴 «범위»를 자기 것으로 만든다
```

그리고 그 도구는 **같은 날 아침에 이미 지어져 있었다** — S-271(`6ea4f7b2`)의 `session_contract.in_savepoint`. 다만 형제가 없었다: `in_savepoint` 는 성공하면 «항상» RELEASE 한다. 건식이 필요한 것은 「돌리고 «버리기»」다.

```python
def in_savepoint(db, where: str, work):
    return _in_savepoint(db, where, work, keep=True)

def discarding(db, where: str, work):
    return _in_savepoint(db, where, work, keep=False)
```

**한 몸이고, 다른 것은 마지막 «한 몸짓»뿐이다.**

```python
# 🔴 [S-274] THE ONE LINE THE TWO SIBLINGS DIFFER BY. `commit` here RELEASEs the
# savepoint (the work stands); `rollback` undoes it and leaves the CALLER's
# transaction exactly as it was - which is what a dry run owes the caller and what
# a bare `db.rollback()` took from it.
(nested.commit if keep else nested.rollback)()
```

좌석은 그래서 한 줄이 됐다:

```python
stats = session_contract.discarding(
    db, "enrichment_sweep",
    lambda: enrichment.candidates.confirm_keys(
        db, rule, keyed, apply=False, tx_prefix="enrichment_sweep", caps=caps))
```

---

## ③ 🔴 「공유 코드」 주장을 «읽어서» 재지 않고 «돌려서» 쟀다

판정 415 게이트 ③ 은 「25P01 갈래가 `in_savepoint` 와 «같은 한 줄»인지」였다. 구현자가 그것을 **소스 대조가 아니라 실행 대조**로 단언했다.

```python
def test_the_two_siblings_differ_by_exactly_one_gesture():
    """⚠️ ONE BODY, SO THE 25P01 ARM CANNOT COME TO HAVE TWO SPELLINGS (ruling 415 ③).
    Asserted by driving both, because a claim about shared code that only reads the source
    would pass on two copies that happen to match today."""
    kept, dropped = _Session(), _Session()
    session_contract.in_savepoint(kept, "probe", lambda: None)
    session_contract.discarding(dropped, "probe", lambda: None)
    assert kept.acts == ["nested", "release"]
    assert dropped.acts == ["nested", "undo"]
```

거절 줄도 같은 방식으로 «양쪽을 돌려» 견준다.

```python
assert lines["keep"] == lines["drop"], lines
```

> **「오늘 우연히 같은 사본 둘」도 소스 읽기로는 통과한다.** 이 저장소가 여러 번 치른 부류이고, 여기서는 그 함정에 안 들어갔다.

---

## ④ 빨강을 «먼저» 보였고, «양쪽»을 단언한다

```
옛 좌석으로   호출자 행이 «사라진다»   -> 「the dry run discarded work it did not do」
새 좌석으로   호출자 행은 «남고», 건식이 쓴 것은 «안 남는다»
```

둘째 단언이 없으면 **「되돌리기를 그냥 관둔」 빌드도 초록**이다. 그것이 「범위를 자기 것으로 했다」와 「되돌리기를 관뒀다」를 가르는 자리다.

총괄이 착지 뒤 **직접 A/B 로** 다시 쟀다:

```
호출자가 미커밋 작업을 쌓아 두고 좌석을 부른 뒤, 그 작업이 남아 있나
  옛 모양 db.rollback()   ->  0 행   (남의 작업이 사라진다)
  새 모양 discarding      ->  1 행   (살아남는다)
같은 픽스처 · 같은 세션 · 다른 답
```

⚠️ **pysqlite 는 이 부류를 대부분 «못 본다»** — SELECT 에 트랜잭션을 안 연다. 그래서 위 단언들은 «몸짓»에 대한 것이고, 성질 자체는 `@pytest.mark.pg` 한 벌이 진짜 INSERT 로 잰다. 호출자 커밋 «전»과 «후» 둘 다 확인한다.

```python
held = {row[0] for row in session.execute(text("SELECT who FROM s274_probe"))}
assert held == {"caller"}, held
session.commit()
after = {row[0] for row in session.execute(text("SELECT who FROM s274_probe"))}
assert after == {"caller"}, after
```

---

## ⑤ 「16」은 «명단»이 아니라 «자릿수»다 — 그리고 단계로 간다

판정 415 가 「한 커밋으로 16 을 고치지 않는다」의 사유를 적었다. S-181 의 「나눠 착지시키면 그 사이가 거짓」은 **한 사실을 여러 자리가 접을 때**의 규칙이고, 여기는 다르다 — **쌍 하나를 고치면 그 쌍이 즉시 안전하고 나머지와 무관하다.**

```
1단계 (이 커밋)  형제 primitive + 원형 하나 (run_auto_confirm_sweep 과 그 호출 자리 넷)
2단계            나머지 12 쌍 — «열어서 확정»한 것만
3단계            commit 쪽 — 이 시점에 «안 셌다»
```

🔴 그리고 술어가 이 라운드에서 한 번 바뀌었다. 초기의 두 수(응용 66/34/44 · 구현자 43/37/32)는 「틀린 것과 옳은 것」이 아니라 **«다른 술어»**였고, 판정이 응용 쪽을 정본으로 골랐다 — `connection`·`conn` 도 세션 이름으로 세고, **«자기 세션을 여는» 함수는 빌린 것이 아니므로 뺀다**(후자가 이 부류의 정의 그 자체다). 그리고 행동의 근거를 «총계»가 아니라 **«이름 붙은 16 쌍»**으로 놓았다 — 총계는 술어가 바뀌면 움직이고 명단은 안 움직인다.

---

## ⑥ 부수적으로 드러난 것 — 커밋 «하나»가 이 부류의 사례를 «둘» 넣었다

총괄이 검증 중 보고 한 줄을 뒤집었다. 문제의 rollback 이 「오늘 진단기를 안전하게 만들려고 들어갔다」가 아니었다 — blob 을 열어 보니 `6f45a004`(09-11)에 «이미» 있었다.

```
git log -S"db.rollback()" -- parsers/directory_watcher.py   ->   6f45a004  (09-11)
```

🔴 **그래서 `6f45a004` 한 커밋이 이 부류의 사례를 «둘» 넣었다** — 만료된 객체를 읽는 자리(D-39)와, 빌린 세션을 롤백하는 자리. 계측기 224줄, 시험 «0». 이날 승격된 「계측기는 코드다」가 이보다 선명할 수 없다. 정정은 «수리»가 아니라 «문장»이었고, 그 자리(`_plan_digest`)는 판정이 **이번 라운드에서 명시적으로 뺐다**.

---

## ⑦ 아키텍처 영향

- `session_contract` 가 **형제 둘**을 낸다 — 살리는 판(`in_savepoint`)과 버리는 판(`discarding`). 「한 축은 한 칸·한 함수」의 모양이 유지된 채 축이 하나 늘었다.
- 25P01 거절이 **구조적으로 한 철자**다. 두 함수가 같은 `_in_savepoint` 를 지나므로 갈라질 자리가 없다 — 「같은 기능에 두 경로가 «갈라질 수» 있나」 기준의 통과 판이다.
- 건식 스윕이 **호출자의 트랜잭션을 안 건드린다.** 그 세션을 빌려 준 넷(어드민 소급 둘 · 라우트 · CLI)이 코드 변경 «0» 으로 같이 안전해졌다.
- 판정이 **census 의 술어를 정본화**했다 — 「빌린 세션」의 정의에서 «자기 세션을 여는 함수»를 뺀 것.

---

## ⑧ 그때 남아 있던 것

- **나머지 12 쌍은 안 고쳤다**(2단계). 그리고 이 항목을 쓰는 시점 기준, 2단계에서 여덟을 «열어» 본 결과 오늘 실제로 파괴하는 쌍은 **0** 이었고 **코드 변경도 0** 이었다. 「12 중 12 고쳤습니다」가 아니라 「열어 보니 아니었다」가 그 라운드의 산출물이다.
- **commit 쪽은 «아직 안 셌다»**(3단계). 「좌석 N 이 commit 한다」는 수는 결함 수가 아니다 — 호출자가 «커밋되기를 바라는» 자리가 많다.
- `_plan_digest` 는 «두 번» 미뤄졌다. 사유는 「그 파일이 오늘만 네 번(뒤에는 다섯 번) 바뀌었다」이고, 결함 판정이 아니다.
- 커밋 시점에 **운영은 이 변경을 안 받았다.** 보고가 「재기동 부탁드립니다」로 끝난다.
- 「16」의 판별식(「호출 뒤 같은 이름이 다시 나온다」)은 **정적 근사**다. 판정이 그것을 적고 「명단을 그대로 쓰지 말라」를 지시로 달았다 — 즉 **이 시점에 «진짜 쌍»의 수는 아무도 모른다.**
- `discarding` 을 쓰는 좌석은 이 시점에 «하나»다.

---
📎 이 항목의 수(668 / 1 · 91 / 0 · 6,812 · 135 / 2 · 0행 vs 1행)는 «이 박스»의 것이다.
📎 사유 코드: S-271(`6ea4f7b2`, `in_savepoint` 와 `session_contract` 의 출생) · S-272(`dc78afcd`, 25P01 을 «만드는» 자리) · S-167(빌린 연결의 함정) · D-39/`6f45a004`(계측기가 넣은 같은 부류 둘) · S-274(이 라운드) · 판정 415.
