import threading
from typing import List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from database import models
from database import schemas

class AuditLogCache:
    """
    최신 히스토리 로그(트랜잭션 단위 100그룹)를 인메모리에 캐싱하여
    대시보드 및 히스토리 패널 새로고침 시 DB 부하를 최소화합니다.
    단일 프로세스 멀티스레딩 환경에서 Thread-Safe하게 동작하도록 설계되었습니다.
    """
    def __init__(self):
        self.groups: List[Dict] = []
        self.is_loaded = False
        self._lock = threading.Lock()

    def load_initial(self, db: Session, limit_groups: int = 100):
        """서버 기동 후 최초 1회만 DB에서 청크 단위로 조회하여 캐시를 로드합니다."""
        with self._lock:
            if self.is_loaded: 
                return
            
            groups = []
            current_group_logs = []
            last_tid = None
            group_count = 0
            
            chunk_size = 5000
            offset = 0
            
            while group_count < limit_groups:
                chunk = db.query(models.AuditLog)\
                          .filter(or_(
                              models.AuditLog.row_id == "_BATCH_",
                              db.query(models.DataRow).filter(models.DataRow.row_id == models.AuditLog.row_id).exists()
                          ))\
                          .order_by(desc(models.AuditLog.timestamp), desc(models.AuditLog.id))\
                          .offset(offset).limit(chunk_size).all()
                          
                if not chunk:
                    break
                    
                for log in chunk:
                    tid = log.transaction_id
                    
                    if not tid or tid != last_tid:
                        if current_group_logs:
                            groups.append({"transaction_id": last_tid, "logs": current_group_logs})
                            group_count += 1
                            if group_count >= limit_groups:
                                break
                                
                        current_group_logs = [log]
                        last_tid = tid
                    else:
                        current_group_logs.append(log)
                        
                if group_count >= limit_groups:
                    break
                    
                offset += chunk_size
                
            if current_group_logs and group_count < limit_groups:
                groups.append({"transaction_id": last_tid, "logs": current_group_logs})

            # schemas.AuditLogResponse 형태로 변환하여 저장
            self.groups = []
            for g in groups:
                self.groups.append({
                    "transaction_id": g["transaction_id"],
                    "logs": [schemas.AuditLogResponse.model_validate(l) for l in g["logs"]]
                })
                
            self.is_loaded = True

    def prepend_transaction(self, tx_id: str, logs: List[schemas.AuditLogResponse]):
        """새로운 트랜잭션 그룹을 캐시 최상단에 추가합니다."""
        with self._lock:
            if not self.is_loaded: 
                return
            
            if any(g.get("transaction_id") == tx_id for g in self.groups):
                return
                
            self.groups.insert(0, {"transaction_id": tx_id, "logs": logs})
            
            recent_subset = self.groups[:5]
            recent_subset.sort(key=lambda g: g["logs"][0].timestamp if g["logs"] else 0, reverse=True)
            self.groups[:5] = recent_subset
            
            if len(self.groups) > 100:
                self.groups.pop()

    def add_log(self, log_dict: dict):
        """단일 로그 발생 시 캐시에 동적으로 편입합니다."""
        with self._lock:
            if not self.is_loaded: 
                return
            
            tid = log_dict.get("transaction_id")
            log_model = schemas.AuditLogResponse.model_validate(log_dict)
            
            # 기존 그룹 중에 같은 transaction_id가 있는지 확인 (주로 맨 앞)
            for group in self.groups[:5]:
                if group["transaction_id"] == tid:
                    group["logs"].insert(0, log_model)
                    return
            
            # 없으면 새 그룹 생성
            self.groups.insert(0, {"transaction_id": tid, "logs": [log_model]})
            
            recent_subset = self.groups[:5]
            recent_subset.sort(key=lambda g: g["logs"][0].timestamp if g["logs"] else 0, reverse=True)
            self.groups[:5] = recent_subset
            
            if len(self.groups) > 100:
                self.groups.pop()

    def remove_deleted_rows(self, row_ids: List[str]):
        """삭제된 행의 과거 로그를 캐시에서 제거합니다."""
        with self._lock:
            if not self.is_loaded: 
                return
                
            for group in self.groups:
                group["logs"] = [l for l in group["logs"] if l.row_id not in row_ids or l.row_id == "_BATCH_"]
            
            self.groups = [g for g in self.groups if g["logs"]]

audit_cache = AuditLogCache()
