# 체인 계약판 «받기» 열 — 기준 판 (응용 C, 2026-10-22)

지시 78eec1ec1 게이트 [C]. 도구 `server/tests/contract_board/` (`BOARD_COLUMN=fetch`), 버리는 DB 에서 판 하나씩.
기준 = main `78eec1ec1` (받기 좌석 착지 전). 「착지 뒤」 칸은 B 착지 뒤 같은 판으로 채운다.

판정 칸: 끝 값(오라클) · 껍데기 · 같은 키 · 고아 층 · 치워 둔 것 · 타입 — 쓰기 열과 같음. 더해 «읽은 자리»:
R = `rule_run.run_rule` 안에서 판 표를 읽은 SELECT 수, W = `hold_commit` 쥔 동안 대상 표 말고 읽은 수.
둘 다 0 이어야 초록 (총괄 10-22). 맵퍼 자신의 `sql()` 판(own sql)은 R 이 남고 «reads outside the fetch» 줄로 판정.
group_by 의 끝 값 = 그 키의 행 «전체»로 센 수 (소유자 10-22 넓힘 승인 — 기준에서 빨강, 착지 뒤 초록).

## 요약 — 판정 낱말별 판 수

| 낱말 | 판 |
|---|---|
| read in the run | 36 |
| oracle | 6 |
| GREEN | 3 |
| outbox failed | 2 |
| no «reads outside the fetch» line | 1 |

## 기준에서 본 것

- ③b(g01, 맵 교체 · 맵 안 편집): 끝 값은 초록 — `57a786ae3` 이 맵 전체를 맵퍼 호출 «안»에서 읽는다(R 2: 씨앗 1 + 편집 1). 빨강은 «읽은 자리» 하나.
- R 은 판 전체(씨앗 포함)를 센다. 그래서 R2 판도 씨앗 때 읽은 R 1 로 빨강이다.
- group_by 6 판의 끝 값 빨강: 키 안의 한 행만 건네져 n 이 그 행 수로 쓰인다(예: 편집 뒤 M2 n=1). 초록 셋은 맵 M2 가 빈 판(재지 않음) · 리플레이(전부 건넴) · R2(전부 거둠).
- **제품 빨강 둘(g04 · g13)** — 맵 교체 · 잡 규칙에서 맵 M2 행을 «전부» 지우면 그룹이 실패한다: 지워진 행들이 맵 칸(m) 없이 맵퍼에 건네져, 맵퍼가 낸 표에 m 이 없다는 `MapperContractError` (outbox FAILED 1). 한 행만 지우면(g03 · g12) 맵의 남은 행이 같이 건네져 안 터진다. 끝 값은 지운 행 거두기가 맞춘다.
- W 는 46 판 모두 0. 다음 쪽(more())은 조인이 왼쪽 행 1,000 마다 내는데(`keyset_scan.pages`), 이 판들은 6 행이라 다음 쪽이 안 생긴다. 생겨도 조인의 다음 쪽은 한 번 읽어 둔 답을 자르기만 해 판 표를 안 읽는다. 그래서 W 는 빨강→초록 칸이 아니라 «0 을 지키는» 칸이다.
- 파일 교체 판 10 개(g06 · g07 · g15 · g16 · g24 · g25 · g33 · g34 · g42 · g43)는 씨앗을 «파일»로 넣어 다시 돌린 값이다. 처음 판은 씨앗을 사용자 층으로 넣어, 파일이 K1 값도 K4 의 맵도 못 바꿨다(와처 «changed 0» · 떠난 맵 판은 «unchanged 3»).

## 판마다

