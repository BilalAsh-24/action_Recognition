"""Open-vocabulary Foley prompt synthesis.

The curated classes in prompt_map.py are hand-tuned and validated by ear, but they
are a closed set: any action outside them used to resolve to nothing, and the job
never reached the sound model at all.

This module removes that ceiling. Given an arbitrary action phrase from Module 2
("kicking a football", "chopping vegetables", "a dog barking"), it writes a MOSS
prompt and picks the synchronisation strategy that the phrase implies, so every
recognised action can be sounded.

It is deterministic on purpose. The same phrase always yields the same prompt, which
keeps the content-addressed Foley cache meaningful and makes the behaviour testable
without invoking a model.

How the strategy is chosen
--------------------------
A Foley class needs four things beyond a prompt: how to find the audible instant in
the video (strategy), which part of the frame to measure motion in (region), how to
cut the 10 s generated asset down (selection), and how loud it sits (level). All four
follow from the ARCHETYPE of the verb, not from the object. "Kick", "slam" and "drop"
are all single transients regardless of what is kicked, slammed or dropped.
"""
from __future__ import annotations
import re
from typing import Optional

# --------------------------------------------------------------------------- verbs
# Each archetype maps to (strategy, region, selection, target_rms_dbfs).
# strategy  : footstep | hold | contact | continuous
# region    : feet | head | table | full
# selection : steps | wet_segment | event | slice

ARCHETYPE_SYNC = {
    "locomotion": ("footstep",   "feet",  "steps",       -34.0),
    "impact":     ("contact",    "full",  "event",       -31.0),
    "placement":  ("contact",    "table", "event",       -33.0),
    "pickup":     ("contact",    "table", "event",       -33.0),
    "mechanism":  ("contact",    "full",  "event",       -32.0),
    "friction":   ("continuous", "full",  "slice",       -34.0),
    "liquid":     ("continuous", "table", "slice",       -34.0),
    "oral":       ("hold",       "head",  "wet_segment", -38.0),
    "ambient":    ("continuous", "full",  "slice",       -36.0),
}

ARCHETYPE_VERBS: dict[str, set[str]] = {
    "locomotion": {"walk", "run", "jog", "sprint", "march", "step", "stroll", "pace",
                   "tiptoe", "climb", "descend", "stomp", "shuffle"},
    "impact":     {"kick", "hit", "strike", "punch", "slam", "bang", "knock", "drop",
                   "throw", "toss", "catch", "bounce", "land", "jump", "hop", "stamp",
                   "chop", "slice", "cut", "smash", "crash", "tap", "clap", "slap",
                   "whack", "swing", "batter", "dribble", "serve", "spike", "head"},
    "placement":  {"place", "put", "set", "insert", "load", "lower", "deposit",
                   "stack", "rest", "lay"},
    "pickup":     {"pick", "lift", "take", "grab", "remove", "pull", "retrieve",
                   "raise", "collect", "snatch"},
    "mechanism":  {"open", "close", "shut", "press", "push", "click", "flip", "toggle",
                   "switch", "turn", "twist", "unlock", "lock", "zip", "unzip",
                   "latch", "buckle", "fasten", "crank", "wind", "plug"},
    "friction":   {"stir", "scrub", "rub", "saw", "sweep", "brush", "wipe", "sand",
                   "grate", "grind", "whisk", "mix", "knead", "slide", "drag", "scrape",
                   "polish", "file", "type", "write", "scribble", "erase", "shave",
                   "ride", "cycle", "pedal", "row", "paddle", "roll", "skate",
                   "zip", "comb", "fold", "tear", "rip", "crumple", "shake"},
    "liquid":     {"pour", "splash", "drip", "spill", "fill", "rinse", "wash", "flush",
                   "sprinkle", "squirt", "spray", "boil", "bubble"},
    "oral":       {"drink", "sip", "eat", "chew", "bite", "swallow", "gulp", "slurp",
                   "lick", "taste", "munch"},
    "ambient":    {"bark", "meow", "chirp", "sing", "rain", "blow", "rustle", "burn",
                   "crackle", "hum", "buzz", "ring", "idle", "whistle", "howl",
                   "purr", "growl", "flutter", "flap", "wave", "breathe"},
}

# Objects that pull the motion measurement to a specific band of the frame, whatever
# the verb suggests. Region drives which pixels the visual localiser watches.
REGION_HINTS: dict[str, set[str]] = {
    "feet": {"ball", "football", "soccer", "foot", "feet", "shoe", "shoes", "boot",
             "boots", "floor", "ground", "pedal", "stair", "stairs", "step", "steps",
             "leg", "legs", "knee", "kick"},
    "head": {"mouth", "lip", "lips", "face", "head", "teeth", "tongue", "straw",
             "bottle", "glass", "mug", "cup", "can", "sandwich", "apple", "food"},
    "table": {"table", "desk", "counter", "worktop", "surface", "board", "plate",
              "tray", "shelf", "bench", "keyboard", "chopping"},
}

# Per-archetype acoustic guidance. The literal action phrase is quoted separately
# in the prompt, so these describe only HOW the sound behaves, not what it is.
ARCHETYPE_PROMPT: dict[str, str] = {
    "locomotion":
        "heard as a steady sequence of individual footsteps, each step a distinct heel "
        "strike followed by a softer toe contact, even natural walking pace, clean "
        "separation between steps",
    "impact":
        "heard as a single sharp impact, one clean percussive strike with a fast attack "
        "and a short natural decay, solid and believable, no repetition",
    "placement":
        "heard as one soft contact followed by a short natural "
        "settle and brief resonance, restrained and believable",
    "pickup":
        "heard as subtle contact and friction against the "
        "surface followed by a gentle lift, realistic hand handling",
    "mechanism":
        "heard as one crisp mechanical action with a short "
        "travel and a definite seat at the end, small domestic scale",
    "friction":
        "heard as sustained rhythmic friction, continuous contact between two "
        "surfaces with fine textural detail, even and unhurried",
    "liquid":
        "heard as a continuous liquid flow with fine splashing detail and "
        "natural gurgle, believable domestic scale",
    "oral":
        "heard as a quiet close-miked mouth sound, soft intimate swallow and subtle lip "
        "contact, restrained and natural, low level",
    "ambient":
        "heard as a continuous natural sound, steady and unforced with realistic texture",
}

