"""Quality validation for generated Foley, run BEFORE anything reaches the mixer.

MOSS occasionally produces degenerate output: a near-constant, near-silent tone with
almost no dynamic range. Such a file contains no usable signal, but an active-RMS
leveller will still try to raise it to its class target — applying enormous gain and
turning quantisation noise into audible hiss.

This module measures the RAW generated WAV (never a normalised copy) and rejects assets
that are clearly unusable. A rejected asset is left on disk for diagnostics but is never
placed in the mix; its action interval stays silent and the reason is reported.

Gates are deliberately multi-criteria — no single metric decides.
"""
from __future__ import annotations
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
import numpy as np
import soundfile as sf
import librosa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import config as C

# ---- thresholds ------------------------------------------------------------
MIN_EFFECTIVE_BITS = 9.0          # peak below ~-42 dBFS carries too little signal
MIN_DYNAMIC_RANGE_DB = 6.0        # Foley is impulsive; a flat file is not Foley
TONAL_HARMONIC_RATIO = 0.80       # near-pure tone ...
TONAL_MAX_DYNAMIC_DB = 10.0       # ... combined with little dynamic movement
# A second, independent tonality test. The pair above only fires when a tone is ALSO
# flat in level, so a musical tone with a natural envelope slipped through: one backend
# produced a 346 Hz sine for "cup placed on table" with 32 dB of dynamic range and it
# passed. Foley is inharmonic; a near-pure tone is disqualifying on its own.
PURE_TONE_HARMONIC_RATIO = 0.90
PURE_TONE_MAX_FLATNESS = 0.01
MAX_AUTO_GAIN_DB = 25.0           # hard ceiling on automatic make-up gain
# A candidate scoring at or above this passes without generating alternatives.
GOOD_ENOUGH_SCORE = 45.0
MIN_DURATION_S = 0.05


@dataclass
class FoleyMetrics:
    path: str
    sample_rate: int
    channels: int
    duration_s: float
    peak_dbfs: float
    active_rms_dbfs: float
    dynamic_range_db: float
    effective_bits: float
    spectral_flatness: float
    harmonic_ratio: float
    required_gain_db: float
    silence_pct: float
    target_rms_dbfs: float
    finite: bool
    def dict(self): return asdict(self)


@dataclass
class FoleyVerdict:
    ok: bool
    metrics: FoleyMetrics
    failures: list[str] = field(default_factory=list)
    reason: str = ""
    user_reason: str = ""
    score: float = 0.0
    def dict(self):
        return {"ok": self.ok, "score": self.score, "failures": self.failures,
                "reason": self.reason, "user_reason": self.user_reason,
                "metrics": self.metrics.dict()}


