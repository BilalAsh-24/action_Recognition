#!/usr/bin/env python
"""Module 2 runner — executed INSIDE venv-qwen.

Reuses the validated algorithm from the existing
03-FoleyCrafter-Test/action-recognition/action_recognition.py (windowing, response
parsing, action-head extraction, merging) and from resolve_segments.py (deterministic
boundary resolution). Only the video path is parameterised; no algorithm is rewritten
and neither source file is modified.

    run_module2.py --video PATH --out PATH [--progress PATH]
"""
from __future__ import annotations
import argparse, gc, json, os, sys, time
from pathlib import Path

MODULE2_SRC = Path(__file__).resolve().parents[3] / "03-FoleyCrafter-Test" / "action-recognition"
sys.path.insert(0, str(MODULE2_SRC))

import numpy as np, psutil, torch
import action_recognition as AR          # validated Qwen implementation
import resolve_segments as RS            # validated boundary resolution


def emit(path, **kw):
    if path:
        try:
            Path(path).write_text(json.dumps(kw))
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--progress", default=None)
    ap.add_argument("--min-avail-gb", type=float, default=1.5)
    a = ap.parse_args()
    video = str(Path(a.video).resolve())
    t_all = time.time()

    meta = AR.probe(video)
    dur = float(meta["duration"])
    emit(a.progress, stage="probe", pct=2, detail=f"{dur:.2f}s {meta['width']}x{meta['height']}")

    # VIDEO STREAM ONLY — AR.extract_video_frames uses `-map 0:v:0`
    frames = AR.extract_video_frames(video, AR.TW, AR.TH)
    ftimes = np.linspace(0, dur, len(frames), endpoint=False)
    wins = AR.plan_windows(dur)
    emit(a.progress, stage="frames", pct=6, detail=f"{len(frames)} frames, {len(wins)} windows")

    from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
    MODEL_ID = "Qwen/Qwen2.5-VL-3B-Instruct"
    proc = AutoProcessor.from_pretrained(MODEL_ID)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        MODEL_ID, torch_dtype=torch.bfloat16, device_map=None).to("mps").eval()
    emit(a.progress, stage="model", pct=12, detail="Qwen2.5-VL-3B loaded on MPS")

    from PIL import Image
    out_windows, peak_used = [], 0.0
    for i, (s, e) in enumerate(wins, 1):
        vm = psutil.virtual_memory()
        peak_used = max(peak_used, vm.used / 1e9)
        if vm.available / 1e9 < a.min_avail_gb:
            raise MemoryError(f"available RAM {vm.available/1e9:.2f} GB below "
                              f"{a.min_avail_gb} GB guard at window {i}")
        sel = np.flatnonzero((ftimes >= s) & (ftimes < e))
        if len(sel) == 0:
            continue
        pick = sel[np.linspace(0, len(sel) - 1, AR.FRAMES_PER_WINDOW, dtype=int)]
        imgs = [Image.fromarray(frames[j]) for j in pick]
        msgs = [{"role": "user", "content": [{"type": "video", "video": imgs},
                                             {"type": "text", "text": AR.PROMPT}]}]
        text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = proc(text=[text], videos=[imgs], return_tensors="pt").to("mps")
        with torch.inference_mode():
            out = model.generate(**inputs, max_new_tokens=AR.MAX_NEW_TOKENS, do_sample=False,
                                 temperature=None, top_p=None, top_k=None)
        gen = out[:, inputs.input_ids.shape[1]:]
        raw = proc.batch_decode(gen, skip_special_tokens=True)[0].strip()
        act, ev = AR.parse_response(raw)
        out_windows.append({"window": i, "start": float(s), "end": float(e),
                            "action": act, "evidence": ev,
                            "action_head": AR.action_head(act), "raw": raw,
                            "frames_used": len(sel)})
        del inputs, out, gen
        gc.collect(); torch.mps.empty_cache()
        emit(a.progress, stage="recognition", pct=12 + int(70 * i / len(wins)),
             detail=f"window {i}/{len(wins)}: {act}")

    del model, proc
    gc.collect(); torch.mps.empty_cache()

    merged = AR.merge(out_windows)
    # resolve_boundaries returns (segments, adjustments) — unpack exactly as the
    # validated resolve_segments.main() does.
    resolved_raw, adjustments = RS.resolve_boundaries(merged)
    resolved = RS.flag_suspects(resolved_raw, merged)
    validation = RS.validate(resolved)
    validation["count_preserved"] = (len(resolved) == len(merged))

    payload = {
        "module": "Module 2 - Temporal Action Recognition",
        "model": MODEL_ID, "device": "mps", "dtype": "bfloat16",
        "video": {"path": video, "duration": round(dur, 3),
                  "fps": meta.get("r_frame_rate"), "frame_count": meta.get("nb_frames"),
                  "resolution": f"{meta['width']}x{meta['height']}",
                  "codec": meta.get("codec_name"),
                  "audio_present": meta.get("audio_present"), "audio_used": False},
        "config": {"window_s": AR.WINDOW_S, "stride_s": AR.STRIDE_S,
                   "frames_per_window": AR.FRAMES_PER_WINDOW,
                   "resize": f"{AR.TW}x{AR.TH}", "max_new_tokens": AR.MAX_NEW_TOKENS,
                   "prompt": AR.PROMPT},
        "windows": out_windows, "actions": merged, "resolved_actions": resolved,
        "boundary_resolution": {"adjustments": adjustments, "validation": validation},
        "timing": {"total_wall_s": round(time.time() - t_all, 2)},
        "memory": {"peak_used_gb": round(peak_used, 2)},
    }
    Path(a.out).write_text(json.dumps(payload, indent=2))
    emit(a.progress, stage="done", pct=100, detail=f"{len(resolved)} actions")
    print(json.dumps({"ok": True, "actions": len(resolved), "out": a.out}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        sys.exit(1)
