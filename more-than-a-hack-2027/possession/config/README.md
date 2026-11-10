# config

Every number the pipeline depends on, in one place, so no other module hides a threshold.

Two kinds of number live here:

- **Facts about the match**, published by the organisers. These never change.
- **Parameters**, which are our choices: how close a player must be to "have" the ball, how long a
  team must hold it before we call it a turnover, and so on. They are collected in one `Params`
  object, so a run is described by that object alone.

```python
from possession.config import Params

params = Params()                              # the defaults
stricter = Params(confirm_turnover=20)         # a turnover now needs 0.8 s of control
```

`config.py` is the source of truth. If this page and that file ever disagree, the file is right.

---

## Facts about the match

| name | value | meaning |
|---|---|---|
| `FPS` | 25 | frames per second. 25 frames is one second |
| `PITCH` | (105.3, 68.0) | length and width in metres. The tracking is in 0-1 units; multiply by these |
| `N_FRAMES` | 199,319 | frames in the tactical video, and rows in a submission |
| `GRADED_HALVES` | (1, 11185, 90651), (2, 110808, 190197) | the only frames that are scored, inclusive |

The second half is graded from 110,808 but does not kick off until 113,742, so it opens with about
two minutes of dead ball. The first half is graded from the kickoff itself.

## Team codes

Every module uses the same integer codes for a team:

| code | value | meaning |
|---|---|---|
| `HOME` | 0 | Barcelona |
| `AWAY` | 1 | Athletic Club |
| `NOBODY` | -1 | no team controls the ball on this frame |

`other(HOME)` is `AWAY` and the other way round. `TEAM_LABEL` maps a code to its submission letter.

---

## Parameters

Distances are metres, speeds m/s, durations frames (25 = 1 s).

### Cleaning the ball track

| parameter | default | meaning |
|---|---|---|
| `max_fill_gap` | 12 (0.5 s) | fill a missing ball by straight-line interpolation only across gaps this short. Longer gaps are left missing: the ball may have been in the air, or out of play |
| `speed_window` | 5 | ball speed is averaged over this many frames to remove tracking jitter |

### Who controls the ball

| parameter | default | meaning |
|---|---|---|
| `control_radius` | 2.0 m | a player within this distance of the ball can be controlling it |
| `control_max_speed` | 7.0 m/s | above this the ball is travelling (a pass, a shot, a clearance), not being controlled. A sprinting dribble is about 7 m/s; a firm pass is 10-20 m/s |
| `contested_margin` | 0.5 m | if both teams have a player within `control_radius` and their distances differ by less than this, nobody controls the ball |

### Dead-ball cues

| parameter | default | meaning |
|---|---|---|
| `out_margin` | 1.0 m | the ball counts as off the pitch once it is this far past a line. The margin absorbs tracking noise on balls running along the touchline |
| `still_speed` | 0.5 m/s | below this the ball is not moving: placed for a free kick, held for a throw-in |
| `slow_players_speed` | 1.5 m/s | if the average speed of all tracked players is below this, play has stopped. In open play someone is always running |
| `slow_window` | 25 (1 s) | average player speed is smoothed over this many frames |

### State machine timings

| parameter | default | meaning |
|---|---|---|
| `confirm_turnover` | 10 (0.4 s) | frames of control the other team needs before we accept a turnover. Shorter and every deflection becomes a possession; longer and quick interceptions are missed. The public ground truth has a possession of 0.76 s, so this cannot be large |
| `challenge_timeout` | 75 (3 s) | if the challenger stops touching the ball for this long, the challenge is dropped and the ball stays with the team that had it |
| `enter_dead` | 25 (1 s) | frames of dead-ball cues needed before we accept a stoppage |
| `confirm_live` | 10 (0.4 s) | frames free of dead-ball cues needed before we accept that play has restarted |

---

## How the parameters were chosen

From football, not from the ground truth. The rules forbid tuning on the public 5 minutes, and the
organisers' EVALUATION.md shows that doing so picks the wrong value even on a one-parameter
baseline.

Looking at the data to sanity-check a value is fine. For example, plot a histogram of average
player speed over the whole match and check that 1.5 m/s sits between the stoppage peak and the
open-play peak. Searching for the value that scores best on the public window is not.