def _active_rms(x: np.ndarray) -> float:
    """RMS of the active portion. Mirrors audio_processing.active_rms exactly, so the
    gain predicted here is the gain the mixer would actually apply."""
    f = 1024
    fr = np.array([np.sqrt(np.mean(x[i:i + f] ** 2))
                   for i in range(0, max(1, len(x) - f), f // 2)])
    if not len(fr):
        return float(np.sqrt(np.mean(x ** 2)))
    thr = max(float(np.percentile(fr, 60)), float(fr.max()) * 10 ** (-40 / 20))
    sel = fr[fr >= thr]
    return float(np.sqrt(np.mean(sel ** 2))) if len(sel) else float(fr.max())


def measure(path: Path, target_rms_dbfs: float) -> FoleyMetrics:
    """Measure the RAW generated file. No gain or normalisation is applied here."""
    y, sr = sf.read(path, always_2d=True)
    ch = y.shape[1]
    y = y[:, 0].astype(np.float64)
    finite = bool(np.isfinite(y).all())
    if not finite:
        y = np.nan_to_num(y)

    peak = float(np.abs(y).max())
    arms = _active_rms(y)
    eff_bits = 16.0 + float(np.log2(max(peak, 1e-12)))

    rf = librosa.feature.rms(y=y, frame_length=1024, hop_length=256)[0]
    # Dynamic range must be measured over frames that actually contain signal.
    # Including frames of EXACT digital silence sends p5 to the numeric floor and
    # returns values like 190 dB — physically impossible for 16-bit audio (~96 dB
    # theoretical) and enough to score full marks. A file that is 90 % silence with a
    # few clicks would otherwise pass as excellent.
    active = rf[rf > max(rf.max(), 1e-12) * 10 ** (-70 / 20)]
    if len(active) < 4:
        active = rf[rf > 0] if np.any(rf > 0) else rf
    db = 20 * np.log10(np.maximum(active, 1e-12) / max(rf.max(), 1e-12))
    dyn = float(min(np.percentile(db, 95) - np.percentile(db, 5), 96.0)) if len(db) else 0.0
    silence_pct = float(100.0 * np.mean(y == 0.0))

    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
    flat = float(librosa.feature.spectral_flatness(S=S).mean())
    harm = float(np.mean(librosa.effects.harmonic(y) ** 2) / (np.mean(y ** 2) + 1e-20))

    gain_db = 20 * np.log10((10 ** (target_rms_dbfs / 20)) / max(arms, 1e-12))

    return FoleyMetrics(
        path=str(path), sample_rate=int(sr), channels=int(ch),
        duration_s=round(len(y) / sr, 4),
        peak_dbfs=round(20 * np.log10(max(peak, 1e-12)), 2),
        active_rms_dbfs=round(20 * np.log10(max(arms, 1e-12)), 2),
        dynamic_range_db=round(dyn, 2), effective_bits=round(eff_bits, 2),
        spectral_flatness=round(flat, 5), harmonic_ratio=round(harm, 4),
        required_gain_db=round(float(gain_db), 2), silence_pct=round(silence_pct, 2),
        target_rms_dbfs=target_rms_dbfs, finite=finite)


def quality_score(m: FoleyMetrics) -> float:
    """Rank passing candidates 0-100. Only meaningful for assets that passed the gate.

    Four independent components, so no single metric dominates:
      dynamic range  (40) — Foley is impulsive; flat material scores nothing
      signal level   (25) — headroom above the quantisation floor
      gain headroom  (20) — the less make-up gain needed, the less noise is lifted
      non-tonality   (15) — Foley is inharmonic; a tone is not a contact sound
    """
    def band(v, lo, hi, pts):
        return float(np.clip((v - lo) / (hi - lo), 0.0, 1.0) * pts)
    return round(
        band(m.dynamic_range_db, 0.0, 40.0, 40.0)
        + band(m.effective_bits, 6.0, 14.0, 25.0)
        + band(MAX_AUTO_GAIN_DB - abs(m.required_gain_db), 0.0, MAX_AUTO_GAIN_DB, 20.0)
        + band(0.5 - min(m.harmonic_ratio, 0.5), 0.0, 0.5, 15.0), 1)


def validate(path: Path, target_rms_dbfs: float,
             expect_sr: int = C.DEFAULTS["sample_rate"]) -> FoleyVerdict:
    """Decide whether a generated asset may enter the mix."""
    m = measure(path, target_rms_dbfs)
    f: list[str] = []

    if not m.finite:
        f.append("audio contains NaN or Inf")
    if m.duration_s < MIN_DURATION_S:
        f.append(f"duration {m.duration_s:.3f}s below {MIN_DURATION_S}s")
    if m.sample_rate != expect_sr:
        f.append(f"sample rate {m.sample_rate} Hz, expected {expect_sr} Hz")
    if m.effective_bits < MIN_EFFECTIVE_BITS:
        f.append(f"effective bits {m.effective_bits:.1f} below {MIN_EFFECTIVE_BITS} "
                 f"(peak {m.peak_dbfs:.1f} dBFS — almost no signal)")
    if m.dynamic_range_db < MIN_DYNAMIC_RANGE_DB:
        f.append(f"dynamic range {m.dynamic_range_db:.1f} dB below "
                 f"{MIN_DYNAMIC_RANGE_DB} dB (flat, not impulsive)")
    if m.harmonic_ratio > TONAL_HARMONIC_RATIO and m.dynamic_range_db < TONAL_MAX_DYNAMIC_DB:
        f.append(f"harmonic ratio {m.harmonic_ratio:.2f} above {TONAL_HARMONIC_RATIO} "
                 f"with only {m.dynamic_range_db:.1f} dB dynamic range (a sustained tone)")
    if (m.harmonic_ratio > PURE_TONE_HARMONIC_RATIO
            and m.spectral_flatness < PURE_TONE_MAX_FLATNESS):
        f.append(f"harmonic ratio {m.harmonic_ratio:.2f} with spectral flatness "
                 f"{m.spectral_flatness:.4f} — a near-pure musical tone, not a "
                 f"physical contact sound")
    if m.required_gain_db > MAX_AUTO_GAIN_DB:
        f.append(f"would need {m.required_gain_db:+.1f} dB of make-up gain, above the "
                 f"{MAX_AUTO_GAIN_DB} dB safety limit (would amplify noise)")

    ok = not f
    v = FoleyVerdict(
        ok=ok, metrics=m, failures=f,
        reason="; ".join(f) if f else "passed all quality gates",
        user_reason="" if ok else "generated audio failed quality validation")
    v.score = quality_score(m) if ok else 0.0
    return v
