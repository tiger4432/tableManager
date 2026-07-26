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
        # [P2 #10] 다중 tx 혼재 배치 경고 1회 게이트 (핫패스 로그 홍수 방지)
        self._multi_tx_warned = False

    def load_initial(self, db: Session, limit_groups: int = 100):
        """서버 기동 후 최초 1회만 DB에서 청크 단위로 조회하여 캐시를 로드합니다."""
        with self._lock:
            if self.is_loaded: 
                return
            
            groups_dict = {}
            groups_order = [] # To maintain chronological order of transactions
            
            chunk_size = 5000
            offset = 0
            
            while len(groups_order) < limit_groups:
                chunk = db.query(models.AuditLog)\
                          .order_by(desc(models.AuditLog.timestamp), desc(models.AuditLog.id))\
                          .offset(offset).limit(chunk_size).all()
                          
                if not chunk:
                    break
                    
                for log_obj in chunk:
                    tid = log_obj.transaction_id or "no_tid"
                    
                    log_dict = log_obj.__dict__.copy()
                    log_dict["business_key"] = log_obj.business_key
                    log_model = schemas.AuditLogResponse.model_validate(log_dict)
                    
                    if tid not in groups_dict:
                        if len(groups_order) >= limit_groups:
                            continue
                        new_group = {"transaction_id": tid, "logs": [], "total_count": 0}
                        groups_dict[tid] = new_group
                        groups_order.append(new_group)
                    
                    groups_dict[tid]["total_count"] += 1
                    # [성능 최적화] 인메모리 캐시에는 트랜잭션당 최대 500건만 유지 (나머지는 DB 조회)
                    if len(groups_dict[tid]["logs"]) < 500:
                        groups_dict[tid]["logs"].append(log_model)
                         
                offset += chunk_size
                
            self.groups = groups_order
                
            self.is_loaded = True

    def prepend_transaction(self, tx_id: str, logs: List[schemas.AuditLogResponse]):
        """새로운 트랜잭션 그룹을 캐시 최상단에 추가합니다."""
        with self._lock:
            if not self.is_loaded: 
                return
            
            if any(g.get("transaction_id") == tx_id for g in self.groups):
                return
            
            # [최적화] 캡핑 적용
            actual_count = len(logs)
            self.groups.insert(0, {"transaction_id": tx_id, "logs": logs[:500], "total_count": actual_count})
            
            if len(self.groups) > 100:
                self.groups.pop()

    def add_log(self, log_dict: dict):
        """단일 로그 발생 시 캐시에 동적으로 편입합니다."""
        with self._lock:
            if not self.is_loaded: 
                return
            
            tid = log_dict.get("transaction_id") or "no_tid"
            log_model = schemas.AuditLogResponse.model_validate(log_dict)
            
            # [Fix] 기존 그룹 중에 같은 transaction_id가 있는지 전체 검색
            for group in self.groups:
                if group["transaction_id"] == tid:
                    group["total_count"] += 1
                    # [최적화] 인메모리 캡핑 (500건)
                    if len(group["logs"]) < 500:
                        group["logs"].insert(0, log_model)
                        
                    # 해당 그룹을 최상단으로 이동 (최신 활동 트랜잭션 순서 유지)
                    if self.groups.index(group) > 0:
                        self.groups.remove(group)
                        self.groups.insert(0, group)
                    return
            
            # 없으면 새 그룹 생성
            self.groups.insert(0, {"transaction_id": tid, "logs": [log_model], "total_count": 1})

    def add_logs_batch(self, logs_list: List[dict], message_total_count: int = None):
        """대량의 로그를 단일 락(Lock) 획득으로 캐시에 일괄 편입합니다.

        [P2 이슈 #10 / QA D-1] `message_total_count`의 의미론 = **이 메시지 1건이 나르는
        로그의 절단 전 실건수(=이 tx에 대한 이 메시지의 기여분)**이며, 그룹 total_count에는
        **누적(+=)** 된다. 종전 이름(`override_total_count`)과 SET 대입은 "같은 tx id로
        메시지가 2회 이상 도착하는 경로"에서 마지막 메시지가 이전 총계를 지워 과소 표기를
        일으켰다. 실제 도달 경로(2026-07-26 실측):

          - 체인 워커: 한 소스 tx가 여러 target_table 룰을 트리거하면 `chain_{tx}` 하나로
            target_table 수만큼 broadcast가 발신된다(chain_ingestion_worker target_table 루프).
            600건 → 50건 순 도착 시 종전 SET는 total_count를 50으로 만들었다(실제 650).
          - 워처(파일 인제션): 파일당 file_tx_id가 유일하고 통지도 1회 → 신·구 의미론 동일.
          - override 미전달(crud 내부 호출): 종전과 동일하게 len(logs) 누적.

        절단 없는 재전송(중복 배달)이 존재하면 누적은 과대 표기가 되지만, 현행 발신 경로
        (post_event 단발 POST, 복구 스윕은 created_logs 미동봉)에는 재전송이 없다.
        **발신 경로를 추가할 때는 "같은 tx로 같은 로그가 두 번 오는가"를 먼저 확인할 것.**

        `logs_list` 하나에 서로 다른 tx가 섞여 있으면 기여분을 tx별로 나눌 근거가 없으므로
        message_total_count를 적용하지 않고 그룹별 len(logs)로 폴백한다(경고 1회).
        """
        if not logs_list:
            return
        with self._lock:
            if not self.is_loaded:
                return

            from collections import defaultdict
            logs_by_tx = defaultdict(list)
            for log_dict in logs_list:
                tid = log_dict.get("transaction_id") or "no_tid"
                try:
                    log_model = schemas.AuditLogResponse.model_validate(log_dict)
                    logs_by_tx[tid].append(log_model)
                except Exception:
                    continue

            # 다중 tx가 섞인 메시지에서는 message_total_count를 어느 tx에 귀속시킬지 알 수 없다.
            # (현행 발신 경로는 메시지당 단일 tx — 방어적 폴백 + 1회 경고)
            effective_total = message_total_count
            if effective_total is not None and len(logs_by_tx) > 1:
                if not self._multi_tx_warned:
                    self._multi_tx_warned = True
                    print(
                        "[AuditCache] message_total_count ignored: batch contains "
                        f"{len(logs_by_tx)} transactions — falling back to per-group len(logs). "
                        "(Sender should emit one transaction per message.)"
                    )
                effective_total = None

            for tid, logs in logs_by_tx.items():
                contribution = effective_total if (effective_total is not None) else len(logs)

                found = False
                for group in self.groups:
                    if group["transaction_id"] == tid:
                        # [P2 #10] SET → 누적. 같은 tx가 여러 메시지로 나뉘어 도착해도
                        # 총계가 마지막 메시지 값으로 덮어써지지 않는다.
                        group["total_count"] += contribution

                        for log_model in reversed(logs):
                            if len(group["logs"]) < 500:
                                group["logs"].insert(0, log_model)
                        
                        idx = self.groups.index(group)
                        if idx > 0:
                            self.groups.pop(idx)
                            self.groups.insert(0, group)
                        found = True
                        break
                
                if not found:
                    self.groups.insert(0, {
                        "transaction_id": tid,
                        "logs": logs[:500],
                        "total_count": contribution
                    })
            
            while len(self.groups) > 100:
                self.groups.pop()

    def remove_deleted_rows(self, row_ids: List[str]):
        """삭제된 행의 과거 로그를 캐시에서 제거하지 않고 보존합니다."""
        pass

audit_cache = AuditLogCache()
