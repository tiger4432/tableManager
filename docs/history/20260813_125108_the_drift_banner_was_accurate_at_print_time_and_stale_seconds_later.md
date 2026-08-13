# The drift banner was accurate at print time and stale seconds later

**Date:** 2026-08-13 12:51 · **Domain:** Server (부팅 사전점검 / 스키마 드리프트) · **Status:** 착지 — `eb700e5`

> ⚠️ **주입·측정은 이 박스의 테스트 픽스처 기준이다. 운영의 증거가 아니다.**

---

## 배경 — 운영자가 조치하고 재기동했더니 사라진 빨간 블록

제품 소유자가 「`dt_map`을 건드리는 모든 화면이 당신이 조치할 때까지 실패한다」는 빨간 블록을
만났다. 조치하고, 재기동하고, **사라진 것을 봤다.**

원인은 어느 쪽의 버그도 아니라 **프로세스 간 순서**다. 런처는 자기가 띄울 워커들이 각자
`sync_dynamic_tables_schema(engine)`을 돌리기 **전에** 검사한다. 그래서 배너는 **인쇄 시점에는
정확했고 몇 초 뒤에 낡았다.**

검사를 뒤로 옮기는 것으로는 못 고친다 — 사전점검의 값어치는 **재기동 전에 도는 것**이다. 고칠 수
있던 것은 **배너**였다.

## 술어를 지시서가 아니라 «수리기의 소스»에서 뽑았다

`_sync_repairs`는 `sync_dynamic_tables_schema`의 루프가 가진 게이트 셋을 순서대로 옮겼다 —
테이블이 `DYNAMIC_TABLES`에 있고, 물리적으로 이미 존재하고, 이름이 **대소문자 무시로** 없을 것.

그리고 그 dict를 **읽는다**, 복사하지 않는다.

```python
def _dynamic_table_names():
    """The exact dict `sync_dynamic_tables_schema` loops over, read - not copied.

    Deliberately `models.DYNAMIC_TABLES` and not `table_config.json`. The config is
    the DECLARATION; this dict is what the repairer actually iterates, and the two
    can differ inside one process ...
    """
    try:
        from database import models
        return set(getattr(models, "DYNAMIC_TABLES", None) or ())
    except Exception:
        return set()
```

except가 이렇게 넓은 것도 판단이다 — **빈 답이 안전한 방향**이다. 아무것도 self-healing으로
분류되지 않고 모든 발견이 오늘의 전체 심각도를 유지한다. **수리기를 볼 수 없는 분류기는 무엇도
무해하다고 부를 자격이 없다.**

그리고 예측은 **읽기가 아니라 «행동»에 대해 채점**됐다. 한 테스트는 sync를 돌려 예측된 컬럼이
나타나는 것을, 다른 테스트는 sync를 돌려도 대소문자 다른 컬럼이 **여전히 없는** 것을 단언한다.
자기가 분류하는 대상에 한 번도 대조되지 않은 분류기는 **표를 단 추측**이다.

## 조용한 쪽을 화이트리스트로 잡았다

```python
    # QUIET IS THE WHITELIST, and it has to be this way round. Written as
    # `stuck = severity in ("TABLE-DOWN", "MISSING-TABLE")` a severity nobody has
    # invented yet ... would fall through to neither bucket and be printed as
    # harmless.
    _QUIET = ("SELF-HEALING", "INFO")
```

`SEVERITY_ORDER`에 `SELF-HEALING`이 들어가며 `INFO`가 2에서 3으로 밀렸다. 자가치유 건은 테이블·
컬럼·심각도·수동 ALTER·에스컬레이션 경로를 **그대로 유지한 채** 경고로 인쇄되고 「할 일 없음」을
말한다. 진짜로 막힌 건은 **바이트 단위로 그날의 배너 그대로**다. 자가치유 건이 함께 있을 때는
빨간 블록 **아래**에 별도로 붙는다 — 「위 테이블」이 막힌 것만 가리켜야 하기 때문이다.

직전 라운드의 발견은 이 검사가 **넉 달 동안 실제 마이그레이션에 대해 침묵했다**는 것이었다.
그래서 잘못된 절반을 부드럽게 만드는 것이 소음보다 나빴을 것이다.

## 레인이 덮지 않은 셋

- 🔴 **대소문자가 접힌 컬럼은 영원히 보고되고 영원히 수리되지 않는다.** `check()`는 정확히
  비교하고 sync는 소문자로 비교한다. 선언 `Foo` 대 저장 `foo`는 매 부팅 보고되고 수리기가
  영구히 건너뛴다 — **실패 로그조차 남기지 않고.** 이 라운드가 만든 것이 아니라 이 라운드가
  비로소 **볼 수 있게 된** 것이다.
- 🔴 **`check()`는 타입 불일치를 감지하지 못하고, 한 번도 못 했다.** 지시서는 타입 불일치를
  「계속 시끄러워야 할 회귀 케이스」로 요구했다. **지을 수 없다 — 능력이 없기 때문이다.**
  꾸며내는 대신 **테스트로 못 박았다**(모든 컬럼을 `BLOB`으로 재생성한 테이블에서 발견 0건).
  타입 감지는 추가되지 **않았다.**
- **게이트 하나는 `check()`에서 도달 불가**라 주입해도 초록으로 남고 단위 테스트 하나로만
  덮인다. 어느 쪽도 과대 주장하지 않도록 **함수와 테스트 양쪽에** 적었다.

## 🔴 계측기가 한 번 거짓말했고, 그게 기억할 부분이다

두 번째 주입 실행이 **모든 주입에서 모든 테스트 초록**을 보고했다 — 첫 실행과 정확히 반대다.
`-v -q`가 pytest의 테스트별 출력을 상쇄해서 정규식이 아무것도 못 잡았고,
`all(v == "PASSED" for v in {})`는 **공허하게 참**이라 대조 장치가 알아채지 못했다.

믿었다면 **경보가 하나도 울리지 않는다고 보고했을 것이다.** 하니스는 이제 물어본 모든 테스트에
대해 판정을 파싱했는지 단언한다. **빈 집합이 모든 검사를 통과하는 모양**은 이 프로젝트가 다른
이름으로 이미 물린 적 있는 형태다.

## 그때 남아 있던 것

- 4파일 +588/-13. 새 테스트 파일 `server/tests/test_schema_drift_startup.py`가 371줄이다.
- **대소문자 접힘 결함은 고쳐지지 않았다** — 이 라운드는 그것이 보이게 만들었을 뿐이다.
- **타입 감지는 없다.** 새 축이고 교차 방언 오탐 면적이 커서 판정이 필요한 상태로 남았다.
- 도달 불가 게이트는 주입 채점을 받지 못한 채 남았다.
- `check()`가 넉 달간 침묵했던 마이그레이션 건은 이 커밋의 범위 밖이다.
