import re
import json
import httpx
import os
from typing import Dict, Any, List, Optional

class GenericIngester:
    def __init__(self, config_path: str, server_url: str = "http://127.0.0.1:8000"):
        self.config = self._load_json(config_path)
        self.server_url = server_url
        self.rules = self.config.get("rules", [])
        self.filename_rules = self.config.get("filename_rules", [])
        self.header_rules = self.config.get("header_rules", []) # New: Extract data from header lines
        self.table_name = self.config.get("table_name")
        self.source_name = self.config.get("source_name", "generic_ingester")
        self.updated_by = self.config.get("updated_by", "agent_i")
        self.business_key_col = self.config.get("business_key_column")

    def _load_json(self, path: str) -> Dict:
        if not os.path.exists(path):
            # Try relative to the script if absolute path doesn't work
            if not os.path.isabs(path):
                alt_path = os.path.join(os.path.dirname(__file__), path)
                if os.path.exists(alt_path):
                    path = alt_path
                else:
                    raise FileNotFoundError(f"Config file not found: {path} (checked {alt_path})")
            else:
                raise FileNotFoundError(f"Config file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _cast_type(self, value: str, target_type: str) -> Any:
        try:
            if target_type == "int":
                return int(value)
            elif target_type == "float":
                return float(value)
            elif target_type == "bool":
                return value.lower() in ("true", "1", "yes")
            return str(value)
        except (ValueError, TypeError):
            return None

    def parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Parses a single line using the defined regex rules.
        """
        extracted = {}
        found_any = False
        
        for rule in self.rules:
            col = rule["column"]
            pattern = rule["regex"]
            target_type = rule.get("type", "str")
            default = rule.get("default")
            
            match = re.search(pattern, line)
            if match:
                val = match.group(1)
                casted_val = self._cast_type(val, target_type)
                if casted_val is not None:
                    extracted[col] = casted_val
                    found_any = True
                else:
                    extracted[col] = default
            else:
                extracted[col] = default

            # Check if required field was found
            if rule.get("required") and (extracted.get(col) is None):
                return None # Skip this line as it lacks mandatory data

        return extracted if found_any else None

    def process_file(self, file_path: str):
        """
        Reads a file line by line and pushes data to the server via Upsert.
        """
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            return

        filename = os.path.basename(file_path)
        print(f"Processing file: {file_path}")
        
        # 1. Extract data from filename
        filename_data = {}
        for rule in self.filename_rules:
            match = re.search(rule["regex"], filename)
            if match:
                val = match.group(1)
                filename_data[rule["column"]] = self._cast_type(val, rule.get("type", "str"))

        # 2. Extract data from lines (Header and Data)
        persistent_header_data = {}
        
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                
                # Check for header rules
                header_found = False
                for h_rule in self.header_rules:
                    h_match = re.search(h_rule["regex"], line)
                    if h_match:
                        val = h_match.group(1)
                        persistent_header_data[h_rule["column"]] = self._cast_type(val, h_rule.get("type", "str"))
                        print(f"  [Header] Extracted {h_rule['column']} = {persistent_header_data[h_rule['column']]}")
                        header_found = True
                
                if header_found: continue
                
                # Try parsing data line
                data = self.parse_line(line)
                if data:
                    # Merge all metadata
                    full_data = {}
                    full_data.update(filename_data)
                    full_data.update(persistent_header_data)
                    full_data.update(data)
                    
                    # Identify business key value
                    bk_val = full_data.get(self.business_key_col)
                    if bk_val:
                        self.push_to_server(bk_val, full_data)
                    else:
                        print(f"Skipping line (No business key found): {line}")

    def push_to_server(self, business_key_val: Any, updates: Dict[str, Any]):
        url = f"{self.server_url}/tables/{self.table_name}/upsert"
        payload = {
            "business_key_val": business_key_val,
            "updates": updates,
            "source_name": self.source_name,
            "updated_by": self.updated_by
        }
        
        try:
            resp = httpx.put(url, json=payload, timeout=10.0)
            if resp.status_code == 200:
                print(f"Uploaded: {business_key_val} -> {resp.json().get('row_id')}")
            else:
                print(f"Failed to upload {business_key_val}: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Error pushing to server: {e}")

if __name__ == "__main__":
    # Example usage
    config = "server/parsers/custom/parser_config.json"
    sample_text = "server/parsers/custom/sample_log.txt"
    
    # Create sample text for demonstration if it doesn't exist
    if not os.path.exists(sample_text):
        os.makedirs(os.path.dirname(sample_text), exist_ok=True)
        with open(sample_text, "w", encoding="utf-8") as f:
            f.write("LOG: PartNo: PN-55555 Qty: 120 Type: Passive Price: 12.5\n")
            f.write("LOG: PartNo: PN-66666 Qty: 300 Type: IC Price: 155.0\n")
            f.write("ERROR: Check line 45 (No data)\n")
            f.write("LOG: PartNo: PN-55555 Qty: 150 Type: Passive Price: 13.0 (Update)\n")

    ingester = GenericIngester(config)
    ingester.process_file(sample_text)
