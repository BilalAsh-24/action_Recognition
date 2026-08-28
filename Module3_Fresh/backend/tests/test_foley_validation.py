"""Tests for the Foley quality gate and the mixer's hard gain limit."""
from __future__ import annotations
import sys, tempfile, traceback
from pathlib import Path
import numpy as np, soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import config as C
from services.foley_validation import (validate, measure, MAX_AUTO_GAIN_DB,
                                       MIN_EFFECTIVE_BITS, MIN_DYNAMIC_RANGE_DB)
from services.prompt_map import ACTION_PROMPT_MAP
from services.audio_processing import mix

PASS, FAIL = [], []
def test(name):
    def deco(fn):
        try: fn(); PASS.append(name); print(f"  [PASS] {name}")
        except AssertionError as e:
            FAIL.append((name, str(e))); print(f"  [FAIL] {name} — {e}")
        except Exception as e:
            FAIL.append((name, f"{type(e).__name__}: {e}"))
            print(f"  [FAIL] {name} — {type(e).__name__}: {e}"); traceback.print_exc()
        return fn
    return deco

G = C.GENERATED

def asset(prefix, *, degenerate=None):
    """Return a cached asset for `prefix`.

    Several candidates now exist per class (one per seed), so tests must not rely on
    filename ordering. When `degenerate` is True/False the asset is chosen by its
    actual gate verdict, which is what the test is really asking for.
    """
    from services.prompt_map import ACTION_PROMPT_MAP as _M
    m = sorted(G.glob(f"{prefix}_*.wav"))
    assert m, f"no cached asset for {prefix}"
    if degenerate is None:
        return m[0]
    target = _M[prefix].target_rms_dbfs
    scored = [(validate(p, target), p) for p in m]
    if degenerate:
        # the WORST rejected asset, so a test about "all four gates" gets the file
        # that actually trips all four rather than a merely marginal one
        bad = [(v, p) for v, p in scored if not v.ok]
        assert bad, f"no degenerate asset for {prefix}"
        return min(bad, key=lambda x: x[0].metrics.peak_dbfs)[1]
    good = [(v, p) for v, p in scored if v.ok]
    assert good, f"no healthy asset for {prefix}"
    return max(good, key=lambda x: x[0].score)[1]

print("\n=== real generated assets ===")

@test("the known degenerate cup-pickup WAV is REJECTED on all four gates")
def _():
    v = validate(asset("cup_pickup", degenerate=True), ACTION_PROMPT_MAP["cup_pickup"].target_rms_dbfs)
    assert not v.ok, "must be rejected"
    m = v.metrics
    assert m.peak_dbfs < -55, m.peak_dbfs
    assert m.dynamic_range_db < 2.0, m.dynamic_range_db
    assert m.effective_bits < 7.0, m.effective_bits
    assert m.harmonic_ratio > 0.8, m.harmonic_ratio
    assert m.required_gain_db > MAX_AUTO_GAIN_DB, m.required_gain_db
    joined = " ".join(v.failures)
    for expect in ("effective bits", "dynamic range", "harmonic ratio", "make-up gain"):
        assert expect in joined, f"missing '{expect}' in: {joined}"
    # at least four independent gates must fire; more is fine (a later pure-tone gate
    # also catches this file), the point is that no single metric is deciding
    assert len(v.failures) >= 4, f"expected >=4 independent failures, got {len(v.failures)}"

@test("a valid walking WAV PASSES")
def _():
    v = validate(asset("walking"), ACTION_PROMPT_MAP["walking"].target_rms_dbfs)
    assert v.ok, v.failures
    assert v.metrics.dynamic_range_db > 20 and v.metrics.effective_bits > 12

@test("the approved drinking WAV PASSES")
def _():
    v = validate(asset("drinking"), ACTION_PROMPT_MAP["drinking"].target_rms_dbfs)
    assert v.ok, v.failures
    assert v.metrics.harmonic_ratio < 0.5, v.metrics.harmonic_ratio

