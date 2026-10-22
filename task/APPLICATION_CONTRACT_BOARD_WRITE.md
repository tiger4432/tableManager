# 체인 계약판 — «쓰기» 열 기준 (응용 C, 10-21 → 10-22)

지시: 09f58844f(소유자 접기 순서 ㄱ 쓰기) · 총괄 «기준 판은 B 의 쓰기 합치기 착지 전에, main 위에서» · 게이트 확정 0cc712d59.
기준: main 2af64170d(코드는 a775cb669 전), 버리는 DB `assy_c_board_1021`(돌린 뒤 지움). 박스 수 — 운영 주장이 아니다.

## 결론

| 무리 | 수 | 뜻 |
|---|---|---|
| 초록 | 68 | |
| 알려짐 | 5 | 알려진 빨강 다섯 — 5/5 빨강(기준 조건) |
| 제품 | 6 | 같은 가족이 생성 사례에서도 빨강 |
| 제품+환경 | 3 | 같은 가족, 그 판에 시작 전 죽음도 섞임 |
| 환경 | 8 | 슬롯 자식이 «DLL load failed while importing _psycopg» 로 시작 전에 죽고 줄이 치워짐 — 총괄 판정: «돌려줌»이어야 함 |
| 빈칸 | 12 | 그 모양에 그 순간이 없음(제품 빨강 아님) |
| 합 | 102 | 채점 스크립트 탓 빨강 0(다시 돌려 덮음) |

사람 복구 — 킬 판 62: 예 35 · 아니오 27. **게이트: 쓰기 합치기 뒤 «초록 · 예» 24 가 «아니오»로**, 알려짐 · 제품 9 가 초록으로, 나머지 칸(행 · 층 · 사건)은 그대로.

## 판 만드는 법 (요약)

- 축: 통합 선언 스켈레톤의 선택 잎(enabled 뺌) + 길(insert · edit · delete · replay · file_replace · r2) + 칸 타입(string · number · datetime) + 죽이는 자리(아래)
- 짝 전부(greedy all-pairs) 88 사례 — 로더가 이름 대어 거절하는 짝 5 는 `--check` 로만. 킬 판 중 decide · 알려짐은 «손 안 댄 쌍둥이»와도 견줌
- 표 넷: bd_src(k,m,v) · bd_val(k,m,w) · bd_dst(k,m,v,w,wn) · bd_dec(m,v,n). 오라클: 맵퍼 dst == src, 조인 칸 == 값 행(fn), decide 는 쌍둥이
- 죽이는 자리(`sitecustomize` 훅, 씨앗 뒤에만 켜짐): 쓰기 뒤 = `_apply_batch_updates_once` 뒤(체인 쓰기) · 거두기 뒤 EDIT 앞 = `_withdraw_and_tell` 의 `stage_collapsed_event` 앞 · 껍데기 앞 = `cell_layer.delete_shells` 앞 · 처리됨 앞 = `mark_processed(SUCCESS)` 앞 · 처리됨 뒤 = `_retract_deleted_rows` 앞
- 죽은 뒤: 가라앉힘 → 치워 둔 사건이 있으면 운영자 명령 `outbox_triage.py --rerun-set-aside --tables <표> --apply` → «사람 복구 = 예»
- 도구는 세션 스크래치(저장소 밖): `board_gen.py --run <사례…>` · `--compare a b` · `final.py`. 착지 뒤 같은 사례 번호로 다시 돌려 아래 표의 마지막 칸만 채운다

## 제품 빨강 — 무엇이 남나

| 판 | 꼴 |
|---|---|
| g65 · g69 (+ g06 · g39 · g54) | 거두기 뒤 EDIT 앞에서 죽음 → 지운(또는 키를 바꾼) 값 행의 조인 칸이 남음 |
| g38 | 처리됨 뒤(f4k) — K5 칸이 남음, 치워 둔 것 없음 = 운영자가 볼 단서 없음 |
| g34 | 쓰기 뒤 + 맵 교체 — 파일이 뺀 K3 칸이 남음. 치워 둔 줄을 다시 돌려도 지운 행 거두기는 다시 안 돎 |
| g13 | 껍데기 앞(체인 편집 경로, R2 아님) — 빈 행 하나 남음 |
| g33 | R2 껍데기 앞 + 원천 표시 잃은 맵퍼 — 빈 행 넷 |

## 착지 뒤 (10-22) — ① 2223b0ac2 · ② db9df5374

