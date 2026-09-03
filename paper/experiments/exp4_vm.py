"""EXPERIMENT 4 - Controlled characterisation of the Visual Microphone implementation.

This is a SYNTHETIC optical test, not an acoustic capture. A textured surface is
translated sinusoidally by a known sub-pixel amplitude at a known frequency, rendered
at several frame rates, and passed through the production pipeline. It answers two
questions the real footage cannot:

  1. Does the implementation recover a known vibration frequency at all?   (correctness)
  2. How does recovery behave as the signal crosses fps/2?                 (Nyquist)

It does NOT show that real sound is recoverable from real video.
"""
import sys, os, json, math, tempfile
AE = "/Users/bilalashfaque/Desktop/Silent-Video-Project/Acoustic eye/acoustic-eye"
sys.path.insert(0, AE)
os.chdir(AE)
import numpy as np, cv2
from backend.processing.visual_microphone import sound_from_frames
from backend.processing import signal_processing as SP

OUT = "/private/tmp/claude-501/-Users-bilalashfaque-Desktop-Silent-Video-Project/d51cc0c7-8606-4a87-a7cc-e9bca72807ee/scratchpad/exp"
rng = np.random.default_rng(7)

W = H = 128
# A static high-contrast texture. Band-limited noise gives energy at many orientations,
# which is what the steerable pyramid needs to see.
base = rng.normal(0.5, 0.22, (H * 3, W * 3)).astype(np.float32)
base = cv2.GaussianBlur(base, (0, 0), 1.6)
base = np.clip((base - base.min()) / (np.ptp(base) + 1e-9), 0, 1)

def render(fps, f0, seconds, amp_px):
    """Frames of the texture shifted by amp_px*sin(2*pi*f0*t) horizontally."""
    n = int(round(fps * seconds))
    frames = []
    for i in range(n):
        t = i / fps
        dx = amp_px * math.sin(2 * math.pi * f0 * t)
        M = np.float32([[1, 0, dx], [0, 1, 0]])
        big = cv2.warpAffine(base, M, (W * 3, H * 3),
                             flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
        frames.append(big[H:2 * H, W:2 * W].astype(np.float64))
    return frames

def recover(frames, fps):
    sig = sound_from_frames(frames, nscale=1, norientation=2)
    sig = np.asarray(sig, dtype=float)
    sig = SP.apply_high_pass(sig, fps, 0.05, 3) if hasattr(SP, "apply_high_pass") else sig
    sig = sig - sig.mean()
    n = len(sig)
    if n < 8: return None
    w = np.hanning(n)
    S = np.abs(np.fft.rfft(sig * w))
    f = np.fft.rfftfreq(n, 1.0 / fps)
    lo = np.searchsorted(f, 0.5)            # ignore DC / drift below 0.5 Hz
    if lo >= len(S): return None
    k = lo + int(np.argmax(S[lo:]))
    tot = float(np.sum(S[lo:] ** 2))
    return dict(dom=float(f[k]), snr_pct=float(100.0 * S[k] ** 2 / (tot + 1e-20)),
                n=n, spec=(f, S))

print("Synthetic source: 128x128 texture, horizontal sinusoid, amplitude 0.30 px")
print("(0.30 px is the sub-pixel regime the Visual Microphone is designed for)\n")

print("=== A. FIXED SIGNAL 10 Hz, VARYING FRAME RATE ===")
print(f"{'fps':>6}{'nyquist':>9}{'frames':>8}{'true Hz':>9}{'recovered':>11}{'err Hz':>8}{'peak share':>12}")
rowsA = []
for fps in (30, 60, 120, 240, 480):
    fr = render(fps, 10.0, 1.5, 0.30)
    r = recover(fr, fps)
    err = abs(r["dom"] - 10.0)
    rowsA.append(dict(fps=fps, nyq=fps/2, true=10.0, dom=r["dom"], err=err, share=r["snr_pct"]))
    print(f"{fps:>6}{fps/2:>9.0f}{r['n']:>8}{10.0:>9.1f}{r['dom']:>11.2f}{err:>8.2f}{r['snr_pct']:>11.1f}%")

print()
print("=== B. FIXED FRAME RATE 120 fps (Nyquist 60 Hz), VARYING SIGNAL ===")
print(f"{'true Hz':>9}{'vs Nyq':>9}{'recovered':>11}{'err Hz':>8}{'peak share':>12}  verdict")
rowsB = []
for f0 in (5, 10, 20, 40, 55, 70, 100):
    fr = render(120, float(f0), 1.5, 0.30)
    r = recover(fr, 120)
    alias = abs(((f0 + 60) % 120) - 60)          # expected alias if above Nyquist
    exp = f0 if f0 < 60 else alias
    ok = abs(r["dom"] - exp) < 2.0
    verdict = ("recovered" if f0 < 60 else f"ALIASED to ~{alias:.0f} Hz") + ("" if ok else "  [!]")
    rowsB.append(dict(true=f0, dom=r["dom"], expected=exp, share=r["snr_pct"], ok=bool(ok)))
    print(f"{f0:>9.0f}{'below' if f0<60 else 'ABOVE':>9}{r['dom']:>11.2f}"
          f"{abs(r['dom']-exp):>8.2f}{r['snr_pct']:>11.1f}%  {verdict}")

print()
print("=== C. AMPLITUDE SENSITIVITY at 240 fps, 10 Hz ===")
print(f"{'amp px':>8}{'recovered':>11}{'err Hz':>8}{'peak share':>12}")
rowsC = []
for amp in (1.0, 0.30, 0.10, 0.03, 0.01):
    fr = render(240, 10.0, 1.5, amp)
    r = recover(fr, 240)
    rowsC.append(dict(amp=amp, dom=r["dom"], share=r["snr_pct"]))
    print(f"{amp:>8.2f}{r['dom']:>11.2f}{abs(r['dom']-10.0):>8.2f}{r['snr_pct']:>11.1f}%")

json.dump(dict(A=rowsA, B=rowsB, C=rowsC),
          open(os.path.join(OUT, "exp4_vm.json"), "w"), indent=2)
print("\n[written] exp4_vm.json")
