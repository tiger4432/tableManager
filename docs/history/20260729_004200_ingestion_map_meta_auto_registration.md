# 39만 개의 맵 키에 메타 행은 9개였다 — 인제션이 자기 프레임을 등록하기 시작했다

> 커밋 `ab6ac02` · 2026-07-29 00:38 · 도메인 Server(인제션 두 경로 · 신규 `map_meta_registrar`)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 안내: [INGESTION_GUIDE §1.10](../guide/INGESTION_GUIDE.md)
> **동반 항목**: [캐노니컬 맵 키](./20260729_003843_canonical_map_key_by_declared_type.md) · [transfer_log "none"](./20260729_004000_transfer_log_none_declared_untracked.md)

## 배경 — 등록 공백은 에러를 내지 않는다

`wafer_map_metadata`는 맵 정렬의 정본이다. 메타가 없어도 예외는 나지 않는다 — 화면에
"화면기준" 칩으로 조용히 드러나는 **등록 공백**일 뿐이다. 수동 맵 에디터는 push마다 메타
행을 등록한다. 그런데 인제션 쓰기 경로 둘(파일 워처 파이프라인, 체인 인제션 워커)은
**한 번도 등록하지 않았다.** 그 결과 `bonding_map`에 distinct 맵 키 약 39만 개에 대해
메타 행이 9개였다. 자동으로 들어온 맵은 사실상 전부 프레임 없이 열렸다.

## 변경 내용

### 발동 조건은 기존 규칙을 그대로 빌린다

새 모듈 `server/map_meta_registrar.py`가 생겼다. 발동 조건은 두 개다: 테이블이
`map_key_columns`를 **선언**하고, `map_overlay.resolve_binding`으로 좌표 바인딩이
해석될 것(선언 > 유도 — 다른 모든 맵 소비자와 같은 규칙을 import해서 쓴다, 복제 아님).
덕분에 `map_split_registry`처럼 키는 있지만 x/y가 없는 레지스트리형 테이블은 **자연히**
제외된다 — 별도 예외 목록이 필요 없었다.

### 정직한 최소 메타 — 웨이퍼 원을 추측하지 않는다

```python
# server/map_meta_registrar.py — synthesize_grid_meta, 이 커밋 시점
half_diag = math.sqrt(cols * cols + rows * rows) / 2.0
return {
    "grid_cols": cols, "grid_rows": rows,
    "grid_start_x": min_x, "grid_start_y": min_y,   # 0이 아니다 — 아래 참조
    "grid_y_invert": False, "rotation": 0, "side": "front",
    "phys_wafer_dia": max(300, math.ceil(2 * (half_diag + 4))),
    "phys_chip_x": 1, "phys_chip_y": 1,
    "phys_offset_x": 0, "phys_offset_y": 0, "phys_edge_margin": 3,
    "auto_registered": True,
}
```

마스크 판정에는 off 스위치가 없다. 그래서 "마스크 없음"을 **마스크 자신의 어휘로**
표현해야 한다 — 격자의 half-diagonal을 외접하는 지름을 계산해 모든 셀 모서리가 마스크
타원 안에 엄격히 들어오게 하고, 그 결과 맵 전체가 push 가능한 상태로 남는다. 실제 웨이퍼
물리 규격은 **추측하지 않았다**(웨이퍼 원 없음 — 유효 다이를 맵 기반으로 보는 M4 방향).

**이 라운드에서 가장 값진 발견은 `grid_start`였다.** 에디터의 '표준' 선택은 `start=(0,0)`을
쓴다. 그대로 베끼면 자동 등록된 모든 맵이 어긋난다 — 에디터의 그 선택은 **로드된 좌표를
동시에 시프트**하기 때문이다. 인제션 행은 원좌표를 그대로 유지하므로 프레임은 데이터가
시작하는 곳에서 시작해야 한다. 소비자의 로드 경로를 읽고서야 잡혔다.
**UI 기본값을 자동 경로로 옮길 때는, 그 기본값이 UI의 동시 변환 덕에만 성립하는지 확인해야
한다** — 값만 복사하면 변환이 빠진다.

### 절대 덮어쓰지 않는다 · 행당 질의 0회

```python
# server/map_meta_registrar.py — flush, 이 커밋 시점
# 1) 이번 런에서 이미 확인된 키 제외(프로세스 수명 캐시)
candidates = [mid for mid in self.bboxes if (self.table_name, mid) not in _known_present]
# 2) 인덱스 컬럼에 대한 배치 존재 검사 — 행당이 아니라 distinct 키당 1회
bk_of = {mid: f"{crud.clean_str_value(self.table_name)}{sep}{crud.clean_str_value(mid)}"
         for mid in candidates}
for i in range(0, len(bk_list), CHUNK_SIZE):
    for (found_bk,) in db.query(model.business_key_val).filter(
            model.business_key_val.in_(bk_list[i:i + CHUNK_SIZE])).all():
        existing.add(found_bk)
missing = [mid for mid in candidates if bk_of[mid] not in existing]
```

