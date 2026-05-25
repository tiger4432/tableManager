# 2026-05-25 client2 실제 서비스(운영) 환경 통합 완료 기록

본 문서는 `client2` (AG-Grid 기반 웹 프론트엔드) 빌드 아티팩트를 FastAPI 백엔드(`server/main.py`)에 정적 자산으로 마운트하여, 별도의 Vite 개발 서버 없이 백엔드 웹 서버 기동만으로 웹 UI 서비스를 통합 제공하도록 아키텍처를 고도화한 내역을 기록합니다.

## 1. 개요 및 변경사항

- **배경**: 기존에는 개발 편의상 로컬 호스트 포트 5173(Vite)과 포트 8080(FastAPI)을 분리하여 기동하였으나, 실제 서비스 배포 및 운영 환경에서는 별개의 웹 서버를 실행하는 대신 단일 서버 포트(8080)에서 API와 UI를 원스톱으로 서빙하여 배포 복잡도를 대폭 줄이고자 통합하였습니다.
- **주요 조치**:
  1. **정적 리소스 서빙 및 라우트 제공**: `fastapi.staticfiles.StaticFiles` 및 `fastapi.responses.FileResponse`를 활용하여 `client2/dist` 하위의 빌드된 자산(`assets/` 및 기타 정적 파일)을 FastAPI 앱에 안전하게 마운트하고, SPA(Single Page Application) 클라이언트 라우팅 대응을 위해 정의되지 않은 서브 패스는 모두 `index.html`로 폴백(fallback)되도록 설정했습니다.
  2. **클라이언트 엔드포인트 동적 감지**: `client2/src/main.js`의 `API_BASE` 및 `WS_URL` 상수를 하드코딩된 로컬 포트가 아닌 `window.location` 객체를 기반으로 동적 탐색하여, 어떤 도메인이나 포트에서 구동되든 백엔드 서비스와 자동으로 매핑되도록 처리했습니다.
  3. **PySide6 데스크톱 클라이언트 런타임 감지**: 데스크톱 래퍼(`client/desktop_wrapper.py`)에서 포트 `5173`이 오픈되어 있으면 개발 환경(Vite Dev Server)을 로드하고, 그렇지 않으면 통합 서버(`localhost:8080`)의 완성된 프로덕션 빌드를 로드하는 동적 프로브(Port Probe) 헬퍼를 추가하여 하이브리드 편의성을 극대화했습니다.

## 2. 세부 코드 구현 내역

### A. FastAPI 정적 마운팅 및 catch-all 라우팅 (`server/main.py`)
```python
# --- Static File Serving & SPA Fallback for client2 ---
script_dir = os.path.dirname(os.path.abspath(__file__))
client2_dist_path = os.path.abspath(os.path.join(script_dir, "..", "client2", "dist"))
if not os.path.exists(client2_dist_path):
    client2_dist_path = os.path.join(script_dir, "dist")

if os.path.exists(client2_dist_path):
    assets_dir = os.path.join(client2_dist_path, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{file_name:path}")
    async def serve_static_or_index(file_name: str):
        # API 및 WebSocket 경로를 가로채지 않도록 선제 404 처리
        if (file_name.startswith("tables") or 
            file_name.startswith("ws") or 
            file_name.startswith("audit_logs") or 
            file_name.startswith("dashboard")):
            raise HTTPException(status_code=404)

        target_path = os.path.join(client2_dist_path, file_name)
        if file_name and os.path.exists(target_path) and os.path.isfile(target_path):
            return FileResponse(target_path)

        index_file = os.path.join(client2_dist_path, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Index file not found")
```

### B. 프론트엔드 동적 API 스코프 바인딩 (`client2/src/main.js`)
```javascript
const isDevServer = window.location.port === '5173';
const API_BASE = isDevServer ? 'http://127.0.0.1:8080' : window.location.origin;
const WS_URL = isDevServer ? 'ws://127.0.0.1:8080/ws' : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;
```

### C. 데스크톱 래퍼 포트 프로빙 런타임 바인딩 (`client/desktop_wrapper.py`)
```python
    import socket
    def is_port_open(host, port):
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            return False
            
    if is_port_open("127.0.0.1", 5173):
        url = "http://localhost:5173/"
        print("[Desktop Wrapper] Vite dev server detected on port 5173. Loading development URL.")
    else:
        url = "http://localhost:8080/"
        print("[Desktop Wrapper] Vite dev server not detected. Loading integrated FastAPI URL on port 8080.")
```

## 3. 검증 결과
1. **Vite 빌드 통과**: `client2`에서 `npm run build` 결과 1.1MB 크기의 단일 JS 및 CSS, index.html이 정상 압축 컴파일됨을 확인하였습니다.
2. **파이썬 컴파일 통과**: `server/main.py`와 `client/desktop_wrapper.py` 파일의 컴파일 오류가 없음을 확인하였습니다.
3. **단일 기동 검증**: 백엔드 포트 8080만 기동 후 웹브라우저로 `http://localhost:8080/` 접속 시, 별도의 Vite 5173 포트가 닫혀있음에도 최적화된 웹 화면이 성공적으로 서빙되고 백엔드 API와 실시간 WebSocket 접속이 완벽히 바인딩됨을 확인했습니다.
