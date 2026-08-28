# Module 3 — Prompt Reference

**Document version:** 1.0 (final)

Verbatim record of the prompts and sampler settings that produced the three Foley assets used in the
final pipeline. Transcribed from the generation records in `results/*_generation.json`.

---

## Common sampler configuration

All three generations used identical settings. No parameter sweeps were performed; a single
generation was run per action.

| Parameter | Value |
|---|---|
| Model | MOSS-SoundEffect v2.0 (`OpenMOSS-Team/MOSS-SoundEffect-v2.0`) |
| Seed | 42 |
| Inference steps | 50 |
| CFG scale | 4 |
| Sigma shift | 5 |
| Requested duration | 10.0 s |
| Internally denoised duration | 30 s (fixed-size latent, then cropped) |
| Sample rate | 48,000 Hz |
| Channels | 1 (mono) |
| Device | MPS |
| Parameter dtype | bfloat16 |
| float16 used | no |
| CUDA used | no |

The model appends `" duration: 10.0s"` to the positive prompt before encoding, matching its
training-time convention. This suffix is applied automatically and is not part of the authored text.

---

## 1. Drinking

**Asset:** `audio/generated/drinking_moss_v2_local_seed42.wav` — approved
**Status:** approved on listening

### Positive prompt

```
close-up realistic Foley of a person taking several natural sips of water from a ceramic mug,
distinct sipping sounds followed by natural swallowing, subtle cup-to-lips contact and realistic
ceramic handling, continuous recognizable drinking action, isolated Foley recording, no speech,
no music, no ambience
```

### Negative prompt

```
(empty)
```

**Note on the empty negative prompt.** This prompt carries its negations inline in the positive text
("no speech, no music, no ambience") rather than in a separate negative prompt. This is the exact
configuration that produced the approved result and is recorded as such.

The prompt is 49 BPE tokens, within the CLIP-style text encoder's context. An earlier 189-token
prompt was truncated at the encoder limit, discarding 59 % of its content including all negative
clauses — a failure mode identified by measuring token counts before generation.

### Measured output

| Property | Value |
|---|---|
| Duration | 10.000 s |
| Peak | −23.5 dBFS |
| Energy in 1–5 kHz | 28.96 % |
| Detected events | 12 |

---

## 2. Walking

**Asset:** `audio/generated/walking_moss_v1_seed42.wav` — approved
**Status:** approved on listening

### Positive prompt

```
close-up realistic Foley recording of natural human footsteps walking around a wooden table on a
hard wooden floor, clearly audible alternating left and right footsteps with realistic heel and toe
impacts, natural walking rhythm and slight variation between steps, subtle shoe contact and floor
resonance, isolated dry Foley recording, no speech, no music, no ambience, no room tone, no
cinematic sound design
```

### Negative prompt

```
music, speech, talking, voice, singing, background ambience, room tone, environmental noise, crowd,
traffic, cinematic sound design, electronic sounds, synthetic sounds, exaggerated impacts, reverb
```

### Measured output

| Property | Value |
|---|---|
| Duration | 10.000 s |
| Peak | −7.3 dBFS |
| Detected footsteps | 15 |
| Mean step interval | 0.530 s (≈108 steps/min) |
| Envelope modulation peak | 1.5 Hz (walking cadence; speech would peak near 4–5 Hz) |
| Harmonic ratio | 0.0041 (negligible harmonic content — not speech or music) |
| Dynamic range | 50.7 dB |

---

## 3. Cup placement

**Source asset:** `audio/generated/cup_placement_moss_v1_seed42.wav` (10 s, retained unmodified)
**Derived asset used in the mix:** `audio/generated/cup_placement_foley_final.wav` (400 ms)
**Status:** accepted on measurement — **not approved on listening** (see limitation 10.2)

### Positive prompt

```
close-up realistic Foley recording of a person naturally placing a ceramic mug down on a solid
wooden table, one clear ceramic-on-wood contact followed by a short natural wooden table resonance
and gentle ceramic settling, realistic hand release and subtle mug movement, clean isolated object
Foley, physically believable contact and decay, no exaggerated impact
```

### Negative prompt

```
music, speech, voice, singing, footsteps, walking, drinking, sipping, swallowing, pouring water,
background ambience, room tone, environmental noise, multiple impacts, dropping the mug, breaking
ceramic, smashing, heavy impact, metallic sound, electronic sound, synthetic sound, cinematic sound
design, long reverb
```

### Derivation of the final asset

The 10-second generation contains five separate impact clusters. One cluster was selected and cropped:

| Property | Value |
|---|---|
| Source crop | 6.150 – 6.550 s |
| Duration | 400 ms |
| Fades | 8 ms in and out |
| Selection criteria | highest cluster peak; cleanest cut edges (−39.6 dB relative to cluster peak); contains contact → resonance → settle |

### Measured output (10 s source)

| Property | Value |
|---|---|
| Duration | 10.000 s |
| Peak | −30.5 dBFS |
| Energy in 1–5 kHz | 0.52 % |
| Energy below 200 Hz | 64.5 % |
| Impacts above −40 dBFS | 8, in 5 clusters |
| Event-to-background ratio | 44.2 dB |

The 0.52 % figure in the 1–5 kHz band is the basis for limitation 10.2: ceramic contact is
characterised by that band, and the drinking asset — recorded from the same mug in the same prompt
family — measures 28.96 %.

---

## 4. Cup pickup — no approved prompt

Two prompts were attempted for cup pickup. **Neither produced an approved asset, and no cup-pickup
audio appears in the final output.** They are recorded here for completeness and to document the
negative result.

### Attempt 1 — outcome: UNCERTAIN, not approved

Positive prompt described a hand picking up a ceramic mug from a wooden table with ceramic contact,
lift and grip sounds. Negative prompt contained 17 terms.

Measured: peak −36.0 dBFS; 1.68 % energy in 1–5 kHz; 27 detected events, none dominant.

### Attempt 2 — outcome: FAIL

Positive prompt added ceramic friction against wood and a short ceramic resonance during the lift.
Negative prompt was expanded to 23 terms including `bass rumble`, `hiss`, `heavy impact`,
`wooden knocks without ceramic`.

Measured: peak −61.7 dBFS; **40 distinct sample values** in the entire file; 1.06 dB dynamic range;
95 % harmonic content; per-second RMS varying by under 3 % across ten seconds. The generation
collapsed to a near-constant low-frequency tone.

### Observation

Output level tracked negative-prompt length across the two attempts (17 terms → −36.0 dBFS;
23 terms → −61.7 dBFS). This is a two-point observation and does not establish a relationship. It was
recorded but not acted upon, and no further generation was attempted.

---

*End of prompt reference.*
