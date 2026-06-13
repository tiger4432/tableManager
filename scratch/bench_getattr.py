import time
from sqlalchemy import create_engine, Column, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class MockTable(Base):
    __tablename__ = "mock_table"
    row_id = Column(String, primary_key=True)
    col1 = Column(String)
    col2 = Column(Float)
    col3 = Column(String)
    col4 = Column(Float)

# Create an in-memory SQLite database
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# Add a mock row
row = MockTable(row_id="1", col1="test", col2=10.5, col3="hello", col4=20.0)
session.add(row)
session.commit()

# Retrieve row
db_row = session.query(MockTable).first()

# Columns to access
cols = ["col1", "col2", "col3", "col4"] * 25000  # 100,000 accesses

# Test getattr
start = time.time()
for col in cols:
    val = getattr(db_row, col, None)
t_getattr = time.time() - start
print(f"getattr: {t_getattr:.4f}s")

# Test __dict__.get
start = time.time()
for col in cols:
    val = db_row.__dict__.get(col)
t_dict = time.time() - start
print(f"__dict__.get: {t_dict:.4f}s")
print(f"Speedup: {t_getattr / t_dict:.2f}x")
