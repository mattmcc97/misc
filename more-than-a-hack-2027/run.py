"""Build a submission from the tracking data with the possession state machine.

    python run.py --data-dir /path/to/data --out output/state_machine.csv

`--data-dir` is the folder that contains `tactical/`. It defaults to $MTAH_DATA_DIR, then ./data.

What it does, in order:

1. Reads the tactical tracking (cached after the first run, see possession/tracking.py).
2. Works out, for every frame, which team controls the ball and whether it looks like a stoppage
   (possession/observations.py).
3. Runs the state machine over each graded half separately (possession/state_machine.py).
4. Writes X outside the two halves, checks the file and writes it (possession/submission.py).
5. Prints a summary: label counts and how many possessions the file claims.

With `--log changes.csv` it also writes every confirmed change of label, with the frame where the
machine became sure and the frame it backdated to. That is the file to open next to the video when
a possession looks wrong.

Then check the file with the organisers' tools:

    python evaluation/validate_submission.py output/state_machine.csv
    python evaluation/run_evaluation.py
"""

import argparse
import os
import time

import numpy as np

from possession import observations, submission, tracking
from possession.config import GRADED_HALVES, Params
from possession.state_machine import PossessionMachine

HERE = os.path.dirname(os.path.abspath(__file__))


def label_match(obs, params):
    """Run the machine over each graded half. Returns (full-length labels, list of Change)."""
    halves, changes = [], []
    for _, first, last in GRADED_HALVES:
        machine = PossessionMachine(params)
        labels = machine.run(obs.controller[first:last + 1], obs.dead_cue[first:last + 1],
                             offset=first)
        halves.append((first, labels))
        changes.extend(machine.changes)
    return submission.full_match(halves), changes


def write_log(path, changes):
    """The possession log: one row per confirmed change of label."""
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", newline="\n") as handle:
        handle.write("confirmed_frame,start_frame,label,reason\n")
        for change in changes:
            handle.write("{},{},{},{}\n".format(change.frame, change.start, change.label,
                                                change.reason))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default=os.environ.get("MTAH_DATA_DIR")
                        or os.path.join(HERE, "data"))
    parser.add_argument("--out", default=os.path.join(HERE, "output", "state_machine.csv"))
    parser.add_argument("--log", help="also write the possession log to this CSV")
    parser.add_argument("--cache-dir", default=os.path.join(HERE, "cache"))
    args = parser.parse_args()
    params = Params()

    started = time.time()
    print("reading tracking from {}".format(args.data_dir))
    data = tracking.load(args.data_dir, args.cache_dir)
    print("  H = {}, A = {}   ({:.0f} s)".format(data.team_names[0], data.team_names[1],
                                                time.time() - started))

    obs = observations.build(data, params)
    graded = np.concatenate([np.arange(first, last + 1) for _, first, last in GRADED_HALVES])
    print("graded frames: ball known on {:.1f}%, a team in control on {:.1f}%, "
          "dead-ball cue on {:.1f}%".format(
              100 * np.mean(~np.isnan(obs.ball[graded, 0])),
              100 * np.mean(obs.controller[graded] >= 0),
              100 * np.mean(obs.dead_cue[graded])))

    labels, changes = label_match(obs, params)
    path = submission.write(args.out, labels)
    summary = submission.summarise(labels)
    frames = summary["frames"]
    print("wrote {}".format(path))
    print("  graded frames  H {H}  A {A}  D {D}  X {X}".format(**frames))
    print("  possessions {}  (mean {} s)   stoppages {}".format(
        summary["possessions"], summary["mean_possession_s"], summary["stoppages"]))

    if args.log:
        write_log(args.log, changes)
        print("wrote {} ({} changes)".format(args.log, len(changes)))


if __name__ == "__main__":
    main()
