"""Turn the tracking into two simple facts per frame, which are all the state machine reads.

    controller[t]   which team is controlling the ball on frame t: HOME, AWAY or NOBODY
    dead_cue[t]     True if frame t looks like a stoppage

Keeping the machine's inputs this small is deliberate. Each fact can be plotted, checked against
the video and improved on its own, without touching the possession logic.

Who controls the ball
---------------------
A team controls the ball on a frame when all of these hold:

1. The ball position is known (tracked, or filled across a gap of at most 0.5 s).
2. The nearest player is within 2 m of it.
3. The ball is moving slower than 7 m/s. Faster than that it is a pass or a shot in flight, and
   the player it happens to fly past is not controlling it.
4. It is not contested: if both teams have a player within 2 m and their distances differ by less
   than 0.5 m, nobody controls it.

Example, one frame, ball moving at 3 m/s:

    nearest Barcelona player 0.8 m, nearest Athletic player 4.1 m   -> HOME
    nearest Barcelona player 1.2 m, nearest Athletic player 1.4 m   -> NOBODY (contested)
    nearest Barcelona player 3.0 m, nearest Athletic player 5.0 m   -> NOBODY (nobody close)
    same as the first line, but the ball moves at 15 m/s            -> NOBODY (in flight)

NOBODY is the normal answer for much of the match: passes in flight, loose balls, and the 41% of
graded frames with no ball. The state machine treats NOBODY as "no new information", so the team
that had the ball keeps it.

What a stoppage looks like
--------------------------
A frame is a dead-ball cue when either:

- the ball is more than 1 m past a touchline or goal line, or
- the players have slowed down (average speed under 1.5 m/s over one second) **and** the ball is
  either missing or not moving.

The second rule is there because the ball is often not tracked during stoppages. Players walking
back for a free kick, or standing around for a throw-in, are visible even when the ball is not.
Neither rule alone decides anything: the state machine only accepts a stoppage once the cue has
held for a full second.
"""

from dataclasses import dataclass

import numpy as np

from .config import AWAY, FPS, HOME, NOBODY, PITCH, Params


@dataclass
class Observations:
    """Per-frame inputs to the state machine, plus the intermediate values behind them.

    Only `controller` and `dead_cue` are used by the machine. The rest are kept so you can plot
    them and see why a frame got the answer it did.
    """

    controller: np.ndarray       # int8, HOME / AWAY / NOBODY
    dead_cue: np.ndarray         # bool
    ball: np.ndarray             # (T, 2) metres, short gaps filled
    ball_speed: np.ndarray       # m/s, NaN where unknown
    nearest_home: np.ndarray     # metres to the nearest home player, NaN if none tracked
    nearest_away: np.ndarray     # metres to the nearest away player
    team_speed: np.ndarray       # average speed of tracked players, m/s, smoothed
    ball_out: np.ndarray         # bool


def fill_short_gaps(ball, max_gap):
    """Fill missing ball positions by a straight line, but only across gaps of `max_gap` frames or fewer.

    Example with max_gap=2, x values only:

        in   1.0  NaN  NaN  4.0  NaN  NaN  NaN  8.0
        out  1.0  2.0  3.0  4.0  NaN  NaN  NaN  8.0     <- the 3-frame gap is left alone

    Gaps at the very start or end have nothing on one side and are left alone too.
    """
    ball = np.array(ball, dtype=np.float64)
    n = len(ball)
    seen = ~np.isnan(ball[:, 0])
    index = np.arange(n)
    previous = np.maximum.accumulate(np.where(seen, index, -1))
    following = np.minimum.accumulate(np.where(seen, index, n)[::-1])[::-1]
    gap = following - previous - 1
    fill = ~seen & (previous >= 0) & (following < n) & (gap <= max_gap)
    if fill.any():
        before, after = previous[fill], following[fill]
        weight = ((index[fill] - before) / (after - before))[:, None]
        ball[fill] = ball[before] * (1 - weight) + ball[after] * weight
    return ball


