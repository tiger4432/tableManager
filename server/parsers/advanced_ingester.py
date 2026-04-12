import re
import json
import httpx
import os
from typing import Dict, Any, List, Optional
from generic_ingester import GenericIngester

class AdvancedIngester(GenericIngester):
    def __init__(self, config_path: str, server_url: str = "http://127.0.0.1:8000"):
        super().__init__(config_path, server_url)
        self.header_rules = self.config.get("header_rules", [])
        self.table_start_pattern = self.config.get("table_start_pattern", "")
        self.table_end_pattern = self.config.get("table_end_pattern", "")

    def extract_header_metadata(self, lines: List[str]) -> Dict[str, Any]:
        """
        Scans the lines for header metadata until table_start_pattern is found.
        """
        metadata = {}
        for line in lines:
            if self.table_start_pattern and re.search(self.table_start_pattern, line):
                break
            
            for rule in self.header_rules:
                match = re.search(rule["regex"], line)
                if match:
                    val = match.group(1)
                    metadata[rule["column"]] = self._cast_type(val, rule.get("type", "str"))
        return metadata

    def process_file(self, file_path: str):
        """
        Processes a file by extracting header metadata first, then parsing table rows.
        """
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            return

        print(f"[{self.source_name}] Processing file: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()

        # 1. Extract Header Metadata
        header_metadata = self.extract_header_metadata(all_lines)
        print(f"Extracted Header Metadata: {header_metadata}")

        # 2. Extract Filename Metadata (Inherited from GenericIngester logic if applicable)
        filename = os.path.basename(file_path)
        filename_data = {}
        if hasattr(self, "filename_rules"):
            for rule in self.filename_rules:
                match = re.search(rule["regex"], filename)
                if match:
                    val = match.group(1)
                    filename_data[rule["column"]] = self._cast_type(val, rule.get("type", "str"))

        # 3. Parse Table Rows
        in_table = False
        for line in all_lines:
            line = line.strip()
            if not in_table:
                if self.table_start_pattern and re.search(self.table_start_pattern, line):
                    in_table = True
                continue
            
            # Stop if we hit a footer or another divider (optional logic)
            if self.table_end_pattern and re.search(self.table_end_pattern, line):
                print(f"[{self.source_name}] Table end detected: {line}")
                break

            row_data = self.parse_line(line)
            if row_data:
                # Merge all metadata
                row_data.update(header_metadata)
                row_data.update(filename_data)
                
                # Identify business key value
                bk_val = row_data.get(self.business_key_col)
                if bk_val:
                    self.push_to_server(bk_val, row_data)
                else:
                    print(f"Skipping line (No business key found): {line}")

if __name__ == "__main__":
    # Get the directory of the current script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Paths relative to the script directory
    config = os.path.join(base_dir, "custom", "advanced_config.json")
    sample_text = os.path.join(base_dir, "custom", "sample_advanced_log.txt")
    
    ingester = AdvancedIngester(config)
    ingester.process_file(sample_text)
