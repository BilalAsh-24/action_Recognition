"""
Project action vocabulary for Foley-oriented action recognition.

Design principle (derived from our empirical X-CLIP tests):
  - BROAD, visually identifiable actions work better than precise mechanical
    descriptions. e.g. "locking a door" outperformed "turning a key in a door lock".
  - Every action here is chosen because it plausibly maps to a Foley sound.
  - UNKNOWN is NOT sent to the model; it is a decision-layer outcome used when
    the model is not confident enough (see temporal_action_recognition.py).
"""

# Grouped for reporting/readability; the model receives the flat list.
ACTION_CATEGORIES = {
    "door": [
        "opening a door",
        "closing a door",
        "locking a door",
        "unlocking a door",
        "knocking on a door",
    ],
    "hand_object": [
        "picking up an object",
        "putting down an object",
        "dropping an object",
        "opening an object",
        "closing an object",
        "turning a handle",
    ],
    "body": [
        "walking",
        "running",
        "jumping",
        "clapping",
        "sitting down",
        "standing up",
    ],
    "liquid": [
        "pouring liquid",
        "drinking",
        "filling a container",
    ],
    "tools": [
        "cutting",
        "hammering",
        "typing",
        "writing",
    ],
}

# Flat list actually passed to X-CLIP.
ACTION_LABELS = [label for group in ACTION_CATEGORIES.values() for label in group]

# Decision-layer sentinel (never sent to the model).
UNKNOWN_ACTION = "UNKNOWN"

# Reverse lookup: action -> category (useful later for Foley sound mapping).
ACTION_TO_CATEGORY = {
    label: category
    for category, labels in ACTION_CATEGORIES.items()
    for label in labels
}


def num_labels() -> int:
    return len(ACTION_LABELS)


def uniform_chance() -> float:
    """Softmax probability of a label under pure chance.

    With N labels this is 1/N. Confidence thresholds are expressed as
    MULTIPLES of this value so they stay meaningful if the vocabulary grows.
    """
    return 1.0 / len(ACTION_LABELS)


if __name__ == "__main__":
    print(f"{num_labels()} labels across {len(ACTION_CATEGORIES)} categories")
    for cat, labels in ACTION_CATEGORIES.items():
        print(f"  {cat:12s} ({len(labels)}): {', '.join(labels)}")
    print(f"uniform chance = {uniform_chance():.4f}")