① = B 의 쓰기 합치기 + g26 · g31 · R2 고침(impl-b-writefold 2223b0ac2), 새 판 도구, 버리는 DB `assy_c_board_1022b`(돌린 뒤 지움). 69 판(쌍둥이 포함). ② = 합치기 첫 판 db9df5374 전체 판 — 슬롯 죽음이 «제자리에서 다시 돎»이던 때라 지금 코드와 다름, ①에 없는 33 판만 그것으로 채움. 박스 수 — 운영 주장이 아니다.

| 게이트 (총괄 10-22) | ① 결과 |
|---|---|
| 알려진 빨강 다섯 초록 | 5/5 |
| 제품 빨강 여섯 초록 | 6/6 |
| g09 초록 | 초록 |
| 같은 꼴(죽임 × delete · file_replace) | 28 판 중 21 판이 죽임에 닿음, 닿은 것 21/21 초록 |
| 같은 꼴(죽임 × edit) | 13 판 중 10 판이 죽임에 닿음, 닿은 것 10/10 초록 |
| 부분 쓰기 없음 | 닿은 킬 판 40 중 부분 쓰기 0 — 없음 |
| 「죽임 자리 × 길」 칸 | 21 칸 중 20 칸을 ①이 덮음 — 못 덮은 칸: before_shells × file_replace(g19 · g48) |

- 「사람 복구 = 예」는 킬 판에서 설계다(소유자 «슬롯 죽음은 다 원래대로 실패») — 게이트에서 뺌. 킬 판은 «치워 둠 → `outbox_triage --rerun-set-aside` → 끝 값이 쌍둥이와 같음»이면 초록.
- 부분 쓰기 칸 = «다시 돌리기 전 대상 표 = 씨앗 직후 대상 표 − 치워 두기가 설계대로 거둔 삭제 키의 행»(총괄 승인). 그 행 수는 판 줄 «target rows the set-aside took back N»에 찍힘.
- ① 빨강: 없음. 빈칸(안 닿음): g00 · g05 · g19 · g21 · g35 · g44 · g48 · g53 · g58 · g60.
- 판 도구가 바뀐 것: 쌍둥이도 치워 둔 것을 다시 돌림(박스 DLL 죽음, 최대 세 번 · 매 번 새로 치워진 것만) · «치워 둔 채» 빨강은 끝까지 다시 안 돈 것만 · 쌍둥이 견주기에서 행마다 층 이름의 행 id 를 접음(g83 · g84 가 그것만 달랐음) · R2 명령이 죽으면 운영자 복구대로 심박 60 초 뒤 취소 문(`request_cancel`)으로 그 런의 잠금을 풀고 같은 명령을 다시 돌림(번호로 프로세스를 죽이는 `stop_retroactive.py` 는 안 씀).

## 판마다 — 마지막 칸이 착지 뒤

`무리`: 초록 · 알려짐 · 제품 · 제품+환경 · 환경 · 빈칸. `복구`: 사람 복구(킬 없음 = «-»). 쌍둥이는 끝에 `t`.

