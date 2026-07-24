# 🛠️ CONTRIBUTING — 개발·문서 갱신 규율 (Docs-as-Code)

> **Status:** 🟢 Living | **Last-verified:** 2026-07-24 | **Owner:** Lead / PM
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · SOP: [starting_prompt](../prompts/starting_prompt.md)

이 문서는 AssyManager를 **지속 관리 가능한 상태로 유지**하기 위한 최소한의 규율을 정의합니다. 문서 드리프트(코드는 진화하는데 문서는 과거에 멈추는 현상)를 구조적으로 방지하는 것이 목적입니다.

---

## 1. 단일 진실 원천 (SSOT) 원칙

- 현재 아키텍처의 권위는 **[overview/SYSTEM_OVERVIEW.md](../overview/SYSTEM_OVERVIEW.md)** 하나뿐입니다.
- 다른 문서에 아키텍처를 중복 서술하지 마십시오. SSOT를 링크하고, 자기 서브시스템의 세부만 다루십시오.
- 어떤 문서든 SSOT와 상충하면 **SSOT가 우선**하며, 상충을 발견하면 즉시 SSOT 또는 해당 문서를 정정합니다.

## 2. Docs-as-Code 갱신 규율 (핵심)

코드 변경 시 **같은 커밋에서** 아래를 판단·수행합니다.

| 변경 성격 | 필수 문서 조치 |
|---|---|
| 아키텍처/프로세스 토폴로지 변경 | `overview/SYSTEM_OVERVIEW.md` + 관련 `architecture/*` 갱신 |
| 서브시스템 동작 변경(파서/맵/체인/동기화 등) | 해당 리빙 가이드([DOC_OWNERSHIP](./DOC_OWNERSHIP.md) 참조) 갱신 |
| API 시그니처/엔드포인트 변경 | `architecture/backend.md` + `spec/api_documentation.md` 갱신 |
| CRUD 코어·공용 함수 시그니처 변경 | 전수 Grep 연쇄 갱신 + [data_preservation 규율](../guide/data_preservation_and_signature_change.md) 준수 |
| 모든 주요 변경 | `docs/history/YYYYMMDD_HHMMSS_summary.md` 이력 작성(코드 스니펫 포함) |

> **판단 기준:** "다음 사람이 이 변경을 알아야 하는가?" 예이면 리빙 문서를 고칩니다. 히스토리 기록만으로는 부족합니다 — 히스토리는 append-only 로그일 뿐, 리빙 문서가 현재 상태를 말합니다.

## 3. 문서 헤더 배지 표준

모든 리빙 문서 상단에 다음 배지를 둡니다.

```markdown
> **Status:** 🟢 Living | **Last-verified:** YYYY-MM-DD | **Owner:** <subsystem> | **Source-of-truth:** <code path>
```

- `Status`: 🟢 Living · 🟠 부분 최신 · ⚪ 참고/스냅샷 · 🗄️ Archived
- `Last-verified`: 마지막으로 **코드와 대조 검증한** 날짜(파일 mtime이 아님).
- 문서를 실질적으로 손대면 `Last-verified`를 갱신합니다.

## 4. 히스토리 인덱스 자동화

`docs/history/README.md`는 **자동 생성물**입니다. 직접 편집하지 마십시오.

```bash
python docs/history/gen_index.py          # 갱신
python docs/history/gen_index.py --check   # CI: 갱신 필요 시 종료코드 1
```

새 히스토리 파일을 추가한 뒤 위 명령으로 인덱스를 재생성합니다. 파일명 규격: `YYYYMMDD_HHMMSS_snake_case_summary.md`.

## 5. 낡은 문서 처리

문서가 현실과 상충하게 되면 **삭제하지 말고** `docs/_archive/`로 이관하고 상단에 배지를 답니다.

```markdown
> 🗄️ **SUPERSEDED** by [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) on YYYY-MM-DD. 히스토리 추적용으로만 보존됩니다.
```

## 6. 버전 체계

불연속 `Phase N.x` 번호 대신 [RELEASE_LOG.md](./RELEASE_LOG.md)에 `YYYY-MM-DD | 영역 | 시맨틱 요약`으로 기록합니다.

## 7. 기술적 안전판 (SOP에서 계승)

- **비동기 GC 방지:** PyQt/PySide 콜백은 `lambda`/로컬 클로저 금지 → 반드시 바운드 메서드 연결. ([SOP §3](../prompts/starting_prompt.md))
- **시그니처 변경 전수 분석:** CRUD/공용 함수 반환 구조 변경 시 라우터·워커·테스트 전수 갱신 후 `pytest`.
- **병합 데이터 보존:** collision_merge 시 사용자 오버라이트 보존 + 소스명 계승 + 이중 추적.

## 8. 문서 추가 시 체크리스트

- [ ] 헤더 배지(§3) 포함
- [ ] [docs/README.md](../README.md) 인덱스에 링크 추가
- [ ] [DOC_OWNERSHIP.md](./DOC_OWNERSHIP.md)에 소유 매핑 추가
- [ ] SSOT와 중복 서술 없음(링크로 대체)
