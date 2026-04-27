import pandas as pd
import io
import random
def parse_file(file_path):
    import csv
    results = []
    if '.csv' in file_path:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row['PROD_LINE'] = 1
                results.append(row)
    elif '.log' in file_path:
        df = pd.read_table(file_path, sep='\t')
        df['unit_price'] = df['part_no'].apply(lambda x : random.randint(1, 100))
        return df.to_dict(orient='records')
                
    return results