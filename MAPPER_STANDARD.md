# MAPPER 표준 — 디자인 패턴 지정 (소유자 제안, 2026-08-17)

> 파편화의 코드 쪽 해소. Profile-서술 정본화(R-P 제안)와 한 쌍이다: mapper가
> 자기 서술을 «클래스 선언으로» 들고 있고, Profile·사전·현황판은 그것을
> **인용**한다 — 서술이 두 벌이 될 자리를 없앤다.

## 1. 패턴: 고정 파이프라인 + 훅 둘 (Template Method)

모든 소스→원장 변환은 다섯 구간이고, **셋은 엔진 공통·둘만 mapper 훅**이다:

```
fetch(커서·워터마크)   → 엔진 공통 (backfill이 이미 함)
group(행→분자)         → 엔진 공통 ← UNIT 선언이 구동  ★표준화의 핵심
interpret(분자→주장)   → 훅 ①  (mapper가 구현)
emit(주장→원자 봉투)   → Pack emitter 공통
gate(전량/거절)        → 엔진 공통 (기존 게이트 그대로)
```

**묶기(group)를 mapper에서 몰수해 엔진으로 올린다.** 묶음 종류는 넷뿐이고
(1단계 분류표), 엔진이 네 가지를 «한 번만» 구현한다:

- `row` — 1행 = 1분자
- `row_pair` — group_by 키로 N행 = 1분자 (스플릿·머지)
- `eav_pivot` — name/value 행들 → 1분자
- `snapshot_diff` — 정렬 키 기준 인접 행 쌍 → 변화 분자

mapper는 묶는 코드를 쓰지 않는다 — **선언하면 엔진이 묶어서 분자를 건네준다.**
「묶음은 어디서 정해지나」의 답이 이로써 한 곳이 된다: `UNIT` 선언.

## 2. 표준 mapper의 모양

```python
class LotEventMapper(LedgerMapper):                    # 베이스가 파이프라인 소유
    mapper_id, version = "lot-event", 1

    UNIT = Unit(kind="row_pair",
                group_by=("lot", "event_type", "event_time"),
                doc="스플릿·머지 1건 = 부모행 + 자식행")
    EMITS = (Emit("derived_from", per="molecule",
                  sentence="「〈자식랏〉은 〈부모랏〉에서 갈라져 나왔다」"),
             Emit("has_wafer", per="slot",
                  sentence="「〈랏〉의 〈슬롯〉에 〈웨이퍼〉가 있다」"),
             Emit("register", per="new_entity", sentence="「〈랏〉이 등장했다」"))
    REQUIRES = ()                                      # 전제(이웃 표 등) — 관측이면 run 표

    def interpret(self, molecule) -> list[Claim]:      # 훅 ① — 유일한 자유 코드
        ...                                            # 검증·event_type 분기·뜻 해석
    # assemble 훅 ②는 eav_pivot 등 분자 내부 정돈이 필요할 때만 (선택)
```

`UNIT`·`EMITS`·`REQUIRES`는 장식이 아니라 **기계가 읽는 계약**이다:

## 2-bis. PAYLOAD는 어떻게 들어가나 — 선언된 세 입구뿐

봉투의 `object_payload`에 잎이 생기는 길은 셋이고, **셋 다 선언**이다. 훅이
임의 dict를 밀어 넣는 넷째 길은 없다(금지 4-②의 실질).

```
① Pack 컴파일 규칙  : role → 골격 잎.  Claim("process/run", step=…, recipe_id=…,
                      recipe_rev=…) → {"step": …, "recipe": {"id": …, "rev": …}}
                      — 중첩 접기·필수 잎 철자는 claim 정의가 소유. 어휘 서명의
                      required와 한 벌(게이트가 재검).
② Profile 수송 잎   : bind의 payload 블록. "payload.inchip_x": "column:inchip_x"
                      — 관측의 좌표·측정치처럼 «그대로 실어 나르는» 열린 잎.
                      대조 엔진의 후보는 대부분 여기서 나온다.
③ interpret 계산값  : 훅이 계산한 값도 **role로만** emitter에 건넨다
                      (예: transfer의 container_recorded). 그 role이 만들 잎
                      철자는 claim 정의에 있고, EMITS의 fields 목록에 올라
                      사전·합의 검사기가 볼 수 있다.
```

결과: **잎 철자의 정본은 claim 정의**다. `bindings`(기전)·`labels`(이름)는 그
철자를 인용하는 소비자이고, 합의 검사기(06)가 「인용이 실물 잎과 맞는가」를
실측 대조한다. 훅에서 봉투를 만들 수 없으므로 — payload에 뭐가 들어가는지
알려면 **claim 정의 + Profile의 payload 블록** 두 곳만 읽으면 되고, 그 두 곳은
모두 사전(03)이 렌더한다.

## 3. 선언을 장식이 되지 못하게 하는 자물쇠 셋

1. **엔진이 UNIT으로 묶는다** — mapper는 다르게 묶을 코드 자체가 없다.
2. **드라이런이 EMITS를 대조한다** — 실제 산출 술어·배수가 선언과 어긋나면
   저장이 아니라 **이름 붙은 거절** (걷기가 어휘 선언과 자기 구현 불일치를
   거절하는 그 패턴).
3. **서술 없는 mapper는 등재 불가** — UNIT·EMITS 없는 클래스는 registry가
   거부한다. 「mapper_id만 덜렁」이 사라진다.

## 4. 금지 (훅 안에서)

- DB 접근 금지 (lookup은 선언된 컨텍스트 배치로만 — 기존 계약)
- 봉투 직접 조립 금지 (Pack emitter 경유 — 게이트 서명과 한 벌 유지)
- provenance·커서·게이트 접촉 금지 (엔진 소유)
- 묶기 재구현 금지 (UNIT으로 선언)

## 5. 효과 (파편화 지적의 종결선)

- **사용자**: 「어떻게 변환되나」= Profile/사전이 UNIT·EMITS를 그대로 렌더 —
  묶음·문장·전제가 한 화면. (파편의 «지도»가 아니라 «해소»)
- **작성자**: 새 구조 변환 = 훅 하나 채우기. 두 줄 문법·짝짓기의 어려움은
  남지만, 그 어려움이 **한 함수 안에** 갇힌다.
- **하니스(1단계)**: 전 mapper가 같은 훅이라 등가 디프·계측이 균일.
- **마법사(04)**: 「구조 변환 mapper 필요」의 뜻이 「interpret 훅 하나 필요」로
  구체화 — 요청서 자동 생성 가능.

## 6. 계획 반영

- 1단계에 **기존 mapper(lot-event)를 이 표준으로 개주하는 작업**을 포함한다 —
  표준의 첫 실증이자 등가 하니스의 첫 표본 (같은 소스, 개주 전/후 디프 0).
- 2단계 Pack 추출은 EMITS 선언을 원료로 쓴다.
- 이 문서가 표준의 정본이며, `COMMON_RULES_DELTA.md`의 B(전환 규칙)와 함께
  모든 단계에 적용된다.
