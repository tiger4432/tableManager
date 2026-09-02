# 뷰가 «체인이 만드는 표»가 됐다 — 그리고 수가 같다는 것은 증거가 «아니었다»

> **커밋:** `c5147985` (13:44) · `4ffc8a7c` (13:59) · `60b16345` (14:27) · `79e2bdc7` (14:41)
> | **일자:** 2026-08-31 오후
> **레인:** 서버(체인 · 매퍼 · 원장)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경 — 「스크립트가 만든 뷰」는 «그 스크립트를 돌린 상자에만» 있다

소유자 지시: **`lot_event` 에서 체인으로 파생하라** (「어느 slot trace가 아니라 lot event에서
파생하라고」).

```
스크립트가 만든 뷰   그 스크립트를 «돌린 상자»에만 있다
그것을 가리키는 선언  스크립트가 안 돈 곳에서는 «아예 나타나지 않는 소스»를 출하한다
운영이 파생 표를 퍼뜨리는 방식   «체인»
```
이것이 「표에 원천 데이터를 넣고 그걸로 원장」 상설의 **파생 표 판**이다 —
**선언이 모르는 자리에서 나온 것은 walk 의 주어가 못 된다.**

## ① 매퍼가 «.sample» 로 출하됐다 — 라이브만 고치면 같은 실수를 한 칸 옆에서 반복한다

`c5147985`. `server/mappers/*` 는 gitignore 이고 기존 매퍼 열은 전부 `.py.sample` 이다.

```
라이브 파일만 커밋   ->  «남이 안 가진» 매퍼를 출하하는 것
=> 이 라운드가 고치려는 «바로 그 결함»을 한 디렉터리 옆에서 다시 만드는 것
```

## 🔴 ② 조용히 틀리는 두 자리를 «선언»과 «거절»로 막았다

```python
# 🔴 THE DELIMITER IS DECLARED, NOT ASSUMED. A separator is a property of the feed, and this
# box's happens to be `:`. Reading it off the rule means another environment states its own
# instead of finding that every wafer id came out glued together - a failure that produces
# rows rather than an error, so nobody would see it until a map was wrong.
#
# 🔴 AND A ROW WHOSE TWO LISTS DISAGREE IS REFUSED, NOT TRIMMED. Zipping to the shorter list
# loses the wafers past the end SILENTLY: the row still lands, the count still looks
# plausible, and the missing wafers are indistinguishable from wafers that were never in the
# lot.
```

**둘 다 «오류가 안 나는» 실패다.**
```
구분자를 잘못 읽으면   오류가 아니라 «행»이 나온다 — 웨이퍼 id 가 통째로 하나로 붙은 채
짧은 쪽에 맞춰 zip   행은 착지하고 수도 그럴듯하고,
                    «빠진 웨이퍼»와 «애초에 랏에 없던 웨이퍼»가 구별 불가능해진다
```
🔴 그리고 거절을 **쓰기 «전»에 쟀다** — 이 상자에서 두 목록을 다 든 행 **80**,
쌍 **907**, 어긋나는 행 **«0»**. 즉 **오늘은 비용이 0 이고**, 피드 모양이 바뀌는 날을 위해
있는 것이다. (컬럼 이름도 같은 이유로 규칙에서 덮어쓸 수 있다 — 피드의 성질이지 매퍼의
성질이 아니다.)

업무 키는 **(lot, slot, wafer, time) 넷 전부**다. 지시서의 유일성 «검사»를 **키 자체**로
표현한 것이다 — 같은 랏·같은 슬롯이 **시각마다 다른 웨이퍼**를 담기 때문에,
시각 없는 키는 **실제 사건 둘을 한 행으로 뭉갠다.**

## 🔴 ③ 「착지는 배선이 아니다」 — 매퍼가 «호출자 0» 으로 출하됐다

`4ffc8a7c`. 매퍼가 **규칙 없이** 갔다. 같은 날 **두 번째**로 같은 모양이었다.
규칙도 같은 이유로 추적되는 `.sample` 에 들어갔다.

**JSON 을 읽어서가 아니라 «진짜 로더»로 증명했다** — 샘플을 라이브 설정으로 갈아 끼우고
`chain_ingestion_worker.load_chain_rules` 가 파싱하는지, 매퍼 모듈이 import 되고 함수가
호출 가능한지, enabled-only 뷰가 그것을 **올바르게 빼는지**까지.

⚠️ **일부러 `enabled: false` 로 출하됐다** — 그 이름은 이 상자에서 «뷰»였고 체인은 뷰에 못
쓴다. 진짜 표인 곳에서 켜면 원장 소스의 기존 `relation` 을 **그대로 둔 채** 돈다.

🔴 그리고 **텍스트로 «덧붙였지» 다시 직렬화하지 않았다.**
```
첫 시도   json.dumps 로 파일 전체 재작성   ->  35 insertions · 5 deletions
                                          배열 재래핑 · em-dash 재이스케이프
                                          아무도 안 고친 줄이 흔들리고 «중요한 한 줄»이 묻힌다
이 커밋   16 insertions · 0 deletions
```
그 첫 시도는 **내용이 생기기도 전에 대상 파일을 쓰기 모드로 열었고**, 인코딩 오류가 나면서
**0바이트**로 남았다. git 에서 복구했고, 이번에는 **임시 파일에 만들고 → 파싱하고 → 그다음
옮긴다.**

