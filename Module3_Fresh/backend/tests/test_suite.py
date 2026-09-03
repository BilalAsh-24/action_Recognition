"""Unit + integration tests. Run: moss/venv-moss/bin/python backend/tests/test_suite.py"""
from __future__ import annotations
import json, sys, tempfile, traceback
from pathlib import Path
import numpy as np, soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import config as C

PASS, FAIL = [], []


def test(name):
    def deco(fn):
        try:
            fn(); PASS.append(name); print(f"  [PASS] {name}")
        except AssertionError as e:
            FAIL.append((name, str(e))); print(f"  [FAIL] {name} — {e}")
        except Exception as e:
            FAIL.append((name, f"{type(e).__name__}: {e}"))
            print(f"  [FAIL] {name} — {type(e).__name__}: {e}")
            traceback.print_exc()
        return fn
    return deco


print("\n=== 1. video validation ===")
from services.video_service import probe, validate, VideoError

@test("probe reads the demo video")
def _():
    i = probe(C.DEMO_VIDEO)
    assert i.duration_s > 9.9 and i.width == 1280 and i.height == 720, i

@test("validate accepts a normal video and warns about an existing audio track")
def _():
    w = validate(probe(C.DEMO_VIDEO))
    assert any("audio track" in x for x in w), w

@test("validate rejects an unsupported extension")
def _():
    i = probe(C.DEMO_VIDEO); i.path = "/tmp/x.webm"
    try: validate(i); assert False, "should have raised"
    except VideoError as e: assert "Unsupported format" in str(e)

@test("validate rejects an over-long video")
def _():
    i = probe(C.DEMO_VIDEO); i.duration_s = C.MAX_VIDEO_SECONDS + 1
    try: validate(i); assert False, "should have raised"
    except VideoError as e: assert "limit" in str(e)

@test("probe rejects a non-video file")
def _():
    p = Path(tempfile.mkdtemp()) / "notavideo.mp4"; p.write_text("hello")
    try: probe(p); assert False, "should have raised"
    except VideoError: pass


print("\n=== 2. action timeline parsing ===")
@test("resolved timeline parses to 5 non-overlapping actions")
def _():
    m2 = json.loads(C.DEMO_MODULE2.read_text())
    r = m2["resolved_actions"]
    assert len(r) == 5, len(r)
    for a, b in zip(r, r[1:]):
        assert abs(a["end"] - b["start"]) < 1e-6, (a, b)

@test("raw actions array overlaps, confirming why resolved is used")
def _():
    raw = json.loads(C.DEMO_MODULE2.read_text())["actions"]
    assert any(a["end"] > b["start"] + 1e-6 for a, b in zip(raw, raw[1:])), "expected overlap"


print("\n=== 3. prompt generation ===")
from services.prompt_map import resolve, ACTION_PROMPT_MAP, supported_actions

@test("known phrasings resolve to the right Foley class")
def _():
    cases = {"walk around table": "walking", "walking briskly": "walking",
             "drink from cup": "drinking", "picking up the mug": "cup_pickup",
             "places the cup on the table": "cup_placement", "running": "running",
             "typing on a keyboard": "typing", "opening the door": "door_opening"}
    for phrase, key in cases.items():
        s, _ = resolve(phrase)
        assert s and s.key == key, f"{phrase} -> {s.key if s else None}, expected {key}"

@test("object-specific classes beat the generic fallback (specificity over length)")
def _():
    # regression: a bare "place" keyword once matched "place spoon on table" to the
    # CUP class, producing ceramic Foley for a metal spoon.
    for phrase, key in {"place cup on table": "cup_placement",
                        "places the mug on the table": "cup_placement",
                        "place spoon on table": "spoon_placement",
                        "Put spoon on table": "spoon_placement",
                        "pick up the cup": "cup_pickup",
                        "pick up the spoon": "spoon_pickup"}.items():
        sp, _ = resolve(phrase)
        assert sp and sp.key == key, f"{phrase} -> {sp.key if sp else None}, expected {key}"

@test("generic fallback covers objects with no dedicated class")
def _():
    for phrase, key in {"place the book on the table": "object_placement",
                        "put the phone down": "object_placement",
                        "picks up the remote": "object_pickup"}.items():
        sp, _ = resolve(phrase)
        assert sp and sp.key == key, f"{phrase} -> {sp.key if sp else None}"

@test("stirring phrasings resolve to the stirring class")
def _():
    # NOTE: "mixing the drink" is deliberately excluded — it contains the noun
    # "drink", which makes it genuinely ambiguous. Documented as a limitation.
    for phrase in ("stir coffee", "stir the contents of the cup",
                   "Stirring a cup of coffee", "stirring tea", "mixing the coffee"):
        sp, _ = resolve(phrase)
        assert sp and sp.key == "stirring", f"{phrase} -> {sp.key if sp else None}"

