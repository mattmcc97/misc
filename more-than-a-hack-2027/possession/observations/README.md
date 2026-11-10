# observations

Reduces each frame of tracking to two facts, which are all the state machine reads:

| array | values | meaning |
|---|---|---|
| `controller[t]` | `HOME`, `AWAY` or `NOBODY` | which team is controlling the ball on frame *t* |
| `dead_cue[t]` | `True` / `False` | does frame *t* look like a stoppage |

Keeping the machine's inputs this small is deliberate. Each fact can be plotted, checked against
the video and improved on its own, without touching the possession logic.

```python
from possession import observations

obs = observations.build(tracking_data, params)
obs.controller       # int8 per frame
obs.dead_cue         # bool per frame
```

`build` also returns the values behind those two facts (filled ball track, ball speed, distance to
the nearest player of each team, average player speed, ball off the pitch), so you can plot them
and see why a frame got the answer it did.

---

## Who controls the ball

A team controls the ball on a frame when all four hold:

1. **The ball position is known**: tracked, or filled across a gap of 0.5 s or less.
2. **The nearest player is within 2 m** of it.
3. **The ball is moving slower than 7 m/s.** Faster than that it is a pass or a shot in flight, and
   the player it happens to fly past is not controlling it.
4. **It is not contested.** If both teams have a player within 2 m and their distances differ by
   less than 0.5 m, nobody controls it.

Examples, one frame each, ball moving at 3 m/s unless stated:

| nearest Barcelona | nearest Athletic | controller | why |
|---|---|---|---|
| 0.8 m | 4.1 m | `HOME` | |
| 1.2 m | 1.4 m | `NOBODY` | contested |
| 3.0 m | 5.0 m | `NOBODY` | nobody close |
| 0.8 m, ball at 15 m/s | 4.1 m | `NOBODY` | a pass in flight |
| no one tracked | 1.0 m | `AWAY` | |
| 0.5 m, ball speed unknown | 3.0 m | `HOME` | an unknown speed does not rule control out |

`NOBODY` is the normal answer for much of the match: passes in flight, loose balls, and the 41% of
graded frames with no ball. The state machine treats `NOBODY` as "no new information", so the team
that had the ball keeps it.

## What a stoppage looks like

A frame is a dead-ball cue when either:

- **the ball is more than 1 m past a touchline or goal line**, or
- **the players have slowed down** (average speed under 1.5 m/s over one second) **and the ball is
  either missing or not moving** (under 0.5 m/s).

The second rule is there because the ball is often not tracked during stoppages. Players walking
back for a free kick, or standing around for a throw-in, are visible even when the ball is not.

| ball | players | cue? |
|---|---|---|
| 2 m past the touchline | running | yes: out of play |
| missing | walking, 0.5 m/s on average | yes |
| still, on the penalty spot | walking | yes |
| missing | running, 4 m/s on average | no: probably in the air |
| rolling at 5 m/s | walking | no |

A cue alone decides nothing. The state machine only accepts a stoppage once cues have held for a
full second.

---

## Functions

Each takes and returns plain arrays, so each can be tested and plotted alone.

| function | does |
|---|---|
| `build(tracking, params)` | everything below, in order. This is what the pipeline calls |
| `fill_short_gaps(ball, max_gap)` | straight-line fill across short ball gaps |
| `ball_speed(ball, window)` | ball speed in m/s, smoothed |
| `nearest_by_team(ball, players, team_of_slot)` | distance from the ball to the nearest home and nearest away player |
| `controlling_team(home, away, speed, params)` | the four control rules above |
| `average_team_speed(speed, window)` | average speed of all tracked players, smoothed |
| `ball_off_pitch(ball, margin)` | the ball is past a line |
| `rolling_nanmean(values, window)` | centred moving average that skips missing values |

### Filling gaps

Only gaps of `max_gap` frames or fewer are filled. Gaps at the very start or end have nothing on
one side and are left alone. With `max_gap=2`, x values only:

```
in   1.0  NaN  NaN  4.0  NaN  NaN  NaN  8.0
out  1.0  2.0  3.0  4.0  NaN  NaN  NaN  8.0     <- the 3-frame gap is left alone
```

### Ball speed

Frame-to-frame movement times the frame rate. A ball that moves 0.4 m between two frames is moving
at 0.4 x 25 = 10 m/s. The result is averaged over `speed_window` frames to remove jitter.

### Moving average

Centred, and missing values are skipped rather than counted as zero. With a window of 3:

```
in   1.0  NaN  3.0  5.0
out  1.0  2.0  4.0  4.0
```
