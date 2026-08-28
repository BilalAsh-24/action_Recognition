"""Orchestrator for the MMAudio first-generation experiment.

Runs phases 1-3 as fully separate subprocesses so the OS reclaims all memory
between them, under a global memory guard that hard-aborts at 1.5 GB available.
ONE generation attempt: any abort or failure stops the run permanently.
"""
import json, os, signal, subprocess, sys, threading, time
from pathlib import Path
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mmcfg as C

PY_EXE = str(C.ROOT / "models" / "venv-mmaudio-fresh" / "bin" / "python")
ABORT_GB = 1.5
MAX_SWAP_GROWTH_GB = 6.0
SAMPLE_S = 0.05

vm0, sw0 = psutil.virtual_memory(), psutil.swap_memory()
MEM = {
    "guard_abort_available_gb": ABORT_GB,
    "guard_max_swap_growth_gb": MAX_SWAP_GROWTH_GB,
    "baseline_used_gb": round(vm0.used / 1e9, 3),
    "baseline_available_gb": round(vm0.available / 1e9, 3),
    "baseline_swap_gb": round(sw0.used / 1e9, 3),
    "total_gb": round(vm0.total / 1e9, 3),
    "peak_used_gb": 0.0, "min_available_gb": 1e9, "peak_swap_gb": 0.0,
    "breach": None, "killed": False, "per_phase": {},
}
_state = {"child": None, "phase": None, "stop": False}
_lock = threading.Lock()


def monitor():
    while not _state["stop"]:
        vm, sw = psutil.virtual_memory(), psutil.swap_memory()
        u, a, s = vm.used / 1e9, vm.available / 1e9, sw.used / 1e9
        with _lock:
            MEM["peak_used_gb"] = max(MEM["peak_used_gb"], u)
            MEM["min_available_gb"] = min(MEM["min_available_gb"], a)
            MEM["peak_swap_gb"] = max(MEM["peak_swap_gb"], s)
            ph = _state["phase"]
            if ph is not None:
                p = MEM["per_phase"].setdefault(
                    ph, {"peak_used_gb": 0.0, "min_available_gb": 1e9, "peak_swap_gb": 0.0})
                p["peak_used_gb"] = max(p["peak_used_gb"], u)
                p["min_available_gb"] = min(p["min_available_gb"], a)
                p["peak_swap_gb"] = max(p["peak_swap_gb"], s)
            growth = s - MEM["baseline_swap_gb"]
            if MEM["breach"] is None and (a < ABORT_GB or growth > MAX_SWAP_GROWTH_GB):
                MEM["breach"] = (f"available {a:.2f} GB < {ABORT_GB} GB (phase {ph})" if a < ABORT_GB
                                 else f"swap growth {growth:.2f} GB > {MAX_SWAP_GROWTH_GB} GB (phase {ph})")
                ch = _state["child"]
                if ch and ch.poll() is None:
                    try:
                        ch.send_signal(signal.SIGTERM); MEM["killed"] = True
                    except Exception as e:
                        MEM["kill_error"] = str(e)
        time.sleep(SAMPLE_S)


