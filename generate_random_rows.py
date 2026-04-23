import sys
import os
import uuid
import random
from datetime import datetime, timedelta
import pandas as pd

categories = ["IC", "Passive", "Connector", "Mechanical", "PCB"]
locations = ["Warehouse-A", "Warehouse-B", "Line-1-Shelf", "Line-2-Shelf"]
db=  []
for i in range(1, 10000):
    row =  {
        "part_no": uuid.uuid4(),
        "category": random.choice(categories),
        "stock_qty": random.randint(0, 5000),
        "location": random.choice(locations),
        "lead_time_days": random.randint(1, 30),
        "unit_price": round(random.uniform(0.1, 500.0), 2)
    }
    db.append(row)



pd.DataFrame(db).to_csv('inventory_master.csv', index = False)