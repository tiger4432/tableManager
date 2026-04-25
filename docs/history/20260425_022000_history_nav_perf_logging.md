# 기술 이력: 히스토리 내비게이션 성능 프로파일링 로그 추가

## 1. 문제 현상 (Phenomenon)
- 히스토리 로그 더블 클릭 시 데이터 위치로 점프하는 과정이 사용자 체감상 느리게 느껴짐.
- 어떤 단계(탭 전환, 레이아웃 대기, 서버 조회, 데이터 로딩)에서 병목이 발생하는지 정량적인 파악이 어려움.

## 2. 해결 방안 (Solution)
- `HistoryNavigator`의 4단계 내비게이션 시퀀스 전반에 `time.time()`을 이용한 정밀 타이밍 로그를 삽입함.
- 각 단계의 시작과 종료 시점에 소요 시간(ms)을 표준 출력(stdout)으로 기록하여 실시간 모니터링 가능하게 함.

## 3. 코드 변경 사항 (Code Changes)

### `client/ui/history_logic.py`

```python
# [Step 1] 시퀀스 시작 및 탭 전환 소요 시간 측정
self._ctx["start_time"] = time.time()
# ... 탭 전환 로직 ...
print(f"[Nav] Step 1 (Tab Switch) took {(time.time() - self._ctx['start_time'])*1000:.2f}ms")

# [Step 2] 레이아웃 안정화 대기 시간 측정
print(f"[Nav] Step 2 (Layout & Viewport Ready) took {(time.time() - self._ctx['start_time'])*1000:.2f}ms")

# [Step 3] 서버 디스커버리 API 응답 시간 측정
self._ctx["discovery_start"] = time.time()
# ... 서버 응답 수신 ...
discovery_duration = (time.time() - self._ctx.get("discovery_start", time.time())) * 1000
print(f"[Nav] Step 3 (Server Discovery API) took {discovery_duration:.2f}ms")

# [Step 4] 최종 데이터 페칭 및 시퀀스 총 소요 시간 출력
print(f"[Nav] Step 4 (Data Load & Scroll) took {(time.time() - self._ctx.get('fetch_start', time.time()))*1000:.2f}ms")
print(f">>> [Nav] SUCCESS: Total Navigation took {total_duration:.2f}ms")
```

## 4. 아키텍처 영향 보고 (Architecture Impact)
- **가시성 확보**: 개발 및 운영 중 발생하는 지연의 원인이 네트워크(Step 3)인지, 클라이언트 레이아웃(Step 1, 2)인지, 혹은 데이터 직렬화(Step 4)인지 즉각 판단 가능함.
- **오버헤드 최소화**: 단순 타임스탬프 계산 및 출력으로 런타임 성능에 미치는 영향은 무시할 수 있는 수준임.

## 5. 검증 결과 (Validation)
- 히스토리 클릭 시 터미널에 단계별로 로그가 정상 출력됨을 확인.
- 예시 로그:
  ```
  [Nav] Step 1 (Tab Switch) took 1.50ms
  [Nav] Step 2 (Layout & Viewport Ready) took 102.34ms
  [Nav] Step 3 (Server Discovery API) took 45.12ms
  [Nav] Step 4 (Data Load & Scroll) took 12.89ms
  >>> [Nav] SUCCESS: Total Navigation took 161.85ms
  ```
