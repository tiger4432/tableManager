# 미선언 컬럼 드롭에 신호를 붙였다 — 동작은 그대로, 침묵만 고쳤다

> 커밋 `08d2b12` · 2026-07-27 05:38 · 도메인 Server / 저장 계층
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 프리미티브: [PRIMITIVES §1 미선언 컬럼](../architecture/PRIMITIVES.md)
> 선행: [제품 소유 테이블 설치기](./20260727_051848_product_owned_table_installer.md)

## 배경

업데이트 페이로드에 있으나 `table_config.json`에 선언되지 않은 컬럼은
**로그 한 줄 없이 버려지고 200이 반환**됐다. 모든 테이블에 열려 있던 **조용한 데이터 손실 통로**다.

바로 앞 커밋에서 발견된 `map_doe`/`map_doe_source`의 `eventtime`·`updated_by` 유실이
정확히 이 경로였다 — **저장이 실패한 적이 없다. 그냥 필드가 사라졌다.**

## 변경 내용

### 거절이 아니라 가시화를 택했다

이게 이 커밋의 유일한 설계 판단이고, 명시적으로 기록해 둘 값이 있다.

> **동작은 바꾸지 않았다.** 미선언 컬럼은 여전히 드롭된다.
> 거절로 바꾸면 config가 클라보다 뒤처진 현장이 **그 순간 전부 멈춘다.**
> 고친 것은 침묵뿐이다.

즉 이것은 데이터 손실의 **해소가 아니라 계측**이다. 손실은 여전히 일어나며,
다만 로그에 남는다.

### warn-once — 같은 파일의 기존 관례를 그대로 따랐다

`crud.py`에 이미 `_warn_audit_truncation_once`가 있다. 새 기계장치를 만들 이유가 없었다.

```python
# server/database/crud.py
# Shape note: this is probed as a dict of per-table sets rather than one set of
# (table, column) tuples so the already-warned path allocates nothing — building a
# tuple key on every cell of a 100k-row ingest is exactly the cost this path cannot
# afford.
_undeclared_column_warned = {}
_MAX_UNDECLARED_WARNED_PER_TABLE = 64
```

키가 **스키마가 아니라 페이로드**에서 온다는 점이 예산 상한의 이유다 —
망가진 헤더 행이나 값을 헤더로 뱉는 파서가 있으면 무한히 자란다.
포화하면 그 테이블은 더 이상 늘지도 경고하지도 않는데, **그 사실 자체를 한 번 알린다.**

> 규율: **한정된 침묵은 되지만, 침묵의 침묵은 안 된다.**

호출 지점은 한 줄이다.

```python
if col_name not in col_types:
    # Drop behaviour is deliberately unchanged: rejecting the write would turn a
    # lagging config into an outage. Only the silence is fixed.
    _warn_undeclared_column_once(table_name, col_name)
    continue
```

### API 응답에는 일부러 싣지 않았다

가장 많이 쓰고 가장 감시가 없는 쓰기 주체는 **워처**이고, 워처는 HTTP를 타지 않는다.
응답 필드로 만들면 **정확히 중요한 경우를 놓친다.**

### 비용은 측정 한계 아래

드롭된 셀당 **105.8 ns**(단독 측정), E2E 실행의 **0.0039%** — 노이즈 바닥이 2,300~6,200배 크다.

## 함께 들어간 것 — `docs/process/PRODUCTION_READINESS.md`

사용자가 말한 조건(사내망 팀·동시 2~5명·수십 MB·준연속 운영)에 대고 운영 준비도를 평가했다.

- **통과**: 데이터 무결성 · 인제션 (측정 근거 있음)
- **막고 있는 것은 전부 운영 쪽**:
  - 런처가 감시 없는 sleep 루프다 → 워처가 죽어도 UI는 멀쩡해 보이고 데이터만 멈춘다
  - health 라우트가 없다. 없는 경로가 **HTML + 200**을 반환한다 → 외부 모니터가 죽은 서버를 살아 있다고 부른다
- 온톨로지는 사용자 지시에 따라 장기 트랙으로 **평가에서 제외**

이 두 항목이 다음 커밋(`8117456`)의 착수 근거가 됐다.

## 검증

- 테스트 4건. **결함 주입 2종(경고 억제 / once 가드 제거)이 서로 겹치지 않는 부분집합을 실패시킨다** —
  "발화하는가"와 "한 번만 발화하는가"를 분리한 것이 요점이다.
- 스위트 **498 passed / 0 failed**.

## 다음 단계

- 이 경고는 **드롭이 일어난 뒤**의 신호다. 선언 누락을 배포 시점에 잡는 것은
  설치기(`install_product_tables.py`) 쪽 책임이며, 현장 소유 테이블은 여전히 사각지대다.
- 포화(테이블당 64종) 이후의 드롭은 다시 무음이다 — 상한은 설계된 절충이지 해소가 아니다.
