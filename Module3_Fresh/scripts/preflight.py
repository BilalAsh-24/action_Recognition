"""Read-only preflight for the MMAudio fresh environment. Installs nothing, loads no models."""
import json, sys, os
from pathlib import Path
import torch, numpy

HERE = Path(__file__).resolve().parent.parent
FORBIDDEN = ("01-Lip-Reading", "02-Auto-AVSR-Test", "03-FoleyCrafter-Test")
leaks = [p for p in sys.path if any(f in p for f in FORBIDDEN)]

r = {
    "python": sys.version.split()[0],
    "sys_prefix": sys.prefix,
    "torch": torch.__version__,
    "numpy": numpy.__version__,
    "numpy_lt_2_1": tuple(int(x) for x in numpy.__version__.split(".")[:2]) < (2, 1),
    "mps_is_built": torch.backends.mps.is_built(),
    "mps_is_available": torch.backends.mps.is_available(),
    "cuda_available": torch.cuda.is_available(),
    "has_RMSNorm": hasattr(torch.nn, "RMSNorm"),
    "sys_path_leaks": leaks,
    "isolation": "OK" if not leaks else "LEAK",
    "mps_recommended_max_memory_gb": round(torch.mps.recommended_max_memory() / 2**30, 2),
}

# MPS seeded generator — official generate() uses torch.Generator(device=device)
try:
    g = torch.Generator(device="mps"); g.manual_seed(42)
    a = torch.randn(4, 8, device="mps", dtype=torch.float32, generator=g)
    g2 = torch.Generator(device="mps"); g2.manual_seed(42)
    b = torch.randn(4, 8, device="mps", dtype=torch.float32, generator=g2)
    r["mps_generator"] = {"works": True, "reproducible": bool(torch.equal(a, b)),
                          "sum": float(a.sum())}
except Exception as e:
    r["mps_generator"] = {"works": False, "error": f"{type(e).__name__}: {e}"}

# checkpoints
CK = {"net": HERE/"models/weights/mmaudio_small_44k.pth",
      "vae": HERE/"models/ext_weights/v1-44.pth",
      "sync": HERE/"models/ext_weights/synchformer_state_dict.pth"}
r["checkpoints"] = {k: {"exists": v.exists(), "bytes": v.stat().st_size if v.exists() else 0}
                    for k, v in CK.items()}
HF = Path.home()/".cache/huggingface/hub"
r["hf_cache"] = {
    "clip": (HF/"models--apple--DFN5B-CLIP-ViT-H-14-384").exists(),
    "bigvgan_44k": (HF/"models--nvidia--bigvgan_v2_44khz_128band_512x").exists(),
}
# context clip
import av
cp = HERE/"work/context_2.0_10.0.mp4"
with av.open(str(cp)) as c:
    vs = c.streams.video[0]
    r["context_clip"] = {"path": str(cp.relative_to(HERE)), "frames": vs.frames,
                         "fps": str(vs.guessed_rate), "duration_s": float(vs.duration*vs.time_base),
                         "audio_streams": len(c.streams.audio)}
print(json.dumps(r, indent=2))
ok = (r["isolation"] == "OK" and r["mps_is_available"] and r["has_RMSNorm"]
      and r["numpy_lt_2_1"] and all(v["exists"] for v in r["checkpoints"].values())
      and all(r["hf_cache"].values()) and r["mps_generator"].get("reproducible")
      and r["context_clip"]["audio_streams"] == 0)
print("\nPREFLIGHT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
