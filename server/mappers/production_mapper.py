from sqlalchemy.orm import Session
from typing import Dict, Any

def reserve_materials_from_plan(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Maps production_plan changes to inventory_master reservation updates.
    Assumes product consumptions: PRODUCT -> MAT_STEEL_01 (Qty * 5).
    """
    row_data = payload.get("data", {})
    print(row_data)
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
                    'part_no' : f"INV_{target_material}"
                },
                "source_name": "chain_ingestion",
                "updated_by": "chain_worker"
            }
        ],
        "silent": False
    }
    
    return target_payload
