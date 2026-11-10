"""The state machine on short, hand-written frame sequences.

Each test writes one frame per character:

    h   home controls the ball
    a   away controls the ball
    .   nobody controls it (in flight, loose, or not tracked)
    x   dead-ball cue

and checks the labels the machine writes. Timings are shrunk (see SMALL) so that a whole scenario
fits on one line. These sequences are invented to exercise the rules; none comes from the match.
"""

import unittest

import numpy as np

from possession.config import AWAY, HOME, NOBODY, Params
from possession.state_machine import PossessionMachine, State

SMALL = Params(confirm_turnover=3, challenge_timeout=4, enter_dead=3, confirm_live=2)


def frames(text):
    """'hh.ax' -> (controller array, dead_cue array). Spaces are ignored, for readability."""
    text = text.replace(" ", "")
    team = {"h": HOME, "a": AWAY, ".": NOBODY, "x": NOBODY}
    controller = np.array([team[c] for c in text], dtype=np.int8)
    dead = np.array([c == "x" for c in text])
    return controller, dead


def label(text, params=SMALL):
    """Run the machine over `text` and return the labels as one string, e.g. 'DDHHH'."""
    machine = PossessionMachine(params)
    return "".join(machine.run(*frames(text)))


class Case(unittest.TestCase):
    def check(self, observed, expected):
        """Compare labels. Both strings may contain spaces to line frames up; they are ignored."""
        observed_clean, expected_clean = observed.replace(" ", ""), expected.replace(" ", "")
        self.assertEqual(len(observed_clean), len(expected_clean), "test strings differ in length")
        self.assertEqual(label(observed_clean), expected_clean)


class RestartTest(Case):
    def test_kickoff_backdates_to_first_clear_frame(self):
        # Two dead frames, then play. The restart is confirmed on the second clear frame and
        # backdated to the first, so possession starts right where the cues stop.
        self.check("xx hh hhh",
                   "DD HH HHH")

    def test_restart_waits_for_a_team(self):
        # Clear of cues but nobody on the ball yet: stays D until away touches it, then all the
        # clear frames become A.
        self.check("x ... a a",
                   "D AAA A A")

    def test_false_restart_returns_to_dead(self):
        # One clear frame is not enough (confirm_live=2); the cue comes back.
        self.check("x h x x",
                   "D D D D")


class PossessionTest(Case):
    def test_pass_between_teammates_keeps_possession(self):
        # Ball in flight (.) between two home players: one possession throughout.
        self.check("hh h.... h h",
                   "HH HHHHH H H")

    def test_turnover_is_backdated_to_first_touch(self):
        # Away controls three frames: turnover. A starts at away's first touch, not on the
        # frame the machine became sure.
        self.check("hh hh aaa a",
                   "HH HH AAA A")

    def test_deflection_is_not_a_turnover(self):
        # Away touches it twice, then home has it again. Below confirm_turnover: no change.
        self.check("hh h aa h h",
                   "HH H HH H H")

    def test_touches_do_not_need_to_be_consecutive(self):
        # Away control interrupted by a loose ball still adds up: a, ., a, a is three touches.
        self.check("hh h a.aa h",
                   "HH H AAAA A")

    def test_challenge_times_out(self):
        # Away touches once, then the ball is loose for longer than challenge_timeout. The
        # challenge lapses, so a later single away touch starts a fresh count.
        self.check("hh h a..... a.. h",
                   "HH H HHHHHH HHH H")

    def test_contested_ball_stays_with_last_team(self):
        self.check("hh ........",
                   "HH HHHHHHHH")


class StoppageTest(Case):
    def test_stoppage_is_backdated_to_first_cue(self):
        # Three cues (enter_dead=3) confirm a stoppage; D starts at the first cue.
        self.check("hh h xxx x",
                   "HH H DDD D")

    def test_short_cue_is_ignored(self):
        # Two cues, then play continues: still one home possession.
        self.check("hh h xx h h",
                   "HH H HH H H")

    def test_turnover_after_restart(self):
        # Home possession, stoppage, away restarts: H, D, A.
        self.check("hh h xxx aa a",
                   "HH H DDD AA A")

    def test_same_team_either_side_of_stoppage_is_two_possessions(self):
        self.check("hh h xxx hh h",
                   "HH H DDD HH H")


class WorkedExampleTest(unittest.TestCase):
    def test_worked_example(self):
        # The worked example in possession/state_machine/README.md, starting from home possession.
        machine = PossessionMachine(SMALL)
        machine.state, machine.team = State.POSSESSION, HOME
        controller, dead = frames("hh..a.hh..aa.ahh")
        for team, cue in zip(controller, dead):
            machine.step(int(team), bool(cue))
        self.assertEqual("".join(machine.labels), "HHHHHHHHHHAAAAAA")
        self.assertEqual(machine.state, State.CHALLENGED)


class ChangeLogTest(unittest.TestCase):
    def test_changes_record_confirmation_and_start(self):
        machine = PossessionMachine(SMALL)
        machine.run(*frames("xx hh aaa"), offset=1000)
        reasons = [(c.reason, c.start, c.frame, c.label) for c in machine.changes]
        # Restart confirmed at frame 3, backdated to 2. Turnover confirmed at 6, backdated to 4.
        self.assertEqual(reasons, [("restart", 1002, 1003, "H"), ("turnover", 1004, 1006, "A")])


if __name__ == "__main__":
    unittest.main()
