"""End-to-end via the REAL upload path: new video -> live Qwen Module 2 -> full pipeline."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from main import app

c = TestClient(app); src = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/new_clip_unseen.mp4")
t0 = time.time()
with open(src, "rb") as f:
    up = c.post("/api/upload", files={"file": (src.name, f, "video/mp4")})
assert up.status_code == 200, up.text
d = up.json(); jid = d["job_id"]
print(f"[up] job {jid}  {d['video']['duration_s']}s  {d['video']['width']}x{d['video']['height']}"
      f"  audio={d['video']['has_audio']}", flush=True)
print(f"[up] warnings: {d['warnings']}", flush=True)
c.post(f"/api/process/{jid}")
last = None
while True:
    s = c.get(f"/api/status/{jid}").json()
    k = (s["current_stage"], round(s["progress"]))
    if k != last:
        print(f"[up] {s['progress']:5.1f}%  {s['current_stage']:<20} {s['status']}", flush=True)
        last = k
    if s["status"] in ("completed", "failed"): break
    time.sleep(2)
print(f"[up] finished in {time.time()-t0:.0f}s -> {s['status']}", flush=True)
if s["status"] == "failed":
    print("[up] errors:", s["errors"]); sys.exit(1)
res = c.get(f"/api/result/{jid}").json()
rep = c.get(f"/api/report/{jid}").json()
print("[up] MODULE 2 RAN LIVE — actions found:")
for a in rep["module2"]["actions"]:
    print(f"      {a['start']:>5.2f}-{a['end']:>5.2f}  {a['action']:<24} {a['confidence']}")
print(f"      windows analysed: {rep['module2']['windows']}  model: {rep['module2']['model']}")
print("[up] counts   :", json.dumps(res["counts"]))
print("[up] generated:", [(g['label'], 'cached' if g['cached'] else 'generated') for g in res["generated"]])
print("[up] unsupported:", [u["action"] for u in res["unsupported"]])
print("[up] render   :", json.dumps({k: res["render"][k] for k in
      ('duration_s','video_codec','audio_codec','frames','resolution','audio_sample_rate','audio_channels')}))
print("[up] mix      :", json.dumps({k: res["mix"][k] for k in ('peak_dbfs','clipped_samples','duration_s')}))
print("[up] OK")
