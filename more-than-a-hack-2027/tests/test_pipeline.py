"""Reading tracking files, writing submissions, and the whole pipeline on an invented match.

The files written here are tiny fakes in the ATD format, built in a temporary folder. They are not
match data.
"""

import os
import tempfile
import unittest

import numpy as np

from possession import observations, submission, tracking
from possession.config import N_FRAMES, PITCH, Params
from possession.state_machine import PossessionMachine

META = """<?xml version="1.0"?>
<Main><Metadata>
  <Teams>
    <Team id="T1"><Name>Home FC</Name></Team>
    <Team id="T2"><Name>Away FC</Name></Team>
  </Teams>
  <Players>
    <Player id="P1" teamId="T1"/>
    <Player id="P2" teamId="T2"/>
  </Players>
</Metadata></Main>
"""


def fake_line(frame_id, home, away, ball, speed=3.0):
    """One ATD line for two slots. Positions are in metres and converted to 0-1 units here."""
    def group(xy, s):
        if xy is None:
            return "NaN,NaN,NaN"
        return "{:.5f},{:.5f},{:.2f}".format(xy[0] / PITCH[0], xy[1] / PITCH[1], s)
    ball_text = "NaN,NaN,NaN" if ball is None else "{:.5f},{:.5f},0".format(
        ball[0] / PITCH[0], ball[1] / PITCH[1])
    return "{}:{};{}:{}\n".format(frame_id, group(home, speed), group(away, speed), ball_text)


def write_fake_data(folder, lines):
    os.makedirs(os.path.join(folder, "tactical"))
    with open(os.path.join(folder, "tactical", tracking.STEM + "_atd.xml"), "w") as handle:
        handle.write(META)
    with open(os.path.join(folder, "tactical", tracking.STEM + "_atd.txt"), "w") as handle:
        handle.writelines(lines)


class TrackingTest(unittest.TestCase):
    def test_parse_line_docstring_example(self):
        frame, slots, x, y = tracking.parse_line("2:0.1,0.2,3.0;NaN,NaN,NaN:0.5,0.5,0", 2)
        self.assertEqual(frame, 1)
        np.testing.assert_allclose(slots[0], [0.1, 0.2, 3.0])
        self.assertTrue(np.isnan(slots[1]).all())
        self.assertEqual((x, y), (0.5, 0.5))

    def test_load_aligns_frames_and_scales_to_metres(self):
        with tempfile.TemporaryDirectory() as folder:
            write_fake_data(folder, [fake_line(1, (10, 20), None, (52.65, 34.0)),
                                     fake_line(3, (11, 20), (30, 30), None)])
            data = tracking.load(folder, cache_dir=os.path.join(folder, "cache"), n_frames=4)
            self.assertEqual(data.team_names, ("Home FC", "Away FC"))
            np.testing.assert_array_equal(data.team_of_slot, [0, 1])
            np.testing.assert_allclose(data.ball[0], [52.65, 34.0], atol=1e-3)  # frame_id 1 -> row 0
            self.assertTrue(np.isnan(data.ball[1]).all())                       # frame_id 2 absent
            np.testing.assert_allclose(data.players[2, 1], [30, 30], atol=1e-3)
            # Second load comes from the cache and gives the same arrays.
            again = tracking.load(folder, cache_dir=os.path.join(folder, "cache"), n_frames=4)
            np.testing.assert_array_equal(again.players, data.players)

    def test_missing_data_names_the_files(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError) as caught:
                tracking.load(folder)
            self.assertIn("BAR-ATH_tactical_atd.txt", str(caught.exception))


class SubmissionTest(unittest.TestCase):
    def test_runs_docstring_example(self):
        self.assertEqual(submission.runs(["H", "H", "D", "A"]),
                         [("H", 0, 1), ("D", 2, 2), ("A", 3, 3)])

    def test_write_and_check(self):
        labels = submission.full_match([(11185, np.array(["H", "A"]))])
        self.assertEqual(len(labels), N_FRAMES)
        self.assertEqual(labels[11184], "X")
        with tempfile.TemporaryDirectory() as folder:
            path = submission.write(os.path.join(folder, "out.csv"), labels)
            with open(path) as handle:
                lines = handle.read().splitlines()
        self.assertEqual(lines[0], "frame,label")
        self.assertEqual(len(lines), N_FRAMES + 1)
        self.assertEqual(lines[11186], "11185,H")

    def test_check_rejects_bad_files(self):
        with self.assertRaises(ValueError):
            submission.check(np.array(["H"] * 10))
        bad = np.full(N_FRAMES, "X")
        bad[5] = "Q"
        with self.assertRaises(ValueError):
            submission.check(bad)

    def test_summary_counts_possessions_within_halves(self):
        labels = np.full(20, "X")
        labels[0:10] = list("HHHDDAAAHH")
        summary = submission.summarise(labels, halves=((1, 0, 9),), fps=1)
        self.assertEqual(summary["possessions"], 3)
        self.assertEqual(summary["stoppages"], 1)


class InventedMatchTest(unittest.TestCase):
    """A 9-second invented passage of play, end to end through observations and the machine.

    0-2 s   dead: ball still at the centre spot, everyone walking
    2-4 s   home player dribbles the ball
    4-5 s   a long home pass, ball in flight at 15 m/s, passing the away player
    5-7 s   away player picks it up and dribbles away: a turnover
    7-9 s   ball goes out over the touchline: dead
    """

    def test_labels(self):
        fps, n = 25, 225
        ball = np.zeros((n, 2))
        home = np.zeros((n, 2))
        away = np.zeros((n, 2))
        speed = np.zeros((n, 2))

        t = np.arange(n)
        for frame in t:
            if frame < 50:                       # dead ball at the centre spot
                ball[frame] = (52, 34)
                home[frame] = (51, 34)
                away[frame] = (60, 34)
                speed[frame] = 0.3
            elif frame < 100:                    # home dribbles at 4 m/s
                x = 52 + (frame - 50) * 4 / fps
                ball[frame] = (x, 34)
                home[frame] = (x - 0.5, 34)
                away[frame] = (80, 40)
                speed[frame] = 4.0
            elif frame < 125:                    # pass at 15 m/s, flies past the away player
                x = 60 + (frame - 100) * 15 / fps
                ball[frame] = (x, 34)
                home[frame] = (60, 34)
                away[frame] = (70, 34.5)
                speed[frame] = 4.0
            elif frame < 175:                    # away has it and dribbles at 3 m/s
                y = 34 + (frame - 125) * 3 / fps
                ball[frame] = (75, y)
                away[frame] = (75, y - 0.5)
                home[frame] = (60, 34)
                speed[frame] = 4.0
            else:                                # out of play over the touchline, players stop
                ball[frame] = (75, 70)
                away[frame] = (75, 66)
                home[frame] = (60, 34)
                speed[frame] = 0.5

        data = tracking.Tracking(ball, np.stack([home, away], axis=1), speed,
                                 np.array([0, 1]), ("Home FC", "Away FC"))
        obs = observations.build(data, Params())
        labels = "".join(PossessionMachine(Params()).run(obs.controller, obs.dead_cue))

        compressed = "".join(label for i, label in enumerate(labels)
                             if i == 0 or label != labels[i - 1])
        self.assertEqual(compressed, "DHAD")
        # The turnover lands within a few frames of the away player's first touch (frame 125).
        self.assertLess(abs(labels.index("A") - 125), 5)


if __name__ == "__main__":
    unittest.main()
