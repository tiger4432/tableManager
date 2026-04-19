from database.database import SessionLocal, engine
from database.models import Base, DataRow
import uuid
import random
from datetime import datetime, timedelta

# Ensure tables are created
Base.metadata.create_all(bind=engine)

def clear_db():
    db = SessionLocal()
    db.query(DataRow).delete()
    db.commit()
    db.close()
    print("Database cleared.")

def create_row(table_name, data):
    return DataRow(
        row_id=str(uuid.uuid4()),
        table_name=table_name,
        data={k: {"value": v, "is_overwrite": False} for k, v in data.items()}
    )

def seed():
    db = SessionLocal()
    
    # 1. Inventory Master (재고 관리)
    print("Seeding inventory_master (500 rows)...")
    categories = ["IC", "Passive", "Connector", "Mechanical", "PCB"]
    locations = ["Warehouse-A", "Warehouse-B", "Line-1-Shelf", "Line-2-Shelf"]
    for i in range(1, 100000):
        row = create_row("inventory_master", {
            "part_no": f"PN-{10000+i}",
            "category": random.choice(categories),
            "stock_qty": random.randint(0, 5000),
            "location": random.choice(locations),
            "lead_time_days": random.randint(1, 30),
            "unit_price": round(random.uniform(0.1, 500.0), 2)
        })
        db.add(row)

    # 2. Production Plan (생산 계획)
    print("Seeding production_plan (300 rows)...")
    models = ["Model-X", "Model-Y", "Model-Z", "Alpha-1", "Beta-2"]
    lines = ["Line-A", "Line-B", "Line-C"]
    start_date = datetime.now()
    for i in range(1, 301):
        row = create_row("production_plan", {
            "plan_id": f"PLN-{20260000+i}",
            "line_id": random.choice(lines),
            "model_name": random.choice(models),
            "planned_qty": random.choice([50, 100, 200, 500]),
            "start_date": (start_date + timedelta(days=i//10)).strftime("%Y-%m-%d"),
            "priority": random.choice(["URGENT", "NORMAL", "LOW"])
        })
        db.add(row)

    # 3. Sensor Metrics (센서 데이터)
    print("Seeding sensor_metrics (1000 rows)...")
    sensors = [f"SENSOR-{str(i).zfill(3)}" for i in range(1, 51)]
    for i in range(1, 1001):
        row = create_row("sensor_metrics", {
            "sensor_id": random.choice(sensors),
            "temperature": round(random.uniform(20.0, 85.0), 1),
            "humidity": round(random.uniform(30.0, 70.0), 1),
            "pressure": round(random.uniform(0.9, 1.2), 3),
            "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        db.add(row)

    # 4. Original Raw Table (기존 호환용)
    print("Seeding raw_table_1 (200 rows)...")
    for i in range(1, 201):
        row = create_row("raw_table_1", {
            "id": i,
            "name": f"Item {i}",
            "status": "OK" if i % 2 == 0 else "WARNING"
        })
        db.add(row)

    db.commit()
    db.close()
    print("Total rows:", db.query(DataRow).count())
    print("Seed complete.")

if __name__ == "__main__":
    # Clear existing data first
    clear_db()
    seed()