_NEG_BASE = ("music, speech, talking, voice, singing, background ambience, room tone, "
             "environmental noise, crowd, traffic, cinematic sound design, electronic "
             "sounds, synthetic sounds, exaggerated impacts, reverb")

ARCHETYPE_NEGATIVE: dict[str, str] = {
    "locomotion": "running, sprinting, scuffing, dragging, uneven rhythm, single step",
    "impact":     "multiple impacts, repetition, echo, breaking, shattering, explosion",
    "placement":  "dropping, breaking, smashing, multiple impacts",
    "pickup":     "dropping, breaking, smashing, heavy impact",
    "mechanism":  "beeping, electronic beep, alarm, motor, repeated clicks",
    "friction":   "single impact, tapping, knocking, clinking, silence",
    "liquid":     "single splash, silence, bubbling boil, steam hiss",
    "oral":       "loud gulping, exaggerated slurping, burping, speech, chewing loudly",
    "ambient":    "sudden impacts, transients, speech, music",
}

_FILLERS = {"a", "an", "the", "his", "her", "their", "its", "of", "to", "on", "in",
            "at", "with", "from", "into", "onto", "is", "are", "and", "person",
            "man", "woman", "someone", "he", "she", "they", "it", "down", "up",
            "over", "around", "towards", "toward", "against", "some"}

_ALL_VERBS = set().union(*ARCHETYPE_VERBS.values())


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z]+", s.lower())


def _stem_candidates(w: str) -> list[str]:
    """Every plausible base form of a word, best guess first.

    A single strip rule cannot cover English -ing: "tapping" needs the doubled
    consonant removed, "writing" needs an "e" restored, "kicking" needs neither.
    Guessing one rule mis-stems the others ("opening" -> "ope"), so instead we
    generate all the candidates and let the verb lexicon decide which is real.
    """
    out = [w]
    for suffix in ("ing", "ed"):
        if w.endswith(suffix) and len(w) > len(suffix) + 2:
            base = w[: -len(suffix)]
            out += [base, base + "e"]
            if len(base) > 2 and base[-1] == base[-2]:
                out.append(base[:-1])          # tapp -> tap
    if w.endswith("es") and len(w) > 4:
        out += [w[:-2], w[:-1]]
    elif w.endswith("s") and len(w) > 3:
        out.append(w[:-1])
    return out


def _stem(w: str) -> str:
    """Single best-guess base form, for object filtering and region hints."""
    for cand in _stem_candidates(w):
        if cand in _ALL_VERBS:
            return cand
    c = _stem_candidates(w)
    return c[1] if len(c) > 1 else w


def classify(phrase: str) -> tuple[str, Optional[str], list[str]]:
    """Return (archetype, object_phrase, all_content_words) for an action phrase."""
    words = [w for w in _tokens(phrase) if w not in _FILLERS]

    # An unrecognised verb defaults to a gentle continuous texture rather than a
    # sharp transient: a wrongly-placed impact is far more jarring than a wrongly-
    # placed texture, and we are guessing by definition.
    archetype, verb_index = "ambient", None
    for i, w in enumerate(words):
        for cand in _stem_candidates(w):
            hit = next((a for a, vs in ARCHETYPE_VERBS.items() if cand in vs), None)
            if hit:
                archetype, verb_index = hit, i
                break
        if verb_index is not None:
            break

    obj_words = [w for i, w in enumerate(words)
                 if i != verb_index and _stem(w) not in _ALL_VERBS]
    obj = " ".join(obj_words[:3]) if obj_words else None
    return archetype, obj, words


def _region(archetype: str, words: list[str]) -> str:
    stems = {_stem(w) for w in words} | set(words)
    for region, hints in REGION_HINTS.items():
        if stems & hints:
            return region
    return ARCHETYPE_SYNC[archetype][1]


def synthesise(phrase: str):
    """Build a FoleySpec for an arbitrary action phrase. Never returns None."""
    from .prompt_map import FoleySpec          # local import avoids a cycle

    archetype, obj, words = classify(phrase)
    strategy, _default_region, selection, rms = ARCHETYPE_SYNC[archetype]
    region = _region(archetype, words)

    body = ARCHETYPE_PROMPT[archetype]
    action = re.sub(r"^(a|an|the|person|man|woman|someone)\s+", "",
                    phrase.strip().lower()).strip() or phrase.strip().lower()

    prompt = (f"close-up realistic Foley of {action}, {body}, dry close-miked "
              f"recording, isolated Foley, no speech, no music, no ambience")
    negative = f"{_NEG_BASE}, {ARCHETYPE_NEGATIVE[archetype]}"

    # Key by archetype + object rather than by the raw phrase, so "kick the ball" and
    # "kicking a football" share one generation instead of paying for two.
    slug = re.sub(r"[^a-z]+", "_", f"{archetype}_{obj or 'generic'}").strip("_")

    return FoleySpec(
        key=slug,
        label=phrase.strip().capitalize(),
        prompt=prompt,
        negative=negative,
        strategy=strategy,
        region=region,
        selection=selection,
        generic=True,
        target_rms_dbfs=rms,
        match=[],
    )
