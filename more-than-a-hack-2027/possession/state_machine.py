"""The possession state machine: per-frame observations in, one H / A / D label per frame out.

It reads the match one frame at a time, the way you would watch it, and keeps track of what state
play is in. It only changes its mind when the evidence has held for long enough, and when it does,
it goes back and relabels from the moment the change actually started. That second part,
backdating, is what stops every hand-over landing late.

The five states
---------------
    state        label written   meaning
    -----------  --------------  ----------------------------------------------------------------
    DEAD         D               the ball is out of play
    RESTARTING   D for now       dead-ball cues have stopped; waiting to be sure play is live
    POSSESSION   the team        one team has the ball
    CHALLENGED   the team        the other team has touched it; waiting to see if they keep it
    STOPPING     the team        dead-ball cues have started; waiting to be sure play has stopped

RESTARTING, CHALLENGED and STOPPING are "maybe" states. While in one, the machine keeps writing
the old label. If the change is confirmed, it overwrites everything from the frame the maybe-state
began. If not, the old labels were right all along and nothing is overwritten.

Transitions
-----------
    DEAD        -> RESTARTING   no dead-ball cue on this frame
    RESTARTING  -> DEAD         a dead-ball cue comes back before the restart is confirmed
    RESTARTING  -> POSSESSION   10 clear frames, and some team has controlled the ball
                                (backdated: possession starts where RESTARTING started)
    POSSESSION  -> CHALLENGED   the other team controls the ball
    POSSESSION  -> STOPPING     a dead-ball cue
    CHALLENGED  -> POSSESSION   the challenger controls it for 10 frames in total: a turnover
                                (backdated: the new team's possession starts at its first touch)
    CHALLENGED  -> POSSESSION   the original team touches it again: no turnover, nothing changes
    CHALLENGED  -> POSSESSION   the challenger has not touched it for 3 s: no turnover
    CHALLENGED  -> STOPPING     a dead-ball cue
    STOPPING    -> DEAD         dead-ball cues for 25 frames (backdated: dead from the first cue)
    STOPPING    -> POSSESSION   the cues stop before that: play carried on

The frame counts are defaults from `config.Params`.

How this follows the possession rules (CHALLENGE.md)
----------------------------------------------------
- **A pass between teammates** changes nothing. While the ball travels, nobody controls it, and
  when a teammate receives it, it is the same team. The machine never leaves POSSESSION.
- **A loose or contested ball** stays with the last team, because NOBODY is never evidence for a
  change.
- **A touch or deflection without control** is a short CHALLENGED that never reaches 10 frames.
  It ends when the original team gets the ball back, or after 3 s, and leaves no trace.
- **A dead ball** has no owner: DEAD always writes D.

Worked example
--------------
One letter per frame. h = home controls, a = away controls, . = nobody. The machine starts in
home possession, and confirm_turnover=3 to keep it short:

    frame      0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5
    observed   h h . . a . h h . . a a . a h h
    state      P P P P C C P P P P C C C P C C      P = POSSESSION, C = CHALLENGED
    written    H H H H H H H H H H A A A A A A
                                   ^     ^
                                   |     frame 13: the third away frame confirms the turnover
                                   frame 10: labels are rewritten as A from here

The first 'a' was a deflection: home got the ball straight back, so nothing was rewritten. The
second challenge reached three away frames, so the possession switches, starting from the frame
away first touched it. The 'h' after that is now a challenge by home against away.

Usage
-----
    machine = PossessionMachine(Params())
    labels = machine.run(controller, dead_cue)        # numpy array of "H", "A", "D"
    for change in machine.changes:                    # every confirmed transition, for debugging
        print(change)

Run it once per half. A new machine starts in DEAD, which is right for both halves: each opens
with a kickoff.
"""

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from .config import NOBODY, TEAM_LABEL, Params, other


class State(Enum):
    DEAD = "dead"
    RESTARTING = "restarting"
    POSSESSION = "possession"
    CHALLENGED = "challenged"
    STOPPING = "stopping"


@dataclass
class Change:
    """One confirmed change of label, for the possession log.

    `frame` is where the machine became sure. `start` is where the new label was written from,
    after backdating. `start` is never later than `frame`.
    """

    frame: int
    start: int
    label: str
    reason: str


