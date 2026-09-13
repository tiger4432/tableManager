# 평면이 «패키지»가 된 오후 — 그리고 옮기지 «않은» 이름들

> **커밋:** `4e1b92ac`~`aa77a2fe` (09-13 12:09~14:37)
> **일자:** 2026-09-13 (오후)
> **레인:** 구현자(서버) · 응용(문서)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 무엇이 일어났나

오후의 문장은 **「경계는 «세어서» 긋는다」**이다 — import 방향을 재서 여덟 패키지를 만들고,
고리를 «먼저» 끊고, 그리고 **옮기면 안 되는 이름을 «재서» 남겼다**. 마지막 것이 이 오후에
값을 가장 많이 치른 항목이고, **되돌린 커밋 하나가 그 값이었다.** 착지 커밋 단위로 적는다.

## ① 고리를 «먼저» 끊었다 — 패키지는 그다음 (`4e1b92ac` 12:09 · `49241226` 12:25)

```
4e1b92ac   거절 문장이 «두 독자 아래»로 — `virtual_join/refusal`
49241226   철회 원시연산이 «두 독자 아래»로 — `chain/cell_layer`, 네 모듈 고리가 풀림
```
🔴 **순서가 설계다.** 고리가 있는 채로 패키지를 지으면 «패키지끼리» 고리가 되고, 그때는
「어느 쪽이 위인가」가 파일이 아니라 «디렉토리»의 문제가 되어 훨씬 비싸진다.
🔵 그리고 두 번 다 처방이 같다 — **공통을 «두 독자 아래»로 내린다.** 위로 올리면 그 자리가
다시 양쪽을 알아야 한다.

## ② 경로를 «한 파일»이 정한다 (S-211 ③ `936b5cda` 12:44)

다섯 좌석이 각자 「서버가 어디 있나」를 계산하고 있었고, 이제 한 파일이 답한다.
📌 부류는 상설 구성 기준 ④ 「같은 기능에 두 경로」다 — 다섯이 «갈릴 수» 있었고,
갈린 쪽은 «조용하다».

## ③ 평면 36 이 여덟 패키지가 됐다 (S-211 `aa77a2fe` 14:37, 289 파일)

```
admin/        auth · audit_cache · audit_history · dev_bench · retroactive · schema_drift
chain/        activity · builtins · cell_layer · graph · ingestion_worker · key_gate · replay
enrichment/   analysis · backfill · candidates · config · mapper
ingestion/    activity · checkpoint · file_ingestion_status
ledger/       admin · explorer · trace · trace_router
maps/         alignment_batch_counts · frame_confirmation · preset_routing
runtime/      health · launcher_args · loops · process_supervisor · system_reload
virtual_join/ config · executor · refusal
```
🔵 **접두가 사라지는 것이 요점이다** — `chain_ingestion_worker` 는 `chain/` 안에서
`ingestion_worker` 면 충분하고, 이름이 «자기 집»을 두 번 말하지 않는다.
⚠️ 일반 이름 여섯은 «점 표기»로 부른다(판정 362·363) — `config` 같은 이름은 패키지가 둘이면
같은 낱말이 두 파일을 가리키므로, 부를 때 `enrichment.config` 처럼 «집과 같이» 말한다.

## ④ 🔴 그런데 «옮기면 안 되는 이름»이 있었고, 그것을 되돌린 커밋이 가르쳤다

