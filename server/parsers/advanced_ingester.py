import re
import json
import os
from typing import Dict, Any, List, Optional

class AdvancedIngester:
    """
    통합 인제스터: 정규표현식 기반의 범용 파싱 기능과 
    헤더 메타데이터 추출 기능을 하나의 클래스로 제공합니다.
    """
    def __init__(self, config_path: str, server_url: str = "http://127.0.0.1:8000"):
        self.config = self._load_json(config_path)
        self.server_url = server_url
        
        # 기본 규칙 (Generic)
        self.rules = self.config.get("rules", [])
        self.filename_rules = self.config.get("filename_rules", [])
        self.table_name = self.config.get("table_name")
        self.source_name = self.config.get("source_name", "advanced_ingester")
        self.updated_by = self.config.get("updated_by", "agent_adv")
        self.business_key_col = self.config.get("business_key_column", "id")
        
        # 고급 규칙 (Advanced)
        self.header_rules = self.config.get("header_rules", [])
        self.table_start_pattern = self.config.get("table_start_pattern", "")
        self.table_end_pattern = self.config.get("table_end_pattern", "")

    def _load_json(self, path: str) -> Dict:
        if not os.path.exists(path):
            if not os.path.isabs(path):
                alt_path = os.path.join(os.path.dirname(__file__), path)
                if os.path.exists(alt_path): path = alt_path
                else: raise FileNotFoundError(f"Config not found: {path}")
            else: raise FileNotFoundError(f"Config not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _cast_type(self, value: str, target_type: str) -> Any:
        try:
            if target_type == "int": return int(value)
            if target_type == "float": return float(value)
            if target_type == "bool": return value.lower() in ("true", "1", "yes")
            return str(value)
        except: return None

    def extract_header_metadata(self, lines: List[str]) -> Dict[str, Any]:
        """헤더 영역에서 메타데이터를 추출합니다."""
        metadata = {}
        if not self.header_rules: return metadata
        
        for line in lines:
            if self.table_start_pattern and re.search(self.table_start_pattern, line):
                break
            for rule in self.header_rules:
                match = re.search(rule["regex"], line)
                if match:
                    val = match.group(1)
                    metadata[rule["column"]] = self._cast_type(val, rule.get("type", "str"))
        return metadata

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        """정규표현식 규칙에 따라 한 줄을 파싱합니다."""
        extracted = {}
        found_any = False
        for rule in self.rules:
            col, pattern = rule["column"], rule["regex"]
            match = re.search(pattern, line)
            if match:
                val = self._cast_type(match.group(1), rule.get("type", "str"))
                if val is not None:
                    extracted[col] = val
                    found_any = True
                else: extracted[col] = rule.get("default")
            else: extracted[col] = rule.get("default")
            
            if rule.get("required") and (extracted.get(col) is None):
                return None
        return extracted if found_any else None

    def process_file(self, file_path: str) -> List[Dict[str, Any]]:
        """파일 전체를 스캔하여 파싱된 행 리스트를 반환합니다."""
        if not os.path.exists(file_path): return []
        
        with open(file_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        header_metadata = self.extract_header_metadata(all_lines)
        
        filename = os.path.basename(file_path)
        filename_data = {}
        for rule in self.filename_rules:
            match = re.search(rule["regex"], filename)
            if match:
                val = self._cast_type(match.group(1), rule.get("type", "str"))
                filename_data[rule["column"]] = val

        parsed_rows = []
        in_table = not bool(self.table_start_pattern) # 패턴 없으면 즉시 시작
        
        for line in all_lines:
            line = line.strip()
            if not line: continue
            
            if not in_table:
                if re.search(self.table_start_pattern, line):
                    in_table = True
                continue
            
            if self.table_end_pattern and re.search(self.table_end_pattern, line):
                break

            row_data = self.parse_line(line)
            if row_data:
                full_data = {**header_metadata, **filename_data, **row_data}
                parsed_rows.append(full_data)
        
        return parsed_rows

if __name__ == "__main__":
    # 통합 테스트용 더미 설정 및 로그
    print("Testing Consolidated AdvancedIngester...")
    # ... 테스트 코드는 생략하거나 필요시 추가
