"""PHASE 2 - diffusion only: MMAudio small_44k in float32 on MPS.

No FeaturesUtils is constructed at all. Reproduces the sampling portion of
mmaudio.eval_utils.generate() verbatim, preserving the official RNG ordering:
the seeded generator's FIRST and ONLY consumer is x0, created before
preprocess_conditions, exactly as upstream does it.
"""
import gc, json, sys, time, warnings
from pathlib import Path
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mmcfg as C

T0 = time.time()
out = {"phase": 2, "role": "diffusion (MMAudio net only)"}

from mmaudio.model.flow_matching import FlowMatching
from mmaudio.model.networks import MMAudio, get_my_mmaudio
from mmaudio.model.utils.features_utils import FeaturesUtils

cfg = C.model_config()

# ---- conditioning from phase 1 ---------------------------------------------
payload = torch.load(C.FEATURES, map_location="cpu", weights_only=False)
meta = payload["meta"]
LAT, CLP, SYN = meta["latent_seq_len"], meta["clip_seq_len"], meta["sync_seq_len"]
clip_features = payload["clip"].to(C.DEVICE, C.DTYPE_DIFFUSION)
sync_features = payload["sync"].to(C.DEVICE, C.DTYPE_DIFFUSION)
text_features = payload["text"].to(C.DEVICE, C.DTYPE_DIFFUSION)
negative_text_features = payload["negative_text"].to(C.DEVICE, C.DTYPE_DIFFUSION)
del payload
print(f">>> conditioning loaded: latent {LAT} clip {CLP} sync {SYN}", flush=True)
out["conditioning_in"] = {k: list(v.shape) for k, v in
                          [("clip", clip_features), ("sync", sync_features),
                           ("text", text_features), ("negative_text", negative_text_features)]}

# prove no conditioning model is instantiated in this phase
fu_empty = FeaturesUtils(tod_vae_ckpt=None, synchformer_ckpt=None, enable_conditions=False,
                         mode=cfg.mode, bigvgan_vocoder_ckpt=None, need_vae_encoder=False)
n_empty = sum(p.numel() for p in fu_empty.parameters())
assert fu_empty.clip_model is None and fu_empty.synchformer is None and fu_empty.tod is None
assert n_empty == 0, f"expected an empty FeaturesUtils, got {n_empty} params"
out["featuresutils_empty_params"] = n_empty
del fu_empty; gc.collect()

# ---- diffusion network only -------------------------------------------------
print(">>> load MMAudio small_44k (float32, mps)", flush=True)
t0 = time.time()
net: MMAudio = get_my_mmaudio(cfg.model_name).to(C.DEVICE, C.DTYPE_DIFFUSION).eval()
net.load_weights(torch.load(cfg.model_path, map_location=C.DEVICE, weights_only=True))
net.update_seq_lengths(LAT, CLP, SYN)
load_s = time.time() - t0
ver = C.check_module(net, "MMAudio net small_44k", C.DTYPE_DIFFUSION)
ver["load_s"] = round(load_s, 2)
print(f"    {ver}", flush=True)
out["verification"] = ver

# ---- official RNG ordering: seed, then x0 as the generator's ONLY consumer ---
rng = torch.Generator(device=C.DEVICE)
rng.manual_seed(C.SEED)
x0 = torch.randn(1, net.latent_seq_len, net.latent_dim,
                 device=C.DEVICE, dtype=C.DTYPE_DIFFUSION, generator=rng)
print(f"    x0 {tuple(x0.shape)} mean {x0.mean().item():+.6f} std {x0.std().item():.6f}")
out["rng"] = {"seed": C.SEED, "device": C.DEVICE, "generator_consumers": ["x0"],
              "x0_shape": list(x0.shape), "x0_mean": float(x0.mean()),
              "x0_std": float(x0.std()), "x0_sum": float(x0.sum())}

# ---- official sampling body -------------------------------------------------
preprocessed_conditions = net.preprocess_conditions(clip_features, sync_features, text_features)
empty_conditions = net.get_empty_conditions(1, negative_text_features=negative_text_features)
fm = FlowMatching(min_sigma=C.MIN_SIGMA, inference_mode=C.INFERENCE_MODE, num_steps=C.NUM_STEPS)
cfg_ode_wrapper = lambda t, x: net.ode_wrapper(t, x, preprocessed_conditions,
                                               empty_conditions, C.CFG_STRENGTH)

print(f"\n>>> ONE generation | {C.INFERENCE_MODE} {C.NUM_STEPS} steps | "
      f"cfg {C.CFG_STRENGTH} | seed {C.SEED} <<<", flush=True)
t0 = time.time()
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    with torch.inference_mode():
        x1 = fm.to_data(cfg_ode_wrapper, x0)
        x1 = net.unnormalize(x1)
    torch.mps.synchronize()
    caught = sorted({str(x.message)[:200] for x in w})
diff_s = time.time() - t0
fin = bool(torch.isfinite(x1).all())
print(f"    diffusion {diff_s:.2f}s  x1 {tuple(x1.shape)} finite={fin} "
      f"absmax={x1.abs().max().item():.4f}")
assert fin, "latent contains NaN/Inf"
out["latent"] = {"shape": list(x1.shape), "finite": fin,
                 "mean": float(x1.mean()), "std": float(x1.std()),
                 "absmax": float(x1.abs().max())}
out["warnings"] = caught

torch.save({"x1": x1.detach().float().cpu(), "meta": meta}, C.LATENT)
out["handoff"] = {"file": str(C.LATENT.relative_to(C.ROOT)),
                  "bytes": C.LATENT.stat().st_size}

del net, preprocessed_conditions, empty_conditions, cfg_ode_wrapper, fm, x0, x1, rng
del clip_features, sync_features, text_features, negative_text_features
gc.collect(); torch.mps.empty_cache(); gc.collect()
resid = {MMAudio.__name__: sum(1 for o in gc.get_objects() if type(o) is MMAudio)}
print(f"    residency after free: {resid}")
out["residency_after_free"] = resid

out["timing_s"] = {"model_load": round(load_s, 2), "diffusion": round(diff_s, 2),
                   "phase_total": round(time.time() - T0, 2)}
print(json.dumps({"PHASE2_RESULT": out}))
