"""Action -> Foley prompt mapping, plus the sync strategy each action needs.

Module 2 returns free-text action phrases ("walk around table", "drink from cup").
This layer resolves an arbitrary phrase to a canonical Foley class, then supplies
the MOSS prompt and the visual-localisation strategy for that class.

Adding a new supported action means adding one entry here — no other file changes.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import re
from typing import Optional


def _tokens(s: str) -> list[str]:
    return re.findall(r"[a-z]+", s.lower())


@dataclass
class FoleySpec:
    key: str
    label: str
    prompt: str
    negative: str = ""
    # how the audible instant is found in the video
    strategy: str = "contact"        # footstep | hold | contact | continuous | none
    region: str = "table"            # feet | head | table | full
    # how the generated 10 s asset is cut down
    selection: str = "event"         # steps | wet_segment | event | slice
    generic: bool = False            # fallback class: only used when nothing specific matches
    target_rms_dbfs: float = -34.0
    match: list[str] = field(default_factory=list)


_NEG_COMMON = ("music, speech, talking, voice, singing, background ambience, room tone, "
               "environmental noise, crowd, traffic, cinematic sound design, electronic sounds, "
               "synthetic sounds, exaggerated impacts, reverb")

ACTION_PROMPT_MAP: dict[str, FoleySpec] = {
    "walking": FoleySpec(
        key="walking", label="Walking",
        prompt=("close-up realistic Foley recording of natural human footsteps walking on a hard "
                "wooden floor, clearly audible alternating left and right footsteps with realistic "
                "heel and toe impacts, natural walking rhythm and slight variation between steps, "
                "subtle shoe contact and floor resonance, isolated dry Foley recording, no speech, "
                "no music, no ambience, no room tone, no cinematic sound design"),
        negative=_NEG_COMMON,
        strategy="footstep", region="feet", selection="steps", target_rms_dbfs=-34.0,
        match=["walk", "walking", "footstep", "footsteps", "stroll", "pace", "step"]),

    "running": FoleySpec(
        key="running", label="Running",
        prompt=("close-up realistic Foley recording of a person running on a hard floor, rapid "
                "alternating footfalls with firm heel and toe impacts, natural running cadence, "
                "shoe contact and floor resonance, isolated dry Foley recording, no speech, no "
                "music, no ambience"),
        negative=_NEG_COMMON,
        strategy="footstep", region="feet", selection="steps", target_rms_dbfs=-32.0,
        match=["run", "running", "jog", "jogging", "sprint"]),

    "drinking": FoleySpec(
        key="drinking", label="Drinking",
        prompt=("close-up realistic Foley of a person taking several natural sips of water from a "
                "ceramic mug, distinct sipping sounds followed by natural swallowing, subtle "
                "cup-to-lips contact and realistic ceramic handling, continuous recognizable "
                "drinking action, isolated Foley recording, no speech, no music, no ambience"),
        negative="",     # validated configuration: negations carried inline
        strategy="hold", region="head", selection="wet_segment", target_rms_dbfs=-38.0,
        match=["drink", "drinking", "sip", "sipping", "swallow", "swallowing"]),

    "cup_placement": FoleySpec(
        key="cup_placement", label="Cup placement",
        prompt=("close-up realistic Foley recording of a person naturally placing a ceramic mug "
                "down on a solid wooden table, one clear ceramic-on-wood contact followed by a "
                "short natural wooden table resonance and gentle ceramic settling, realistic hand "
                "release and subtle mug movement, clean isolated object Foley, physically "
                "believable contact and decay, no exaggerated impact"),
        negative=("music, speech, voice, singing, footsteps, walking, drinking, sipping, "
                  "swallowing, pouring water, background ambience, room tone, environmental noise, "
                  "multiple impacts, dropping the mug, breaking ceramic, smashing, heavy impact, "
                  "metallic sound, electronic sound, synthetic sound, cinematic sound design, "
                  "long reverb"),
        strategy="contact", region="table", selection="event", target_rms_dbfs=-32.0,
        # NOTE: no bare "place"/"put" keyword. A bare verb matched "place spoon on
        # table" to this class and produced ceramic-mug Foley for a metal spoon.
        # Every keyword names the object.
        match=["place cup", "place mug", "put cup", "put mug", "set cup", "set mug",
               "sets the cup", "puts the cup", "put down cup", "set down mug",
               "place the cup", "place the mug"]),

    "cup_pickup": FoleySpec(
        key="cup_pickup", label="Cup pickup",
        prompt=("close-up realistic Foley recording of a hand picking up a ceramic mug from a "
                "wooden table, subtle ceramic contact and friction against the wooden surface "
                "followed by a gentle lift, realistic hand grip and ceramic handling, short "
                "natural object interaction, isolated dry Foley recording, no speech, no music, "
                "no ambience"),
        negative=("music, speech, background ambience, room tone, dropping the mug, breaking "
                  "ceramic, smashing, multiple cups, heavy impact"),
        strategy="contact", region="table", selection="event", target_rms_dbfs=-32.0,
        # NOTE: no bare "pick"/"lift". They matched any object, not just a mug.
        match=["pick up cup", "pick up mug", "pick up the cup", "pick up the mug",
               "lift cup", "lift mug", "grab cup", "grab mug", "take cup", "take mug",
               "picking up the cup", "picking up the mug"]),

    "stirring": FoleySpec(
        key="stirring", label="Stirring",
        prompt=("close-up realistic Foley of a metal teaspoon stirring liquid inside a ceramic "
                "mug, repeated gentle spoon-against-ceramic contacts in a steady circular "
                "rhythm, soft liquid swirling between the taps, dry indoor recording, isolated "
                "Foley, no speech, no music, no ambience"),
        negative=_NEG_COMMON,
        strategy="continuous", region="table", selection="slice", target_rms_dbfs=-34.0,
        match=["stir", "stirring", "stir coffee", "stir tea", "stir the contents",
               "mixing", "mix the", "whisk", "whisking"]),

    "spoon_placement": FoleySpec(
        key="spoon_placement", label="Spoon placement",
        prompt=("close-up realistic Foley of a small metal teaspoon being set down on a wooden "
                "table, one light metallic contact followed by a very short settle, quiet and "
                "restrained, dry indoor recording, isolated Foley, no speech, no music, "
                "no ambience"),
        negative=(_NEG_COMMON + ", ceramic, heavy impact, dropping, clattering, multiple objects"),
        strategy="contact", region="table", selection="event", target_rms_dbfs=-34.0,
        match=["place spoon", "put spoon", "set spoon", "place the spoon", "put the spoon",
               "spoon on table", "spoon down", "drop spoon"]),

    "spoon_pickup": FoleySpec(
        key="spoon_pickup", label="Spoon pickup",
        prompt=("close-up realistic Foley of a small metal teaspoon being picked up from a "
                "wooden table, a light metallic scrape and lift, quiet and restrained, dry "
                "indoor recording, isolated Foley, no speech, no music, no ambience"),
        negative=(_NEG_COMMON + ", ceramic, heavy impact, dropping, clattering"),
        strategy="contact", region="table", selection="event", target_rms_dbfs=-34.0,
        match=["pick up spoon", "pick up the spoon", "take spoon", "lift spoon",
               "grab spoon", "picking up the spoon"]),

    "object_placement": FoleySpec(
        generic=True,
        key="object_placement", label="Object placement",
        prompt=("close-up realistic Foley of a small object being set down gently on a wooden "
                "table, one soft contact followed by a short natural settle and brief wooden "
                "resonance, restrained and believable, dry indoor recording, isolated Foley, "
                "no speech, no music, no ambience"),
        negative=(_NEG_COMMON + ", dropping, breaking, smashing, multiple impacts"),
        strategy="contact", region="table", selection="event", target_rms_dbfs=-33.0,
        match=["place on table", "put on table", "set on table", "put down", "set down",
               "place down", "puts down", "sets down", "place object", "put object"]),

    "object_pickup": FoleySpec(
        generic=True,
        key="object_pickup", label="Object pickup",
        prompt=("close-up realistic Foley of a small object being picked up from a wooden "
                "table, subtle contact and friction against the surface followed by a gentle "
                "lift, realistic hand handling, dry indoor recording, isolated Foley, no "
                "speech, no music, no ambience"),
        negative=(_NEG_COMMON + ", dropping, breaking, smashing, heavy impact"),
        strategy="contact", region="table", selection="event", target_rms_dbfs=-33.0,
        match=["pick up object", "pick up the object", "picks up", "picking up",
               "lift object", "lifts the", "take from table"]),

    "door_opening": FoleySpec(
        key="door_opening", label="Door opening",
        prompt=("close-up realistic Foley of a wooden door being opened, latch release followed by "
                "hinge movement and a soft swing, isolated dry Foley recording, no speech, no "
                "music, no ambience"),
        negative=_NEG_COMMON,
        strategy="contact", region="full", selection="event", target_rms_dbfs=-32.0,
        match=["open door", "opening door", "door open", "opens the door"]),

    "door_closing": FoleySpec(
        key="door_closing", label="Door closing",
        prompt=("close-up realistic Foley of a wooden door closing, hinge movement followed by a "
                "firm latch click and short wooden resonance, isolated dry Foley recording, no "
                "speech, no music, no ambience"),
        negative=_NEG_COMMON,
        strategy="contact", region="full", selection="event", target_rms_dbfs=-32.0,
        match=["close door", "closing door", "door close", "shuts the door", "shut door"]),

    "sitting": FoleySpec(
        key="sitting", label="Sitting down",
        prompt=("close-up realistic Foley of a person sitting down on a wooden chair, clothing "
                "rustle followed by a soft weight settling and slight chair creak, isolated dry "
                "Foley recording, no speech, no music, no ambience"),
        negative=_NEG_COMMON,
        strategy="contact", region="full", selection="event", target_rms_dbfs=-36.0,
        match=["sit", "sitting", "sits down", "sit down"]),

    "clapping": FoleySpec(
        key="clapping", label="Clapping",
        prompt=("close-up realistic Foley of a person clapping their hands, sharp natural hand "
                "claps with slight variation between them, dry indoor recording, isolated Foley, "
                "no speech, no music, no ambience"),
        negative=_NEG_COMMON,
        strategy="footstep", region="full", selection="steps", target_rms_dbfs=-30.0,
        match=["clap", "clapping", "applaud", "applause"]),

    "typing": FoleySpec(
        key="typing", label="Typing",
        prompt=("close-up realistic Foley of fingers typing on a mechanical keyboard, crisp "
                "rhythmic key presses with natural variation, dry indoor recording, isolated "
                "Foley, no speech, no music, no ambience"),
        negative=_NEG_COMMON,
        strategy="continuous", region="full", selection="slice", target_rms_dbfs=-34.0,
        match=["typ", "typing", "keyboard", "type on"]),

    "pouring": FoleySpec(
        key="pouring", label="Pouring liquid",
        prompt=("close-up realistic Foley of water being poured into a ceramic mug, natural liquid "
                "flow and rising pitch as the vessel fills, isolated dry Foley recording, no "
                "speech, no music, no ambience"),
        negative=_NEG_COMMON,
        strategy="continuous", region="table", selection="slice", target_rms_dbfs=-34.0,
        match=["pour", "pouring", "fill", "filling"]),
}

# Actions that legitimately produce no Foley. Not failures.
SILENT_ACTIONS: dict[str, str] = {
    "standing": "Standing still produces no Foley event.",
    "stand": "Standing still produces no Foley event.",
    "looking": "No physical contact event.",
    "waiting": "No physical contact event.",
    "idle": "No physical contact event.",
    "move hand": "Hand movement alone produces no audible Foley.",
    "moving hand": "Hand movement alone produces no audible Foley.",
    "reach": "Reaching toward an object produces no audible contact.",
    "reaching": "Reaching toward an object produces no audible contact.",
    "hold": "Holding an object still produces no Foley event.",
    "holding": "Holding an object still produces no Foley event.",
    "unknown": "Action not recognised confidently enough to select a Foley class.",
}


def resolve(action_phrase: str) -> tuple[Optional[FoleySpec], Optional[str]]:
    """Resolve a free-text action phrase to a FoleySpec.

    Returns (spec, None) when a Foley class matches, or (None, reason) when the
    action is deliberately silent or unsupported.
    """
    p = (action_phrase or "").strip().lower()
    if not p:
        return None, "Empty action label."

    # Token-based matching: a keyword matches when all of its words appear in the
    # phrase, so "opening the door" still matches the keyword "open door". Filler
    # words are stripped first. Longest keyword wins, so "place cup" beats "place".
    fillers = {"a", "an", "the", "his", "her", "their", "its", "of", "to", "on", "in",
               "at", "with", "from", "into", "onto", "is", "are", "and", "person",
               "man", "woman", "someone"}
    words = [w for w in _tokens(p) if w not in fillers]
    stem = lambda w: w[:-4] if w.endswith("ping") or w.endswith("ting") else (
        w[:-3] if w.endswith("ing") and len(w) > 5 else w.rstrip("s"))
    stems = {stem(w) for w in words} | set(words)

    def _match(pool):
        best, best_len = None, 0
        for spec in pool:
            for kw in spec.match:
                kw_words = [w for w in _tokens(kw) if w not in fillers]
                if not kw_words:
                    continue
                hit = all(any(kwd == w or stem(kwd) == stem(w) or w.startswith(kwd)
                              for w in stems) for kwd in kw_words)
                if hit and len(kw) > best_len:
                    best, best_len = spec, len(kw)
        return best

    # Specificity beats keyword length: a class that names the object ("place cup")
    # must win over the generic fallback ("place on table"), even though the generic
    # keyword is the longer string.
    specific = [s for s in ACTION_PROMPT_MAP.values() if not s.generic]
    generic = [s for s in ACTION_PROMPT_MAP.values() if s.generic]
    best = _match(specific) or _match(generic)
    if best:
        return best, None

    for kw, reason in SILENT_ACTIONS.items():
        if kw in p:
            return None, reason

    return None, (f"No Foley class is defined for '{action_phrase}'. "
                  f"This interval will remain silent.")


def supported_actions() -> list[dict]:
    return [{"key": s.key, "label": s.label, "strategy": s.strategy,
             "generic": s.generic, "keywords": s.match} for s in ACTION_PROMPT_MAP.values()]
