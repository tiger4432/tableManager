import os
import re

def audit_callbacks(directory):
    patterns = {
        "lambda_connect": r"\.connect\(lambda.*?\)",
        "lambda_single_shot": r"QTimer\.singleShot\(.*?, lambda.*?\)",
        "nested_def": r"def\s+\w+\(.*\):\s*\n\s+def\s+\w+"
    }
    
    results = []
    
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                        lines = content.splitlines()
                        
                        for key, pattern in patterns.items():
                            matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)
                            for match in matches:
                                line_no = content[:match.start()].count('\n') + 1
                                context = lines[line_no-1].strip()
                                results.append({
                                    "file": path,
                                    "line": line_no,
                                    "type": key,
                                    "context": context
                                })
                except:
                    pass
                            
    return results

if __name__ == "__main__":
    client_dir = r"c:\Users\kk980\Developments\assyManager\client"
    audit_results = audit_callbacks(client_dir)
    
    print(f"--- Callback Audit Report ({len(audit_results)} issues found) ---")
    current_file = ""
    for r in audit_results:
        if r['file'] != current_file:
            print(f"\n[File] {r['file']}")
            current_file = r['file']
        print(f"  [{r['line']:4}] {r['type']:20} | {r['context']}")
