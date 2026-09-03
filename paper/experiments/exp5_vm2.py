"""EXPERIMENT 5 - Visual Microphone detection floor + throughput."""
import sys, os, json, math, time
AE = "/Users/bilalashfaque/Desktop/Silent-Video-Project/Acoustic eye/acoustic-eye"
sys.path.insert(0, AE); os.chdir(AE)
import numpy as np, cv2
from backend.processing.visual_microphone import sound_from_frames
OUT = "/private/tmp/claude-501/-Users-bilalashfaque-Desktop-Silent-Video-Project/d51cc0c7-8606-4a87-a7cc-e9bca72807ee/scratchpad/exp"
rng = np.random.default_rng(7)
W = H = 128
base = rng.normal(0.5, 0.22, (H*3, W*3)).astype(np.float32)
base = cv2.GaussianBlur(base, (0,0), 1.6)
base = np.clip((base-base.min())/(np.ptp(base)+1e-9), 0, 1)

def render(fps, f0, seconds, amp):
    out=[]
    for i in range(int(round(fps*seconds))):
        dx = amp*math.sin(2*math.pi*f0*(i/fps))
        big = cv2.warpAffine(base, np.float32([[1,0,dx],[0,1,0]]), (W*3,H*3),
                             flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        out.append(big[H:2*H, W:2*W].astype(np.float64))
    return out

def recover(frames, fps):
    sig = np.asarray(sound_from_frames(frames, nscale=1, norientation=2), float)
    sig = sig - sig.mean(); n=len(sig)
    S = np.abs(np.fft.rfft(sig*np.hanning(n))); f = np.fft.rfftfreq(n, 1.0/fps)
    lo = np.searchsorted(f, 0.5); k = lo+int(np.argmax(S[lo:]))
    return float(f[k]), float(100.0*S[k]**2/(np.sum(S[lo:]**2)+1e-20))

print("=== DETECTION FLOOR: 240 fps, 10 Hz, decreasing sub-pixel amplitude ===")
print(f"{'amp px':>9}{'recovered Hz':>14}{'peak share':>12}  detected?")
rows=[]
for amp in (0.10, 0.05, 0.03, 0.02, 0.015, 0.01, 0.005):
    d, s = recover(render(240, 10.0, 1.5, amp), 240)
    det = abs(d-10.0) < 0.5 and s > 5.0
    rows.append(dict(amp=amp, dom=d, share=s, detected=bool(det)))
    print(f"{amp:>9.3f}{d:>14.2f}{s:>11.1f}%  {'YES' if det else 'no'}")

print()
print("=== THROUGHPUT (this machine, Apple M4) ===")
print(f"{'frame px':>12}{'frames':>8}{'seconds':>10}{'fps proc':>10}")
tp=[]
for side, n in ((64,180),(128,180),(256,180)):
    b = cv2.resize(base, (side*3, side*3))
    fr=[]
    for i in range(n):
        dx = 0.3*math.sin(2*math.pi*10*(i/120))
        big = cv2.warpAffine(b, np.float32([[1,0,dx],[0,1,0]]), (side*3,side*3),
                             flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        fr.append(big[side:2*side, side:2*side].astype(np.float64))
    t0=time.time(); sound_from_frames(fr, nscale=1, norientation=2); el=time.time()-t0
    tp.append(dict(side=side, frames=n, seconds=el, fps=n/el))
    print(f"{f'{side}x{side}':>12}{n:>8}{el:>10.2f}{n/el:>10.1f}")

json.dump(dict(floor=rows, throughput=tp), open(os.path.join(OUT,"exp5_vm2.json"),"w"), indent=2)
print("\n[written] exp5_vm2.json")
