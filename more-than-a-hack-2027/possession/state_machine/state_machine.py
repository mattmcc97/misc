"""The possession state machine: per-frame observations in, one H / A / D label per frame out.

Five states (DEAD, RESTARTING, POSSESSION, CHALLENGED, STOPPING). A change is only accepted once the
evidence has held for long enough, and is then backdated to the frame it began. README.md in this
folder has the transition table and a worked example.

    machine = PossessionMachine(Params())
    labels = machine.run(controller, dead_cue)        # numpy array of "H", "A", "D"
"""

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from ..config import NOBODY, TEAM_LABEL, Params, other


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
    """Feed it frames with `step`, or a whole half with `run`. See README.md in this folder."""

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
