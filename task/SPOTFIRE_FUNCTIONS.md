# 스팟파이어 함수 목록 — 서버 · 화면 계산기의 첫 판 범위 (클라 10-12 밤, 총괄 0b7d84462 «0»)

**출처** — 소유자 로컬 Spotfire Analyst **14.4.1** 데스크톱의 «Add calculated column» 식 창입니다. 함수 목록과 범주는 그 창의 «Function» 목록과 «Category» 고르기를 그대로 읽었습니다(UI Automation, 저장 없음).
- 전체 **245** 개, 범주 **13** 개입니다.
- 범주별 수: Statistical 66 · Date and Time 33 · Conversion 25 · Math 23 · Text 20 · Operators 19 · OVER 14 · Keywords 13 · Binning 10 · Property 8 · Spatial 7 · Logical 4 · Ranking 3.
- 이 문서의 «뜻» 칸은 스팟파이어 설명을 읽고 제 말로 한 줄로 적은 것입니다. 스팟파이어 글은 옮기지 않았습니다.
- «빈 값» 칸에는 그 설명에 «적힌» 규칙만 적었습니다. 안 적힌 곳은 «설명에 없음»이고, 그 칸은 벡터를 짓기 전에 소유자 스팟파이어에서 재야 합니다.

**첫 판 범위**(총괄 지시): 통계(집계) 전부 · 조건(If · Case) · 비교 · 논리 · 기본 수학. 글자 · 날짜 · 그 밖 범주는 맨 끝에 이름만 적습니다(짓지 않음).

**집계의 두 꼴** — 스팟파이어의 Avg · Sum · Min · Max · Median · Product · MeanDeviation · MedianAbsoluteDeviation 은 인자 수로 뜻이 갈립니다.
```
인자 하나    그 칸의 «모든 행»을 모은다            Avg([Sales])
인자 여럿    «행마다» 그 인자들을 모은다            Avg(2, -3, 4)
```
우리 시험대에서는 «모든 행» 대신 «점 · 칸 안에 든 값들»입니다(afcb79f14 ⑤).

## 1. 통계(집계) — Statistical functions 66 + 다른 범주의 집계

### 1-a. 짓는 것 (이미 걷기 집계 · 시험대에 이름이 있는 일곱 + 가까운 것)

| 이름 | 인자 | 뜻 | 빈 값 |
|---|---|---|---|
| Count | (값?) | 값이 빈 칸이 아닌 수. 인자가 없으면 행 수 | 빈 값은 안 센다 |
| UniqueCount | (값) | 빈 칸이 아닌 서로 다른 값의 수 | 빈 값은 안 센다 |
| Sum | (값) · (a, b, …) | 합 | 설명에 없음 |
| Avg | (값) · (a, b, …) | 산술 평균 | 설명에 없음 |
| Min | (값) · (a, b, …) | 가장 작은 값 | 설명에 없음 |
| Max | (값) · (a, b, …) | 가장 큰 값 | 설명에 없음 |
| Median | (값) · (a, b, …) | 가운데 값 | 설명에 없음 |
| Product | (값) · (a, b, …) | 곱 (범주는 Math) | 설명에 없음 |
| First | (값) | 행의 물리적 순서(정렬 안 함)로 첫 «유효한» 값 | 유효한 값만 본다 |
| Last | (값) | 행의 물리적 순서로 마지막 «유효한» 값 | 유효한 값만 본다 |
| UniqueConcatenate | (값) | 서로 다른 값을 이어 붙인 글 (범주는 Text) | 설명에 없음 |
| MostCommon | (값) | 가장 자주 나온 값 (범주는 Text) | 설명에 없음 |

⚠️ 스팟파이어에는 **Latest 가 없습니다.** 가장 가까운 것은 First · Last 이고, 기준은 «시간»이 아니라 «행의 물리적 순서»입니다. 우리 Latest 는 원자 시각(occurred_at)으로 고르는 «우리 것»이라 이 목록 밖에 따로 적어야 합니다.

### 1-b. 분포 · 산포

