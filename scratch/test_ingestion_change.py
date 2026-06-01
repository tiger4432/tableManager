import os
import shutil

raws_dir = r"C:\Users\kk980\Developments\assyManager\server\ingestion_workspace\inventory_master\raws"
source_file = r"C:\Users\kk980\Developments\assyManager\server\ingestion_workspace\inventory_master\archives\user(kk980)_inventory_master_5abfb1e3.csv"

# Read the original file
with open(source_file, "r") as f:
    lines = f.readlines()

# Modify the first data row (line index 1)
# Original: cd4eb761-dc30-4e5e-a03e-fd7b00e0facb,Connector,1010,Line-2-Shelf,8,354.86
# Let's change stock_qty from 1010 to 9999
parts = lines[1].strip().split(",")
parts[2] = "9999" # change stock_qty
lines[1] = ",".join(parts) + "\n"

# Write to a new file in the raws folder
target_file = os.path.join(raws_dir, "user(kk980)_inventory_master_change_test.csv")
with open(target_file, "w") as f:
    f.writelines(lines)

print(f"Created change test file at: {target_file}")
