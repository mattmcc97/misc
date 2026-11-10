"""The per-frame observations, on tiny invented arrays."""

import unittest

import numpy as np

from possession import observations
from possession.config import AWAY, HOME, NOBODY, Params
from possession.tracking import Tracking

nan = np.nan


class FillGapsTest(unittest.TestCase):
    def test_docstring_example(self):
        x = np.array([1, nan, nan, 4, nan, nan, nan, 8], dtype=float)
        ball = np.stack([x, x], axis=1)
        filled = observations.fill_short_gaps(ball, max_gap=2)[:, 0]
        np.testing.assert_allclose(filled, [1, 2, 3, 4, nan, nan, nan, 8])

    def test_edges_are_not_filled(self):
        x = np.array([nan, 1, nan], dtype=float)
        filled = observations.fill_short_gaps(np.stack([x, x], axis=1), max_gap=5)[:, 0]
        np.testing.assert_allclose(filled, [nan, 1, nan])


class RollingMeanTest(unittest.TestCase):
    def test_docstring_example(self):
        out = observations.rolling_nanmean(np.array([1, nan, 3, 5], dtype=float), 3)
        np.testing.assert_allclose(out, [1, 2, 4, 4])


class BallSpeedTest(unittest.TestCase):
    def test_constant_speed(self):
        # 0.4 m per frame at 25 fps is 10 m/s.
        x = np.arange(10) * 0.4
        ball = np.stack([x, np.zeros(10)], axis=1)
        speed = observations.ball_speed(ball, window=1)
        np.testing.assert_allclose(speed[1:], 10.0)
        self.assertTrue(np.isnan(speed[0]))


class ControllerTest(unittest.TestCase):
    params = Params()

    def control(self, home, away, speed):
        return int(observations.controlling_team(
            np.array([home]), np.array([away]), np.array([speed]), self.params)[0])

    def test_docstring_examples(self):
        self.assertEqual(self.control(0.8, 4.1, 3.0), HOME)
        self.assertEqual(self.control(1.2, 1.4, 3.0), NOBODY)   # contested
        self.assertEqual(self.control(3.0, 5.0, 3.0), NOBODY)   # nobody close
        self.assertEqual(self.control(0.8, 4.1, 15.0), NOBODY)  # in flight

    def test_away_and_missing_values(self):
        self.assertEqual(self.control(nan, 1.0, 2.0), AWAY)     # no home player tracked
        self.assertEqual(self.control(nan, nan, 2.0), NOBODY)   # nobody tracked
        self.assertEqual(self.control(0.5, 3.0, nan), HOME)     # unknown speed is allowed


class DeadCueTest(unittest.TestCase):
    def tracking(self, ball, player_speed):
        """Two players per team standing near the ball, all moving at `player_speed`."""
        n = len(ball)
        players = np.zeros((n, 4, 2))
        players[:] = [[50, 34], [60, 34], [40, 34], [70, 34]]
        speed = np.full((n, 4), player_speed)
        return Tracking(np.array(ball, dtype=float), players, speed,
                        np.array([HOME, HOME, AWAY, AWAY]), ("Home", "Away"))

    def test_ball_off_pitch_is_a_cue(self):
        obs = observations.build(self.tracking([[110.0, 34.0]] * 30, player_speed=4.0))
        self.assertTrue(obs.dead_cue.all())

    def test_slow_players_and_missing_ball_is_a_cue(self):
        obs = observations.build(self.tracking([[nan, nan]] * 30, player_speed=0.5))
        self.assertTrue(obs.dead_cue.all())

    def test_fast_players_and_missing_ball_is_not_a_cue(self):
        # Ball not tracked but players running: open play, probably the ball is in the air.
        obs = observations.build(self.tracking([[nan, nan]] * 30, player_speed=4.0))
        self.assertFalse(obs.dead_cue.any())


if __name__ == "__main__":
    unittest.main()
