# 2026-07-17 어드민 대시보드 강제 전체화면 확장 버그 및 백엔드 정적 파일 캐싱 개선

## 1. 개요 및 동기
* **현상 및 원인**: 
  1. 인라인 편집 단추 클릭 시, 모나코 코드 에디터의 부모 뷰포트 레이아웃 크기는 `position: fixed`로 화면 전체를 메웠으나, 자식 블록 요소(`.detail-block`, `.detail-block-body`, `#monaco-editor-container`)들이 부모의 확장 높이를 100% 온전히 상속받지 못해 에디터 자체 높이와 버튼이 좁은 영역에 그대로 갇혀서 렌더링되던 결함이 있었습니다.
  2. 브라우저 정적 캐싱으로 인해 새로고침을 거치더라도 이전 버전의 프론트엔드 코드 에셋(js, html 등)이 강제 재사용되어 신규 핫픽스가 갱신 반영되지 않는 네트워크 서빙 정합성 오류가 확인되었습니다.

---

## 2. 주요 개선 사항

### A. 백엔드 어드민 서빙 캐시 금지(No-Cache) 헤더 추가 (`server/main.py`)
FastAPI가 `/admin` 및 `admin.html` 리소스를 반환할 때, 브라우저가 최신 빌드 아티팩트를 강제로 요청 로드하도록 No-Cache 응답 헤더를 주입해 브라우저 리소스 캐시를 즉시 만료 및 격리시켰습니다.

```python
# server/main.py
@app.get("/admin")
@app.get("/admin.html")
def serve_admin_page():
    no_cache_headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    admin_file = os.path.join(client2_dist_path, "admin.html")
    if os.path.exists(admin_file):
        return FileResponse(admin_file, headers=no_cache_headers)
```

### B. 전체화면 시 자식 엘리먼트 팽창 CSS 정의 (`client2/admin.html`)
부모 래퍼(`fullscreen-mode`)가 활성화될 시, 자식 카드 및 모나코 컨테이너도 100% 높이 비율을 동적으로 온전히 사용하도록 강제 스타일을 추가 배치해 레이아웃 깨짐을 완전히 차단했습니다.

```css
/* client2/admin.html */
#editor-content-wrapper.fullscreen-mode .detail-block {
  flex: 1 !important;
  height: 100% !important;
  max-height: none !important;
  display: flex !important;
  flex-direction: column !important;
  margin: 0 !important;
  border: none !important;
  background: transparent !important;
}
#editor-content-wrapper.fullscreen-mode .detail-block-body {
  flex: 1 !important;
  height: calc(100% - 60px) !important;
  padding: 0 !important;
  margin: 0 !important;
}
#editor-content-wrapper.fullscreen-mode #monaco-editor-container {
  height: 100% !important;
  width: 100% !important;
}
```

---

## 3. 빌드 및 푸시 적용
* **Vite 번들링**: 수정 작업을 마치고 `client2` 디렉토리에서 `npm run build` 번들링을 무결하게 수행하여 최종 `dist/admin.html` 리소스를 온전히 컴파일 갱신 서빙하도록 처리했습니다.