| 판 | 선언 | 길 | 타입 | 죽임 | 무리 | 복구 | 착지 뒤 |
|---|---|---|---|---|---|---|---|
| g00 | decide expression | delete | string | 껍데기 앞 | 빈칸 | 아니오 | 빈칸(안 닿음) ① |
| g00t | decide expression | delete | string | - | 환경 | - | 초록 ① |
| g01 | decide record | insert | datetime | 처리됨 뒤 | 초록 | 아니오 | 초록 ① |
| g01t | decide record | insert | datetime | - | 초록 | - | 초록 ① |
| g02 | decide expression | replay | number | 처리됨 앞 | 초록 | 예 | 초록 ① |
| g02t | decide expression | replay | number | - | 초록 | - | 초록 ① |
| g03 | join record | file_replace | datetime | - | 초록 | - | 초록 ② |
| g04 | decide record | edit | number | 쓰기 뒤 | 초록 | 예 | 초록 ① |
| g04t | decide record | edit | number | - | 초록 | - | 초록 ① |
| g05 | mapper board_copy | delete | string | 거두기 뒤 EDIT 앞 | 빈칸 | 아니오 | 빈칸(안 닿음) ① |
| g06 | join max | delete | datetime | 거두기 뒤 EDIT 앞 | 제품+환경 | 예 | 초록 ① |
| g07 | decide record | r2 | string | - | 초록 | - | 초록 ② |
| g08 | join unique_concat | insert | string | 처리됨 앞 | 초록 | 예 | 초록 ① |
| g09 | mapper board_pick_columns | file_replace | number | 처리됨 뒤 | 초록 | 아니오 | 초록 ① |
| g10 | join name | edit | datetime | 쓰기 뒤 | 초록 | 예 | 초록 ① |
| g11 | join count | r2 | number | 껍데기 앞 | 초록 | 아니오 | 초록 ② |
| g12 | decide expression | replay | datetime | - | 초록 | - | 초록 ② |
| g13 | mapper board_copy | edit | string | 껍데기 앞 | 제품 | 예 | 초록 ① |
| g14 | join min | replay | datetime | 쓰기 뒤 | 초록 | 예 | 초록 ① |
| g15 | decide record | edit | datetime | 처리됨 앞 | 초록 | 예 | 초록 ① |
| g15t | decide record | edit | datetime | - | 초록 | - | 초록 ① |
| g16 | join name | insert | number | - | 초록 | - | 초록 ② |
| g17 | mapper board_pick_columns | replay | datetime | - | 초록 | - | 초록 ② |
| g18 | join record | edit | number | 거두기 뒤 EDIT 앞 | 초록 | 예 | 초록 ① |
| g19 | join max | file_replace | number | 껍데기 앞 | 환경 | 아니오 | 빈칸(안 닿음) ① |
| g20 | join unique_concat | file_replace | string | 처리됨 뒤 | 초록 | 예 | 초록 ① |
| g21 | decide expression | delete | number | 거두기 뒤 EDIT 앞 | 빈칸 | 아니오 | 빈칸(안 닿음) ① |
| g21t | decide expression | delete | number | - | 초록 | - | 초록 ① |
| g22 | decide expression | r2 | datetime | 껍데기 앞 | 환경 | 예 | 초록 ① |
| g22t | decide expression | r2 | datetime | - | 초록 | - | 초록 ① |
| g23 | decide expression | file_replace | string | 쓰기 뒤 | 환경 | 예 | 초록 ① |
| g23t | decide expression | file_replace | string | - | 초록 | - | 초록 ① |
| g24 | join min | edit | number | - | 초록 | - | 초록 ② |
| g25 | mapper board_pick_columns | insert | string | 쓰기 뒤 | 초록 | 예 | 초록 ① |
| g26 | join count | delete | datetime | 처리됨 앞 | 초록 | 예 | 초록 ① |
| g27 | mapper board_copy | replay | number | 처리됨 앞 | 초록 | 예 | 초록 ② |
| g28 | join name | replay | string | 처리됨 뒤 | 초록 | 예 | 초록 ① |
| g29 | decide record | file_replace | datetime | 처리됨 앞 | 환경 | 예 | 초록 ① |
| g29t | decide record | file_replace | datetime | - | 환경 | - | 초록 ① |
| g30 | decide expression | insert | datetime | 처리됨 뒤 | 환경 | 예 | 초록 ② |
| g30t | decide expression | insert | datetime | - | 초록 | - | 초록 ② |
| g31 | join count | edit | datetime | 처리됨 뒤 | 초록 | 예 | 초록 ① |
| g32 | join record | insert | string | 쓰기 뒤 | 빈칸 | 아니오 | 빈칸(안 닿음) ② |
| g33 | mapper board_pick_columns | r2 | datetime | 껍데기 앞 | 제품 | 아니오 | 초록 ① |
| g34 | join max | file_replace | datetime | 쓰기 뒤 | 제품 | 예 | 초록 ① |
| g35 | decide expression | delete | number | 거두기 뒤 EDIT 앞 | 빈칸 | 아니오 | 빈칸(안 닿음) ① |
| g35t | decide expression | delete | number | - | 초록 | - | 초록 ① |
| g36 | join unique_concat | delete | number | - | 초록 | - | 초록 ② |
| g37 | join unique_concat | r2 | datetime | 껍데기 앞 | 초록 | 아니오 | 초록 ② |
| g38 | join record | delete | number | 처리됨 뒤 | 제품 | 아니오 | 초록 ① |
| g39 | join min | edit | datetime | 거두기 뒤 EDIT 앞 | 제품+환경 | 예 | 초록 ① |
| g40 | join count | replay | datetime | - | 초록 | - | 초록 ② |
| g41 | decide record | delete | string | 쓰기 뒤 | 초록 | 예 | 초록 ① |
| g41t | decide record | delete | string | - | 초록 | - | 초록 ① |
| g42 | mapper board_copy | insert | datetime | - | 초록 | - | 초록 ② |
| g43 | decide record | replay | number | - | 초록 | - | 초록 ② |
| g44 | join unique_concat | edit | string | 껍데기 앞 | 빈칸 | 아니오 | 빈칸(안 닿음) ① |
| g45 | decide expression | edit | string | 처리됨 뒤 | 초록 | 예 | 초록 ① |
| g45t | decide expression | edit | string | - | 초록 | - | 초록 ① |
| g46 | join name | file_replace | number | 처리됨 앞 | 초록 | 예 | 초록 ① |
| g47 | join name | delete | number | 껍데기 앞 | 초록 | 아니오 | 초록 ① |
| g48 | decide record | file_replace | number | 껍데기 앞 | 빈칸 | 아니오 | 빈칸(안 닿음) ① |
| g48t | decide record | file_replace | number | - | 환경 | - | 초록 ① |
| g49 | join min | insert | number | 처리됨 뒤 | 초록 | 아니오 | 초록 ② |
| g50 | join max | insert | number | - | 초록 | - | 초록 ② |
| g51 | mapper board_pick_columns | delete | string | 처리됨 앞 | 초록 | 예 | 초록 ① |
| g52 | mapper board_copy | file_replace | string | 쓰기 뒤 | 초록 | 예 | 초록 ① |
| g53 | mapper board_pick_columns | edit | datetime | 거두기 뒤 EDIT 앞 | 빈칸 | 아니오 | 빈칸(안 닿음) ① |
| g54 | join count | delete | string | 거두기 뒤 EDIT 앞 | 제품+환경 | 예 | 초록 ① |
| g55 | join max | edit | number | 처리됨 앞 | 초록 | 예 | 초록 ① |
| g56 | join max | replay | datetime | 처리됨 뒤 | 초록 | 예 | 초록 ② |
| g57 | join count | insert | number | 쓰기 뒤 | 빈칸 | 아니오 | 빈칸(안 닿음) ② |
| g58 | join min | delete | datetime | 껍데기 앞 | 빈칸 | 아니오 | 빈칸(안 닿음) ① |
| g59 | join min | file_replace | number | 처리됨 앞 | 초록 | 예 | 초록 ① |
| g60 | decide record | edit | string | 거두기 뒤 EDIT 앞 | 빈칸 | 아니오 | 빈칸(안 닿음) ① |
| g60t | decide record | edit | string | - | 초록 | - | 초록 ① |
| g61 | join name | r2 | number | - | 초록 | - | 초록 ② |
| g62 | join unique_concat | insert | number | 쓰기 뒤 | 빈칸 | 아니오 | 빈칸(안 닿음) ② |
| g63 | join record | delete | string | 껍데기 앞 | 초록 | 아니오 | 초록 ① |
| g64 | join record | delete | number | 처리됨 앞 | 초록 | 예 | 초록 ① |
| g65 | join name | delete | datetime | 거두기 뒤 EDIT 앞 | 제품 | 아니오 | 초록 ① |
| g66 | decide record | r2 | datetime | - | 초록 | - | 초록 ② |
| g67 | mapper board_copy | insert | number | 처리됨 뒤 | 초록 | 아니오 | 초록 ② |
| g68 | join count | file_replace | number | 처리됨 앞 | 초록 | 예 | 초록 ① |
| g69 | join unique_concat | delete | number | 거두기 뒤 EDIT 앞 | 제품 | 예 | 초록 ① |
| g70 | mapper board_copy | r2 | datetime | - | 초록 | - | 초록 ② |
| g71 | join min | r2 | number | - | 초록 | - | 초록 ② |
| g72 | join record | replay | string | 처리됨 뒤 | 초록 | 예 | 초록 ② |
| g73 | join unique_concat | replay | string | - | 초록 | - | 초록 ② |
| g74 | join max | r2 | number | 껍데기 앞 | 초록 | 아니오 | 초록 ② |
| g75 | mapper board_copy | insert | string | - | 초록 | - | 초록 ② |
| g80 | mapper board_copy | delete | string | - | 초록 | - | 초록 ② |
| g81 | join record | delete | datetime | - | 초록 | - | 초록 ② |
| g82 | decide expression | edit | string | - | 초록 | - | 초록 ② |
| g83 | mapper board_copy | delete | string | 처리됨 뒤 | 알려짐 | 아니오 | 초록 ① |
| g83t | mapper board_copy | delete | string | - | 초록 | - | 초록 ① |
| g84 | mapper board_copy | edit | string | 거두기 뒤 EDIT 앞 | 알려짐 | 예 | 초록 ① |
| g84t | mapper board_copy | edit | string | - | 초록 | - | 초록 ① |
| g85 | mapper board_copy | r2 | string | 껍데기 앞 | 알려짐 | 아니오 | 초록 ① |
| g85t | mapper board_copy | r2 | string | - | 초록 | - | 초록 ① |
| g86 | mapper board_pick_columns | delete | string | - | 알려짐 | - | 초록 ① |
| g87 | mapper board_pick_columns | edit | string | - | 알려짐 | - | 초록 ① |
