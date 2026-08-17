# [Task] Ledger config — 파일 구조 단순화 (chains 제거, 선언만으로 활성화)

> **상태:** 제안(대기) — 착수 승인 필요
> **우선순위:** config 확정 직후, 매퍼 개주와 같은 묶음
> **등록:** 2026-08-18
> **소유자 지시:** 「chain은 왜 필요한건지 검토해서 없앨 수 있으면 없애고 그냥 ledger
> config 활성화되게 해」 (2026-08-18)

## 판정: chains는 없앨 수 있다

`dataflows/chains.json`의 `ledger_v2_execution.sources.<id>` = `{mode, parity_status,
approval_ref}`는 legacy→v2 전환기의 소스별 스위치다. 세 칸을 각각 실측했다.

### `mode` — 두 위치 중 하나가 죽어 있다

`mode: "v2"`는 v2 경로로 보낸다(`backfill.py:263`). 그러면 `mode: "legacy"`는?

- CLI가 `--legacy` 없이 돌면 `cfg = {}`로 시작한다 (`backfill.py:1570`)
- `run()`이 v2가 아니면 legacy 분기로 내려가 `source_config({}, source)`를 부른다
- 빈 config에는 선언이 없으므로 `None` → `refuse` → `atoms=0, refused_source=True`

즉 **`mode:"legacy"`는 아무것도 하지 않고 정상 종료한다.** 진짜 legacy 실행은
`--legacy --config <경로>`뿐이고, 그 경로는 chains를 아예 읽지 않는다. 스위치의 한쪽
위치가 어디로도 연결돼 있지 않다.

### `parity_status` / `approval_ref` — 검증하지 않는 증거

`cutover_v2.py:238-248`이 확인하는 것은 "문자열이 비어 있지 않다"와 "값이 `approved`다"
뿐이다. `approval_ref`는 이후 `dry_run_report`에 그대로 메아리치는 것 외에 아무 데도 쓰이지
않고, `shadow_parity.py`는 테스트 밖 호출자가 없다. **승인 근거를 이름으로 요구하지만
대조하지 않는다.**

### 결론

chains가 실제로 하는 일은 «선언한 소스마다 `approved`라고 한 번 더 적게 하는 것»이다.
실행 여부를 결정하는 정보는 이미 `sources`에 전부 있다. 전환기 유물이며, 전환은 끝났다.

## 함께 정리되는 두 파일

| 파일 | 실측 | 판정 |
|---|---|---|
| `dataflows/enrichments.json` | 소비자 0. 스냅샷 해시에만 들어감 | 제거 |
| `catalog/virtual_joins.json` | 규칙을 켜면 오히려 실행이 거절됨(검증된 조인 공급 경로가 항상 비어 있음). `{}` 외엔 쓸 수 없음 | 제거 (조인 기능을 실제로 살릴 때 다시 도입) |
| `dataflows/chains.json` | 위 판정 | 제거 |

## 목표 구조

```text
server/config/ontology/
└─ ledger_config.json      # 이것 하나
```

- `setup_version`을 `ledger_config.json` 안으로 옮기면 `manifest.json`의 존재 이유가
  사라진다(파일이 하나면 열거할 것이 없다).
- `catalog/tables.json`의 `tables`는 `ledger_config.json`의 한 섹션으로 들어온다.
  물리 사실과 논리 선언의 구분은 **섹션 이름**으로 충분하다.
- **선언이 곧 활성화다.** `sources`에 있으면 돈다. 별도 스위치를 두지 않는다.

### 「선언은 해 뒀지만 아직 돌리기 싫다」는?

별도 스위치가 필요해 보이지만 이미 막혀 있다. 프로필의 바인딩이 하나라도 `approved`가
아니면 `require_ready_bundle`이 로드를 거절한다(`setup_bundle.py:1260`). 즉 **작성 중인
소스는 이미 못 돈다.** 스위치를 하나 더 둘 이유가 없다.

정말로 «완성됐지만 지금은 끄고 싶다»가 필요해지면 `sources.<id>.enabled`처럼 그 소스의
선언 안에 둔다. 별도 파일로 분리하지 않는다 — 지금 chains가 겪는 문제(화면에 안 보임,
소스와 따로 놀아 빠뜨림)가 그대로 재발한다.

## 부수 효과 — 오히려 이득

스냅샷 해시가 실행과 무관한 칸(enrichments, approval_ref)까지 포함해서 계산되는 문제가
같이 사라진다. 지금은 승인 근거 문자열 하나만 고쳐도 커서가 `cursor_snapshot_reset_required`로
막히고, `--reset-cursor`는 무조건 거절이라 승인된 복구 경로가 없다.