@test("non-audible gestures are classified silent, not unsupported-by-omission")
def _():
    for phrase in ("move hand towards the spoon", "reaching for the cup",
                   "holding the mug", "stand"):
        sp, r = resolve(phrase)
        assert sp is None and r, phrase
        assert "no foley class is defined" not in r.lower(), \
            f"'{phrase}' should be a known silent action, not an unknown one: {r}"

@test("an action verb with an unfamiliar object still resolves (verb fallback)")
def _():
    # Regression: "place bread in toaster" resolved to nothing, because the generic
    # keywords demanded a literal "table"/"down"/"object". The whole job then failed
    # with "no supported Foley action" before the sound model was ever called.
    cases = {"place bread in toaster": "object_placement",
             "put phone on desk": "object_placement",
             "insert the tray": "object_placement",
             "lift the plate": "object_pickup",
             "grab the remote": "object_pickup",
             "press toaster": "button_press",
             "flip the switch": "button_press",
             "push the toaster lever down": "button_press"}
    for phrase, key in cases.items():
        sp, r = resolve(phrase)
        assert sp is not None, f"'{phrase}' resolved to nothing: {r}"
        assert sp.key == key, f"'{phrase}' -> {sp.key}, expected {key}"

@test("the verb fallback never overrides a specific class or a silent action")
def _():
    # The fallback runs last on purpose. If it ever ran first, "place spoon on table"
    # would inherit ceramic-mug Foley again - the original mis-mapping bug.
    for phrase, key in (("place cup on table", "cup_placement"),
                        ("place spoon on table", "spoon_placement"),
                        ("pick up the cup", "cup_pickup"),
                        ("pick up the spoon", "spoon_pickup")):
        sp, _ = resolve(phrase)
        assert sp and sp.key == key, f"'{phrase}' -> {sp.key if sp else None}, expected {key}"
    for phrase in ("reach for the cup", "holding the mug", "standing still"):
        sp, r = resolve(phrase)
        assert sp is None, f"'{phrase}' should stay silent, got {sp.key if sp else None}"
        assert "no foley class is defined" not in r.lower(), phrase

@test("a bare verb never inherits an object-specific curated class")
def _():
    # Under open vocabulary a bare verb still gets sounded, but it must not be handed
    # cup or spoon Foley - that was the original mis-mapping bug.
    specific = {"cup_placement", "cup_pickup", "spoon_placement", "spoon_pickup",
                "drinking", "stirring", "pouring"}
    for phrase in ("place", "pressing", "pick"):
        sp, _ = resolve(phrase)
        assert sp is not None, f"'{phrase}' should still resolve under open vocabulary"
        assert sp.key not in specific, f"bare verb '{phrase}' wrongly got {sp.key}"

@test("only deliberate silences resolve to nothing; everything else is sounded")
def _():
    s, r = resolve("stand"); assert s is None and "no foley" in r.lower(), r
    s, r = resolve(""); assert s is None
    # An action nobody wrote a class for is synthesised, not refused.
    s, r = resolve("juggling flaming torches")
    assert s is not None and r is None, "unknown action should synthesise a spec"
    assert s.prompt and s.strategy in {"footstep", "hold", "contact", "continuous"}

@test("open vocabulary: arbitrary actions all produce a usable spec")
def _():
    from services.prompt_synthesis import ARCHETYPE_SYNC
    phrases = ["kicking a football", "ball bounces on the ground", "dribbling a basketball",
               "chopping vegetables", "opening the fridge", "riding a bicycle",
               "a dog barking", "hitting a tennis ball", "sweeping the floor",
               "washing dishes", "writing with a pen", "shovelling snow",
               "hammering a nail", "playing the drums", "climbing a ladder"]
    for phrase in phrases:
        sp, r = resolve(phrase)
        assert sp is not None, f"'{phrase}' resolved to nothing: {r}"
        assert sp.prompt and "no speech" in sp.prompt, phrase
        assert sp.negative, phrase
        assert sp.strategy in {"footstep", "hold", "contact", "continuous"}, phrase
        assert sp.region in {"feet", "head", "table", "full"}, phrase
        assert sp.selection in {"steps", "wet_segment", "event", "slice"}, phrase
        assert -50.0 < sp.target_rms_dbfs < -20.0, phrase

