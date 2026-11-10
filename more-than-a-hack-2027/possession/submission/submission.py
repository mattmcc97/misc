"""Write the submission file, check it, and count the possessions it claims.

README.md in this folder describes the file format and what the summary numbers mean.

    labels = full_match([(11185, first_half), (110808, second_half)])
    write("output/state_machine.csv", labels)
"""

import os

import numpy as np

from ..config import FPS, GRADED_HALVES, N_FRAMES

VALID_LABELS = {"H", "A", "D", "X"}


def full_match(halves, n_frames=N_FRAMES):
    """Place per-half label arrays into one full-length array, with X everywhere else.

    `halves` is [(first_frame, labels)], e.g. [(11185, labels_1st), (110808, labels_2nd)].
    """
    labels = np.full(n_frames, "X", dtype="<U1")
    for first, half_labels in halves:
        labels[first:first + len(half_labels)] = half_labels
    return labels


def check(labels, n_frames=N_FRAMES):
    """Raise ValueError if `labels` would be rejected. Returns nothing if it is fine."""
    if len(labels) != n_frames:
        raise ValueError("{} labels, need exactly {}".format(len(labels), n_frames))
    bad = sorted(set(np.unique(labels)) - VALID_LABELS)
    if bad:
        raise ValueError("invalid labels {}; allowed are H, A, D, X".format(bad))


def write(path, labels):
    """Check `labels`, then write them as a frame,label CSV. Returns the path."""
    check(labels)
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", newline="\n") as handle:
        handle.write("frame,label\n")
        handle.writelines("{},{}\n".format(frame, label) for frame, label in enumerate(labels))
    return path


def runs(labels):
    """[(label, first frame, last frame)] for every maximal run of one label.

    Example:  runs(["H", "H", "D", "A"]) -> [("H", 0, 1), ("D", 2, 2), ("A", 3, 3)]
    """
    labels = np.asarray(labels)
    if len(labels) == 0:
        return []
    starts = np.concatenate(([0], np.flatnonzero(labels[1:] != labels[:-1]) + 1))
    ends = np.concatenate((starts[1:] - 1, [len(labels) - 1]))
    return [(str(labels[s]), int(s), int(e)) for s, e in zip(starts, ends)]


def summarise(labels, halves=GRADED_HALVES, fps=FPS):
    """Frame counts and possession statistics over the graded halves.

    Returns a dict with these keys:
        frames              {"H": n, "A": n, "D": n, "X": n}, graded frames only
        possessions         number of maximal H or A runs, counted within each half
        mean_possession_s   their mean length in seconds
        stoppages           number of maximal D runs
    """
    graded = np.concatenate([labels[first:last + 1] for _, first, last in halves])
    possessions = []
    stoppages = 0
    for _, first, last in halves:
        for label, start, end in runs(labels[first:last + 1]):
            if label in ("H", "A"):
                possessions.append(end - start + 1)
            elif label == "D":
                stoppages += 1
    return {
        "frames": {label: int(np.sum(graded == label)) for label in ("H", "A", "D", "X")},
        "possessions": len(possessions),
        "mean_possession_s": round(float(np.mean(possessions)) / fps, 1) if possessions else 0.0,
        "stoppages": stoppages,
    }