| 이름 | 인자 | 뜻 | 빈 값 |
|---|---|---|---|
| StdDev | (값) | 표준편차 | 설명에 없음 |
| Var | (값) | 분산 | 설명에 없음 |
| StdErr | (값) | 표준오차 | 설명에 없음 |
| MeanDeviation | (값) · (a, b, …) | 평균에서 떨어진 정도의 평균(절대) | 설명에 없음 |
| MedianAbsoluteDeviation | (값) · (a, b, …) | 중앙값에서 떨어진 정도의 중앙값(절대) | 설명에 없음 |
| GeometricMean | (값) | 기하 평균 | 음수가 하나라도 있으면 빈 값, 0 이 있으면 0 |
| TrimmedMean | (값, 퍼센트) | 위아래 끝을 반씩 잘라 낸 평균(10 이면 위 5 % · 아래 5 %) | 설명에 없음 |
| WeightedAverage | (무게, 값) | 무게를 곱한 평균 — 첫 인자가 무게 | 설명에 없음 |
| Covariance | (값1, 값2) | 공분산 | 설명에 없음 |
| Range | (값) | 가장 큰 값 − 가장 작은 값 | 설명에 없음 |
| Q1 · Q3 | (값) | 1사분위 · 3사분위 | 설명에 없음 |
| IQR | (값) | Q3 − Q1 | 설명에 없음 |
| P10 · P90 | (값) | 10 · 90 백분위 | 설명에 없음 |
| Percentile | (값, 퍼센트) | 그 퍼센트 백분위 | 설명에 없음 |
| Percent | (값, 퍼센트) | 최솟값에서 (최대 − 최소)의 그 퍼센트만큼 위의 값 | 설명에 없음 |
| NthLargest · NthSmallest | (값, n) | n 번째로 큰 · 작은 값 | n 이 값 수보다 크면 가장 작은 · 큰 값 |
| ValueForMax · ValueForMin | (기준, 값) | 기준이 최대 · 최소인 행의 값 — 같은 최대가 여럿이면 «첫» 행 | 설명에 없음 |
| LastValueForMax · LastValueForMin | (기준, 값) | 위와 같고, 여럿이면 «마지막» 행 | 설명에 없음 |
| L95 · U95 | (값) | 95 % 신뢰구간의 아래 · 위 끝(고정 t 1.959964, 표본 40 이상용) | 설명에 없음 |
| LAV · UAV | (값) | 아래 · 위 인접값 | 설명에 없음 |
| LIF · UIF | (값) | 아래 · 위 안쪽 울타리 Q1 − 1.5·IQR · Q3 + 1.5·IQR | 설명에 없음 |
| LOF · UOF | (값) | 아래 · 위 바깥 울타리 Q1 − 3·IQR · Q3 + 3·IQR | 설명에 없음 |
| Outliers | (값) | 인접값 범위 밖 값의 수 | 설명에 없음 |
| PctOutliers | (값) | 인접값 범위 밖 값의 퍼센트 | 설명에 없음 |
| CountBig | (값?) | Count 와 같고 결과가 긴 정수 | 빈 값은 안 센다 |

### 1-c. 분포 함수 (값 하나를 받는 수학 — 집계 아님)

| 이름 | 인자 | 뜻 | 빈 값 |
|---|---|---|---|
| NormDist · NormInv | (x, 평균?, 표준편차?) | 정규분포 위꼬리 p 값 · 분위수. 생략하면 0, 1 | 설명에 없음 |
| TDist · TInv | (x, 자유도) | t 분포 위꼬리 p 값 · 분위수 | 설명에 없음 |
| ChiDist · ChiInv | (x, 자유도) | 카이제곱 위꼬리 p 값 · 분위수 | 설명에 없음 |
| FDist · FInv | (x, 자유도1, 자유도2) | F 분포 위꼬리 p 값 · 분위수 | 설명에 없음 |