| 판 | 꼴 | 경로 | 받기 대상 | 기준 | 읽은 수 | 착지 뒤 |
|---|---|---|---|---|---|---|
| g00 | map_replace | insert | map | RED: read in the run (R 2) | R 2 · W 0 · D 19 | |
| g01 | map_replace | edit | map | RED: read in the run (R 2) | R 2 · W 0 · D 20 | |
| g02 | map_replace | edit | left map/key | RED: read in the run (R 2) | R 2 · W 0 · D 21 | |
| g03 | map_replace | delete | map | RED: read in the run (R 2) | R 2 · W 0 · D 17 | |
| g04 | map_replace | delete | left map/key | RED: outbox failed, read in the run (R 2) | R 2 · W 0 · D 17 | |
| g05 | map_replace | replay | map | RED: read in the run (R 4) | R 4 · W 0 · D 24 | |
| g06 | map_replace | file_replace | map | RED: read in the run (R 3) | R 3 · W 0 · D 19 | |
| g07 | map_replace | file_replace | left map/key | RED: read in the run (R 3) | R 3 · W 0 · D 19 | |
| g08 | map_replace | r2 | map | RED: read in the run (R 1) | R 1 · W 0 · D 32 | |
| g09 | job | insert | job | RED: read in the run (R 2) | R 2 · W 0 · D 19 | |
| g10 | job | edit | job | RED: read in the run (R 2) | R 2 · W 0 · D 20 | |
| g11 | job | edit | left map/key | RED: read in the run (R 2) | R 2 · W 0 · D 21 | |
| g12 | job | delete | job | RED: read in the run (R 2) | R 2 · W 0 · D 17 | |
| g13 | job | delete | left map/key | RED: outbox failed, read in the run (R 2) | R 2 · W 0 · D 17 | |
| g14 | job | replay | job | RED: read in the run (R 5) | R 5 · W 0 · D 26 | |
| g15 | job | file_replace | job | RED: read in the run (R 3) | R 3 · W 0 · D 19 | |
| g16 | job | file_replace | left map/key | RED: read in the run (R 3) | R 3 · W 0 · D 19 | |
| g17 | job | r2 | job | RED: read in the run (R 1) | R 1 · W 0 · D 32 | |
| g18 | group_by | insert | job | RED: oracle | R 0 · W 0 · D 19 | |
| g19 | group_by | edit | job | RED: oracle | R 0 · W 0 · D 20 | |
| g20 | group_by | edit | left map/key | RED: oracle | R 0 · W 0 · D 21 | |
| g21 | group_by | delete | job | RED: oracle | R 0 · W 0 · D 17 | |
| g22 | group_by | delete | left map/key | GREEN | R 0 · W 0 · D 17 | |
| g23 | group_by | replay | job | GREEN | R 0 · W 0 · D 19 | |
| g24 | group_by | file_replace | job | RED: oracle | R 0 · W 0 · D 19 | |
| g25 | group_by | file_replace | left map/key | RED: oracle | R 0 · W 0 · D 19 | |
| g26 | group_by | r2 | job | GREEN | R 0 · W 0 · D 27 | |
| g27 | join | insert | value table | RED: read in the run (R 7) | R 7 · W 0 · D 26 | |
| g28 | join | edit | value table | RED: read in the run (R 8) | R 8 · W 0 · D 28 | |
| g29 | join | edit | left map/key | RED: read in the run (R 8) | R 8 · W 0 · D 29 | |
| g30 | join | delete | value table | RED: read in the run (R 5) | R 5 · W 0 · D 25 | |
| g31 | join | delete | left map/key | RED: read in the run (R 5) | R 5 · W 0 · D 25 | |
| g32 | join | replay | value table | RED: read in the run (R 14) | R 14 · W 0 · D 31 | |
| g33 | join | file_replace | value table | RED: read in the run (R 11) | R 11 · W 0 · D 27 | |
| g34 | join | file_replace | left map/key | RED: read in the run (R 11) | R 11 · W 0 · D 27 | |
| g35 | join | r2 | value table | RED: read in the run (R 5) | R 5 · W 0 · D 37 | |
| g36 | decide | insert | map | RED: read in the run (R 2) | R 2 · W 0 · D 21 | |
| g37 | decide | edit | map | RED: read in the run (R 2) | R 2 · W 0 · D 21 | |
| g38 | decide | edit | left map/key | RED: read in the run (R 2) | R 2 · W 0 · D 23 | |
| g39 | decide | delete | map | RED: read in the run (R 2) | R 2 · W 0 · D 19 | |
| g40 | decide | delete | left map/key | RED: read in the run (R 2) | R 2 · W 0 · D 18 | |
| g41 | decide | replay | map | RED: read in the run (R 4) | R 4 · W 0 · D 24 | |
| g42 | decide | file_replace | map | RED: read in the run (R 3) | R 3 · W 0 · D 21 | |
| g43 | decide | file_replace | left map/key | RED: read in the run (R 3) | R 3 · W 0 · D 22 | |
| g44 | decide | r2 | map | RED: read in the run (R 1) | R 1 · W 0 · D 28 | |
| g45 | own sql | edit | map | RED: no «reads outside the fetch» line | R 7 · W 0 · D 20 | |
