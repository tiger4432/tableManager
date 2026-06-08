from sqlalchemy.orm import Session
from typing import Dict, Any, List
import pandas as pd

def reserve_materials_from_plan(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Maps production_plan changes to inventory_master reservation updates.
    Assumes product consumptions: PRODUCT -> MAT_STEEL_01 (Qty * 5).
    """
    row_data = payload.get("data", {})
    planned_qty = int(row_data.get("target_qty", {}).get("value") or 0)
    
    # Target raw material details
    target_material = row_data.get("model_name", {}).get("value")
    required_qty = planned_qty * 5
    
    # Return formatted payload according to GeneralUpdateBatch schema
    target_payload = {
        "updates": [
            {
                "business_key_val": f"INV_{target_material}",
                "updates": {
                    "stock_qty": required_qty,
                    "part_no": f"INV_{target_material}"
                },
                "source_name": "chain_ingestion",
                "updated_by": "chain_worker"
            }
        ],
        "silent": False
    }
    
    return target_payload


def _payloads_to_df(payloads: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Helper to convert nested payload dictionary list into a 1D Pandas DataFrame.
    """
    flat_rows = []
    for p in payloads:
        row_id = p.get("row_id")
        raw_data = p.get("data", {})
        
        flat_row = {"row_id": row_id}
        for col_name, cell_detail in raw_data.items():
            if isinstance(cell_detail, dict) and "value" in cell_detail:
                flat_row[col_name] = cell_detail["value"]
            else:
                flat_row[col_name] = cell_detail
                
        flat_rows.append(flat_row)
        
    return pd.DataFrame(flat_rows)


def reserve_materials_batch_df(db: Session, payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Batch mapping utilizing pandas DataFrames to aggregate quantities by unique model_name.
    """
    if not payloads:
        return {"updates": []}
        
    # 1. Convert to DataFrame
    df = _payloads_to_df(payloads)
    
    # 2. Basic cleanup
    if "model_name" not in df.columns:
        return {"updates": []}
        
    df = df.dropna(subset=["model_name"])
    if df.empty:
        return {"updates": []}
        
    # Ensure target_qty is numeric
    if "target_qty" in df.columns:
        df["target_qty"] = pd.to_numeric(df["target_qty"], errors="coerce").fillna(0).astype(int)
    else:
        df["target_qty"] = 0
        
    # 3. Aggregate by unique model_name (Sum quantities)
    df_grouped = df.groupby("model_name", as_index=False)["target_qty"].sum()
    
    # 4. Construct general updates payload
    updates = []
    for _, row in df_grouped.iterrows():
        model = row["model_name"]
        total_planned_qty = row["target_qty"]
        required_qty = total_planned_qty * 5
        
        updates.append({
            "business_key_val": f"INV_{model}",
            "updates": {
                "stock_qty": required_qty,
                "part_no": f"INV_{model}"
            },
            "source_name": "chain_ingestion",
            "updated_by": "chain_worker"
        })
        
    return {
        "updates": updates,
        "silent": False
    }
