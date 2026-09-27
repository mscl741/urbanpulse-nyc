from pathlib import Path
import urllib.request
import json

env = {}
for line in Path(r"C:\Users\burni\Projects\urbanpulse-nyc\.env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env[k.strip()] = v.strip().strip('"').strip("'")

key = env.get("GEMINI_API_KEY", "")
print(f"ACTIVE_AI={env.get('ACTIVE_AI')}")
print(f"prefix={key[:4]} len={len(key)}")
url = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-2.0-flash:generateContent?key={key}"
)
body = json.dumps({"contents": [{"parts": [{"text": "Reply OK"}]}]}).encode()
req = urllib.request.Request(
    url, data=body, headers={"Content-Type": "application/json"}, method="POST"
)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        print(f"SMOKE=PASS status={r.status} reply={text[:80]!r}")
except Exception as e:
    body_err = e.read().decode(errors="replace")[:600] if hasattr(e, "read") else str(e)
    print(f"SMOKE=FAIL code={getattr(e, 'code', None)} body={body_err}")
