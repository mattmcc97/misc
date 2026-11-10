# tests

Checks every module without any match data, so the tests run on a fresh clone.

```bash
python -m unittest            # from the project root
```

Everything here is invented to exercise the rules. None of it comes from the match.

---

## What each file covers

| file | covers |
|---|---|
| `test_state_machine.py` | one test per possession rule, on hand-written frame sequences |
| `test_observations.py` | gap filling, ball speed, the control rules and the dead-ball cues, on tiny arrays |
| `test_pipeline.py` | reading fake ATD files, writing and checking a submission, and a 9-second invented passage of play run end to end |

## How the state machine tests are written

Each test is a string with one character per frame, and the labels the machine should write
underneath it:

| character | meaning |
|---|---|
| `h` | home controls the ball |
| `a` | away controls the ball |
| `.` | nobody controls it |
| `x` | dead-ball cue |

```python
def test_turnover_is_backdated_to_first_touch(self):
    self.check("hh hh aaa a",
               "HH HH AAA A")
```

Spaces are ignored. They are only there to line frames up so you can read the test. `check` fails
if the two strings are different lengths, so a miscounted test fails loudly instead of passing by
accident.

The timings are shrunk so a whole scenario fits on one line: 3 frames of control for a turnover,
3 frames of cues for a stoppage, 2 clear frames for a restart and a 4-frame challenge timeout
(`SMALL` at the top of the file). The real defaults are in `possession/config/`.

## The invented match

`test_pipeline.py`, `InventedMatchTest`, builds 9 seconds of tracking by hand:

| time | what happens |
|---|---|
| 0-2 s | dead ball: ball still at the centre spot, everyone walking |
| 2-4 s | a home player dribbles the ball |
| 4-5 s | a long home pass at 15 m/s, flying past the away player |
| 5-7 s | the away player picks it up and dribbles away: a turnover |
| 7-9 s | the ball goes out over the touchline: dead |

It runs the real observations and the real state machine with default parameters, and checks the
labels come out as `D`, `H`, `A`, `D`, with the turnover within a few frames of the away player's
first touch.