@test("the placement WAV PASSES")
def _():
    v = validate(asset("cup_placement"), ACTION_PROMPT_MAP["cup_placement"].target_rms_dbfs)
    assert v.ok, v.failures
    assert v.metrics.required_gain_db <= MAX_AUTO_GAIN_DB, v.metrics.required_gain_db

@test("the locked approved assets also pass the gate")
def _():
    for p, key in ((C.MODULE3 / "audio/generated/walking_moss_v1_seed42.wav", "walking"),
                   (C.MODULE3 / "audio/generated/drinking_moss_v2_local_seed42.wav", "drinking")):
        v = validate(p, ACTION_PROMPT_MAP[key].target_rms_dbfs)
        assert v.ok, (p.name, v.failures)

print("\n=== synthetic gate cases (each isolates one criterion) ===")

def _write(y, sr=48000):
    p = Path(tempfile.mkdtemp()) / "t.wav"
    sf.write(p, y.astype(np.float32), sr, subtype="PCM_16"); return p

@test("gain above +25 dB alone triggers rejection")
def _():
    rng = np.random.RandomState(0)
    y = np.zeros(48000 * 3)
    for i in range(6):                       # real transients, but very quiet
        a = int((0.3 + i * 0.4) * 48000)
        env = np.exp(-np.linspace(0, 10, 4800))
        y[a:a + 4800] += env * rng.randn(4800) * 0.004
    v = validate(_write(y), -32.0)
    assert not v.ok
    assert any("make-up gain" in f for f in v.failures), v.failures

@test("a flat sustained tone is rejected for dynamic range and tonality")
def _():
    t = np.arange(48000 * 3) / 48000
    y = 0.2 * np.sin(2 * np.pi * 120 * t)
    v = validate(_write(y), -32.0)
    assert not v.ok
    assert any("dynamic range" in f for f in v.failures), v.failures

@test("a near-silent file is rejected for effective bits")
def _():
    rng = np.random.RandomState(1)
    y = rng.randn(48000 * 2) * (10 ** (-60 / 20))
    v = validate(_write(y), -32.0)
    assert not v.ok
    assert any("effective bits" in f for f in v.failures), v.failures

@test("healthy impulsive Foley passes every gate")
def _():
    rng = np.random.RandomState(2)
    y = np.zeros(48000 * 3)
    for i in range(6):
        a = int((0.3 + i * 0.4) * 48000)
        env = np.exp(-np.linspace(0, 10, 4800))
        y[a:a + 4800] += env * rng.randn(4800) * 0.5
    v = validate(_write(y), -32.0)
    assert v.ok, v.failures

@test("validation measures the RAW file — a normalised copy is not what is judged")
def _():
    p = asset("cup_pickup", degenerate=True)
    y, sr = sf.read(p); y = y.astype(np.float64)
    boosted = _write(y / max(np.abs(y).max(), 1e-12) * 0.5, sr)   # same content, normalised
    raw = validate(p, -32.0); norm = validate(boosted, -32.0)
    assert not raw.ok, "raw degenerate file must fail"
    assert raw.metrics.peak_dbfs < -55, raw.metrics.peak_dbfs
    assert norm.metrics.peak_dbfs > -8, norm.metrics.peak_dbfs
    # normalising hides the level problem but not the structural ones
    assert not norm.ok, "normalised degenerate audio must still fail on structure"
    assert any("dynamic range" in f or "harmonic" in f for f in norm.failures), norm.failures

print("\n=== mixer hard limit ===")

