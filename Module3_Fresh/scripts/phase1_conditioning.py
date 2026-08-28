"""PHASE 1 - conditioning only: CLIP + Synchformer in bfloat16 on MPS.

Loads FeaturesUtils with tod_vae_ckpt=None so the VAE and vocoder are never
constructed (official constructor flag, no repo modification). Reproduces the
conditioning portion of mmaudio.eval_utils.generate() verbatim and in the same
order, then saves only the four feature tensors and exits.
"""
import gc, json, sys, time
from pathlib import Path
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mmcfg as C

T0 = time.time()
out = {"phase": 1, "role": "conditioning (CLIP + Synchformer)"}

from mmaudio.eval_utils import load_video
from mmaudio.model.utils.features_utils import FeaturesUtils
from mmaudio.ext.synchformer import Synchformer

cfg = C.model_config()
seq_cfg = cfg.seq_cfg

# ---- video: read frames with NO model resident ------------------------------
print(">>> load context clip (video stream only)", flush=True)
video_info = load_video(C.CONTEXT_CLIP, C.DURATION, load_all_frames=False)
clip_frames = video_info.clip_frames.unsqueeze(0)
sync_frames = video_info.sync_frames.unsqueeze(0)
actual_duration = video_info.duration_sec
seq_cfg.duration = actual_duration
LAT, CLP, SYN = seq_cfg.latent_seq_len, seq_cfg.clip_seq_len, seq_cfg.sync_seq_len
print(f"    clip_frames {tuple(clip_frames.shape)}  sync_frames {tuple(sync_frames.shape)}")
print(f"    requested {C.DURATION}s -> actual {actual_duration:.4f}s  fps {video_info.fps}")
print(f"    seq lengths: latent {LAT}  clip {CLP}  sync {SYN}  sr {seq_cfg.sampling_rate}")
out["video"] = {"path": str(C.CONTEXT_CLIP.relative_to(C.ROOT)),
                "requested_duration_s": C.DURATION,
                "actual_duration_s": round(actual_duration, 6),
                "orig_fps": str(video_info.fps),
                "clip_frames_shape": list(clip_frames.shape),
                "sync_frames_shape": list(sync_frames.shape)}
out["seq_cfg"] = {"latent_seq_len": LAT, "clip_seq_len": CLP, "sync_seq_len": SYN,
                  "sampling_rate": seq_cfg.sampling_rate,
                  "num_audio_frames": seq_cfg.num_audio_frames}
del video_info
gc.collect()

# ---- conditioning models ONLY ----------------------------------------------
print("\n>>> construct FeaturesUtils(enable_conditions=True, tod_vae_ckpt=None)", flush=True)
t0 = time.time()
fu = FeaturesUtils(tod_vae_ckpt=None, synchformer_ckpt=cfg.synchformer_ckpt,
                   enable_conditions=True, mode=cfg.mode,
                   bigvgan_vocoder_ckpt=None, need_vae_encoder=False)
fu = fu.to(C.DEVICE, C.DTYPE_COND).eval()
load_s = time.time() - t0

assert fu.tod is None, "VAE/vocoder unexpectedly constructed in the conditioning phase"
assert fu.clip_model is not None and fu.synchformer is not None
ver = C.check_module(fu, "FeaturesUtils(conditions)", C.DTYPE_COND)
ver["clip_params_M"] = round(sum(p.numel() for p in fu.clip_model.parameters()) / 1e6, 2)
ver["synchformer_params_M"] = round(sum(p.numel() for p in fu.synchformer.parameters()) / 1e6, 2)
ver["tod_is_none"] = True
ver["load_s"] = round(load_s, 2)
print(f"    {ver}", flush=True)
out["verification"] = ver

# ---- official generate() conditioning body, same calls, same order ----------
print("\n>>> extract conditioning (official order: clip -> sync -> text -> negative)", flush=True)
t0 = time.time()
with torch.inference_mode():
    clip_video = clip_frames.to(C.DEVICE, C.DTYPE_COND, non_blocking=True)
    clip_features = fu.encode_video_with_clip(clip_video, batch_size=1 * C.CLIP_BS_MULT)

    sync_video = sync_frames.to(C.DEVICE, C.DTYPE_COND, non_blocking=True)
    sync_features = fu.encode_video_with_sync(sync_video, batch_size=1 * C.SYNC_BS_MULT)

    text_features = fu.encode_text([C.PROMPT])
    negative_text_features = fu.encode_text([C.NEGATIVE])
torch.mps.synchronize()
extract_s = time.time() - t0

feats = {"clip": clip_features, "sync": sync_features,
         "text": text_features, "negative_text": negative_text_features}
out["features"] = {}
for k, v in feats.items():
    fin = bool(torch.isfinite(v).all())
    print(f"    {k+'_features':<24} {tuple(v.shape)} {v.dtype} finite={fin}")
    out["features"][k] = {"shape": list(v.shape), "dtype": str(v.dtype), "finite": fin,
                          "absmax": round(float(v.float().abs().max()), 6)}
    assert fin, f"{k} features contain NaN/Inf"

assert clip_features.shape[1] == CLP, f"clip len {clip_features.shape[1]} != {CLP}"
assert sync_features.shape[1] == SYN, f"sync len {sync_features.shape[1]} != {SYN}"

# ---- hand off as float32 on CPU (phase 2 runs the diffusion path in float32) --
payload = {k: v.detach().float().cpu() for k, v in feats.items()}
payload["meta"] = {"latent_seq_len": LAT, "clip_seq_len": CLP, "sync_seq_len": SYN,
                   "sampling_rate": seq_cfg.sampling_rate,
                   "actual_duration_s": actual_duration}
torch.save(payload, C.FEATURES)
out["handoff"] = {"file": str(C.FEATURES.relative_to(C.ROOT)),
                  "saved_dtype": "torch.float32", "saved_device": "cpu",
                  "bytes": C.FEATURES.stat().st_size,
                  "note": "upcast bf16 -> fp32 at the phase boundary; phase 2 is float32"}

del fu, clip_video, sync_video, clip_frames, sync_frames, feats, payload
gc.collect(); torch.mps.empty_cache(); gc.collect()
resid = {c.__name__: sum(1 for o in gc.get_objects() if type(o) is c)
         for c in (Synchformer, FeaturesUtils)}
print(f"\n    residency after free: {resid}")
out["residency_after_free"] = resid

out["timing_s"] = {"model_load": round(load_s, 2), "extract": round(extract_s, 2),
                   "phase_total": round(time.time() - T0, 2)}
print(json.dumps({"PHASE1_RESULT": out}))
