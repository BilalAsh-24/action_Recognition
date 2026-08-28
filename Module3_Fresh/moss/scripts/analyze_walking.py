"""Footstep-oriented quality analysis for a generated walking Foley WAV."""
import json, sys
from pathlib import Path
import numpy as np, soundfile as sf, librosa

WAV = Path(sys.argv[1]); OUT = Path(sys.argv[2])
y, sr = sf.read(WAV, always_2d=True); ch = y.shape[1]; y = y[:, 0].astype(np.float64); N = len(y)
R = {"file": str(WAV)}

# --- 7. basic integrity ----------------------------------------------------
rms_all = float(np.sqrt(np.mean(y**2))); pk = float(np.abs(y).max())
R["basic"] = {"sample_rate": sr, "channels": ch, "duration_s": round(N/sr, 6), "samples": N,
              "rms": rms_all, "peak": pk, "peak_dbfs": round(20*np.log10(max(pk,1e-12)), 2),
              "crest_db": round(20*np.log10(pk/rms_all), 2),
              "clipped_samples": int(np.sum(np.abs(y) >= 1.0)),
              "nan": int(np.isnan(y).sum()), "inf": int(np.isinf(y).sum()),
              "all_finite": bool(np.isfinite(y).all())}

# --- 1/8. footstep event detection (transient-oriented) --------------------
hop = 256
env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop, aggregate=np.median)
# Footsteps are >=0.25 s apart at any plausible cadence; require that spacing and a
# level gate so noise-floor ripples are not counted as steps.
MIN_STEP_GAP_S = 0.25
peaks = librosa.util.peak_pick(env, pre_max=8, post_max=8, pre_avg=16, post_avg=16,
                               delta=float(np.percentile(env, 75) * 0.45),
                               wait=int(MIN_STEP_GAP_S*sr/hop))
times = librosa.frames_to_time(peaks, sr=sr, hop_length=hop)
# level gate: keep transients within 30 dB of the loudest one
_pk = np.array([float(np.abs(y[max(0,int((t-0.02)*sr)):min(N,int((t+0.25)*sr))]).max()) for t in times]) \
      if len(times) else np.array([])
if len(_pk):
    keep = _pk >= _pk.max() * (10 ** (-30/20))
    times, _pk = times[keep], _pk[keep]
R["detection"] = {"min_step_gap_s": MIN_STEP_GAP_S, "level_gate_db_below_max": 30,
                  "candidates_before_gate": int(len(keep)) if len(_pk) else 0}
rms_f = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
tf = librosa.frames_to_time(np.arange(len(rms_f)), sr=sr, hop_length=hop)

events = []
for k, pt in enumerate(times):
    # window ends at the next onset so consecutive events never share a peak
    nxt = times[k+1] if k+1 < len(times) else (N/sr)
    i0 = max(0, int((pt - 0.02) * sr)); i1 = min(N, int(min(pt + 0.45, nxt - 0.01) * sr))
    seg = y[i0:i1]
    if len(seg) < 512: continue
    a = np.abs(seg); p = float(a.max()); ip = int(np.argmax(a))
    # attack: 10%->90% of peak before the max ; decay: peak -> 10% after
    pre = a[:ip+1]; post = a[ip:]
    try:
        atk = (ip - int(np.argmax(pre >= 0.1*p))) / sr
    except Exception: atk = float("nan")
    below = np.flatnonzero(post <= 0.1*p)
    dec = (below[0]/sr) if len(below) else len(post)/sr
    cen = float(librosa.feature.spectral_centroid(y=seg, sr=sr).mean())
    S = np.abs(librosa.stft(seg, n_fft=1024, hop_length=256))
    f = librosa.fft_frequencies(sr=sr, n_fft=1024); tot = np.sum(S**2) + 1e-20
    band = lambda lo, hi: float(100*np.sum(S[(f>=lo)&(f<hi)]**2)/tot)
    events.append({"t_s": round(float(pt), 4), "peak": round(p, 5),
                   "peak_dbfs": round(20*np.log10(max(p,1e-12)), 1),
                   "attack_ms": round(atk*1000, 1), "decay_ms": round(dec*1000, 1),
                   "centroid_hz": round(cen, 0),
                   "e_low_0_200": round(band(0,200),1), "e_lowmid_200_800": round(band(200,800),1),
                   "e_mid_800_3k": round(band(800,3000),1), "e_hi_3k_12k": round(band(3000,12000),1)})
R["events"] = events
R["event_count"] = len(events)

