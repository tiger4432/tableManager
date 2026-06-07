from sqlalchemy.orm import Session
from typing import Dict, Any

def reserve_materials_from_plan(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Maps production_plan changes to inventory_master reservation updates.
    Assumes product consumptions: PRODUCT -> MAT_STEEL_01 (Qty * 5).
    """
    row_data = payload.get("data", {})
    
    product_code = row_data.get("PRODUCT_CODE", {}).get("value")
    planned_qty = int(row_data.get("PLANNED_QTY", {}).get("value") or 0)
    
    if not product_code:
        return {}
        
    # Target raw material details
    target_material = "MAT_STEEL_01"
    required_qty = planned_qty * 5
    
    # Return formatted payload according to GeneralUpdateBatch schema
    target_payload = {
        "updates": [
            {
                "row_id": f"INV_{target_material}",
                "updates": {
                    "RESERVED_QTY": required_qty
                },
                "source_name": "chain_ingestion",
                "updated_by": "chain_worker"
            }
        ],
        "silent": False
    }
    
    return target_payload
