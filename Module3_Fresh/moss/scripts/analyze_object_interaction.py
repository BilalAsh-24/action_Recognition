"""Objective analysis for a short object-interaction Foley WAV (e.g. cup pickup)."""
import json, sys
from pathlib import Path
import numpy as np, soundfile as sf, librosa
from scipy.signal import hilbert

WAV=Path(sys.argv[1]); OUT=Path(sys.argv[2])
y,sr=sf.read(WAV,always_2d=True); ch=y.shape[1]; y=y[:,0].astype(np.float64); N=len(y)
R={"file":str(WAV)}
rms_all=float(np.sqrt(np.mean(y**2))); pk=float(np.abs(y).max())
R["basic"]={"sample_rate":sr,"channels":ch,"duration_s":round(N/sr,6),"samples":N,
    "rms":rms_all,"rms_dbfs":round(20*np.log10(max(rms_all,1e-12)),2),
    "peak":pk,"peak_dbfs":round(20*np.log10(max(pk,1e-12)),2),
    "crest_db":round(20*np.log10(pk/rms_all),2),
    "clipped_samples":int(np.sum(np.abs(y)>=1.0)),
    "nan":int(np.isnan(y).sum()),"inf":int(np.isinf(y).sum()),
    "all_finite":bool(np.isfinite(y).all()),
    "effective_bits_used":round(16+np.log2(max(pk,1e-12)),1)}

hop=256
env_s=librosa.onset.onset_strength(y=y,sr=sr,hop_length=hop,aggregate=np.median)
peaks=librosa.util.peak_pick(env_s,pre_max=6,post_max=6,pre_avg=12,post_avg=12,
        delta=float(np.percentile(env_s,75)*0.40),wait=int(0.08*sr/hop))   # objects: 80 ms min
times=librosa.frames_to_time(peaks,sr=sr,hop_length=hop)
amp=np.abs(hilbert(y)); amp=np.convolve(amp,np.ones(int(0.002*sr))/int(0.002*sr),mode="same")
cand=len(times)
if len(times):
    pkv=np.array([amp[max(0,int((t-0.02)*sr)):min(N,int((t+0.30)*sr))].max() for t in times])
    keep=pkv>=pkv.max()*(10**(-25/20))            # within 25 dB of loudest
    times,pkv=times[keep],pkv[keep]
R["detection"]={"candidates":cand,"kept":len(times),"min_gap_s":0.08,"gate_db":25}

ev=[]
for k,t in enumerate(times):
    nxt=times[k+1] if k+1<len(times) else N/sr
    i0=max(0,int((t-0.02)*sr)); i1=min(N,int(min(t+0.60,nxt-0.005)*sr))
    seg=y[i0:i1]; e=amp[i0:i1]
    if len(seg)<512: continue
    ip=int(np.argmax(e)); p=float(e[ip])
    pre=e[:ip+1]; atk=(ip-int(np.argmax(pre>=0.1*p)))/sr*1000
    post=e[ip:]
    def dec(fr):
        b=np.flatnonzero(post<=fr*p); return round(b[0]/sr*1000,1) if len(b) else None
    S=np.abs(librosa.stft(seg,n_fft=2048,hop_length=256)); f=librosa.fft_frequencies(sr=sr,n_fft=2048)
    tot=np.sum(S**2)+1e-20; band=lambda lo,hi: round(float(100*np.sum(S[(f>=lo)&(f<hi)]**2)/tot),1)
    spec=S.mean(axis=1); top=f[np.argsort(spec)[-3:][::-1]]
    ev.append({"t_s":round(float(t),4),"peak":round(p,6),"peak_dbfs":round(20*np.log10(max(p,1e-12)),1),
        "attack_ms":round(atk,1),"decay20_ms":dec(0.1),"decay60_ms":dec(0.001),
        "centroid_hz":round(float(librosa.feature.spectral_centroid(y=seg,sr=sr).mean()),0),
        "flatness":round(float(librosa.feature.spectral_flatness(y=seg).mean()),4),
        "dominant_hz":[round(float(x),0) for x in top],
        "b_0_200":band(0,200),"b_200_1k":band(200,1000),"b_1k_5k":band(1000,5000),"b_5k_15k":band(5000,15000)})
