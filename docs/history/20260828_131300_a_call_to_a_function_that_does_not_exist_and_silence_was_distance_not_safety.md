# 없는 함수를 부르는 줄이 조용했던 이유는 «안전»이 아니라 «거리»였고, 거절문에서 파일 경로가 아예 빠졌다

> **커밋:** `d70dfb3f` (09:32) · `8fd7d6b7` (09:32) · `bef61462` (12:12) · `b8d1dab2` (12:26)
> · `79ff99f6` (13:13)
> | **일자:** 2026-08-28 낮
> **레인:** 서버(정리)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 🔴 없는 함수를 부르는 줄이 «도달 가능해지기를 기다리고» 있었다

`79ff99f6`. `_quantity_node(...)`가 여전히 호출되고 있었는데 그 헬퍼는 **전날 밤에 지워졌다.**
한 번도 안 던진 이유:

```
decode_node_id 는 quantity 씨앗을 «만들 수 없다»
   -> {"kind": "entity"} 를 돌려주거나 raise 한다. 그게 «유일한» 두 반환이다
=> 그 줄은 «도달 가능한 경로를 기다리는 NameError» 로 앉아 있었다
```

> **침묵은 안전이 아니었다. 거리였다.**

함께 나간 것: quantity 씨앗 갈래와 그 호출, **그 한 갈래를 위해 «매 요청»마다 돌던**
`mechanism_gate.load()`와 `models_by_name`, `_seed_node`로 실려 가던 그 인자,
`quantity_refs` 프런티어 필터, 그리고 위가 나가자 안 쓰이게 된 `mechanism_gate` 임포트.

```
게이트: walk 200 · 노드 1000 · 엣지 1612
       타입 wafer 1 · die 877 · defect 121 · defect_kind 1
```

## 파일이 자기 «독자들» 옆으로 갔다 — 흡수할 온톨로지 내용이 없었기 때문

`bef61462`. 판정은 흡수였는데 **측정이 방향을 틀었다** — 흡수할 온톨로지 내용이 남아 있지
않아서, 파일이 **자기 사용자들 옆으로** 갔다.

```
server/ledger_api/finding_kinds.py  ->  server/scripts/support/finding_kinds.py
임포트가 4개 씨앗 스크립트 · 2개 시험 파일의 «9자리»에서 다시 겨눠졌다
ledger_api/ledger_subgraph.py       finding_kinds 임포트 제거 — 본문에서 «한 번도 안 쓰였다»
                                    전날 밤 노드 빌더 삭제가 남긴 고아
```

🔴 **`config/finding_kinds.json`은 «안 옮겼다» — 판정에서 유일하게 벗어난 자리다.**
그것은 운영자의 라이브 gitignore config 이고 **총괄이 그날 아침 만들었고 그 기록자다.**
**남의 레인의 라이브 파일을 옮기는 것은 이 저장소에 인시던트가 있는 행위**다.
`_config_path`가 두 층 대신 세 층 위로 걸어서 **모듈이 config 를 따라간다** — 폴백이
하드코딩이 아니라 계산되므로 **누가 옮겨도 계속 돈다.**

## 🔴 그리고 거절문이 «같은 자리를 두 번 틀렸다» — 그래서 경로를 지웠다

`b8d1dab2`. 그 문장은 `server/ledger_api/finding_kinds.py`를 가리켰다. 그 경로는
**오늘 이전에도 틀렸고**(한때 존재한 적 없는 `server/finding_kinds.py`를 가리켰다)
**오늘 아침 이동 뒤에 또 틀렸다.**

```
전   "An observation source translates ONE kind of finding
      (`server/ledger_api/finding_kinds.py` is the registry of what a kind is), ..."
후   "An observation source translates ONE kind of finding, and that value lands in
      every atom this source writes - ..."
```

**세 번째 철자도 같은 방식으로 만료될 것이므로, 고치는 대신 «경로를 없앴다».**
잃은 것은 **어디에**뿐이다. 거절문은 여전히 **무엇이 없고 왜 추측할 수 없는지**를 말하고,
그게 거절문이 하는 일이다.

## 파일 이름이 «없어진 반쪽»을 이름 대기를 그만뒀다

`d70dfb3f` + `8fd7d6b7`. 참조 반쪽이 사라졌으므로 파일명이 그것을 안 부른다.
두 번째 커밋은 **rename 이 스테이지에 남긴 옛 경로**를 떨어뜨린 것이다.

## 아키텍처 영향

- walk 모듈에서 **quantity 씨앗 갈래와 매 요청 로드가 사라졌다.**
- `finding_kinds`가 **자기 독자들 옆에 산다**(`server/scripts/support/`). config 경로는 계산된다.
- **거절문이 파일 경로를 이름 대지 않는다** — 두 번 틀린 뒤의 판정이다.

## 그때 남아 있던 것

- **`config/finding_kinds.json`은 옮겨지지 않았다.** 총괄이 그 파일의 기록자이고,
  옮기든 안 옮기든 모듈은 계속 돈다.
- `79ff99f6`이 지운 줄은 **어떤 시험에서도 빨간 적이 없었다** — 닿을 수 없었기 때문.