## 🔴 ④ 배치 매퍼가 «리스트»를 돌려주자 체인이 «0 items» 라고 답했다

`60b16345`. 매퍼는 직접 부르면 완벽히 도는데 체인을 지나면 **`mapper_items: 0`** 이었다.
**오류가 아니라 0 이다.**

```python
# 🔴 A DICT, NOT A LIST. `chain_replay` wraps an `is_batch` mapper's return in a list of
# its own and then reads `.get("updates")` on each element, so returning a list of
# batches produces a list where a dict is expected - and the chain reports zero items
# rather than an error. Measured: the same payloads that make 907 updates here came
# back as `mapper_items: 0` through the chain until this changed. `target_table` is not
# ours to state either; the RULE declares it, which is why the chain never asked.
return {"updates": updates}
```
기존 배치 매퍼 «둘»에 대조해서 확인한 계약이다. 그리고 `target_table` 도 매퍼가 말할 것이
아니다 — **규칙이 선언한다.** 그래서 체인이 애초에 안 물어봤다.

## 🔴 ⑤ 전환 — 순서가 있고, 마지막 단계가 «내용»이다

```
① 기준선   has_wafer 원자 «907»  (보고서에서 가져오지 않고 «직접 쟀다»)
② 뷰       드롭. 선언된 표가 그 자리에 서고, «비어 있다»
③ 규칙     라이브에서 켰다 — «그 한 줄만»
④ 체인     907 행 생성 · 5,442 셀 · 907 개의 서로 다른 키   (콜론 목록이 펴진 결과)
⑤ 원장     랏 25 에 대한 범위 재번역 — 범위 안 907 · 회수 907 · 기록 907
⑥ 증거     has_wafer 원자 «907» = 기준선과 «같다»
```
🔴 **그리고 «수»가 아니라 «내용»으로도 같다** — 수가 같다는 것은 **무엇으로 만들어졌는지를
가린다.** 술어 하나 `has_wafer`, 서로 다른 `{lot, slot}` 주어 **238**, 목적어 타입 `wafer`.

`create_lot_slot_wafer_view.py` 는 **⑥이 새 경로가 같은 원장을 낸다는 것을 증명한 뒤 «마지막»
에 지워졌다** — 창이 열려 있는 동안 그것이 **돌아갈 길**이었기 때문이다.

## 🔴 ⑥ 그리고 그 라운드가 «자기가 만든 문장»을 낡게 했다

`79e2bdc7`. 출하되는 주석이 이렇게 말하고 있었다 —
「`lot_slot_wafer` 는 그 상자에서 «뷰»이고 체인은 뷰에 못 쓴다」.
**같은 라운드가 그 뷰를 지웠다.**

```
문장이 «자기를 만든 변경 안»에서 낡았다
그리고 그것은 «출하된다» -> 모든 환경이 「이 규칙이 왜 꺼져 있는지」에 대해 «거짓»을 읽는다
```
이제는 **오래 가는 진짜 이유**를 적는다 — **대상 표가 «먼저 있어야» 한다. 체인은 표를
만들지 못한다.** 그리고 주장 대신 **증명**을 나른다: 위의 순서와 수, 그리고
**수가 같은 것만으로는 증거가 아니라는 요점**까지.
샘플에서 `enabled` 는 **false 로 남는다** — 그 표가 있는 상자는 여기뿐이고, 여기의 라이브
파일은 출하되는 것이 아니다.

## 아키텍처 영향

- `lot_slot_wafer` 가 **스크립트가 만든 뷰**에서 **체인 규칙이 채우는 표**가 됐다.
  선언은 기존 `relation` 을 그대로 쓴다.
- 매퍼와 규칙이 **`.sample` 로 추적**된다 — 라이브만 고치면 남이 못 갖는다.
- 배치 매퍼의 반환 계약이 **dict** 임이 주석에 못 박혔다. 리스트를 주면 **오류 없이 0** 이다.
- 구분자·컬럼 이름이 **규칙 선언**이고, 목록 쌍이 어긋나면 **이름을 대고 거절**한다.

## 그때 남아 있던 것

- 샘플 규칙은 **`enabled: false`** 다. 이 상자에서만 켜져 있고, 라이브 설정 파일은 출하되지
  않는다.
- 이 상자에서 어긋나는 행이 **0** 이라, 목록 쌍 거절은 **한 번도 발화한 적이 없다.**
- 907 · 5,442 · 238 · 80 은 전부 **이 상자의 씨앗 데이터**에서 잰 수다.
- 첫 시도가 남긴 **0바이트 파일은 git 에서 복구됐다** — 그 사고는 커밋에 남지 않았고
  커밋 본문에만 기록돼 있다.
