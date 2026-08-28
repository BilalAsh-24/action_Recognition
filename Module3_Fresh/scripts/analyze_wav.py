"""Objective analysis of the single generated WAV. Read-only."""
import json, sys
from pathlib import Path
import numpy as np, soundfile as sf, librosa
sys.path.insert(0, str(Path(__file__).resolve().parent)); import mmcfg as C

y, sr = sf.read(C.WAV_OUT, always_2d=True)
ch = y.shape[1]; y = y[:, 0].astype(np.float64)
N = len(y); dur = N / sr
AW = C.ACTION_IN_CLIP                      # action window inside the generated clip
A = dict(zip(("s","e"), (int(AW[0]*sr), int(AW[1]*sr))))

R = {"file": str(C.WAV_OUT.relative_to(C.ROOT))}
R["1_duration_s"] = round(dur, 6)
R["2_sample_rate"] = sr
R["3_channels"] = ch
R["4_rms"] = float(np.sqrt(np.mean(y**2)))
R["5_peak"] = float(np.abs(y).max())
R["5_peak_dbfs"] = float(20*np.log10(max(np.abs(y).max(), 1e-12)))
R["6_clipping"] = {"samples_at_or_over_1.0": int(np.sum(np.abs(y) >= 1.0)),
                   "samples_over_0.99": int(np.sum(np.abs(y) > 0.99)), "clipped": False}
R["6_clipping"]["clipped"] = R["6_clipping"]["samples_at_or_over_1.0"] > 0
R["7_nan_inf"] = {"nan": int(np.isnan(y).sum()), "inf": int(np.isinf(y).sum()),
                  "all_finite": bool(np.isfinite(y).all())}
R["crest_factor_db"] = round(R["5_peak_dbfs"] - 20*np.log10(max(R["4_rms"],1e-12)), 2)

# ---- envelope -------------------------------------------------------------
hop = 128
rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
t = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
db = 20*np.log10(np.maximum(rms, 1e-12) / max(rms.max(), 1e-12))
floor = float(np.percentile(rms, 10))
thr = floor + 0.10*(rms.max() - floor)          # acoustic threshold
active = rms > thr

R["8_acoustic_onset_s"] = round(float(t[np.argmax(active)]), 4) if active.any() else None
R["9_acoustic_offset_s"] = round(float(t[len(active)-1-np.argmax(active[::-1])]), 4) if active.any() else None
R["envelope"] = {"noise_floor_p10": floor, "threshold": float(thr),
                 "env_peak": float(rms.max()),
                 "db_p5": round(float(np.percentile(db,5)),2), "db_p50": round(float(np.percentile(db,50)),2),
                 "db_p95": round(float(np.percentile(db,95)),2),
                 "dynamic_range_p95_p5_db": round(float(np.percentile(db,95)-np.percentile(db,5)),2)}

# ---- events: contiguous active runs, merged across short gaps ---------------
MIN_EV, MERGE_GAP = 0.040, 0.080
idx = np.flatnonzero(np.diff(np.concatenate(([0], active.view(np.int8), [0]))))
runs = [[t[a], t[min(b, len(t)-1)]] for a, b in zip(idx[::2], idx[1::2])]
merged = []
for r in runs:
    if merged and r[0] - merged[-1][1] < MERGE_GAP: merged[-1][1] = r[1]
    else: merged.append(list(r))
events = [e for e in merged if e[1]-e[0] >= MIN_EV]
durs = [round(e[1]-e[0], 4) for e in events]
gaps = [round(events[i+1][0]-events[i][1], 4) for i in range(len(events)-1)]

R["10_event_count"] = len(events)
R["11_event_durations_s"] = durs
R["11_event_duration_stats"] = ({"mean": round(float(np.mean(durs)),4), "min": min(durs),
                                 "max": max(durs)} if durs else None)
R["12_event_spacing_s"] = gaps
R["12_event_spacing_stats"] = ({"mean": round(float(np.mean(gaps)),4), "min": min(gaps),
                                "max": max(gaps)} if gaps else None)