@test("mixer refuses a clip needing more than +25 dB and mixes the rest")
def _():
    tmp = Path(tempfile.mkdtemp())
    pl = [{"asset": str(asset("cup_pickup", degenerate=True)), "asset_start_s": 0.0, "asset_end_s": 0.4,
           "video_start_s": 2.6, "target_rms_dbfs": -32.0, "action": "pick up cup"},
          {"asset": str(asset("walking")), "asset_start_s": 0.5, "asset_end_s": 2.5,
           "video_start_s": 0.2, "target_rms_dbfs": -34.0, "action": "walk"}]
    log = mix(pl, 10.005, tmp / "m.wav")
    assert [t["action"] for t in log["tracks"]] == ["walk"], log["tracks"]
    assert len(log["rejected"]) == 1 and log["rejected"][0]["action"] == "pick up cup"
    assert log["rejected"][0]["required_gain_db"] > MAX_AUTO_GAIN_DB
    assert log["max_auto_gain_db"] == MAX_AUTO_GAIN_DB

@test("one rejected action does not prevent the others being mixed")
def _():
    tmp = Path(tempfile.mkdtemp())
    pl = [{"asset": str(asset("cup_pickup", degenerate=True)), "asset_start_s": 0.0, "asset_end_s": 0.4,
           "video_start_s": 2.6, "target_rms_dbfs": -32.0, "action": "pick up cup"},
          {"asset": str(asset("walking")), "asset_start_s": 0.5, "asset_end_s": 2.5,
           "video_start_s": 0.2, "target_rms_dbfs": -34.0, "action": "walk"},
          {"asset": str(asset("drinking")), "asset_start_s": 1.6, "asset_end_s": 2.3,
           "video_start_s": 6.3, "target_rms_dbfs": -38.0, "action": "drink"}]
    log = mix(pl, 10.005, tmp / "m.wav")
    assert len(log["tracks"]) == 2 and len(log["rejected"]) == 1
    y, _ = sf.read(tmp / "m.wav")
    assert np.abs(y).max() > 0 and not log["silent"]

@test("an all-rejected mix produces a valid silent track, not a crash")
def _():
    tmp = Path(tempfile.mkdtemp())
    pl = [{"asset": str(asset("cup_pickup", degenerate=True)), "asset_start_s": 0.0, "asset_end_s": 0.4,
           "video_start_s": 2.6, "target_rms_dbfs": -32.0, "action": "pick up cup"}]
    log = mix(pl, 10.005, tmp / "m.wav")
    y, sr = sf.read(tmp / "m.wav")
    assert log["silent"] is True and len(log["tracks"]) == 0
    assert abs(len(y) / sr - 10.005) < 0.001 and np.abs(y).max() == 0.0

@test("the rejected asset is preserved on disk for diagnostics")
def _():
    p = asset("cup_pickup", degenerate=True)
    assert p.is_file() and p.stat().st_size > 1000, "rejected asset must not be deleted"

print("\n=== cache key stability ===")
from services.sound_generation import cache_key

@test("numeric type differences do not change the cache key")
def _():
    sp = ACTION_PROMPT_MAP["cup_pickup"]
    base = dict(C.DEFAULTS)
    # same VALUES, different numeric types — derived from the active defaults so this
    # holds whichever backend is selected
    as_int = {k: int(base[k]) for k in ("duration", "cfg_scale", "sigma_shift", "seed")
              if float(base[k]).is_integer()}
    as_float = {k: float(base[k]) for k in ("duration", "cfg_scale", "sigma_shift", "seed")}
    variants = [base, {**base, **as_int}, {**base, **as_float},
                {**base, **as_int, **{k: float(v) for k, v in as_int.items()}}]
    keys = {cache_key(sp, v) for v in variants}
    assert len(keys) == 1, f"equivalent settings produced {len(keys)} keys: {keys}"

@test("a genuinely different setting still changes the cache key")
def _():
    sp = ACTION_PROMPT_MAP["cup_pickup"]
    a = cache_key(sp, C.DEFAULTS)
    for change in ({"seed": 43}, {"steps": 60}, {"cfg_scale": 5.0}, {"duration": 12.0}):
        assert cache_key(sp, {**C.DEFAULTS, **change}) != a, change


