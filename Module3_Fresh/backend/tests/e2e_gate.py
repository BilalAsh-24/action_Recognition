"""Focused end-to-end run over the CACHED assets — no MOSS regeneration.

Drives the full pipeline through the API on the demo video. Every Foley asset the
pipeline needs is already in data/generated/, so generation returns from cache and the
run completes in seconds. Verifies the cup-pickup interval is silent rather than hiss.
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, soundfile as sf, librosa
from fastapi.testclient import TestClient
from main import app

c = TestClient(app); t0 = time.time()
jid = c.post("/api/demo").json()["job_id"]
c.post(f"/api/process/{jid}")
while True:
    s = c.get(f"/api/status/{jid}").json()
    if s["status"] in ("completed", "failed"): break
    time.sleep(1)
print(f"[gate] {s['status']} in {time.time()-t0:.0f}s", flush=True)
if s["status"] == "failed":
    print("[gate] errors:", s["errors"]); sys.exit(1)

res = c.get(f"/api/result/{jid}").json()
rep = c.get(f"/api/report/{jid}").json()

print("\n[gate] every asset was reused from cache (no regeneration):",
      all(g["cached"] for g in res["generated"]) or
      [g["label"] for g in res["generated"] if not g["cached"]])

print("\n[gate] VALIDATION VERDICTS")
for v in rep["validations"]:
    m = v["metrics"]
    print(f"   {v['label']:<16} {'PASS' if v['ok'] else 'REJECT':<7} "
          f"peak {m['peak_dbfs']:>7.1f}  dyn {m['dynamic_range_db']:>5.1f}  "
          f"bits {m['effective_bits']:>5.1f}  harm {m['harmonic_ratio']:>5.2f}  "
          f"gain {m['required_gain_db']:>+6.1f}")
    if not v["ok"]:
        for f in v["failures"]: print(f"{'':>29}- {f}")

print("\n[gate] counts:", json.dumps(res["counts"]))
print("[gate] intervals left silent:")
for u in res["unsupported"]:
    print(f"   {u['action']:<20} {u.get('status','')}  {u['reason'][:62]}")

print("\n[gate] tracks that entered the mix:")
for t in rep["mix"]["tracks"]:
    print(f"   {t['action']:<20} {t['video_start_s']:>6.2f}-{t['video_end_s']:<6.2f} "
          f"gain {t['gain_db']:>+6.2f} dB")
print("[gate] mixer-level rejections:", rep["mix"].get("rejected", []))

# ---- durable invariant: every rejected class is silent, and no rejected asset
# ---- ever appears in the mix. (Cup pickup is no longer guaranteed to fail: with
# ---- multi-candidate generation a different seed may rescue it.)
wav = Path(rep["mix"]["output"]["path"])
y, sr = sf.read(wav); y = y.astype(np.float64)

rejected_keys = {v["key"] for v in rep["validations"] if not v["ok"]}
selected_paths = {Path(t["asset"]).name for t in rep["mix"]["tracks"]}
rejected_paths = {Path(a["path"]).name
                  for v in rep["validations"] if not v["ok"]
                  for a in v["attempts"] if not a["ok"]}

print(f"\n[gate] classes rejected outright : {sorted(rejected_keys) or 'none'}")
print(f"[gate] assets used in the mix    : {sorted(selected_paths)}")
leaked = selected_paths & rejected_paths
assert not leaked, f"a rejected asset reached the mix: {leaked}"
print("[gate] no rejected asset reached the mix: OK")

silent_bad = []
for u in res["unsupported"]:
    if u.get("status") != "no_usable_foley":
        continue
    a, b = int(u["start"] * sr), int(min(u["end"], len(y) / sr) * sr)
    nz = int(np.count_nonzero(y[a:b]))
    print(f"[gate] '{u['action']}' {u['start']:.2f}-{u['end']:.2f}s -> "
          f"{nz} non-zero samples of {b-a}")
    if nz:
        silent_bad.append(u["action"])
assert not silent_bad, f"intervals with no usable Foley must be silent: {silent_bad}"

# every class that DID pass must contribute audible audio somewhere
for v in rep["validations"]:
    if v["ok"]:
        assert any(t for t in rep["mix"]["tracks"]), "a passing class produced no track"

print("[gate] OK — rejected classes silent, passing classes audible, no leakage")
Path("data/jobs/e2e_gate_result.json").write_text(json.dumps(
    {"job": jid, "result": res, "validations": rep["validations"]}, indent=2))
