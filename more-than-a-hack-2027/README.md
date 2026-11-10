# Ball possession: state machine

Our entry for [More Than A Hack 2027](https://github.com/metrica-sports/more-than-a-hack-2027),
Phase 1: for every frame of FC Barcelona vs Athletic Club, say which team has the ball (`H` / `A`)
or that the ball is dead (`D`).

This first version reads the tracking data one frame at a time and runs a five-state machine over
it. It only changes its answer once the evidence has held for long enough, and then goes back and
relabels from the frame the change began. No model, no training, numpy only.

```bash
pip install -r requirements.txt
python run.py --data-dir /path/to/data --log output/changes.csv
```

`--data-dir` is the folder that holds `tactical/` from the organisers' download. It defaults to
`$MTAH_DATA_DIR`, then `./data`. The submission is written to `output/state_machine.csv`.

---

## How it works

Four steps, one folder each. Every folder has its own README with the detail and examples.

```
tracking/           observations/                    state_machine/            submission/
---------           -------------                    --------------            -----------
ATD files    --->   per frame:                --->   per half:          --->   X outside the
in metres           controller  H / A / nobody       H / A / D labels          halves, checked
one row per         dead_cue    True / False         + a log of every          CSV, possession
video frame                                          change of label           count
```

| step | folder | in one line |
|---|---|---|
| 1 | [`possession/tracking/`](possession/tracking/) | read the tracking files into arrays, in metres, one row per video frame |
| 2 | [`possession/observations/`](possession/observations/) | for each frame: which team controls the ball, and does it look like a stoppage |
| 3 | [`possession/state_machine/`](possession/state_machine/) | turn those two facts into one label per frame, backdating every confirmed change |
| 4 | [`possession/submission/`](possession/submission/) | write the CSV, check it, count the possessions it claims |
| | [`possession/config/`](possession/config/) | every threshold, with what it means on the pitch |
| | [`tests/`](tests/) | what is tested, and how to run it |

`run.py` chains the four steps together.

### The idea in one example

One letter per frame: `h` home controls the ball, `a` away controls it, `.` nobody does (a pass in
flight, a loose ball, or no ball tracked). A turnover here needs 3 frames of control:

```
observed   h h . . a . h h . . a a . a h h
written    H H H H H H H H H H A A A A A A
```

The first `a` is a deflection: home gets it straight back, so nothing changes. The second time,
away keeps it for three frames, so the machine switches to `A`, and writes `A` from away's first
touch rather than from the frame it became sure. The
[state machine README](possession/state_machine/) walks through this frame by frame.

---

## Checking the output

```bash
python run.py --log output/changes.csv
```

`output/changes.csv` has one row per change of label. These example rows come from a test run on
invented data:

```
confirmed_frame,start_frame,label,reason
11194,11185,H,restart
11508,11499,A,turnover
```

`start_frame` is where the new label begins after backdating, and `confirmed_frame` is where the
machine became sure. Open the video at `start_frame` (frame / 25 = seconds) to see whether the
change is real.

`run.py` also prints how many possessions the file claims. That is the first number to look at:
the public 5 minutes have 17, about 3.4 a minute, so a full match should be in the hundreds.

Then run the organisers' tools, from a clone of their repository:

```bash
python evaluation/validate_submission.py /path/to/output/state_machine.csv
python evaluation/run_evaluation.py         # scores files in evaluation/results/ on the public 5 minutes
```

The public score is a pipeline check, not a ranking. Seventeen possessions cannot tell two
versions apart.

## Known gaps

- **Dead-ball timing is approximate.** Player speed is averaged over one second, so a stoppage or
  restart can be placed a few frames off. A restart is really the frame the ball is struck, and
  that could be found from the ball's speed.
- **Long ball gaps carry the last team.** If a turnover happens while the ball is untracked, it is
  only picked up when the new team is seen on the ball.
- **Smart Tagging is not used yet.** Its set pieces mark restarts, and its team tags are a second
  opinion on who has the ball.
- **Thresholds are fixed.** Whether 2 m and 10 frames are right needs checking against the video.

## Data and rules

The match data is not in this repository and must never be. `.gitignore` excludes `data/`,
`cache/` (the parsed tracking) and `output/` (submissions and logs). No labels in this pipeline
come from a person: every one is produced by the code from the tracking data. Every threshold was
set from football reasoning, not by tuning on the public 5 minutes, which the rules forbid.
