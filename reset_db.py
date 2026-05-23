import json
import os

db_path = "database.json"
if os.path.exists(db_path):
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    for contact in data:
        contact["status"] = "Not Started"
        contact["date_sent"] = None
        contact["date_accepted"] = None
        contact["logs"] = None
        
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print("Database reset successfully.")
else:
    print("Database file not found.")