R["events_detail"] = [{"idx": i+1, "start_s": round(e[0],3), "end_s": round(e[1],3),
                       "dur_s": round(e[1]-e[0],3),
                       "in_action_window": bool(e[1] > AW[0] and e[0] < AW[1]),
                       "peak": float(np.abs(y[int(e[0]*sr):int(e[1]*sr)]).max()) if e[1]>e[0] else 0.0}
                      for i, e in enumerate(events)]

# ---- 13 spectral ------------------------------------------------------------
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
def band(lo, hi):
    f = librosa.fft_frequencies(sr=sr, n_fft=2048)
    m = (f >= lo) & (f < hi)
    return float(100*np.sum(S[m]**2)/max(np.sum(S**2), 1e-20))
R["13_spectral"] = {
    "centroid_hz_mean": round(float(librosa.feature.spectral_centroid(S=S, sr=sr).mean()),1),
    "centroid_hz_std": round(float(librosa.feature.spectral_centroid(S=S, sr=sr).std()),1),
    "rolloff95_hz": round(float(librosa.feature.spectral_rolloff(S=S, sr=sr, roll_percent=.95).mean()),1),
    "bandwidth_hz": round(float(librosa.feature.spectral_bandwidth(S=S, sr=sr).mean()),1),
    "flatness_mean": round(float(librosa.feature.spectral_flatness(S=S).mean()),5),
    "zcr_mean": round(float(librosa.feature.zero_crossing_rate(y, frame_length=1024, hop_length=hop).mean()),5),
    "frame_to_frame_self_similarity": round(float(np.mean(np.sum(
        (S/(np.linalg.norm(S,axis=0,keepdims=True)+1e-12))[:, :-1] *
        (S/(np.linalg.norm(S,axis=0,keepdims=True)+1e-12))[:, 1:], axis=0))),4),
    "energy_pct_0_200hz": round(band(0,200),2), "energy_pct_200_1k": round(band(200,1000),2),
    "energy_pct_1k_4k": round(band(1000,4000),2), "energy_pct_4k_8k": round(band(4000,8000),2),
    "energy_pct_8k_16k": round(band(8000,16000),2), "energy_pct_16k_22k": round(band(16000,22050),2)}

# ---- 14 silence -------------------------------------------------------------
R["14_silence"] = {
    "pct_frames_below_-20db": round(float(100*np.mean(db < -20)),2),
    "pct_frames_below_-30db": round(float(100*np.mean(db < -30)),2),
    "pct_frames_below_-40db": round(float(100*np.mean(db < -40)),2),
    "pct_frames_below_acoustic_threshold": round(float(100*np.mean(~active)),2),
    "true_digital_silence_pct": round(float(100*np.mean(y == 0.0)),4)}

# ---- 15 activity through the action window ----------------------------------
seg = {"pre_0_to_%.2f" % AW[0]: (0, A["s"]), "ACTION_%.2f_%.2f" % AW: (A["s"], A["e"]),
       "post_%.2f_end" % AW[1]: (A["e"], N)}
R["15_action_window_activity"] = {"action_window_in_clip_s": list(AW),
    "action_window_in_source_s": [C.ACTION_START, C.ACTION_END], "segments": {}}
for k, (a, b) in seg.items():
    s_ = y[a:b]
    fa, fb = int(a/hop), int(b/hop)
    act = active[fa:fb]
    R["15_action_window_activity"]["segments"][k] = {
        "dur_s": round((b-a)/sr,3), "rms": round(float(np.sqrt(np.mean(s_**2))) if len(s_) else 0.0, 6),
        "peak": round(float(np.abs(s_).max()) if len(s_) else 0.0, 6),
        "pct_active": round(float(100*np.mean(act)) if len(act) else 0.0, 2)}
ev_in = [e for e in R["events_detail"] if e["in_action_window"]]
R["15_action_window_activity"]["events_in_action_window"] = len(ev_in)
R["15_action_window_activity"]["longest_gap_inside_action_s"] = round(max(
    [ev_in[i+1]["start_s"]-ev_in[i]["end_s"] for i in range(len(ev_in)-1)] or [0.0]), 3)

# per-second RMS trace
R["per_second_rms"] = [round(float(np.sqrt(np.mean(y[i*sr:min((i+1)*sr,N)]**2))),6)
                       for i in range(int(np.ceil(dur)))]

C.ANA_JSON.write_text(json.dumps(R, indent=2))
print(json.dumps(R, indent=2))
