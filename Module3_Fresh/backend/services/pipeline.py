"""End-to-end Module 2 + Module 3 pipeline, driven by the job store."""
from __future__ import annotations
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import config as C
from core.jobs import Job, JobStore
from services import video_service as VS
from services import action_recognition as AR
from services import sound_generation as SG
from services import synchronization as SY
from services import audio_processing as AP
from services import video_render as VR
from services import foley_validation as FV
from services.prompt_map import resolve

# Actions whose sound may legitimately begin before the labelled interval
# (footsteps often start while an earlier label is still active).
WIDE_SEARCH_STRATEGIES = {"footstep"}


def _conf(status: str) -> str:
    return {"confirmed": "High", "suspect": "Medium"}.get(status, "Medium")


def run_pipeline(job: Job, store: JobStore) -> None:
    jid = job.id
    settings = {**C.DEFAULTS, **(job.settings or {})}
    jdir = C.JOBS / jid
    jdir.mkdir(parents=True, exist_ok=True)
    video = Path(job.video_path)

    # ---------------------------------------------------------- 2. validation
    store.stage(jid, "validation", "active", 4)
    info = VS.probe(video)
    warnings = VS.validate(info)
    store.stage(jid, "validation", "done", 8,
                video_info=info.dict(), warnings=warnings)

    # -------------------------------------------------- 3. action recognition
    store.stage(jid, "action_recognition", "active", 10)
    m2_json = jdir / "module2.json"
    if job.is_demo and C.DEMO_MODULE2.is_file():
        m2 = AR.load_existing(C.DEMO_MODULE2)
        m2_json.write_text(json.dumps(m2, indent=2))
    else:
        prog = jdir / "m2_progress.json"

        def _poll():
            while True:
                j = store.get(jid)
                if not j or j.stages.get("action_recognition") != "active":
                    return
                try:
                    d = json.loads(prog.read_text())
                    store.stage(jid, "action_recognition", "active",
                                10 + 0.35 * float(d.get("pct", 0)))
                except Exception:
                    pass
                time.sleep(1.0)

        import threading
        threading.Thread(target=_poll, daemon=True).start()
        m2 = AR.run(video, m2_json, progress_file=prog)
    store.stage(jid, "action_recognition", "done", 45)

    # ------------------------------------------------------------ 4. timeline
    store.stage(jid, "timeline", "active", 46)
    resolved = m2.get("resolved_actions") or m2.get("actions") or []
    if not resolved:
        raise RuntimeError("Action recognition completed but produced no action timeline.")
    actions = [{"action": a["action"], "start": float(a["start"]), "end": float(a["end"]),
                "status": a.get("status", "candidate"),
                "confidence": _conf(a.get("status", ""))} for a in resolved]
    store.stage(jid, "timeline", "done", 50, actions=actions)

    # ---------------------------------------------- 5. Foley generation (MOSS)
    store.stage(jid, "foley_generation", "active", 51)
    needed: dict[str, object] = {}
    unsupported: list[dict] = []
    for a in actions:
        spec, reason = resolve(a["action"])
        if spec is None:
            unsupported.append({"action": a["action"], "start": a["start"],
                                "end": a["end"], "reason": reason})
        else:
            needed.setdefault(spec.key, spec)

    if not needed:
        store.stage(jid, "foley_generation", "skipped", 55, unsupported=unsupported)
        raise RuntimeError(
            "Action recognition completed, but no supported Foley action was found. "
            "The original video can still be exported without generated audio.")

    generated: list[dict] = []
    for i, (key, spec) in enumerate(needed.items(), 1):
        base_pct = 51 + 21 * (i - 1) / max(1, len(needed))

        def _prog(n, total, seed, _b=base_pct, _k=spec.label):
            store.stage(jid, "foley_generation", "active",
                        _b + 21 / max(1, len(needed)) * (n - 1) / max(1, total),
                        current_detail=f"{_k}: candidate {n}/{total} (seed {seed})")

        t0 = time.time()
        best, attempts = SG.generate_best(
            spec, settings, max_candidates=int(settings.get("max_candidates", 3)),
            on_progress=_prog)
        generated.append({
            "key": key, "label": spec.label,
            "path": best["path"] if best else attempts[-1]["path"],
            "cached": all(a["cached"] for a in attempts),
            "seconds": round(time.time() - t0, 1),
            "prompt": spec.prompt, "negative": spec.negative,
            "candidates": len(attempts), "attempts": attempts,
            "selected_seed": best["seed"] if best else None,
            "selected_score": best["score"] if best else 0.0,
            "validated": bool(best)})
        store.stage(jid, "foley_generation", "active",
                    51 + 21 * i / max(1, len(needed)), generated_audio=generated)
    store.stage(jid, "foley_generation", "done", 72,
                generated_audio=generated, unsupported=unsupported)

    # ------------------------------------- 6. Foley quality validation
    # Candidates were measured RAW during generation. This stage records the verdicts
    # and decides which assets may enter the mix. A class whose every candidate failed
    # is marked unsupported and its intervals stay silent; the job continues.
    store.stage(jid, "foley_validation", "active", 73)
    validations, usable = [], {}
    for g in generated:
        spec = needed[g["key"]]
        best = next((a for a in g["attempts"]
                     if a["seed"] == g["selected_seed"]), None) if g["selected_seed"] else None
        validations.append({
            "key": g["key"], "label": spec.label,
            "ok": bool(best), "selected_seed": g["selected_seed"],
            "score": g["selected_score"], "candidates_tried": len(g["attempts"]),
            "attempts": [{"seed": a["seed"], "ok": a["ok"], "score": a["score"],
                          "reason": a["reason"], "metrics": a["metrics"]}
                         for a in g["attempts"]],
            "reason": (best["reason"] if best else
                       "; ".join(f"seed {a['seed']}: {a['reason']}" for a in g["attempts"])),
            "metrics": (best or g["attempts"][-1])["metrics"]})
        if best:
            g["quality"] = {k: best["metrics"][k] for k in
                            ("peak_dbfs", "dynamic_range_db", "effective_bits",
                             "harmonic_ratio", "required_gain_db")}
            usable[g["key"]] = Path(best["path"])
        else:
            last = g["attempts"][-1]
            g["quality"] = {k: last["metrics"][k] for k in
                            ("peak_dbfs", "dynamic_range_db", "effective_bits",
                             "harmonic_ratio", "required_gain_db")}
            for a in actions:
                sp, _ = resolve(a["action"])
                if sp and sp.key == g["key"] and not any(
                        u["action"] == a["action"] and u["start"] == a["start"]
                        for u in unsupported):
                    unsupported.append({
                        "action": a["action"], "start": a["start"], "end": a["end"],
                        "reason": (f"No usable Foley generated — all {len(g['attempts'])} "
                                   f"candidate(s) failed quality validation. The interval "
                                   f"was intentionally left silent."),
                        "detail": "; ".join(f"seed {a2['seed']}: {a2['reason']}"
                                            for a2 in g["attempts"]),
                        "status": "no_usable_foley",
                        "candidates_tried": len(g["attempts"]),
                        "metrics": last["metrics"]})
    store.stage(jid, "foley_validation", "done", 76,
                generated_audio=generated, unsupported=unsupported,
                report={**(job.report or {}), "validations": validations})

    # -------------------------------------------------- 7. visual sync
    store.stage(jid, "visual_sync", "active", 77)
    mo = SY.analyse_video(video)
    by_key = usable

    # Merge consecutive intervals that resolve to the SAME Foley class. Module 2 emits
    # one span per window, so a single continuous activity (e.g. stirring) arrives as
    # several adjacent labels. Treating them separately would place the same short
    # source segment repeatedly, which is audible as an obvious loop.
    merged_actions, MERGE_GAP = [], 0.15
    for a in actions:
        sp, _ = resolve(a["action"])
        key = sp.key if sp else None
        # Only CONTINUOUS activities merge. Discrete contact events must not: two
        # separate spoon placements are two separate sounds, and merging them would
        # discard one of the visual events.
        mergeable = sp is not None and sp.strategy == "continuous"
        if (merged_actions and key is not None and mergeable
                and merged_actions[-1]["_key"] == key
                and a["start"] - merged_actions[-1]["end"] <= MERGE_GAP):
            merged_actions[-1]["end"] = a["end"]
            merged_actions[-1]["_merged"].append(a["action"])
        else:
            merged_actions.append({**a, "_key": key, "_merged": [a["action"]]})
    merge_log = [{"action": m["action"], "start": m["start"], "end": m["end"],
                  "merged_from": m["_merged"]}
                 for m in merged_actions if len(m["_merged"]) > 1]
    placements, vis_events = [], []
    for a in merged_actions:
        spec, _ = resolve(a["action"])
        if spec is None or spec.key not in by_key:
            continue
        search = (0.0, a["end"]) if spec.strategy in WIDE_SEARCH_STRATEGIES else None
        evs = SY.detect_events(mo, a["action"], spec, a["start"], a["end"], search)
        vis_events += [e.dict() for e in evs]
        for pl in SY.plan_action(spec, by_key[spec.key], evs, (a["start"], a["end"]),
                                 info.duration_s, search):
            pl.update(action=a["action"], action_key=spec.key,
                      asset=str(by_key[spec.key]), target_rms_dbfs=spec.target_rms_dbfs)
            placements.append(pl)
    # An empty placement list is a legitimate outcome when every asset was rejected
    # or no visual event could be located. The video is still produced, silent.
    silent_output = not placements
    if silent_output and not unsupported:
        raise RuntimeError(
            "Foley was generated, but no visual event could be located to synchronise it to. "
            "The original video can still be exported without generated audio.")
    store.stage(jid, "visual_sync", "done", 85, visual_events=vis_events)

    # ------------------------------------------------------- 7. audio mixing
    store.stage(jid, "audio_mixing", "active", 86)
    out_wav = C.OUTPUTS / f"{jid}_audio.wav"
    mixlog = AP.mix(placements, info.duration_s, out_wav, settings["sample_rate"])
    store.stage(jid, "audio_mixing", "done", 92,
                mix=mixlog, final_audio=str(out_wav))

    # ---------------------------------------------------------- 8. rendering
    store.stage(jid, "rendering", "active", 93)
    out_mp4 = C.OUTPUTS / f"{jid}_final.mp4"
    render = VR.mux(video, out_wav, out_mp4, settings["sample_rate"])
    store.stage(jid, "rendering", "done", 99, final_video=str(out_mp4))

    # ------------------------------------------------------------- 9. report
    errs = [abs(e) for p in placements for e in p.get("per_event_error_ms", [])]
    worst = round(max(errs), 1) if errs else None
    report = {
        "job_id": jid, "settings": settings, "video": info.dict(),
        "validations": validations,
        "silent_output": silent_output,
        "module2": {"model": m2.get("model"), "actions": actions,
                    "windows": len(m2.get("windows", []))},
        "visual_events": vis_events, "merged_intervals": merge_log,
        "foley": generated, "unsupported": unsupported,
        "placements": placements, "mix": mixlog, "render": render,
        "sync": {"worst_error_ms": worst,
                 "note": "measured from the alignment plan; footstep runs report per-event error"},
        "counts": {"actions_detected": len(actions),
                   "sounds_generated": len(usable),
                   "sounds_rejected": len(generated) - len(usable),
                   "placements": len(placements),
                   "unsupported_actions": len(unsupported)},
    }
    (jdir / "report.json").write_text(json.dumps(report, indent=2))
    store.update(jid, report=report)
