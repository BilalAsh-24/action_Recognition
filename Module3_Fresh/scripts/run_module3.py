#!/usr/bin/env python
"""Module 3 end-to-end orchestrator.

  silent video -> Module 2 timeline -> visual event localisation -> approved MOSS Foley
    -> temporal synchronisation -> mixing -> final MP4 -> quality gate -> reports

Run:  moss/venv-moss/bin/python scripts/run_module3.py
"""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import m3_config as C

STEPS = [("derive placement asset", "make_placement_asset.py"),
         ("localise visual events",  "visual_events.py"),
         ("build sync plan",         "sync_actions.py"),
         ("mix audio",               "audio_mixer.py"),
         ("build final video",       "build_final_video.py"),
         ("quality gate",            "analyze_sync.py"),
         ("write final reports",     "write_reports.py"),
         ("polish mix",              "polish_mix.py"),
         ("build polished video",    "build_polished_video.py"),
         ("polished QA",             "qa_polished.py"),
         ("write polished report",   "write_polished_report.py")]


def main() -> int:
    for i, (label, script) in enumerate(STEPS, 1):
        print(f"\n{'='*70}\n[{i}/{len(STEPS)}] {label}  ({script})\n{'='*70}", flush=True)
        r = subprocess.run([sys.executable, str(HERE / script)])
        if r.returncode != 0:
            print(f"\nFAILED at step {i}: {script}")
            return r.returncode
    print("\nModule 3 build complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
