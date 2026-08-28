"""
MODULE 2 — POST-PROCESSING: boundary resolution + conservative suspect flagging.

Operates ONLY on an existing results JSON. Runs no model, loads no checkpoint.

    RAW WINDOW PREDICTIONS   (untouched, audit record)
        -> MERGED OVERLAPPING SEGMENTS   (untouched, audit record)
            -> RESOLVED NON-OVERLAPPING SEGMENTS   (new field)

BOUNDARY RESOLUTION (deterministic)
    Segments are sorted chronologically. For each consecutive pair whose spans
    overlap, the shared boundary becomes the MIDPOINT of the overlap:
        mid = (current.end + next.start) / 2
        current.end = mid ;  next.start = mid
    Processing runs strictly left-to-right, so each boundary is decided once and
    the result is deterministic. No action is invented, relabelled, or deleted.

SUSPECT FLAGGING (conservative — never deletes)
    A segment is marked "suspect" when its evidence is thin (currently: supported
    by a single window). It is ALWAYS preserved, with the reasons recorded, so a
    human can review. No confidence threshold ever removes an action.
"""
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(HERE, "results", "module2_action_segments.json")
TIMELINE_PATH = os.path.join(HERE, "results", "module2_action_timeline.txt")
MIN_SUPPORT_CONFIRMED = 2      # >=2 supporting windows -> "confirmed"
EPS = 1e-6


def fingerprint(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]


def resolve_boundaries(segments):
    """Midpoint boundary resolution. Returns new list; inputs are not mutated."""
    segs = [dict(s) for s in sorted(segments, key=lambda s: (s["start"], s["end"]))]
    adjustments = []
    for i in range(len(segs) - 1):
        cur, nxt = segs[i], segs[i + 1]
        if cur["end"] > nxt["start"] + EPS:                 # overlap
            mid = round((cur["end"] + nxt["start"]) / 2.0, 3)
            adjustments.append({
                "between": [cur["action"], nxt["action"]],
                "overlap": [nxt["start"], cur["end"]],
                "overlap_duration": round(cur["end"] - nxt["start"], 3),
                "midpoint_boundary": mid,
                "prev_end_before": cur["end"], "next_start_before": nxt["start"],
            })
            cur["end"] = mid
            nxt["start"] = mid
    return segs, adjustments


def flag_suspects(resolved, original):
    """Conservative: flag thin evidence, never delete."""
    orig_by_action = {(s["action"], tuple(s["supporting_windows"])): s for s in original}
    n = len(resolved)
    out = []
    for i, s in enumerate(resolved):
        support = len(s.get("supporting_windows", []))
        dur = round(s["end"] - s["start"], 3)
        reasons = []
        if support < MIN_SUPPORT_CONFIRMED:
            reasons.append(f"single_window_support ({support} window)")
        if dur <= 0 + EPS:
            reasons.append("collapsed_to_zero_duration_by_boundary_resolution")
        if i == 0:
            reasons.append("first_segment (window sees pre-action framing)")
        if i == n - 1:
            reasons.append("last_segment (window sees post-action framing)")
        status = "confirmed" if support >= MIN_SUPPORT_CONFIRMED else "suspect"
        if s["action"].upper() == "UNKNOWN":
            status = "unknown"                              # preserved, never dropped
        out.append({
            "action": s["action"],
            "action_head": s.get("action_head"),
            "start": round(s["start"], 3),
            "end": round(s["end"], 3),
            "duration": dur,
            "supporting_windows": s.get("supporting_windows", []),
            "support_count": support,
            "status": status,
            "flags": reasons,
            "original_span": [orig_by_action.get((s["action"], tuple(s.get("supporting_windows", []))), {}).get("start"),
                              orig_by_action.get((s["action"], tuple(s.get("supporting_windows", []))), {}).get("end")],
        })
    return out


def validate(resolved):
    checks = {}
    checks["chronological"] = all(resolved[i]["start"] <= resolved[i + 1]["start"] + EPS
                                  for i in range(len(resolved) - 1))
    checks["non_overlapping"] = all(resolved[i]["end"] <= resolved[i + 1]["start"] + EPS
                                    for i in range(len(resolved) - 1))
    checks["no_negative_duration"] = all(s["end"] >= s["start"] - EPS for s in resolved)
    checks["count_preserved"] = None  # filled by caller
    return checks


def main():
    with open(JSON_PATH) as f:
        data = json.load(f)

    fp_windows_before = fingerprint(data["windows"])
    fp_actions_before = fingerprint(data["actions"])
    n_before = len(data["actions"])

    print("=== INPUT (audit records, must stay untouched) ===")
    print(f"  raw windows:      {len(data['windows'])}  fingerprint={fp_windows_before}")
    print(f"  merged segments:  {n_before}  fingerprint={fp_actions_before}\n")

    print("=== MERGED OVERLAPPING SEGMENTS (before) ===")
    for s in data["actions"]:
        print(f"  {s['start']:5.2f} - {s['end']:5.2f}  {s['action']:<20} windows={s['supporting_windows']}")

    resolved_raw, adjustments = resolve_boundaries(data["actions"])
    resolved = flag_suspects(resolved_raw, data["actions"])

    print(f"\n=== BOUNDARY ADJUSTMENTS ({len(adjustments)}) ===")
    for a in adjustments:
        print(f"  '{a['between'][0]}' | '{a['between'][1]}': overlap {a['overlap']} "
              f"({a['overlap_duration']}s) -> boundary @ {a['midpoint_boundary']}")

    print("\n=== RESOLVED NON-OVERLAPPING SEGMENTS ===")
    for s in resolved:
        fl = f"  flags={s['flags']}" if s["flags"] else ""
        print(f"  {s['start']:5.2f} - {s['end']:5.2f}  {s['action']:<20} "
              f"dur={s['duration']:4.2f}s  support={s['support_count']}  [{s['status']}]{fl}")

    checks = validate(resolved)
    checks["count_preserved"] = (len(resolved) == n_before)
    checks["raw_windows_unmodified"] = (fingerprint(data["windows"]) == fp_windows_before)
    checks["merged_segments_unmodified"] = (fingerprint(data["actions"]) == fp_actions_before)
    print("\n=== VALIDATION ===")
    for k, v in checks.items():
        print(f"  {k:28s}: {'PASS' if v else 'FAIL'}")

    data["resolved_actions"] = resolved
    data["boundary_resolution"] = {
        "method": "midpoint of overlap, left-to-right, deterministic",
        "min_support_confirmed": MIN_SUPPORT_CONFIRMED,
        "policy": "never delete; thin-evidence segments preserved and marked 'suspect'",
        "adjustments": adjustments,
        "validation": checks,
    }
    with open(JSON_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nwrote resolved_actions -> {JSON_PATH}")

    with open(TIMELINE_PATH) as f:
        existing = f.read()
    with open(TIMELINE_PATH, "w") as f:
        f.write(existing.rstrip() + "\n\n")
        f.write("RESOLVED NON-OVERLAPPING SEGMENTS (midpoint boundary resolution)\n\n")
        for s in resolved:
            tag = "" if s["status"] == "confirmed" else f"   [{s['status'].upper()}]"
            f.write(f"{s['start']:5.2f} {'-'*14} {s['end']:5.2f}  {s['action']:<22} "
                    f"({s['duration']:.2f}s, {s['support_count']} win){tag}\n")
    print(f"appended resolved timeline -> {TIMELINE_PATH}")
    print("\nRESULT:", "POSTPROCESS_OK" if all(checks.values()) else "POSTPROCESS_VALIDATION_FAILED")


if __name__ == "__main__":
    main()