def run_phase(n, script):
    print(f"\n{'='*74}\nPHASE {n}: {script}\n{'='*74}", flush=True)
    _state["phase"] = n
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
    t0 = time.time()
    ch = subprocess.Popen([PY_EXE, str(C.ROOT / "scripts" / script)], cwd=str(C.ROOT),
                          env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    _state["child"] = ch
    lines, result = [], None
    for line in ch.stdout:
        lines.append(line.rstrip())
        if line.startswith('{"PHASE'):
            result = json.loads(line)[f"PHASE{n}_RESULT"]
        else:
            print(line, end="", flush=True)
    rc = ch.wait()
    _state["child"] = None
    _state["phase"] = None
    wall = round(time.time() - t0, 2)
    MEM["per_phase"].setdefault(n, {})["wall_s"] = wall
    print(f"--- phase {n} exit={rc} wall={wall}s ---", flush=True)
    if rc != 0 or result is None:
        return False, {"exit_code": rc, "tail": lines[-25:]}
    return True, result


mt = threading.Thread(target=monitor, daemon=True); mt.start()
print(f"memory guard armed: hard abort at {ABORT_GB} GB available", flush=True)
print(f"baseline: used {MEM['baseline_used_gb']:.2f} GB  "
      f"available {MEM['baseline_available_gb']:.2f} GB  "
      f"swap {MEM['baseline_swap_gb']:.2f} GB", flush=True)

report = {
    "run": "drinking_mmaudio_v1", "generations": 1,
    "action": {"label": C.ACTION, "start_s": C.ACTION_START, "end_s": C.ACTION_END,
               "duration_s": round(C.ACTION_END - C.ACTION_START, 3),
               "source": "Module 2 resolved_actions (confirmed, 3 supporting windows)"},
    "video": {"source": str(C.SOURCE_VIDEO.relative_to(C.ROOT)),
              "context_window_s": [C.CONTEXT_START, C.CONTEXT_END],
              "context_clip": str(C.CONTEXT_CLIP.relative_to(C.ROOT)),
              "action_within_context_s": list(C.ACTION_IN_CLIP),
              "audio_stream_used": False},
    "model": {"variant": C.VARIANT, "mode": C.MODE, "device": C.DEVICE,
              "net_ckpt": str(C.NET_CKPT.relative_to(C.ROOT)),
              "vae_ckpt": str(C.VAE_CKPT.relative_to(C.ROOT)),
              "synchformer_ckpt": str(C.SYNC_CKPT.relative_to(C.ROOT)),
              "clip": "apple/DFN5B-CLIP-ViT-H-14-384 (HF cache)",
              "vocoder": "nvidia/bigvgan_v2_44khz_128band_512x (HF cache)"},
    "precision": {"clip_synchformer": str(C.DTYPE_COND),
                  "diffusion": str(C.DTYPE_DIFFUSION), "decode": str(C.DTYPE_DECODE),
                  "float16_used": False},
    "sampler": {"seed": C.SEED, "num_steps": C.NUM_STEPS, "cfg_strength": C.CFG_STRENGTH,
                "inference_mode": C.INFERENCE_MODE, "min_sigma": C.MIN_SIGMA,
                "clip_batch_multiplier": C.CLIP_BS_MULT,
                "sync_batch_multiplier": C.SYNC_BS_MULT},
    "prompt": {"text": C.PROMPT, "negative_text": C.NEGATIVE},
    "phases": {}, "status": "INCOMPLETE"}
try:
    for n, script in [(1, "phase1_conditioning.py"), (2, "phase2_diffusion.py"),
                      (3, "phase3_decode.py")]:
        ok, res = run_phase(n, script)
        report["phases"][f"phase{n}"] = res
        if not ok:
            report["status"] = "ABORTED_MEMORY" if MEM["breach"] else "FAILED"
            report["failed_phase"] = n
            break
    else:
        report["status"] = "SUCCESS"
finally:
    _state["stop"] = True; mt.join(timeout=2)
    sw = psutil.swap_memory()
    MEM["final_swap_gb"] = round(sw.used / 1e9, 3)
    MEM["swap_growth_gb"] = round(MEM["peak_swap_gb"] - MEM["baseline_swap_gb"], 3)
    for k in ("peak_used_gb", "min_available_gb", "peak_swap_gb"):
        MEM[k] = round(MEM[k], 3)
    for p in MEM["per_phase"].values():
        for k in ("peak_used_gb", "min_available_gb", "peak_swap_gb"):
            if k in p: p[k] = round(p[k], 3)
    report["memory"] = MEM

print(f"\n{'='*74}\nSTATUS: {report['status']}")
print(f"baseline used {MEM['baseline_used_gb']:.2f} / available {MEM['baseline_available_gb']:.2f}"
      f" / swap {MEM['baseline_swap_gb']:.2f} GB")
print(f"peak used {MEM['peak_used_gb']:.2f} GB   min available {MEM['min_available_gb']:.2f} GB")
print(f"peak swap {MEM['peak_swap_gb']:.2f} GB   swap growth {MEM['swap_growth_gb']:.2f} GB")
print(f"breach: {MEM['breach']}   killed: {MEM['killed']}")
C.GEN_JSON.write_text(json.dumps(report, indent=2))
print(f"wrote {C.GEN_JSON}")
sys.exit(0 if report["status"] == "SUCCESS" else 1)