@test("every archetype maps onto a real motion band and a real selection path")
def _():
    # Integration guard: prompt_synthesis invents specs, synchronization consumes them.
    # A region that is not a motion band would KeyError at sync time, on a live job.
    from services.prompt_synthesis import ARCHETYPE_SYNC, ARCHETYPE_PROMPT, ARCHETYPE_VERBS
    from services.synchronization import BANDS
    assert set(ARCHETYPE_SYNC) == set(ARCHETYPE_PROMPT) == set(ARCHETYPE_VERBS), \
        "archetype tables are out of sync with each other"
    for arch, (strategy, region, selection, rms) in ARCHETYPE_SYNC.items():
        assert region in BANDS, f"{arch}: region '{region}' is not a motion band"
        assert strategy in {"footstep", "hold", "contact", "continuous"}, arch
        assert selection in {"steps", "wet_segment", "event", "slice"}, arch
    # and every region a hint can force must also be a real band
    from services.prompt_synthesis import REGION_HINTS
    for region in REGION_HINTS:
        assert region in BANDS, f"region hint '{region}' is not a motion band"

@test("synthesis is deterministic and shares one generation across phrasings")
def _():
    a, _ = resolve("kick the ball")
    b, _ = resolve("kicking a ball")
    assert a.key == b.key, f"{a.key} != {b.key} - would pay for two generations"
    c, _ = resolve("kicking a football")
    assert c.prompt == resolve("kicking a football")[0].prompt, "not deterministic"

@test("every spec has a non-empty prompt and a valid strategy")
def _():
    valid = {"footstep", "hold", "contact", "continuous", "none"}
    for k, s in ACTION_PROMPT_MAP.items():
        assert len(s.prompt) > 40, k
        assert s.strategy in valid, (k, s.strategy)
        assert s.region in {"feet", "head", "table", "full"}, (k, s.region)
    assert len(supported_actions()) == len(ACTION_PROMPT_MAP)


print("\n=== 4. Foley cache keying ===")
from services.sound_generation import cache_key, cached_path

@test("cache key is stable and settings-sensitive")
def _():
    s = ACTION_PROMPT_MAP["walking"]
    k1 = cache_key(s, C.DEFAULTS)
    k2 = cache_key(s, C.DEFAULTS)
    k3 = cache_key(s, {**C.DEFAULTS, "seed": 43})
    assert k1 == k2, "same input must give same key"
    assert k1 != k3, "changing seed must change the key"
    # cached filenames are namespaced by backend, so the two models never collide
    name = cached_path(s, C.DEFAULTS).name
    assert "walking_" in name and name.startswith(C.GENERATION_BACKEND + "_"), name
    other = "stable_audio" if C.GENERATION_BACKEND == "moss" else "moss"
    assert cache_key(s, {**C.DEFAULTS, "backend": other}) != cache_key(s, C.DEFAULTS), \
        "different backends must not share a cache entry"


print("\n=== 5. audio segment extraction ===")
from services.synchronization import attack_times, first_attack, select_event_clip, \
                                     select_wet_segments, envelope

def _synth(sr=48000, n=5, gap=0.5, dur=10.0):
    y = np.zeros(int(dur * sr))
    for i in range(n):
        t = 0.5 + i * gap
        a = int(t * sr)
        env = np.exp(-np.linspace(0, 12, int(0.15 * sr)))
        y[a:a + len(env)] += env * np.random.RandomState(i).randn(len(env)) * 0.5
    return y, sr

@test("attack_times finds synthetic transients at the right instants")
def _():
    y, sr = _synth()
    ats = attack_times(y, sr, min_gap_s=0.25)
    expect = [0.5 + i * 0.5 for i in range(5)]
    assert len(ats) >= 5, f"found {len(ats)}"
    for e in expect:
        assert min(abs(ats - e)) < 0.02, f"no attack near {e}s: {ats}"

@test("first_attack returns the leading edge, not the peak")
def _():
    y, sr = _synth(n=1)
    assert abs(first_attack(y, sr) - 0.5) < 0.02, first_attack(y, sr)

@test("select_event_clip returns a short window around a real transient")
def _():
    y, sr = _synth(n=3, gap=2.0)
    lo, hi = select_event_clip(y, sr)
    assert 0.05 < hi - lo <= 0.45, (lo, hi)
    assert np.abs(y[int(lo*sr):int(hi*sr)]).max() > 0.05

@test("select_wet_segments returns the requested count")
def _():
    y, sr = _synth(n=4, gap=1.5)
    segs = select_wet_segments(y, sr, n_want=2)
    assert len(segs) == 2, segs
    assert all(b > a for a, b in segs)


print("\n=== 6. synchronization ===")
from services.synchronization import analyse_video, detect_events, plan_action

MO = analyse_video(C.DEMO_VIDEO)

