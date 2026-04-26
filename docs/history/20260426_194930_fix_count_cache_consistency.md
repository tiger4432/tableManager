# 🏁 2026-04-26 19:49:30 - 서버 카운트 캐시 정합성 해결 및 검색 캐시 복구

데이터 추가/삭제 시 전체 행 개수(Total Count)가 즉각 반영되지 않던 버그를 해결하고, 조회 성능 최적화를 위해 검색 조건별 캐시 로직을 복구하였습니다.

## 🛠️ 주요 변경 사항

### 1. 통합 캐시 무효화 함수 도입 (Server)
테이블과 관련된 모든 캐시 키를 한 번에 제거하는 유틸리티를 도입하여 무효화 누락을 원천 차단했습니다.

```python
# [server/main.py]
def invalidate_table_cache(table_name: str):
    all_keys = list(TABLE_COUNT_CACHE.keys())
    targets = [k for k in all_keys if k == table_name or k.startswith(f"{table_name}_")]
    for k in targets:
        TABLE_COUNT_CACHE.pop(k, None)
```

### 2. 검색어별 카운트 캐시 복구 (Server)
`get_table_data` 엔드포인트에서 검색어(`q`)와 컬럼(`cols`)이 포함된 경우에도 캐시가 작동하도록 복구하였습니다.

- **캐시 키**: `{table_name}_total_count_{q}_{cols}`
- **TTL**: 5.0초 (사용자 요청 반영)

### 3. 내보내기(Export) 정확성 강화
`export_table_csv` 엔드포인트에서는 데이터의 정확한 행 개수 파악이 최우선이므로 캐시를 사용하지 않고 항상 실시간 DB 카운트를 수행하도록 변경했습니다.

---

## 📈 아키텍처 영향 보고
- **정합성**: 이제 데이터 업서트, 삭제, 실시간 인제션 발생 시 즉시 관련 캐시가 파괴되어 클라이언트가 항상 최신 개수를 볼 수 있습니다.
- **성능**: 검색 조건이 포함된 스크롤 시 5초간 캐시가 유지되어 DB 부하를 줄였습니다.
- **가독성**: 중구난방이던 캐시 키 명명 규칙을 `{table_name}_total_count...`로 통일하였습니다.
