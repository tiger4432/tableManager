import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ConfigChangeHandler(FileSystemEventHandler):
    def __init__(self, engine=None):
        self.engine = engine
        self.last_triggered = 0
        
    def on_modified(self, event):
        if event.is_directory:
            return
        
        # table_config.json 파일의 수정을 감지
        if os.path.basename(event.src_path) == "table_config.json":
            # 파일 수정 시 여러 번 이벤트가 연속으로 들어오는 경우를 위한 디바운싱(Debounce) 처리
            now = time.time()
            if now - self.last_triggered < 1.0:
                return
            self.last_triggered = now
            
            # 파일 쓰기가 완료될 때까지 미세 대기 (Windows OS 파일 쓰기 버퍼 보정)
            time.sleep(0.1)
            
            print(f"[Config Watcher] Configuration change detected on {event.src_path}. Reloading dynamic models...")
            try:
                from database import crud, models
                # 1. crud.TABLE_CONFIG 재구성
                new_config = crud.load_table_config()
                if new_config:
                    crud.TABLE_CONFIG.clear()
                    crud.TABLE_CONFIG.update(new_config)
                    
                    # 2. models.DYNAMIC_TABLES 동적 모델 갱신 및 핫스왑
                    models.init_dynamic_models(new_config)
                    
                    # 3. 데이터베이스 엔진이 인입된 경우(웹 서버 전용) 실제 DB 물리 컬럼 동기화 가동
                    if self.engine:
                        models.sync_dynamic_tables_schema(self.engine)
                        print("[Config Watcher] Physical database schema synced successfully.")
                        
                    print("[Config Watcher] Dynamic models reloaded and hot-swapped successfully.")
            except Exception as e:
                print(f"[Config Watcher] Failed to hot-swap configuration changes: {e}")

def start_config_watcher(engine=None):
    """
    table_config.json 설정 폴더를 비동기로 감시하는 watchdog 스레드를 시작합니다.
    """
    from database import crud
    config_dir = os.path.dirname(crud.CONFIG_PATH)
    
    event_handler = ConfigChangeHandler(engine=engine)
    observer = Observer()
    observer.schedule(event_handler, path=config_dir, recursive=False)
    observer.start()
    print(f"[Config Watcher] Started config folder watchdog on '{config_dir}'")
    return observer
