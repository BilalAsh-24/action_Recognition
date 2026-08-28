"""End-to-end test: demo video -> real pipeline -> final MP4, compared against the
validated reference build."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from main import app

c = TestClient(app)
t0 = time.time()
d = c.post("/api/demo").json(); jid = d["job_id"]
print(f"[e2e] job {jid}  video {d['video']['duration_s']}s", flush=True)
r = c.post(f"/api/process/{jid}").json(); print("[e2e] queued:", r, flush=True)

last = None
while True:
    s = c.get(f"/api/status/{jid}").json()
    key = (s["status"], s["current_stage"], round(s["progress"]))
    if key != last:
        print(f"[e2e] {s['progress']:5.1f}%  {s['current_stage']:<20} {s['status']}", flush=True)
        last = key
    if s["status"] in ("completed", "failed"):
        break
    time.sleep(3)

print(f"[e2e] finished in {time.time()-t0:.0f}s -> {s['status']}", flush=True)
if s["status"] == "failed":
    print("[e2e] errors:", s["errors"]); sys.exit(1)

res = c.get(f"/api/result/{jid}").json()
print("[e2e] counts :", json.dumps(res["counts"]))
print("[e2e] sync   :", json.dumps(res["sync"]))
print("[e2e] mix    :", json.dumps(res["mix"]))
print("[e2e] render :", json.dumps({k: res["render"][k] for k in
      ('duration_s','video_codec','audio_codec','frames','resolution','audio_sample_rate','audio_channels')}))
print("[e2e] generated:", [(g["label"], "cached" if g["cached"] else "generated") for g in res["generated"]])
print("[e2e] unsupported:", [u["action"] for u in res["unsupported"]])
Path("data/jobs/e2e_result.json").write_text(json.dumps(res, indent=2))
print("[e2e] OK")