R["events"]=ev; R["event_count"]=len(ev)
if len(ev)>1:
    ioi=np.diff([e["t_s"] for e in ev])
    R["timing"]={"ioi_s":[round(float(x),3) for x in ioi],"ioi_mean":round(float(ioi.mean()),3),
                 "span_s":round(ev[-1]["t_s"]-ev[0]["t_s"],3)}

# background between events (criterion 5)
mask=np.ones(N,bool)
for e in ev: mask[max(0,int((e["t_s"]-0.05)*sr)):min(N,int((e["t_s"]+0.45)*sr))]=False
bg=y[mask]
rf=librosa.feature.rms(y=y,frame_length=1024,hop_length=hop)[0]
dbrel=20*np.log10(np.maximum(rf,1e-12)/rf.max())
S=np.abs(librosa.stft(y,n_fft=2048,hop_length=512)); f=librosa.fft_frequencies(sr=sr,n_fft=2048)
tot=np.sum(S**2)+1e-20
Sn=S/(np.linalg.norm(S,axis=0,keepdims=True)+1e-12)
ee=rf-rf.mean(); E=np.abs(np.fft.rfft(ee*np.hanning(len(ee)))); mf=np.fft.rfftfreq(len(ee),d=hop/sr); E[mf<0.3]=0
R["background"]={"bg_fraction_of_file":round(float(mask.mean()),3),
    "bg_rms":round(float(np.sqrt(np.mean(bg**2))) if len(bg) else 0.0,8),
    "bg_rms_dbfs":round(float(20*np.log10(max(np.sqrt(np.mean(bg**2)),1e-12))),1) if len(bg) else None,
    "event_to_bg_ratio_db":round(float(20*np.log10(pk/max(np.sqrt(np.mean(bg**2)),1e-12))),1) if len(bg) else None,
    "pct_below_-20db":round(float(100*np.mean(dbrel<-20)),2),
    "pct_below_-40db":round(float(100*np.mean(dbrel<-40)),2)}
R["character"]={"spectral_flatness":round(float(librosa.feature.spectral_flatness(S=S).mean()),5),
    "frame_self_similarity":round(float(np.mean(np.sum(Sn[:,:-1]*Sn[:,1:],axis=0))),4),
    "dyn_range_p95_p5_db":round(float(np.percentile(dbrel,95)-np.percentile(dbrel,5)),2),
    "harmonic_ratio_hpss":round(float(np.mean(librosa.effects.harmonic(y)**2)/(np.mean(y**2)+1e-20)),4),
    "envelope_mod_peak_hz":round(float(mf[int(np.argmax(E))]),2),
    "energy_0_200":round(float(100*np.sum(S[(f>=0)&(f<200)]**2)/tot),2),
    "energy_200_1k":round(float(100*np.sum(S[(f>=200)&(f<1000)]**2)/tot),2),
    "energy_1k_5k":round(float(100*np.sum(S[(f>=1000)&(f<5000)]**2)/tot),2),
    "energy_5k_15k":round(float(100*np.sum(S[(f>=5000)&(f<15000)]**2)/tot),2),
    "per_second_rms":[round(float(np.sqrt(np.mean(y[i*sr:min((i+1)*sr,N)]**2))),6) for i in range(int(np.ceil(N/sr)))]}
OUT.write_text(json.dumps(R,indent=2))
print(json.dumps({k:R[k] for k in ("basic","detection","event_count","timing","background","character") if k in R},indent=2))
print("\n=== EVENT TIMELINE ===")
print(f"{'#':>3} {'t(s)':>7} {'dBFS':>7} {'atk ms':>7} {'dec20':>7} {'dec60':>7} {'cen Hz':>7} {'flat':>6}  bands 0-200/200-1k/1-5k/5-15k   dominant Hz")
for i,e in enumerate(ev,1):
    print(f"{i:>3} {e['t_s']:>7.3f} {e['peak_dbfs']:>7.1f} {e['attack_ms']:>7.1f} {str(e['decay20_ms']):>7} {str(e['decay60_ms']):>7} "
          f"{e['centroid_hz']:>7.0f} {e['flatness']:>6.3f}  {e['b_0_200']:>5.1f}/{e['b_200_1k']:>5.1f}/{e['b_1k_5k']:>5.1f}/{e['b_5k_15k']:>5.1f}   {e['dominant_hz']}")