### 1-d. 행 순서에 기대는 것 · 외부 엔진 — 짓지 않음 (이름만)
- Lag(값, 걸음?) · Lead(값, 걸음?) — 불러온 순서로 아래 · 위로 민다(기본 1). 시각 정렬을 안 따른다.
- TERR_Binary · TERR_Boolean · TERR_DateTime · TERR_Integer · TERR_Real · TERR_String · TERR_TimeSpan
- TERRAggregation_Binary · _Boolean · _DateTime · _Integer · _Real · _String · _TimeSpan — 외부 R 엔진(TERR) 호출

## 2. 조건 — Logical functions (If · case)

| 이름 | 꼴 | 뜻 | 빈 값 |
|---|---|---|---|
| If | If(조건, 참일 때, 거짓일 때) | 조건이 참이면 둘째, 거짓이면 셋째. 둘째 · 셋째는 같은 타입 | 둘째 · 셋째는 같은 타입이거나 null 이어야 한다. 둘째 · 셋째는 행의 «일부»만 처리한다(열 · 누적 계산에 영향) |
| case (단순) | case 값 when 비교값 then 결과 … else 결과 end | 값이 비교값과 같은 첫 when 의 결과 | 설명에 없음 |
| case (찾기) | case when 조건 then 결과 … else 결과 end | 참인 첫 when 의 결과. 왼쪽부터 | 설명에 없음 |
| Is Null | 값 Is Null | 값이 비었으면 참 | 그 자체가 빈 값 판정 |
| Is Not Null | 값 Is Not Null | 값이 있으면 참 | 그 자체가 빈 값 판정 |

## 3. 비교 — Operators 의 비교 여덟

| 이름 | 꼴 | 뜻 | 빈 값 |
|---|---|---|---|
| = | a = b | 같다 | 설명에 없음 |
| <> · != | a <> b | 다르다(둘은 같은 뜻) | 설명에 없음 |
| < · <= · > · >= | a < b … | 크기 비교 | 설명에 없음 |
| <=> | a <=> b | 같거나, «둘 다 빈 값»이면 참 | 둘 다 빈 값이면 참 — 빈 값끼리 같다고 보는 유일한 비교 |

## 4. 논리 — Operators 의 논리 넷

| 이름 | 꼴 | 뜻 | 빈 값 |
|---|---|---|---|
| And | a and b | 둘 다 참 | 설명에 없음 |
| Or | a or b | 하나라도 참 | 설명에 없음 |
| Xor | a xor b | 정확히 하나만 참 | 설명에 없음 |
| Not | not a | 뒤집기 | 설명에 없음 |

상수 · 낱말(Keywords): TRUE · FALSE · NULL · IS · CASE 의 WHEN · THEN · ELSE · END · DISTINCT(집계를 서로 다른 값에만 — Avg(distinct [값])) · AS(식에 이름) · OVER · NEST · CROSS(범주 축 짜기).

## 5. 기본 수학 — Math functions 23 + 산술 연산자

| 이름 | 인자 | 뜻 | 빈 값 |
|---|---|---|---|
| + · − · * · / | a + b … | 사칙 | 설명에 없음 |
| % · Mod | a % b · Mod(a, b) | 나머지 | 설명에 없음 |
| ^ · Power | a ^ b · Power(a, b) | 거듭제곱 | 설명에 없음 |
| Abs | (x) | 절댓값 | 설명에 없음 |
| Round | (x, 자릿수) | 자릿수까지 반올림. 자릿수는 정수 부분만 쓰고, 음수면 10 · 100 단위. 0.5 는 크기가 커지는 쪽(−0.5 → −1) | 설명에 없음 |
| Ceiling · Floor | (x) | 올림 · 내림(정수) | 설명에 없음 |
| Sqrt | (x) | 제곱근 | 설명에 없음 |
| Exp | (x) | e 의 x 제곱 | 설명에 없음 |
| Ln · Log10 | (x) | 자연로그 · 상용로그 | 설명에 없음 |
| Log | (x, 밑) | 그 밑의 로그 | 설명에 없음 |
| PI | () | 원주율 | — |
| Sin · Cos · Tan | (x) | 삼각함수(라디안) | 설명에 없음 |
| ASin · ACos · ATan | (x) | 역삼각함수 | 설명에 없음 |
| ATan2 | (y, x) | 두 좌표의 각(−π ~ π) | 설명에 없음 |
| Rand | (씨앗) | 0 ~ 1 난수(씨앗은 상수) | — |
| RandBetween | (아래, 위, 씨앗) | 그 범위의 정수 난수 | — |
| Sum · Product | — | 1-a 에 적음 | — |

