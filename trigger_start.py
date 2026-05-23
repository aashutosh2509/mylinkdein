import urllib.request
import json

url = "http://127.0.0.1:5000/api/start"
data = {
    "note_template": "Hello {FirstName}, I would like to connect.",
    "send_with_note": False,
    "delay_min": 10,
    "delay_max": 20,
    "daily_limit": 1
}

req = urllib.request.Request(
    url,
    data=json.dumps(data).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(req) as res:
        response = res.read().decode("utf-8")
        print("Trigger Response:", response)
except Exception as e:
    print("Error triggering start:", str(e))