## 지금이 공짜다

실측(2026-08-18): DB에 `ledger_cursor`·`ledger_events` **테이블 자체가 없다.** 커서가
없으므로 스냅샷 해시가 바뀌어도 막힐 것이 없다. 첫 백필을 돌린 뒤에 이 작업을 하면
커서 재설정 승인이 별도로 필요해진다.

## cutover 하드코딩 — 저것이 무엇인가

`cutover_v2.py:88-105`의 세 함수다.

```python
def trusted_cutover_implementations():          # 신뢰 목록 (이름+버전 2개)
def cutover_preparer_registry():                # 준비기 클래스 등록
def cutover_mapper_registry():                  # 매퍼 클래스 등록
```

**정체:** config가 임의의 파이썬을 실행시키지 못하게 막는 화이트리스트다. config에는
`implementation_id`라는 **이름**만 적히고, 그 이름이 이 목록에 없으면 컴파일이
`untrusted_implementation`으로 거절한다. 선언에서 `module`·`function`·`path`·`eval` 같은
키를 금지한 것(`setup_bundle.py:37`)과 한 쌍이다. **경계 자체는 옳다** — 없애면 config
파일 하나로 임의 코드를 부르게 된다.

**지금 문제는 경계가 아니라 목록이다.**

- 손으로 관리하는 목록이 **세 곳**에 흩어져 있다. 매퍼 하나 추가에 세 곳을 고쳐야 한다.
- 그래서 이미 존재하는 범용 구현 두 개가 **등록 누락으로 잠겨 있다**
  (`DeclarativeRoleMapper`, `DirectJoinSourcePreparer` — 2026-08-18 실측).
- 모듈 이름 `cutover_v2`와 함수 이름 `cutover_*`는 전환기 유물이다. 전환이 끝났는데
  평상시 실행 경로가 «cutover»라는 이름을 달고 있다.

**목표: 목록을 없애고 경계는 남긴다.** 구현 클래스가 자기 `implementation_id`와 버전을
스스로 선언하고, 패키지 import 시점에 등록한다. 등록 가능 조건은 «저장소에 실재하고
`BaseLedgerMapper`/`BaseSourcePreparer`를 상속하며 `map()`을 재정의하지 않을 것»이며,
이는 이미 레지스트리가 강제한다(`roleframe.py:288-296`). 손으로 유지하는 이름 목록만
사라진다.

- 새 매퍼 추가 = **파일 하나**. `cutover_v2.py` 수정 0.
- 범용 구현 두 개는 자동으로 열린다 → 단순 소스는 파이썬 0줄로 개통.
- 모듈은 `ledger/setup.py`(가칭)로 개명한다. 하는 일이 «config 로드 → 스냅샷 컴파일 →
  레지스트리 제공»이지 전환이 아니다.

## 작업 범위

0. 구현 자기 등록으로 전환하고 손수 관리하는 신뢰 목록 세 곳을 제거한다.
   모듈·함수 이름에서 `cutover`를 뗀다.
1. `setup_bundle.load_setup_bundle`을 단일 파일 로더로 바꾼다. `setup_version` 3.
2. `LOGICAL_SECTIONS`에서 `virtual_joins`·`chains`·`enrichments`를 뺀다. `tables`는 유지.
3. `cutover_v2._validate_selector`를 제거하고, `sources` 선언 자체를 실행 대상으로 삼는다.
4. `backfill.run`의 `selection.mode` 분기를 제거한다. `--legacy` 경로는 그대로 둔다
   (legacy 은퇴는 별건).
5. Explorer가 읽는 섹션 목록을 맞춘다 (chains가 화면에 없던 문제도 함께 소멸).
6. 기존 5파일 루트를 새 단일 파일로 옮기는 일회성 변환기를 제공한다.

## 합격 기준

- [ ] `server/config/ontology/ledger_config.json` 하나로 로드·컴파일·실행된다.
- [ ] 전환 전후 같은 입력에서 **원자 디프 0** (도구는 매퍼 개주 과제와 공용).
- [ ] 실행과 무관한 선언을 고쳐도 커서가 막히지 않는다.
- [ ] 선언한 소스는 별도 스위치 없이 돈다.
- [ ] 문서에서 `chains`/`enrichments`/`virtual_joins` 서술이 제거되거나 «미도입»으로 정정된다.

## 비범위

- legacy 경로(`--legacy --config`) 은퇴 — 별건
- virtual join 기능 자체의 구현 — 실제로 필요해질 때 새 섹션으로 다시 도입
