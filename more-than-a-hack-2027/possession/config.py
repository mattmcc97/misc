"""Every number the pipeline depends on, in one place.

Two kinds of number live here:

- **Facts about the match**, published by the organisers: frame count, frame rate, pitch size and
  the two graded halves. These never change.
- **Parameters**, which are our choices: how close a player must be to "have" the ball, how long a
  team must hold it before we call it a turnover, and so on. They are collected in `Params` so a
  run can be described by one object, and so nothing else in the code hides a threshold.

How the parameters were chosen
------------------------------
From football, not from the ground truth. Each one has a comment saying what it means in match
terms. The rules forbid tuning on the public 5 minutes, and EVALUATION.md shows that doing so picks
the wrong value even on a one-parameter baseline. Look at the data to sanity-check a value (for
example, a histogram of team speed over the whole match); do not search for the value that scores
best on the public window.

Example
-------
    from possession.config import Params
    params = Params()                              # the defaults
    stricter = Params(confirm_turnover=20)         # a turnover now needs 0.8 s of control
"""

from dataclasses import dataclass

# -- facts about the match (DATA.md) -------------------------------------------------------------

FPS = 25
"""Frames per second of the tactical video. 25 frames is one second."""

PITCH = (105.3, 68.0)
"""Pitch length and width in metres. The tracking is in 0-1 units; multiply by these."""

N_FRAMES = 199319
"""Frames in the tactical video, and rows in a submission."""

GRADED_HALVES = ((1, 11185, 90651), (2, 110808, 190197))
"""(half, first video frame, last video frame), inclusive. Everything else is never scored.

The second half is graded from 110808 but does not kick off until 113742 (FAQ.md), so it opens
with about two minutes of dead ball. The first half is graded from the kickoff itself.
"""

# -- team codes, shared by every module ----------------------------------------------------------

HOME, AWAY, NOBODY = 0, 1, -1
"""Integer codes for a team. NOBODY means no team: nobody controls the ball on this frame."""

TEAM_LABEL = {HOME: "H", AWAY: "A"}


def other(team):
    """The opposing team. other(HOME) is AWAY."""
    return AWAY if team == HOME else HOME


@dataclass(frozen=True)
class Params:
    """Tunable parameters. Distances are metres, speeds m/s, durations frames (25 = 1 s)."""

    # -- cleaning the ball track -----------------------------------------------------------------
    max_fill_gap: int = 12
    """Fill a missing ball by straight-line interpolation only if the gap is this short (0.5 s).
    Longer gaps are left missing: the ball may have been in the air, or out of play."""

    speed_window: int = 5
    """Ball speed is averaged over this many frames to remove tracking jitter."""

    # -- who controls the ball -------------------------------------------------------------------
    control_radius: float = 2.0
    """A player within this distance of the ball can be controlling it."""

    control_max_speed: float = 7.0
    """Above this ball speed the ball is travelling (a pass, a shot, a clearance), not being
    controlled. A sprinting dribble is about 7 m/s; a firm pass is 10-20 m/s."""

    contested_margin: float = 0.5
    """If players from both teams are within control_radius and their distances differ by less
    than this, the ball is contested and nobody controls it."""

    # -- dead-ball cues --------------------------------------------------------------------------
    out_margin: float = 1.0
    """The ball counts as off the pitch once it is this far past a line. The margin absorbs
    tracking noise on balls that run along the touchline."""

    still_speed: float = 0.5
    """Below this the ball is not moving: placed for a free kick, held for a throw-in."""

    slow_players_speed: float = 1.5
    """If the average speed of all tracked players is below this, play has stopped. In open play
    the average is higher because someone is always running."""

    slow_window: int = 25
    """Average player speed is smoothed over this many frames (1 s)."""

    # -- state machine timings -------------------------------------------------------------------
    confirm_turnover: int = 10
    """Frames of control the other team needs before we accept a turnover (0.4 s). Shorter and
    every deflection becomes a possession; longer and quick interceptions are missed. The public
    ground truth contains a possession of 0.76 s, so this cannot be large."""

    challenge_timeout: int = 75
    """If the challenger stops touching the ball for this long (3 s), the challenge is dropped
    and the ball stays with the team that had it."""

    enter_dead: int = 25
    """Frames of dead-ball cues needed before we accept a stoppage (1 s)."""

    confirm_live: int = 10
    """Frames free of dead-ball cues needed before we accept that play has restarted (0.4 s)."""