print("\n=== candidate generation and selection ===")
import services.sound_generation as SG
from services.foley_validation import quality_score, GOOD_ENOUGH_SCORE

@test("quality_score ranks a good asset above a marginal one")
def _():
    good = validate(asset("walking"), ACTION_PROMPT_MAP["walking"].target_rms_dbfs)
    marg = validate(asset("cup_placement"), ACTION_PROMPT_MAP["cup_placement"].target_rms_dbfs)
    bad  = validate(asset("cup_pickup", degenerate=True), ACTION_PROMPT_MAP["cup_pickup"].target_rms_dbfs)
    assert good.score > marg.score > bad.score, (good.score, marg.score, bad.score)
    assert bad.score == 0.0, "a rejected asset must score zero"
    assert good.score >= GOOD_ENOUGH_SCORE

@test("a first candidate that scores well stops the loop after ONE generation")
def _():
    calls = []
    orig = SG.generate
    try:
        SG.generate = lambda spec, st, timeout_s=3600: (calls.append(st["seed"]),
                                                        (asset("walking"), True))[1]
        best, att = SG.generate_best(ACTION_PROMPT_MAP["walking"], dict(C.DEFAULTS),
                                     max_candidates=3)
    finally:
        SG.generate = orig
    assert len(calls) == 1, f"expected 1 generation, got {len(calls)}"
    assert best and best["ok"] and len(att) == 1

@test("a failing first candidate triggers retries with new seeds")
def _():
    seeds, orig = [], SG.generate
    seq = [asset("cup_pickup", degenerate=True), asset("cup_pickup", degenerate=True),
           asset("cup_placement")]
    try:
        SG.generate = lambda spec, st, timeout_s=3600, _s=seq: (
            seeds.append(st["seed"]), (_s[len(seeds) - 1], True))[1]
        best, att = SG.generate_best(ACTION_PROMPT_MAP["cup_placement"], dict(C.DEFAULTS),
                                     max_candidates=3)
    finally:
        SG.generate = orig
    assert seeds == [42, 43, 44], seeds
    assert len(att) == 3 and [a["ok"] for a in att] == [False, False, True]
    assert best and best["seed"] == 44

@test("the best-scoring candidate wins, not merely the first passing one")
def _():
    orig = SG.generate
    seq = [asset("cup_placement"), asset("walking")]      # 49.8 then ~97
    try:
        SG.generate = lambda spec, st, timeout_s=3600, _s=seq, n=[0]: (
            _s[n[0] % len(_s)], True) if not n.__setitem__(0, n[0] + 1) else None
        best, att = SG.generate_best(ACTION_PROMPT_MAP["walking"], dict(C.DEFAULTS),
                                     max_candidates=2)
    finally:
        SG.generate = orig
    assert len(att) >= 1
    assert best["score"] == max(a["score"] for a in att if a["ok"])

@test("when every candidate fails, no asset is selected")
def _():
    orig = SG.generate
    try:
        SG.generate = lambda spec, st, timeout_s=3600: (asset("cup_pickup", degenerate=True), True)
        best, att = SG.generate_best(ACTION_PROMPT_MAP["cup_pickup"], dict(C.DEFAULTS),
                                     max_candidates=3)
    finally:
        SG.generate = orig
    assert best is None, "no candidate may be selected"
    assert len(att) == 3 and all(not a["ok"] for a in att)
    assert all("effective bits" in a["reason"] for a in att)

@test("each candidate uses a distinct cache key so nothing is regenerated twice")
def _():
    sp = ACTION_PROMPT_MAP["cup_pickup"]
    keys = {cache_key(sp, {**C.DEFAULTS, "seed": 42 + i}) for i in range(3)}
    assert len(keys) == 3, keys


print("\n" + "=" * 62)
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
for n, e in FAIL: print(f"  FAILED {n}: {e}")
print("=" * 62)
sys.exit(1 if FAIL else 0)
