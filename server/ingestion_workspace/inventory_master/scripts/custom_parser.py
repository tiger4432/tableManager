def parse_file(file_path):
    import csv
    results = []
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row['PROD_LINE'] = 1
            results.append(row)
    return results