import pandas as pd
from typing import List, Dict, Any

def payloads_to_df(payloads: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Converts a list of nested database outbox payload dictionaries into a flat Pandas DataFrame.
    Filters nested JSONB structured cells: { col_name: { "value": x } } -> flat row { col_name: x }.
    """
    if not payloads:
        return pd.DataFrame()
        
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
