from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
import uuid
from . import models, schemas

def update_cell(db: Session, table_name: str, cell_update: schemas.CellUpdate):
    row = db.query(models.DataRow).filter(
        models.DataRow.table_name == table_name,
        models.DataRow.row_id == cell_update.row_id
    ).first()
    
    if not row:
        return None
        
    data = row.data
    if cell_update.column_name not in data:
        data[cell_update.column_name] = {}
        
    data[cell_update.column_name].update({
        "value": cell_update.value,
        "is_overwrite": True,
        "updated_by": "user" # Or context-based user
    })
    
    # Notify SQLAlchemy that the JSON column was mutated
    flag_modified(row, "data")
    db.commit()
    db.refresh(row)
    return row

def update_cells_batch(db: Session, table_name: str, batch: schemas.CellUpdateBatch):
    updated_rows = []
    # For now, do iterative updates. Can be aggregated by row_id for better perf.
    for update in batch.updates:
        row = db.query(models.DataRow).filter(
            models.DataRow.table_name == table_name,
            models.DataRow.row_id == update.row_id
        ).first()
        
        if row:
            if update.column_name not in row.data:
                row.data[update.column_name] = {}
            row.data[update.column_name].update({
                "value": update.value,
                "is_overwrite": True,
                "updated_by": "user"
            })
            flag_modified(row, "data")
            if row not in updated_rows:
                updated_rows.append(row)
                
    if updated_rows:
        db.commit()
        for r in updated_rows:
            db.refresh(r)
            
    return updated_rows

def delete_row(db: Session, table_name: str, row_id: str):
    row = db.query(models.DataRow).filter(
        models.DataRow.table_name == table_name,
        models.DataRow.row_id == row_id
    ).first()
    
    if row:
        db.delete(row)
        db.commit()
        return True
    return False

def create_empty_row(db: Session, table_name: str):
    new_row_id = str(uuid.uuid4())
    # Create basic data structure for the row
    # In this app, columns are dynamic in JSON. 
    # We can initialize with an empty dict or pre-fill known columns.
    # For now, let's keep it empty as per instructions.
    new_row = models.DataRow(
        row_id=new_row_id,
        table_name=table_name,
        data={}
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    return new_row
