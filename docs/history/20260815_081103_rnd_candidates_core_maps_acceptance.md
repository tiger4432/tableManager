# R&D Candidates, Core process, Maps acceptance

## 현상

Candidates가 일부 대표값만 보이거나 같은 표시 행을 evidence 수만큼 반복했고, 일부 분석 단위만 Bond 맵을 가졌다. DT/Core layer와 Core STEP/RCP·계측 근거가 비어 있어 브라우저만으로 불량/정상 차이를 추적하기 어려웠다.

## 근본원인

- Candidate 목록·접힘과 Trend metric 선택의 화면 계약이 없었다.
- 맵 렌더가 대표/선택 맵 중심이었고 동일 계층 여러 WF를 배열하는 규칙이 없었다.
- 합성 fixture의 Core 공정과 subject-scoped 공간 데이터가 전 분석 단위를 덮지 않았다.

## 해결

- Candidates를 `Process`/`Measurement` 전수 목록으로 나누고, 완전 동일 비교와 동일 표시 evidence만 닫힌 묶음으로 접었다. 결측 상태와 각 evidence/역마킹 행은 보존한다.
- Trend Table metric 제목 클릭이 해당 차트 한 장과 URL `charts=`를 동기화한다.
- 데이터 있는 맵을 모두 렌더하고 `BONDING → DT → CORE`는 세로, 같은 stage의 WF 맵은 가로로 배열한다.
- SYN-CX 12 WaferLeg 전부에 BOND 1, DT 2, CORE LOGIC/HBM 2맵을 연결했다. Core는 PHOTO/ETCH/CMP/CLN을 포함한 25~27 STEP과 RCP명만 저장하고, 수치는 별도 `measured` 원자 144건으로 분리했다.

## 검증

- 클라이언트 집중 하네스: Investigation 42, Trend 55, Integration 90 assertions 통과.
- 전체 빌드: 7 contracts, gated harness 50/50 green(기존 known-red 5 불변), Vite 93 modules 성공.
- 서버 집중 회귀: 52 passed. fixture 재적재 2회차 `inserted=0`, `deduped=1594`, 공간 변경 0.
- 브라우저 6 defect 대 6 reference: Process는 `ETCH_PATTERN_02`의 excursion RCP가 A 2/15 대 B 0/15이고, Measurement의 `etched_cd=48.8nm`는 A 14/75 대 B 0/75다. 맵은 BOND 12, DT 26, CORE 24로 총 62장 렌더됐다.

## 남은 공백

Process 수치 mechanism binding/DOE 후보는 사용자 판정에 따라 폐기했다. 물리량은 Measurement에서만 비교하며 평균이나 결측 대체값을 만들지 않는다.