def rolling_nanmean(values, window):
    """Centred moving average over `window` frames that skips NaN. NaN if the whole window is NaN.

    Example with window=3:

        in   1.0  NaN  3.0  5.0
        out  1.0  2.0  4.0  4.0
    """
    values = np.asarray(values, dtype=np.float64)
    known = ~np.isnan(values)
    sums = np.concatenate(([0.0], np.cumsum(np.where(known, values, 0.0))))
    counts = np.concatenate(([0], np.cumsum(known)))
    half = window // 2
    index = np.arange(len(values))
    low = np.clip(index - half, 0, len(values))
    high = np.clip(index + half + 1, 0, len(values))
    total, count = sums[high] - sums[low], counts[high] - counts[low]
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0, total / count, np.nan)


def ball_speed(ball, window, fps=FPS):
    """Ball speed in m/s from frame-to-frame movement, smoothed over `window` frames.

    Example: a ball that moves 0.4 m between two frames is moving at 0.4 x 25 = 10 m/s.
    """
    step = np.linalg.norm(np.diff(ball, axis=0), axis=1) * fps
    return rolling_nanmean(np.concatenate(([np.nan], step)), window)


def nearest_by_team(ball, players, team_of_slot):
    """(distance to nearest home player, distance to nearest away player) on every frame.

    NaN where the ball is missing or the team has nobody tracked.
    """
    distance = np.hypot(players[..., 0] - ball[:, None, 0], players[..., 1] - ball[:, None, 1])
    out = []
    for team in (HOME, AWAY):
        columns = distance[:, team_of_slot == team]
        if columns.shape[1] == 0:
            out.append(np.full(len(ball), np.nan))
        else:
            out.append(np.fmin.reduce(columns, axis=1))
    return out[0], out[1]


def controlling_team(nearest_home, nearest_away, speed, params):
    """HOME, AWAY or NOBODY on every frame, by the four rules in the module docstring.

    An unknown ball speed (NaN, e.g. a single isolated sighting) does not rule control out.
    """
    home = np.where(np.isnan(nearest_home), np.inf, nearest_home)
    away = np.where(np.isnan(nearest_away), np.inf, nearest_away)
    closest = np.minimum(home, away)
    team = np.where(home <= away, HOME, AWAY)

    close = closest <= params.control_radius
    slow = ~(speed > params.control_max_speed)
    both_close = (home <= params.control_radius) & (away <= params.control_radius)
    with np.errstate(invalid="ignore"):       # inf - inf where nobody is tracked
        contested = both_close & (np.abs(home - away) < params.contested_margin)
    return np.where(close & slow & ~contested, team, NOBODY).astype(np.int8)


def average_team_speed(speed, window):
    """Average speed of all tracked players on each frame, smoothed over `window` frames."""
    known = ~np.isnan(speed)
    count = known.sum(axis=1)
    total = np.where(known, speed, 0.0).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        per_frame = np.where(count > 0, total / count, np.nan)
    return rolling_nanmean(per_frame, window)


def ball_off_pitch(ball, margin, pitch=PITCH):
    """True where the ball is more than `margin` metres past a line. False where it is missing."""
    length, width = pitch
    x, y = ball[:, 0], ball[:, 1]
    with np.errstate(invalid="ignore"):
        return (x < -margin) | (x > length + margin) | (y < -margin) | (y > width + margin)


def build(tracking, params=Params()):
    """All observations for a `Tracking`. This is the function the pipeline calls."""
    ball = fill_short_gaps(tracking.ball, params.max_fill_gap)
    speed = ball_speed(ball, params.speed_window)
    nearest_home, nearest_away = nearest_by_team(ball, tracking.players, tracking.team_of_slot)
    controller = controlling_team(nearest_home, nearest_away, speed, params)

    team_speed = average_team_speed(tracking.speed, params.slow_window)
    out = ball_off_pitch(ball, params.out_margin)
    missing = np.isnan(ball[:, 0])
    still = speed < params.still_speed
    # No players tracked at all (NaN) counts as slow: nobody on the pitch means no play.
    slow_players = ~(team_speed >= params.slow_players_speed)
    dead_cue = out | (slow_players & (missing | still))

    return Observations(controller, dead_cue, ball, speed, nearest_home, nearest_away,
                        team_speed, out)