- **부재 전용**: 존재하는 메타 행은 절대 건드리지 않는다. 생성 행은 소스 `auto_map_meta`,
  레이어 우선순위 99(최하위) — 이후 사용자 편집이 항상 이긴다.
- **10M 규율**: 작업 단위(파일 / 체인 트랜잭션 그룹)당 distinct 키 1회 인덱스 조회.
  bbox 누적은 O(행) 정수 비교로 DB를 건드리지 않는다.
- **재귀 차단은 벨트 + 멜빵**: 등록기가 `wafer_map_metadata`를 명시 거부하고, 메타
  테이블 자체가 `map_key_columns`를 선언하지 않는다.
- **실패 격리**: 등록기 예외는 두 writer 모두에서 로깅 후 삼킨다. 데이터는 이미 커밋된
  뒤이므로 인제션은 정상 완료된다.

메타 행은 `crud.apply_batch_updates`(정상 쓰기 경로)로 나가므로 outbox 이벤트가 흐르고,
체인 워커의 미전달 브로드캐스트 스윕이 클라 갱신을 배달한다.

노브는 `ingestion_settings.json`의 `auto_register_map_meta`(기본 ON), 작업 단위 경계에서
한 번 읽는다 — 다음 단위부터 hot, 한 단위 안에서는 일관(D1 스냅샷 규율).

## 아키텍처 영향

맵 메타 등록이 **에디터 전용 행위에서 쓰기 경로의 성질로** 바뀌었다. 종전에는 "사람이
push한 맵만 프레임을 갖는다"가 사실상의 규칙이었고, 그래서 자동 인제션 맵은 정렬 계층에서
2등 시민이었다. 이제 세 쓰기 경로(에디터·파일 워처·체인 워커)가 모두 메타를 남긴다.

동시에 **합성 메타와 사람 메타의 위계가 명시됐다** — `auto_map_meta` 소스가 최하 우선순위를
받으므로, 레이어링 모델이 이미 갖고 있던 "수동이 자동을 이긴다"는 규칙이 그대로 적용된다.
새 기계장치가 아니라 기존 프리미티브의 재사용이다.

## 검증

| 무엇을 | 어떻게 | 결과 |
|---|---|---|
| 신규 테스트 | `test_map_meta_registrar.py` | 12건 |
| 결함 주입 | `grid_start`를 0,0으로 강제 / 부재 전용 필터 제거 | 각각 3건·1건 실패로 검출 |
| 질의 횟수 | 5,000행 / 2키 → 커서 이벤트 계수 | 존재 검사 SELECT **정확히 1회**, 캐시된 2회차는 0회 |
| E2E | 격리 포트·격리 데이터 루트, 라이브 쓰기 0건 | 신규 키 → 메타 자동 생성 → 에디터가 선택 모달 없이 열림 |
| 스위트 | conda `assy_manager` | M3 단독 시점 905, 야간 배치 합산 커밋 시점 944 |

**음성 대조군이 이 검증의 핵심이었다**: 런 도중 노브를 `false`로 바꾸고 새 키를 떨어뜨리자
행은 들어오고 메타는 생기지 않았으며, 에디터에 "No Grid Metadata Detected" 선택 모달이
다시 나타났다 — M3가 없애려는 바로 그 마찰이다. 이게 없으면 "모달이 안 뜬다"는 관측이
기능 덕인지 우연인지 구분되지 않는다.

## 그때 남아 있던 것

- **백필은 하지 않았다.** 이 커밋은 **지금부터 인제션되는 맵**만 덮는다. 기존의 메타 없는
  약 39만 키는 재인제션될 때만 행을 얻는다. 일회성 백필 여부는 M4 결정으로 남아 있었다.
- 등록기는 `directory_watcher.load_ingestion_settings`의 10줄 로컬 사본을 갖고 있다
  (체인 워커에서 watchdog과 레거시 import shim을 끌어오지 않기 위한 의도적 중복, 코드에
  주석으로 남아 있다).
- 알려진-존재 캐시는 "이 런 중 어느 시점에 존재했다"만 주장한다 — 운영자가 런 도중 메타
  행을 하드 삭제하면 프로세스 재시작 전까지 재등록되지 않는다.
- `compose_map_id`는 **같은 커밋 안에서** 7b 캐노니컬로 재라우팅됐다(동반 항목 참조).
  그 전 상태로 커밋됐다면 등록 측이 조회 측과 다른 정체성을 계속 만들었을 것이다.
