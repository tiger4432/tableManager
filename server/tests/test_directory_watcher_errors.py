import os
import json
import pytest
import sys

# Ensure server/parsers is in python path
script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
parsers_dir = os.path.join(server_dir, "parsers")
if parsers_dir not in sys.path:
    sys.path.insert(0, parsers_dir)

from directory_watcher import IngestionHandler

def test_directory_watcher_syntax_error(tmp_path):
    # 1. Setup mock workspace
    workspace_root = tmp_path / "workspace_syntax_error"
    workspace_root.mkdir()
    
    config_dir = workspace_root / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"table_name": "inventory_master", "columns": ["part_no", "category"]}, f)
    
    # 2. Create invalid syntax script in scripts folder
    scripts_dir = workspace_root / "scripts"
    scripts_dir.mkdir()
    
    bad_script_path = scripts_dir / "bad_syntax_parser.py"
    # Python syntax error: missing colon in class definition
    with open(bad_script_path, "w", encoding="utf-8") as f:
        f.write("""
from pipeline_base import BasePipelineParser

class BadSyntaxParser(BasePipelineParser)
    @classmethod
    def match(cls, file_path: str) -> bool:
        return True
""")

    archives_dir = workspace_root / "archives"
    archives_dir.mkdir()
    dummy_file_path = archives_dir / "test_syntax.csv"
    with open(dummy_file_path, "w", encoding="utf-8") as f:
        f.write("part_no,category\nTEST_PART,TestCategory\n")

    handler = IngestionHandler(
        workspace_path=str(workspace_root),
        config_path=str(config_path),
        archives_path=str(archives_dir),
        default_table_name="inventory_master"
    )

    with pytest.raises(ValueError) as excinfo:
        handler._discover_and_execute_pipeline(str(dummy_file_path))
    
    error_msg = str(excinfo.value)
    assert "No custom pipeline parser matched the file" in error_msg
    assert "bad_syntax_parser.py" in error_msg
    assert "SyntaxError" in error_msg

def test_directory_watcher_match_error(tmp_path):
    # 1. Setup mock workspace
    workspace_root = tmp_path / "workspace_match_error"
    workspace_root.mkdir()
    
    config_dir = workspace_root / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"table_name": "inventory_master", "columns": ["part_no", "category"]}, f)
    
    # 2. Create script with runtime error in match()
    scripts_dir = workspace_root / "scripts"
    scripts_dir.mkdir()
    
    bad_match_path = scripts_dir / "bad_match_parser.py"
    with open(bad_match_path, "w", encoding="utf-8") as f:
        f.write("""
from pipeline_base import BasePipelineParser

class BadMatchParser(BasePipelineParser):
    @classmethod
    def match(cls, file_path: str) -> bool:
        raise RuntimeError("Simulated match exception!")
""")

    archives_dir = workspace_root / "archives"
    archives_dir.mkdir()
    dummy_file_path = archives_dir / "test_match.csv"
    with open(dummy_file_path, "w", encoding="utf-8") as f:
        f.write("part_no,category\nTEST_PART,TestCategory\n")

    handler = IngestionHandler(
        workspace_path=str(workspace_root),
        config_path=str(config_path),
        archives_path=str(archives_dir),
        default_table_name="inventory_master"
    )

    with pytest.raises(ValueError) as excinfo:
        handler._discover_and_execute_pipeline(str(dummy_file_path))
    
    error_msg = str(excinfo.value)
    assert "No custom pipeline parser matched the file" in error_msg
    assert "bad_match_parser.py" in error_msg
    assert "RuntimeError: Simulated match exception!" in error_msg

def test_directory_watcher_no_errors_no_match(tmp_path):
    # 1. Setup mock workspace
    workspace_root = tmp_path / "workspace_no_match"
    workspace_root.mkdir()
    
    config_dir = workspace_root / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"table_name": "inventory_master", "columns": ["part_no", "category"]}, f)
    
    # 2. Create normal parser but not matching
    scripts_dir = workspace_root / "scripts"
    scripts_dir.mkdir()
    
    normal_parser_path = scripts_dir / "normal_parser.py"
    with open(normal_parser_path, "w", encoding="utf-8") as f:
        f.write("""
from pipeline_base import BasePipelineParser

class NormalParser(BasePipelineParser):
    @classmethod
    def match(cls, file_path: str) -> bool:
        return False
""")

    archives_dir = workspace_root / "archives"
    archives_dir.mkdir()
    dummy_file_path = archives_dir / "test_normal.csv"
    with open(dummy_file_path, "w", encoding="utf-8") as f:
        f.write("part_no,category\nTEST_PART,TestCategory\n")

    handler = IngestionHandler(
        workspace_path=str(workspace_root),
        config_path=str(config_path),
        archives_path=str(archives_dir),
        default_table_name="inventory_master"
    )

    # _discover_and_execute_pipeline should return None cleanly since there were no loading/match errors
    res = handler._discover_and_execute_pipeline(str(dummy_file_path))
    assert res is None
