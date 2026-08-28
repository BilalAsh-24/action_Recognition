"""Module 3 — configuration, paths and the approved-asset registry."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent            # Module3_Fresh/
PROJECT = ROOT.parent

# --- inputs (read-only) -----------------------------------------------------
SOURCE_VIDEO_ORIGINAL = PROJECT / "03-FoleyCrafter-Test/action-recognition/module2_test_video.mp4"
SOURCE_VIDEO = ROOT / "input" / "test_video.mp4"          # verified-identical project copy
MODULE2_JSON = ROOT / "module2" / "module2_action_segments.json"

# --- approved Foley assets --------------------------------------------------
GEN = ROOT / "audio" / "generated"
ASSET_DRINKING  = GEN / "drinking_moss_v2_local_seed42.wav"      # LOCKED
ASSET_WALKING   = GEN / "walking_moss_v1_seed42.wav"             # LOCKED
ASSET_PLACEMENT = GEN / "cup_placement_foley_final.wav"          # derived, see make_placement_asset.py
PLACEMENT_SOURCE = GEN / "cup_placement_moss_v1_seed42.wav"      # 10 s MOSS source
PLACEMENT_CROP = (6.15, 6.55)      # chosen cluster: loudest, cleanest edges, contact+resonance+settle

LOCKED = [ASSET_DRINKING, ASSET_WALKING]

# --- outputs ----------------------------------------------------------------
MIXED_WAV  = ROOT / "audio" / "mixed" / "final_synchronized_audio.wav"
FINAL_MP4  = ROOT / "output" / "final_silent_to_audio.mp4"
SYNC_JSON  = ROOT / "results" / "final_synchronization.json"
REPORT_MD  = ROOT / "results" / "final_module3_report.md"
EVENTS_JSON = ROOT / "results" / "visual_events.json"

# --- audio ------------------------------------------------------------------
SR = 48000
FADE_MS = 8.0                      # short fades at every crop boundary

# Perceptual level targets (peak dBFS in the final mix). Chosen for scene balance,
# not to make every asset equally loud: a cup set on a table is the most percussive
# event, footsteps sit mid-ground, sipping is intimate and quiet.
TARGET_PEAK_DBFS = {
    "walk around table":  -20.0,
    "drink from cup":     -24.0,
    "place cup on table": -18.0,
}
MIX_HEADROOM_DBFS = -3.0           # ceiling for the summed mix

# Walking search span (seconds). Module 2 labels 0.0-1.5 s as "stand", but marks it
# suspect with flag "first_segment (window sees pre-action framing)", and the footage
# disagrees: mean lower-body motion is 1.708 in 0.0-1.5 s versus 1.711 in the labelled
# walk interval, and drops to 0.954 only once the person stops to pick up the cup.
# Foot contacts are therefore searched from the start of the video. The Module 2
# boundaries themselves are NOT modified - only where footstep audio is placed.
WALK_SEARCH_SPAN = (0.0, 2.50)

# --- actions with no approved Foley ----------------------------------------
UNAVAILABLE_FOLEY = {
    "pick up cup": "No approved Foley. Two MOSS generations (UNCERTAIN, FAIL) and an "
                   "extraction study from the drinking asset (NOT VIABLE) were rejected. "
                   "Left intentionally silent; not fabricated.",
    # "stand" intentionally omitted: the footage shows walking during that label,
    # so footstep Foley legitimately extends into it (see WALK_SEARCH_SPAN).
}
