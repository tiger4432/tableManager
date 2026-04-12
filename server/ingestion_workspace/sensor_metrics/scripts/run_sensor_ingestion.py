import os
import sys

# Add the parsers directory to sys.path to import AdvancedIngester
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "..", "parsers"))

try:
    from advanced_ingester import AdvancedIngester
except ImportError as e:
    print(f"Error importing AdvancedIngester: {e}")
    sys.exit(1)

def run_sensor_ingestion():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_dir = os.path.join(base_dir, "..")
    
    config_path = os.path.join(workspace_dir, "config", "sensor_config.json")
    raw_dir = os.path.join(workspace_dir, "raws")
    
    ingester = AdvancedIngester(config_path)
    
    # Process all files in raws directory
    for filename in os.listdir(raw_dir):
        if filename.endswith(".txt"):
            file_path = os.path.join(raw_dir, filename)
            ingester.process_file(file_path)

if __name__ == "__main__":
    run_sensor_ingestion()