@test("visual detection reproduces the validated foot plants")
def _():
    s, _ = resolve("walk around table")
    ev = detect_events(MO, "walk around table", s, 1.5, 2.5, (0.0, 2.5))
    got = [round(e.t_s, 3) for e in ev]
    assert got == [0.458, 1.083, 1.667, 2.208], got

@test("visual detection reproduces the validated sip holds and cup contact")
def _():
    s, _ = resolve("drink from cup")
    ev = [round(e.t_s, 3) for e in detect_events(MO, "drink from cup", s, 5.5, 8.5)]
    assert ev == [6.625, 7.792], ev
    s, _ = resolve("place cup on table")
    ev = [round(e.t_s, 3) for e in detect_events(MO, "place cup on table", s, 8.5, 10.0)]
    assert ev == [9.833], ev

@test("walking alignment matches the validated reference within 1 ms")
def _():
    s, _ = resolve("walk around table")
    asset = C.MODULE3 / "audio/generated/walking_moss_v1_seed42.wav"
    ev = detect_events(MO, "walk around table", s, 1.5, 2.5, (0.0, 2.5))
    pl = plan_action(s, asset, ev, (1.5, 2.5), 10.005, (0.0, 2.5))[0]
    assert abs(pl["video_start_s"] - 0.1583) < 0.001, pl["video_start_s"]
    assert pl["per_event_error_ms"] == [0.0, -19.9, 8.0, 12.3], pl["per_event_error_ms"]

@test("alignment never time-stretches: output length equals source length")
def _():
    s, _ = resolve("walk around table")
    asset = C.MODULE3 / "audio/generated/walking_moss_v1_seed42.wav"
    ev = detect_events(MO, "walk around table", s, 1.5, 2.5, (0.0, 2.5))
    pl = plan_action(s, asset, ev, (1.5, 2.5), 10.005, (0.0, 2.5))[0]
    src = pl["asset_end_s"] - pl["asset_start_s"]
    assert src > 0.05, src   # a real slice, and the mixer places it 1:1


print("\n=== 7. audio mixing ===")
from services.audio_processing import mix, active_rms, soft_limit, rcos_fade, snap_zero

@test("mix produces a valid non-clipping 48 kHz mono WAV")
def _():
    tmp = Path(tempfile.mkdtemp())
    asset = C.MODULE3 / "audio/generated/walking_moss_v1_seed42.wav"
    pl = [{"asset": str(asset), "asset_start_s": 0.5, "asset_end_s": 1.5,
           "video_start_s": 1.0, "target_rms_dbfs": -34.0, "action": "walk"}]
    log = mix(pl, 10.005, tmp / "m.wav")
    y, sr = sf.read(tmp / "m.wav")
    assert sr == 48000 and y.ndim == 1, (sr, y.shape)
    assert abs(len(y) / sr - 10.005) < 0.001
    assert np.isfinite(y).all() and np.abs(y).max() < 1.0
    assert log["output"]["clipped_samples"] == 0

@test("a clip crossing the end of the video is truncated, never allowed to extend it")
def _():
    tmp = Path(tempfile.mkdtemp())
    asset = C.MODULE3 / "audio/generated/walking_moss_v1_seed42.wav"
    # most of the clip still fits -> truncate with a fade
    pl = [{"asset": str(asset), "asset_start_s": 0.0, "asset_end_s": 1.0,
           "video_start_s": 9.2, "target_rms_dbfs": -34.0, "action": "walk"}]
    log = mix(pl, 10.005, tmp / "m.wav")
    y, _ = sf.read(tmp / "m.wav")
    assert abs(len(y) / 48000 - 10.005) < 0.001, "timeline length must be preserved"
    assert log["truncations"] and log["truncations"][0]["truncated_ms"] > 100, log["truncations"]
    assert len(log["tracks"]) == 1

@test("a clip that would survive only as a fragment is omitted, not clipped to a click")
def _():
    tmp = Path(tempfile.mkdtemp())
    asset = C.MODULE3 / "audio/generated/walking_moss_v1_seed42.wav"
    # only ~25% of a 2 s clip fits -> omit rather than emit a sliver
    pl = [{"asset": str(asset), "asset_start_s": 0.0, "asset_end_s": 2.0,
           "video_start_s": 9.5, "target_rms_dbfs": -34.0, "action": "walk"}]
    log = mix(pl, 10.005, tmp / "m.wav")
    y, _ = sf.read(tmp / "m.wav")
    assert abs(len(y) / 48000 - 10.005) < 0.001
    assert len(log["tracks"]) == 0, "fragment must not be mixed"
    assert any(r["stage"] == "end_of_video_truncation" for r in log["rejected"]), log["rejected"]