## 6. 짓지 않는 범주 — 이름만

- **Binning 10**: AutoBinNumeric · BinByDateTime · BinByEvenDistance · BinByEvenDistribution · BinByEvenIntervals · BinBySpecificLimits · BinByStdDev · BinBySubstring · BinByTimeSpan · FiscalBinByDateTime
- **Conversion 25**: Base64Decode · Base64Encode · Boolean · Currency · Date · DateTime · FirstValidAfter · FromEpochMilliseconds · FromEpochSeconds · Integer · LastValidBefore · LongInteger · ParseDate · ParseDateTime · ParseReal · ParseTime · ParseTimeSpan · Real · SingleReal · SN · String · Time · TimeSpan · ToEpochMilliseconds · ToEpochSeconds
- **Text 20**: ~= · Concatenate · Find · Left · Len · Lower · Mid · MostCommon · NameDecode · NameEncode · Repeat · Right · RXExtract · RXReplace · Split · Substitute · Substring · Trim · UniqueConcatenate · Upper (MostCommon · UniqueConcatenate 는 1-a 에도 적음) · 그리고 Operators 의 & (글 이어 붙이기)
- **Date and Time 33**: DateAdd · DateDiff · DatePart · DateTimeNow · Day · DayOfMonth · DayOfWeek · DayOfYear · Days · FiscalMonth · FiscalQuarter · FiscalYear · Hour · Hours · ISOWeek · ISOYear · Millisecond · Milliseconds · Minute · Minutes · Month · Quarter · Second · Seconds · Today · TotalDays · TotalHours · TotalMilliseconds · TotalMinutes · TotalSeconds · Week · Year · YearAndWeek
- **OVER 14**: All · AllNext · AllPrevious · FirstNode · Intersect · LastNode · LastPeriods · NavigatePeriod · Next · NextPeriod · ParallelPeriod · Parent · Previous · PreviousPeriod
- **Property 8**: $csearch · $esc · $map · BaseRowId · ColumnProperty · DataTableProperty · DocumentProperty · RowId
- **Ranking 3**: DenseRank · Rank · RankReal
- **Spatial 7**: GreatCircleDistance · WKBEnvelopeXCenter · WKBEnvelopeXMax · WKBEnvelopeXMin · WKBEnvelopeYCenter · WKBEnvelopeYMax · WKBEnvelopeYMin

## 7. 스팟파이어에 «없는» 우리 것 (afcb79f14 · 5ad030347)
- **Latest(값)** — 원자 시각으로 가장 늦은 값. 같은 시각에 둘이면 고르지 않는다.
- **Reach(노드)** — 이 행 노드가 그 노드(허브면 구성원 하나라도)에 닿나. 행을 받는 걷기의 aux 판정(found · none · unknown)으로 답한다.
- **타입("키")** — 노드 생성자. wafer("W01", "W02") · die(wafer="W01", x=3, y=5)
- **[이름 · 걸음.이름]** — 값 참조. 대괄호 안에 노드 이름을 쓰지 않는다.

## 8. 빈 값 — 설명에 «없는» 칸
소유자 스팟파이어에서 재는 길은 닫혔습니다(총괄 10-13 — 웹 보기의 식 단추가 소유자 데스크톱 창을 엶. 웹 보기는 보기 · 간격 재기에만).
- 스팟파이어 온라인 설명서(최신판 함수 쪽, 10-13 읽음 · 7.0.1 통계 정의)가 정하는 칸은 contracts/expression/vectors.json 의 vectors 에 근거(basis · cite)와 함께 있습니다.
- 설명서도 정하지 않거나 두 쪽이 엇갈리는 칸은 같은 파일의 unsettled 에 «무엇이 열렸나 · 왜»로 있습니다 — 채점하지 않고, 정해지면 vectors 로 옮깁니다.