ioi = np.diff([e["t_s"] for e in events]) if len(events) > 1 else np.array([])
if len(ioi):
    R["rhythm"] = {"ioi_s": [round(float(x),3) for x in ioi],
                   "ioi_mean": round(float(ioi.mean()),3), "ioi_std": round(float(ioi.std()),3),
                   "ioi_cv": round(float(ioi.std()/ioi.mean()),3),
                   "ioi_min": round(float(ioi.min()),3), "ioi_max": round(float(ioi.max()),3),
                   "steps_per_sec": round(len(events)/(N/sr), 2)}
    # alternation: do successive IOIs / peaks alternate (long-short or loud-quiet)?
    pks = np.array([e["peak"] for e in events])
    R["rhythm"]["peak_alternation_corr"] = round(float(np.corrcoef(pks[:-1], pks[1:])[0,1]), 3) if len(pks)>2 else None
    if len(ioi) > 2:
        d = np.sign(np.diff(ioi)); flips = int(np.sum(d[:-1]*d[1:] < 0))
        R["rhythm"]["ioi_alternation_flips"] = flips
        R["rhythm"]["ioi_alternation_ratio"] = round(flips/max(len(d)-1,1), 3)

# --- 4. coverage across the 10 s -------------------------------------------
sec_counts = [int(np.sum((np.array([e["t_s"] for e in events]) >= s) &
                         (np.array([e["t_s"] for e in events]) < s+1))) for s in range(int(np.ceil(N/sr)))]
R["coverage"] = {"events_per_second": sec_counts,
                 "seconds_with_events": int(np.sum(np.array(sec_counts) > 0)),
                 "longest_gap_s": round(float(ioi.max()), 3) if len(ioi) else None,
                 "first_event_s": events[0]["t_s"] if events else None,
                 "last_event_s": events[-1]["t_s"] if events else None,
                 "per_second_rms": [round(float(np.sqrt(np.mean(y[i*sr:min((i+1)*sr,N)]**2))),5)
                                    for i in range(int(np.ceil(N/sr)))]}

# --- 6. is it footsteps, or noise/speech/music/ambience? -------------------
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
f = librosa.fft_frequencies(sr=sr, n_fft=2048); tot = np.sum(S**2)+1e-20
Sn = S/(np.linalg.norm(S, axis=0, keepdims=True)+1e-12)
dbrel = 20*np.log10(np.maximum(rms_f, 1e-12)/rms_f.max())
# modulation spectrum of the envelope: speech peaks ~4 Hz, walking ~1.5-2.5 Hz
e = rms_f - rms_f.mean(); E = np.abs(np.fft.rfft(e * np.hanning(len(e))))
mf = np.fft.rfftfreq(len(e), d=hop/sr); E[mf < 0.3] = 0
R["character"] = {
    "spectral_centroid_hz": round(float(librosa.feature.spectral_centroid(S=S, sr=sr).mean()),1),
    "spectral_flatness": round(float(librosa.feature.spectral_flatness(S=S).mean()),5),
    "frame_self_similarity": round(float(np.mean(np.sum(Sn[:,:-1]*Sn[:,1:],axis=0))),4),
    "dyn_range_p95_p5_db": round(float(np.percentile(dbrel,95)-np.percentile(dbrel,5)),2),
    "pct_below_-20db": round(float(100*np.mean(dbrel < -20)),2),
    "pct_below_-30db": round(float(100*np.mean(dbrel < -30)),2),
    "energy_0_200hz": round(float(100*np.sum(S[(f>=0)&(f<200)]**2)/tot),2),
    "energy_200_800hz": round(float(100*np.sum(S[(f>=200)&(f<800)]**2)/tot),2),
    "energy_800_3000hz": round(float(100*np.sum(S[(f>=800)&(f<3000)]**2)/tot),2),
    "energy_3k_12k": round(float(100*np.sum(S[(f>=3000)&(f<12000)]**2)/tot),2),
    "envelope_mod_peak_hz": round(float(mf[int(np.argmax(E))]),2),
    "harmonic_ratio_hpss": round(float(np.mean(librosa.effects.harmonic(y)**2) /
                                      (np.mean(y**2)+1e-20)),4)}
OUT.write_text(json.dumps(R, indent=2))
print(json.dumps({k: R[k] for k in ("basic","event_count","rhythm","coverage","character")}, indent=2))
print("\n=== EVENT TABLE ===")
print(f"{'#':>3} {'t (s)':>7} {'peak':>8} {'dBFS':>7} {'atk ms':>7} {'dec ms':>7} {'cen Hz':>7}  bands lo/lomid/mid/hi")
for i,e in enumerate(R["events"],1):
    print(f"{i:>3} {e['t_s']:>7.3f} {e['peak']:>8.4f} {e['peak_dbfs']:>7.1f} {e['attack_ms']:>7.1f} "
          f"{e['decay_ms']:>7.1f} {e['centroid_hz']:>7.0f}  {e['e_low_0_200']:>4.1f}/{e['e_lowmid_200_800']:>4.1f}/"
          f"{e['e_mid_800_3k']:>4.1f}/{e['e_hi_3k_12k']:>4.1f}")
