"""Read the tactical tracking data (ATD) into numpy arrays, in metres, indexed by video frame.

This is the only module that knows the file format. Everything after it works on the `Tracking`
arrays below, so a change in the export means a change here and nowhere else.

What you get
------------
    tracking = load("data")
    tracking.ball            # (199319, 2)      ball x, y in metres, NaN where not tracked
    tracking.players         # (199319, 46, 2)  every track slot's x, y in metres, NaN if absent
    tracking.speed           # (199319, 46)     every slot's speed in m/s, NaN if absent
    tracking.team_of_slot    # (46,)            HOME (0) or AWAY (1) for each slot
    tracking.team_names      # ("FC Barcelona", "Athletic Club"), for printing

Row i is video frame i, so row i is also submission row i. The file counts frames from 1, so the
loader puts the record for frame_id 1 in row 0. That is the whole alignment for the tactical
recording (DATA.md, "Frame alignment").

The file format
---------------
Two files, both under <data>/tactical/:

    BAR-ATH_tactical_atd.xml    metadata: the two teams, and which team each track slot is on
    BAR-ATH_tactical_atd.txt    one line per frame

A line of the text file looks like this (shortened to two slots):

    11186:0.4921,0.5003,1.25;NaN,NaN,NaN:0.5012,0.4998,0.00

    11186                      frame_id, counting from 1
    0.4921,0.5003,1.25         slot 1: x, y (0-1 units) and speed (m/s)
    NaN,NaN,NaN                slot 2: not tracked on this frame
    0.5012,0.4998,0.00         the ball. Only the first two values, x and y, are used

Slots are not players. There are 46 slots for 22 players, and a slot can follow one person, then
lose them, then pick up someone else. The only thing a slot reliably tells you is its team.

Caching
-------
Parsing the text file takes a minute or two. The parsed arrays are saved to `cache_dir` the first
time and reused after that. The cache is derived match data, so it must never be committed; the
project's .gitignore excludes it.
"""

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import numpy as np

from .config import AWAY, HOME, N_FRAMES, PITCH

STEM = "BAR-ATH_tactical"


@dataclass
class Tracking:
    """Tracking arrays for the whole video. See the module docstring for shapes."""

    ball: np.ndarray
    players: np.ndarray
    speed: np.ndarray
    team_of_slot: np.ndarray
    team_names: tuple


def atd_paths(data_dir):
    """(metadata XML, raw text) paths for the tactical recording, or an error naming what is missing."""
    folder = os.path.join(data_dir, "tactical")
    meta = os.path.join(folder, STEM + "_atd.xml")
    raw = os.path.join(folder, STEM + "_atd.txt")
    missing = [path for path in (meta, raw) if not os.path.isfile(path)]
    if missing:
        raise FileNotFoundError(
            "tracking data not found:\n  {}\n\nThe match data is gated (see the organisers' "
            "DATA.md). Unpack it so that {} contains the tactical/ folder, or pass --data-dir."
            .format("\n  ".join(missing), data_dir))
    return meta, raw


def read_teams(meta_path):
    """(team of each slot, (home name, away name)) from the metadata XML.

    The first <Team> in the file is the home side. That is the FIFA/EPTS convention, and the
    organisers' baseline relies on it too. Slots are listed as <Player> entries in the same order
    as they appear on each line of the text file.

    Example: for a file listing Barcelona first, a slot whose teamId is Barcelona's gets HOME.
    """
    root = ET.parse(meta_path).getroot()
    teams = list(root.iter("Team"))
    if len(teams) != 2:
        raise ValueError("{}: expected 2 teams, found {}".format(meta_path, len(teams)))
    home_id = teams[0].get("id")
    slots = [player.get("teamId") for player in root.iter("Player")]
    if not slots:
        raise ValueError("{}: no Player entries".format(meta_path))
    team_of_slot = np.array([HOME if team_id == home_id else AWAY for team_id in slots],
                            dtype=np.int8)
    names = tuple(team.findtext("Name") for team in teams)
    return team_of_slot, names


def parse_line(line, n_slots):
    """One text-file line -> (video frame, slots array (n_slots, k), ball x, ball y), 0-1 units.

    Example:
        parse_line("2:0.1,0.2,3.0;NaN,NaN,NaN:0.5,0.5,0", 2)
        -> (1, [[0.1, 0.2, 3.0], [nan, nan, nan]], 0.5, 0.5)
    """
    frame_part, player_part, ball_part = line.strip().split(":")
    values = np.array(player_part.replace(";", ",").split(","), dtype=np.float64)
    slots = values.reshape(n_slots, -1)
    ball_values = ball_part.split(",")
    return int(frame_part) - 1, slots, float(ball_values[0]), float(ball_values[1])


def parse_raw(raw_path, n_slots, n_frames=N_FRAMES, pitch=PITCH):
    """Stream the text file into a Tracking-shaped tuple (ball, players, speed), in metres.

    Frames missing from the file stay NaN. Lines that do not have three ':'-separated parts are
    skipped rather than guessed at.
    """
    length, width = pitch
    ball = np.full((n_frames, 2), np.nan, dtype=np.float32)
    players = np.full((n_frames, n_slots, 2), np.nan, dtype=np.float32)
    speed = np.full((n_frames, n_slots), np.nan, dtype=np.float32)

    with open(raw_path) as handle:
        for line in handle:
            if line.count(":") != 2:
                continue
            frame, slots, ball_x, ball_y = parse_line(line, n_slots)
            if not 0 <= frame < n_frames:
                continue
            players[frame, :, 0] = slots[:, 0] * length
            players[frame, :, 1] = slots[:, 1] * width
            if slots.shape[1] >= 3:
                speed[frame] = slots[:, 2]
            ball[frame] = (ball_x * length, ball_y * width)
    return ball, players, speed


def load(data_dir, cache_dir=None, n_frames=N_FRAMES, pitch=PITCH):
    """The tactical tracking as a `Tracking`. Uses the cache in `cache_dir` when it is current.

    The cache is current when it was written from a raw file of the same size and modification
    time. Replace the data bundle and the cache is rebuilt on the next run.
    """
    meta_path, raw_path = atd_paths(data_dir)
    team_of_slot, names = read_teams(meta_path)

    stat = os.stat(raw_path)
    stamp = np.array([stat.st_size, int(stat.st_mtime)], dtype=np.int64)
    cache_path = os.path.join(cache_dir, STEM + "_atd.npz") if cache_dir else None

    if cache_path and os.path.isfile(cache_path):
        cached = np.load(cache_path)
        if np.array_equal(cached["stamp"], stamp) and cached["ball"].shape[0] == n_frames:
            return Tracking(cached["ball"], cached["players"], cached["speed"],
                            team_of_slot, names)

    ball, players, speed = parse_raw(raw_path, len(team_of_slot), n_frames, pitch)
    if cache_path:
        os.makedirs(cache_dir, exist_ok=True)
        np.savez(cache_path, stamp=stamp, ball=ball, players=players, speed=speed)
    return Tracking(ball, players, speed, team_of_slot, names)
