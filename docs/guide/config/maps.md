# `maps.json` 세팅 — 웨이퍼 물리 규격/오프셋 프리셋

> **Status:** 🟢 Living | **Last-verified:** 2026-07-28 | **Owner:** Backend / UI-Map
> 상위: [폴더 인덱스](./README.md) · [CONFIG_GUIDE](../CONFIG_GUIDE.md)

<!-- Loader evidence (2026-07-28):
  load: server/main.py:2998 load_maps_config (missing/corrupt -> {"presets": {}})
  write: server/main.py:3007 save_maps_config via POST/DELETE /api/map-presets (whole-file rewrite)
  per-request read: every endpoint calls load_maps_config()
  is_custom: server-set true on API save (main.py:3051); field model: main.py:3017 MapPresetItem
-->

## 1. 언제 이 파일을 만지는가

- **새 물리 규격 프리셋을 등록할 때** (새 웨이퍼 직경·칩 크기·오프셋 조합) — 계획 stage의 `target_map.preset`이 이름으로 참조하므로, 새 stage를 켜기 전에 그 프리셋이 있어야 합니다
- **원칙: 손편집이 아니라 UI/API로 만집니다.** 맵 에디터 UI → `GET/POST/DELETE /api/map-presets`가 이 파일을 읽고 씁니다. 직접 편집은 서버가 내려가 있거나 대량 이관 때만.

> **개념 구분** — `maps.json` 프리셋(재사용 템플릿) ≠ `wafer_map_metadata`(웨이퍼별 실제 격자, DB 행) ≠ align(메타 델타에서 유도). 프리셋만 만들어서는 정렬이 켜지지 않습니다.

## 2. 세팅 절차

**권장 경로 (API/UI):**

1. 맵 에디터 UI의 프리셋 저장, 또는:
   ```bash
   curl -X POST "http://<host>:8080/api/map-presets" -H "Content-Type: application/json" -d '{
     "name": "300mm Standard (12 x 13 mm)",
     "phys_wafer_dia": 300, "phys_chip_x": 12.0, "phys_chip_y": 13.0,
     "phys_offset_x": 0.0, "phys_offset_y": 0.0, "phys_edge_margin": 3.0,
     "rotation": 0, "side": "front"
   }'
   ```
   `preset_key` 미지정 시 `custom_<epoch_ms>`로 생성되고 `is_custom`은 서버가 `true`로 박습니다.

**손편집 경로 (예외):**

1. **스냅샷**: `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. `presets.<key>`에 항목 추가(키 목록은 §5) 후 저장. **API 쓰기와 겹치지 않게** 하십시오 — API는 전체 파일을 재저장하므로 동시 손편집이 덮일 수 있습니다.
3. 반영은 자동(**요청마다 재읽기**).

## 3. 반영 확인

```
GET /api/map-presets
```

응답 `presets`에 새 키가 보이면 반영된 것입니다. 목록이 **통째로 비어 보이면** 파일 손상 신호 — 서버 콘솔의 `[Maps Config] Error loading maps.json` 로그를 확인하십시오(손상 시 조용히 `{"presets": {}}`로 동작).

## 4. 잘못됐을 때

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore maps_<yymmdd>.json.bak --yes
```

요청마다 재읽으므로 즉시 반영. 삭제 실수는 `DELETE /api/map-presets/{key}` 이력이 없으므로 스냅샷 복원이 유일한 길입니다 → [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md).

## 5. 키 참조 (`presets.<preset_key>`)

| 키 | 타입 / 기본값 | 의미 |
|---|---|---|
| `name` | string (필수) | 표시 이름 — 계획 config의 `target_map.preset`이 참조 |
| `phys_wafer_dia` | number, 300.0 | 웨이퍼 직경(mm) |
| `phys_chip_x` / `phys_chip_y` | number | 칩 물리 크기(mm) |
| `phys_offset_x` / `phys_offset_y` | number, 0.0 | 격자 원점 오프셋(mm) |
| `phys_edge_margin` | number, 3.0 | 엣지 마진(mm) |
| `rotation` | int, 0 | 회전 |
| `side` | string, `"front"` | 면 |
| `is_custom` | boolean | **서버가 정합니다** — 손으로 조작할 값이 아님 |
