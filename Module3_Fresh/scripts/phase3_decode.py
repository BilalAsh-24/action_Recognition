"""PHASE 3 - decode only: VAE decoder + BigVGAN v2 in float32 on MPS.

FeaturesUtils(enable_conditions=False) so CLIP and Synchformer are never
constructed. Uses the official decode()/vocode() methods, then writes exactly
one WAV.
"""
import gc, json, sys, time
from pathlib import Path
import numpy as np
import torch
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mmcfg as C

T0 = time.time()
out = {"phase": 3, "role": "decode (VAE decoder + BigVGAN vocoder)"}

from mmaudio.model.utils.features_utils import FeaturesUtils

cfg = C.model_config()
blob = torch.load(C.LATENT, map_location="cpu", weights_only=False)
meta = blob["meta"]
SR = meta["sampling_rate"]
x1 = blob["x1"].to(C.DEVICE, C.DTYPE_DECODE)
print(f">>> latent {tuple(x1.shape)} loaded, sr {SR}", flush=True)

print(">>> construct FeaturesUtils(enable_conditions=False, tod_vae_ckpt=v1-44)", flush=True)
t0 = time.time()
fu = FeaturesUtils(tod_vae_ckpt=cfg.vae_path, synchformer_ckpt=None,
                   enable_conditions=False, mode=cfg.mode,
                   bigvgan_vocoder_ckpt=cfg.bigvgan_16k_path, need_vae_encoder=False)
fu = fu.to(C.DEVICE, C.DTYPE_DECODE).eval()
load_s = time.time() - t0
assert fu.clip_model is None and fu.synchformer is None, "conditioning models leaked into phase 3"
assert fu.tod is not None
assert not hasattr(fu.tod.vae, "encoder"), "VAE encoder was not dropped"
ver = C.check_module(fu, "FeaturesUtils(decode)", C.DTYPE_DECODE)
ver["vae_decoder_params_M"] = round(sum(p.numel() for p in fu.tod.vae.parameters()) / 1e6, 2)
ver["vocoder_params_M"] = round(sum(p.numel() for p in fu.tod.vocoder.parameters()) / 1e6, 2)
ver["clip_is_none"] = True; ver["synchformer_is_none"] = True
ver["load_s"] = round(load_s, 2)
print(f"    {ver}", flush=True)
out["verification"] = ver

t0 = time.time()
with torch.inference_mode():
    spec = fu.decode(x1)
    audio = fu.vocode(spec)
torch.mps.synchronize()
dec_s = time.time() - t0
print(f"    decode+vocode {dec_s:.2f}s  spec {tuple(spec.shape)}  audio {tuple(audio.shape)}")
out["spec_shape"] = list(spec.shape)
out["audio_shape"] = list(audio.shape)

assert not C.WAV_OUT.exists(), f"refusing to overwrite existing {C.WAV_OUT}"
a = audio.float().cpu()[0].numpy()          # official: audios.float().cpu()[0]
if a.ndim > 1:
    a = a[0] if a.shape[0] <= 2 else a.reshape(-1)
finite = bool(np.isfinite(a).all())
peak = float(np.abs(a).max())
n_over = int(np.sum(np.abs(a) > 1.0))
print(f"    raw float: samples {a.shape[0]}  peak {peak:.6f}  >|1.0| {n_over}  finite {finite}")
assert finite, "generated audio contains NaN/Inf"
out["raw_float"] = {"samples": int(a.shape[0]), "peak": peak, "samples_over_1": n_over,
                    "finite": finite, "rms": float(np.sqrt(np.mean(a**2))),
                    "duration_s": round(a.shape[0] / SR, 6)}

pcm = a if n_over == 0 else np.clip(a, -1.0, 1.0)
sf.write(C.WAV_OUT, pcm.astype(np.float32), SR, subtype="PCM_16")
print(f"    wrote {C.WAV_OUT}")
out["wav"] = {"path": str(C.WAV_OUT.relative_to(C.ROOT)), "sample_rate": SR,
              "subtype": "PCM_16", "channels": 1,
              "clipped_before_write": n_over > 0,
              "bytes": C.WAV_OUT.stat().st_size}

del fu, spec, audio, x1
gc.collect(); torch.mps.empty_cache(); gc.collect()
out["timing_s"] = {"model_load": round(load_s, 2), "decode_vocode": round(dec_s, 2),
                   "phase_total": round(time.time() - T0, 2)}
print(json.dumps({"PHASE3_RESULT": out}))
