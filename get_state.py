import urllib.request
import json

try:
    url = "http://127.0.0.1:5000/api/state"
    with urllib.request.urlopen(url) as res:
        state = json.loads(res.read().decode("utf-8"))
        print(f"Is Running: {state.get('is_running')}")
        print(f"Current Action: {state.get('current_action')}")
        print(f"Progress: {state.get('progress_percent')}%")
        print("\n--- LOGS ---")
        for log in state.get("logs", []):
            print(f"[{log.get('time')}] [{log.get('type').upper()}] {log.get('message')}")
except Exception as e:
    print("Error fetching state:", str(e))