@dataclass
class PossessionMachine:
    """Feed it frames with `step`, or a whole half with `run`. See the module docstring."""

    params: Params = field(default_factory=Params)

    def __post_init__(self):
        self.reset()

    def reset(self):
        """Back to the start-of-half state: ball dead, nobody in possession."""
        self.state = State.DEAD
        self.team = NOBODY          # team in possession; also the last team while dead
        self.since = 0              # first frame of the current maybe-state
        self.count = 0              # supporting frames seen in the current maybe-state
        self.quiet = 0              # CHALLENGED: frames since the challenger last touched it
        self.restart_team = NOBODY  # RESTARTING: first team seen controlling the ball
        self.labels = []
        self.changes = []
        self.offset = 0

    # -- the public interface ------------------------------------------------------------------

    def run(self, controller, dead_cue, offset=0):
        """Label a whole half. Returns a numpy array of "H" / "A" / "D", one per input frame.

        `offset` is added to the frame numbers recorded in `changes`, so a half that starts at
        video frame 11185 can report video frames rather than positions within the half.
        """
        self.reset()
        self.offset = offset
        for team, dead in zip(controller, dead_cue):
            self.step(int(team), bool(dead))
        return np.array(self.labels, dtype="<U1")

    def step(self, controller, dead_cue):
        """Process the next frame: update the state, then write this frame's label."""
        frame = len(self.labels)
        handler = {
            State.DEAD: self._dead,
            State.RESTARTING: self._restarting,
            State.POSSESSION: self._possession,
            State.CHALLENGED: self._challenged,
            State.STOPPING: self._stopping,
        }[self.state]
        handler(frame, controller, dead_cue)
        self.labels.append(self._label())

    # -- one handler per state -----------------------------------------------------------------

    def _dead(self, frame, controller, dead_cue):
        if not dead_cue:
            self._enter(State.RESTARTING, frame)
            self.restart_team = controller
            self._restarting_check(frame)

    def _restarting(self, frame, controller, dead_cue):
        if dead_cue:
            self.state = State.DEAD
            return
        self.count += 1
        if self.restart_team == NOBODY:
            self.restart_team = controller
        self._restarting_check(frame)

    def _restarting_check(self, frame):
        """Confirm the restart once play has been clear for long enough and a team has the ball."""
        if self.count >= self.params.confirm_live and self.restart_team != NOBODY:
            self.team = self.restart_team
            self._commit(State.POSSESSION, frame, self.since, TEAM_LABEL[self.team], "restart")

    def _possession(self, frame, controller, dead_cue):
        if dead_cue:
            self._enter(State.STOPPING, frame)
        elif controller == other(self.team):
            self._enter(State.CHALLENGED, frame)
            self.quiet = 0
            self._challenged_check(frame)

    def _challenged(self, frame, controller, dead_cue):
        challenger = other(self.team)
        if dead_cue:
            self._enter(State.STOPPING, frame)
        elif controller == challenger:
            self.count += 1
            self.quiet = 0
            self._challenged_check(frame)
        elif controller == self.team:
            self.state = State.POSSESSION        # a touch without control: nothing changes
        else:
            self.quiet += 1
            if self.quiet > self.params.challenge_timeout:
                self.state = State.POSSESSION    # the challenger never followed up

    def _challenged_check(self, frame):
        """Confirm a turnover once the challenger has controlled the ball for long enough."""
        if self.count >= self.params.confirm_turnover:
            self.team = other(self.team)
            self._commit(State.POSSESSION, frame, self.since, TEAM_LABEL[self.team], "turnover")

    def _stopping(self, frame, controller, dead_cue):
        if not dead_cue:
            self.state = State.POSSESSION        # play carried on
            if controller == other(self.team):
                self._enter(State.CHALLENGED, frame)
                self.quiet = 0
                self._challenged_check(frame)
            return
        self.count += 1
        if self.count >= self.params.enter_dead:
            self._commit(State.DEAD, frame, self.since, "D", "stoppage")

    # -- helpers -------------------------------------------------------------------------------

    def _enter(self, state, frame):
        """Start a maybe-state at this frame. The current frame counts as its first piece of evidence."""
        self.state = state
        self.since = frame
        self.count = 1

    def _commit(self, state, frame, start, label, reason):
        """Confirm a change: switch state and rewrite every label from `start` up to this frame."""
        self.state = state
        for index in range(start, frame):
            self.labels[index] = label
        self.changes.append(Change(frame + self.offset, start + self.offset, label, reason))

    def _label(self):
        """The label for the current frame, given the state after this frame's update."""
        if self.state in (State.DEAD, State.RESTARTING):
            return "D"
        return TEAM_LABEL[self.team]