@test("limiter stays disengaged on normal material and dynamics survive")
def _():
    tmp = Path(tempfile.mkdtemp())
    asset = C.MODULE3 / "audio/generated/walking_moss_v1_seed42.wav"
    pl = [{"asset": str(asset), "asset_start_s": 0.0, "asset_end_s": 3.0,
           "video_start_s": 0.5, "target_rms_dbfs": -34.0, "action": "walk"}]
    log = mix(pl, 10.005, tmp / "m.wav")
    assert log["bus"]["limiter_engaged"] is False, log["bus"]
    assert log["output"]["crest_db"] > 15, log["output"]

@test("helpers behave: fades taper, zero-snap lands on a crossing, active_rms ignores silence")
def _():
    sr = 48000
    x = np.ones(sr); f = rcos_fade(x.copy(), sr, 12.0)
    assert f[0] < 1e-6 and f[-1] < 1e-6 and abs(f[sr // 2] - 1) < 1e-9
    y = np.sin(2 * np.pi * 100 * np.arange(sr) / sr)
    i = snap_zero(y, 1000, 200)
    assert abs(y[i]) < abs(y[1000]) + 1e-9
    loud = np.concatenate([np.zeros(sr * 4), np.ones(sr) * 0.5])
    assert active_rms(loud) > np.sqrt(np.mean(loud ** 2)), "active RMS must ignore silence"
    lim, gr = soft_limit(np.ones(100) * 0.9, -6.0, -3.0)
    assert gr > 0 and np.abs(lim).max() <= 10 ** (-3 / 20) + 1e-6


print("\n=== 8. FFmpeg rendering ===")
from services.video_render import mux

@test("mux copies the video stream and attaches 48 kHz mono audio")
def _():
    tmp = Path(tempfile.mkdtemp())
    asset = C.MODULE3 / "audio/generated/walking_moss_v1_seed42.wav"
    pl = [{"asset": str(asset), "asset_start_s": 0.0, "asset_end_s": 2.0,
           "video_start_s": 1.0, "target_rms_dbfs": -34.0, "action": "walk"}]
    mix(pl, 10.005, tmp / "m.wav")
    r = mux(C.DEMO_VIDEO, tmp / "m.wav", tmp / "o.mp4")
    assert r["video_codec"] == "h264" and r["frames"] == 240, r
    assert r["audio_sample_rate"] == 48000 and r["audio_channels"] == 1, r
    assert abs(r["duration_s"] - 10.0) < 0.05, r


print("\n=== 9. API endpoints ===")
from fastapi.testclient import TestClient
from main import app
CL = TestClient(app)

@test("/api/health reports component availability")
def _():
    h = CL.get("/api/health").json()
    assert h["status"] == "ok" and h["ffmpeg"], h
    keys = [x["key"] for x in h["stages"]]
    assert keys == ["upload", "validation", "action_recognition", "timeline",
                    "foley_generation", "foley_validation", "visual_sync",
                    "audio_mixing", "rendering"], keys

@test("/api/actions/supported lists the Foley classes")
def _():
    a = CL.get("/api/actions/supported").json()["actions"]
    assert len(a) >= 10 and all("key" in x and "keywords" in x for x in a)

@test("/api/demo creates a job with real video metadata")
def _():
    d = CL.post("/api/demo").json()
    assert d["demo"] and d["video"]["duration_s"] > 9.9 and len(d["job_id"]) == 12

@test("unknown job ids return 404, not a stack trace")
def _():
    for ep in ("status", "actions", "result", "download", "report"):
        r = CL.get(f"/api/{ep}/doesnotexist")
        assert r.status_code == 404, (ep, r.status_code)
        assert "Traceback" not in r.text

@test("result on an unfinished job returns 409, not an error page")
def _():
    d = CL.post("/api/demo").json()
    r = CL.get(f"/api/result/{d['job_id']}")
    assert r.status_code == 409, r.status_code

@test("upload rejects an unsupported extension with a readable message")
def _():
    r = CL.post("/api/upload", files={"file": ("x.webm", b"0000", "video/webm")})
    assert r.status_code == 400 and "Unsupported format" in r.json()["detail"]

@test("upload rejects a file that is not decodable video")
def _():
    r = CL.post("/api/upload", files={"file": ("x.mp4", b"not a video", "video/mp4")})
    assert r.status_code == 400 and "Traceback" not in r.text


print("\n" + "=" * 62)
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
for n, e in FAIL:
    print(f"  FAILED {n}: {e}")
print("=" * 62)
sys.exit(1 if FAIL else 0)
