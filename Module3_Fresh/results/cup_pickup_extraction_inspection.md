# Cup Pickup — Extraction Feasibility Inspection (read-only)

**Date:** 2026-08-25
**Question:** can a ceramic handling/contact segment be safely extracted from the approved drinking
Foley and reused for the cup-pickup event?

# CONCLUSION: ❌ NO SUITABLE SEGMENT EXISTS — no extraction performed

A clean, isolated ceramic transient **does** exist in the drinking asset. It is **not** usable as a
cup pickup. Reporting that rather than forcing an extraction, as instructed.

**Nothing was created, cut, copied or modified.** `drinking_moss_v2_local_seed42.wav` was opened
read-only and remains `r--r--r--` with its recorded hash.

---

## Method

Analysed all 40 transients in the 10 s drinking asset. Each was scored against three ceramic-contact
criteria: sharp attack (≤12 ms), 1–5 kHz dominant (≥35 % of segment energy — the band that carries
ceramic contact and ring), and isolation from neighbouring louder material (≤−9 dB).

**Result: exactly 1 of 40 events met all three.**

## 1. Exact source timestamp of the candidate

| | |
|---|---|
| **Transient peak** | **t = 8.981 s** |
| **Tightest clean window** | **8.860 – 9.000 s** |
| Bright cluster | ~8.925 – 9.000 s |

## 2. Duration

**140 ms** for the isolated window; roughly **50–75 ms** of actual transient content within it.

## 3. Why it is the best candidate

Measured over 8.860–9.000 s:

| Property | Value | Reading |
|---|---|---|
| 1–5 kHz energy | **49.1 %** | strong ceramic band |
| 200 Hz–1 kHz energy | **0.7 %** | essentially **no wet/mouth content** |
| 5–15 kHz | 21.7 % | bright, consistent with ceramic |
| Modal peaks | **4816 / 4851 / 4828 Hz** | tight cluster — a plausible ceramic ring |
| Attack | 2.4 ms | sharp contact |
| Decay to −20 % | 3.9 ms | short, dry |
| Isolation | **−22.1 dB before, −14.3 dB after** | cleanly separable |
| Peak level | −43.1 dBFS | see below |

It is genuinely the one ceramic-dominant, sharply-attacked, well-isolated transient in the file.

## 4. Can it be reused without sounding like drinking?

**It would not sound like drinking — but it would not sound like a pickup either.** Three reasons,
in order of severity:

### It is the wrong physical event

In a drinking recording, a bright ~4.8 kHz ceramic transient is a mug contacting **lips or teeth**.
There is no wooden table anywhere in that recording — the mug is at the person's mouth throughout.

A cup pickup is acoustically a different event: a low-frequency **wood component** as the base parts
from the table, **friction/scrape** across the surface, then the lift. The candidate has none of
that. Its 34.3 % below 200 Hz is broadband residue, not a wood-contact signature.

### It is one impulse, not a sequence

140 ms containing a single tink. A pickup requires a **contact → grip → lift** progression. A single
transient cannot represent it, and repeating or stretching it would be fabrication rather than reuse.

### The level is impractical

−43.1 dBFS: **19.6 dB** below the drinking file's own peak, **35.8 dB** below the approved walking
asset. Matching walking would need roughly **+36 dB**, which also lifts the surrounding floor
(−62 to −67 dBFS) to around −26 to −31 dBFS — audible hiss inside a 140 ms clip.

### Context confirms it belongs to a drinking gesture

Immediately after the candidate, at **9.20–9.35 s**, sit the loudest events in the entire file
(−26 to −32 dBFS, **93–99 % of energy in 200 Hz–1 kHz**) — unmistakable swallow/mouth sounds. The
candidate sits 200 ms ahead of them. Cutting at 9.000 s avoids them cleanly, but their presence
confirms this transient is part of a drinking action, not an independent handling sound.

## Why the other 39 events do not qualify

- Nine are **partial** matches — ceramic-band energy without a sharp attack (attacks of 22–167 ms),
  which is characteristic of liquid and mouth movement rather than a hard contact.
- The loudest events in the file (−27 to −34 dBFS at 0.813, 1.877, 3.264, 6.229, 9.224, 9.331 s) are
  all **200 Hz–1 kHz dominant at 50–97 %** — the sip/swallow content.
- The remainder are low-level broadband material below −57 dBFS.

Overall the file is **62.0 % 200 Hz–1 kHz** — it is predominantly a mouth-and-liquid recording, with
ceramic character present but sparse and quiet.

## Recommendation

**Do not extract.** Reusing this transient would place a 140 ms lip-contact tink, amplified ~36 dB,
where a contact-friction-lift sequence belongs. It would misrepresent the action and add audible
noise. The correct outcome here is the one you allowed for: report that no suitable segment exists.

One observation worth carrying forward: a short, bright ceramic contact transient is a much closer
match for **cup placement** — setting a mug down *is* a contact event — than for a pickup. That is a
note, not a proposal; you have said placement will be generated with MOSS.

## Status of cup pickup

| Asset | Verdict |
|---|---|
| `cup_pickup_moss_v1_seed42.wav` | UNCERTAIN / unapproved — retained |
| `cup_pickup_moss_v2_seed42.wav` | FAIL — retained |
| Extraction from drinking asset | **not viable** — no asset created |

No further MOSS generations for cup pickup, per your instruction. Cup pickup currently has **no
approved asset**.

## Locked assets — verified after inspection

```
drinking_moss_v2_local_seed42.wav: OK   (r--r--r--)
walking_moss_v1_seed42.wav:        OK   (r--r--r--)
```

Nothing synchronised, no MP4, no mixing, no files created or modified.