```
OPERATOR_IMPORT_NAMES      server/parsers/directory_watcher.py :966   — 판정 364
목록의 크기                «열넷»
그중 «최상위 평면 모듈»     «열» — chain_bindings · map_overlay · map_meta_registrar ·
                          map_alignment · dt_frame_transform · dt_map_derivation ·
                          alignment_view_service · event_constants · mapper_sdk · notation_norm
나머지 넷                  `database` 는 «이미 패키지»이고, `pipeline_base`·`html_topology_parser`·
                          `void_sat_format` 은 `parsers/` 밑이라 «삼킬 평면 모듈이 아니었다»
```
🔴 **이 이름들은 소유자의 «라이브 맵퍼»가 import 한다.** 그 파일들은 gitignore 돼 있어
이 저장소가 못 보고, 다른 상자에 있으며, 「사용자 스크립트는 무수정」이 원칙이다.
**패키지가 이름을 하나라도 삼키면 이 저장소가 볼 수 없는 파일이, 닿을 수 없는 기계에서 깨진다.**
🔴 **그리고 그 사실은 «되돌린 커밋»으로 배웠다** — 이동이 한 번 적용됐고, 스위트가 깨졌고,
되돌려졌다. 그 소스의 주석이 자기 오류를 부류로 적는다:
**「«셀 수 없다»고 두 번 썼는데, 그 파일들은 디스크에 있고 「이 파일이 어떤 이름을 import 하나」는
잘 읽힌다. 파일을 «고칠 수 없다»는 것과 «잴 수 없다»는 것은 같지 않다.」**
📌 부류: **「없는 것」과 「내가 안 본 것」을 같은 낱말로 부르면, 안 본 쪽이 없는 것이 된다.**
⚠️ 그리고 마지막 셋은 **게이트가 생긴 «그 순간»에** 잡혔다 — 손으로 센 목록이 줄 앵커 grep 이라
**함수 «안»의 import 를 한 번도 못 봤다**. `event_constants` 는 옮길 집합에 들어 있었고,
게이트가 없었으면 같은 실패가 «두 번» 착지했을 것이다.

## ⑤ 문서가 따라왔다 — 그리고 한 표는 «기계가 못 봤다»

경로 표기 235건과 «맨이름» 표기 267건을 고쳤고, 살아 있는 문서에 옛 이름은 «0»이다.
🔴 **`SERVER_FILE_MAP.md` 만은 기계가 한 줄도 못 잡았다** — 그 표가 이름을 `server/` 없이
«맨이름»으로 적어 두었기 때문이다. 26행을 따로 재서 고쳤고, 나머지 열은 **그 표가 2026-08-28
측정본이라 «애초에 없던 행»**이다(전부 08-30 이후 생겼다 — 제 실측).
📌 부류: **표기를 바꾸면 모집단이 바뀐다** — 같은 스윕이 같은 사실을 두 표에서 «다르게» 본다.
⚠️ 그리고 그 기계적 치환이 부작용 하나를 남겼다: 옆에 «옛 리비전 해시»가 적힌 줄의 경로가
이제 «오늘의 경로»다. `git show <그 해시>:<새 경로>` 는 안 열리고, `git log --follow` 를 써야 한다.
CODE_MAP §0 에 그 주의를 적어 뒀다 — **해시는 「언제」를, 경로는 「어디」를 말하고, 그 둘이 이제
같은 날을 가리키지 않는다.**

## ⑥ ⚠️ 그리고 이 항목이 처음에 «죽은 해시»를 달고 있었다

처음 쓸 때 이 문서는 착지 커밋을 `2992bee2` 로 적었다. 그 커밋은 **14:38 의 amend 로
HEAD 에서 떨어져 나갔고**, 오늘의 것은 `aa77a2fe` 다(같은 14:37, 같은 제목, 같은 rename 36).
```
왜 안 걸렸나   `git log -1 2992bee2` 가 «잘 열린다» — amend 로 버려진 커밋은 객체 저장소에
              한동안 남으므로, 「이 해시가 있나」는 «예»라고 답한다
가르는 검사     git merge-base --is-ancestor <해시> HEAD     -> 2992bee2 «아니오» · aa77a2fe «예»
```
🔴 **「읽힌다」와 「이 역사에 있다」는 다른 질문이고, 앞의 것이 뒤의 것을 통과시킨다.**
📌 부류: 이 저장소가 여러 번 치른 **「대리를 성질로 읽는다」**의 해시 판이다 —
인용하는 해시는 «존재»가 아니라 «조상 여부»로 확인한다.

---
📎 착지 커밋 단위(D-24 지시). 문장마다 해시를 달았고, 「운영」이라 적은 줄은 «없다».
📎 같은 라운드의 문서 착지: CODE_MAP · `SERVER_FILE_MAP.md` · `docs/README.md` ·
`SYSTEM_OVERVIEW.md` 외 서른여덟 · `HARNESS_DISCIPLINE_GUIDE.md`(C-94 접힘, 판정 367).
