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

## 판마다 — 마지막 칸이 착지 뒤

`무리`: 초록 · 알려짐 · 제품 · 제품+환경 · 환경 · 빈칸. `복구`: 사람 복구(킬 없음 = «-»). 쌍둥이는 끝에 `t`.

| 판 | 선언 | 길 | 타입 | 죽임 | 무리 | 복구 | 착지 뒤 |
|---|---|---|---|---|---|---|---|
| g00 | decide expression | delete | string | 껍데기 앞 | 빈칸 | 아니오 | |
| g00t | decide expression | delete | string | - | 환경 | - | |
| g01 | decide record | insert | datetime | 처리됨 뒤 | 초록 | 아니오 | |
| g01t | decide record | insert | datetime | - | 초록 | - | |
| g02 | decide expression | replay | number | 처리됨 앞 | 초록 | 예 | |
| g02t | decide expression | replay | number | - | 초록 | - | |
| g03 | join record | file_replace | datetime | - | 초록 | - | |
| g04 | decide record | edit | number | 쓰기 뒤 | 초록 | 예 | |
| g04t | decide record | edit | number | - | 초록 | - | |
| g05 | mapper board_copy | delete | string | 거두기 뒤 EDIT 앞 | 빈칸 | 아니오 | |
| g06 | join max | delete | datetime | 거두기 뒤 EDIT 앞 | 제품+환경 | 예 | |
| g07 | decide record | r2 | string | - | 초록 | - | |
| g08 | join unique_concat | insert | string | 처리됨 앞 | 초록 | 예 | |
| g09 | mapper board_pick_columns | file_replace | number | 처리됨 뒤 | 초록 | 아니오 | |
| g10 | join name | edit | datetime | 쓰기 뒤 | 초록 | 예 | |
| g11 | join count | r2 | number | 껍데기 앞 | 초록 | 아니오 | |
| g12 | decide expression | replay | datetime | - | 초록 | - | |
| g13 | mapper board_copy | edit | string | 껍데기 앞 | 제품 | 예 | |
| g14 | join min | replay | datetime | 쓰기 뒤 | 초록 | 예 | |
| g15 | decide record | edit | datetime | 처리됨 앞 | 초록 | 예 | |
| g15t | decide record | edit | datetime | - | 초록 | - | |
| g16 | join name | insert | number | - | 초록 | - | |
| g17 | mapper board_pick_columns | replay | datetime | - | 초록 | - | |
| g18 | join record | edit | number | 거두기 뒤 EDIT 앞 | 초록 | 예 | |
| g19 | join max | file_replace | number | 껍데기 앞 | 환경 | 아니오 | |
| g20 | join unique_concat | file_replace | string | 처리됨 뒤 | 초록 | 예 | |
| g21 | decide expression | delete | number | 거두기 뒤 EDIT 앞 | 빈칸 | 아니오 | |
| g21t | decide expression | delete | number | - | 초록 | - | |
| g22 | decide expression | r2 | datetime | 껍데기 앞 | 환경 | 예 | |
| g22t | decide expression | r2 | datetime | - | 초록 | - | |
| g23 | decide expression | file_replace | string | 쓰기 뒤 | 환경 | 예 | |
| g23t | decide expression | file_replace | string | - | 초록 | - | |
| g24 | join min | edit | number | - | 초록 | - | |
| g25 | mapper board_pick_columns | insert | string | 쓰기 뒤 | 초록 | 예 | |
| g26 | join count | delete | datetime | 처리됨 앞 | 초록 | 예 | |
| g27 | mapper board_copy | replay | number | 처리됨 앞 | 초록 | 예 | |
| g28 | join name | replay | string | 처리됨 뒤 | 초록 | 예 | |
| g29 | decide record | file_replace | datetime | 처리됨 앞 | 환경 | 예 | |
| g29t | decide record | file_replace | datetime | - | 환경 | - | |
| g30 | decide expression | insert | datetime | 처리됨 뒤 | 환경 | 예 | |
| g30t | decide expression | insert | datetime | - | 초록 | - | |
| g31 | join count | edit | datetime | 처리됨 뒤 | 초록 | 예 | |
| g32 | join record | insert | string | 쓰기 뒤 | 빈칸 | 아니오 | |
| g33 | mapper board_pick_columns | r2 | datetime | 껍데기 앞 | 제품 | 아니오 | |
| g34 | join max | file_replace | datetime | 쓰기 뒤 | 제품 | 예 | |
| g35 | decide expression | delete | number | 거두기 뒤 EDIT 앞 | 빈칸 | 아니오 | |
| g35t | decide expression | delete | number | - | 초록 | - | |
| g36 | join unique_concat | delete | number | - | 초록 | - | |
| g37 | join unique_concat | r2 | datetime | 껍데기 앞 | 초록 | 아니오 | |
| g38 | join record | delete | number | 처리됨 뒤 | 제품 | 아니오 | |
| g39 | join min | edit | datetime | 거두기 뒤 EDIT 앞 | 제품+환경 | 예 | |
| g40 | join count | replay | datetime | - | 초록 | - | |
| g41 | decide record | delete | string | 쓰기 뒤 | 초록 | 예 | |
| g41t | decide record | delete | string | - | 초록 | - | |
| g42 | mapper board_copy | insert | datetime | - | 초록 | - | |
| g43 | decide record | replay | number | - | 초록 | - | |
| g44 | join unique_concat | edit | string | 껍데기 앞 | 빈칸 | 아니오 | |
| g45 | decide expression | edit | string | 처리됨 뒤 | 초록 | 예 | |
| g45t | decide expression | edit | string | - | 초록 | - | |
| g46 | join name | file_replace | number | 처리됨 앞 | 초록 | 예 | |
| g47 | join name | delete | number | 껍데기 앞 | 초록 | 아니오 | |
| g48 | decide record | file_replace | number | 껍데기 앞 | 빈칸 | 아니오 | |
| g48t | decide record | file_replace | number | - | 환경 | - | |
| g49 | join min | insert | number | 처리됨 뒤 | 초록 | 아니오 | |
| g50 | join max | insert | number | - | 초록 | - | |
| g51 | mapper board_pick_columns | delete | string | 처리됨 앞 | 초록 | 예 | |
| g52 | mapper board_copy | file_replace | string | 쓰기 뒤 | 초록 | 예 | |
| g53 | mapper board_pick_columns | edit | datetime | 거두기 뒤 EDIT 앞 | 빈칸 | 아니오 | |
| g54 | join count | delete | string | 거두기 뒤 EDIT 앞 | 제품+환경 | 예 | |
| g55 | join max | edit | number | 처리됨 앞 | 초록 | 예 | |
| g56 | join max | replay | datetime | 처리됨 뒤 | 초록 | 예 | |
| g57 | join count | insert | number | 쓰기 뒤 | 빈칸 | 아니오 | |
| g58 | join min | delete | datetime | 껍데기 앞 | 빈칸 | 아니오 | |
| g59 | join min | file_replace | number | 처리됨 앞 | 초록 | 예 | |
| g60 | decide record | edit | string | 거두기 뒤 EDIT 앞 | 빈칸 | 아니오 | |
| g60t | decide record | edit | string | - | 초록 | - | |
| g61 | join name | r2 | number | - | 초록 | - | |
| g62 | join unique_concat | insert | number | 쓰기 뒤 | 빈칸 | 아니오 | |
| g63 | join record | delete | string | 껍데기 앞 | 초록 | 아니오 | |
| g64 | join record | delete | number | 처리됨 앞 | 초록 | 예 | |
| g65 | join name | delete | datetime | 거두기 뒤 EDIT 앞 | 제품 | 아니오 | |
| g66 | decide record | r2 | datetime | - | 초록 | - | |
| g67 | mapper board_copy | insert | number | 처리됨 뒤 | 초록 | 아니오 | |
| g68 | join count | file_replace | number | 처리됨 앞 | 초록 | 예 | |
| g69 | join unique_concat | delete | number | 거두기 뒤 EDIT 앞 | 제품 | 예 | |
| g70 | mapper board_copy | r2 | datetime | - | 초록 | - | |
| g71 | join min | r2 | number | - | 초록 | - | |
| g72 | join record | replay | string | 처리됨 뒤 | 초록 | 예 | |
| g73 | join unique_concat | replay | string | - | 초록 | - | |
| g74 | join max | r2 | number | 껍데기 앞 | 초록 | 아니오 | |
| g75 | mapper board_copy | insert | string | - | 초록 | - | |
| g80 | mapper board_copy | delete | string | - | 초록 | - | |
| g81 | join record | delete | datetime | - | 초록 | - | |
| g82 | decide expression | edit | string | - | 초록 | - | |
| g83 | mapper board_copy | delete | string | 처리됨 뒤 | 알려짐 | 아니오 | |
| g83t | mapper board_copy | delete | string | - | 초록 | - | |
| g84 | mapper board_copy | edit | string | 거두기 뒤 EDIT 앞 | 알려짐 | 예 | |
| g84t | mapper board_copy | edit | string | - | 초록 | - | |
| g85 | mapper board_copy | r2 | string | 껍데기 앞 | 알려짐 | 아니오 | |
| g85t | mapper board_copy | r2 | string | - | 초록 | - | |
| g86 | mapper board_pick_columns | delete | string | - | 알려짐 | - | |
| g87 | mapper board_pick_columns | edit | string | - | 알려짐 | - | |
