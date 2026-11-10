# tracking

Reads the tactical tracking data (ATD) into numpy arrays, in metres, one row per video frame.

This is the only module that knows the file format. Everything after it works on the `Tracking`
arrays below, so a change in the export means a change here and nowhere else.

```python
from possession import tracking

data = tracking.load("data", cache_dir="cache")
data.ball            # (199319, 2)      ball x, y in metres, NaN where not tracked
data.players         # (199319, 46, 2)  every track slot's x, y in metres, NaN if absent
data.speed           # (199319, 46)     every slot's speed in m/s, NaN if absent
data.team_of_slot    # (46,)            HOME (0) or AWAY (1) for each slot
data.team_names      # (home club name, away club name), for printing
```

Row *i* is video frame *i*, so row *i* is also submission row *i*.

---

## Frame alignment

The file counts frames from 1. The submission counts from 0. So the loader puts the record for
`frame_id` 1 in row 0:

```
video_frame = frame_id - 1
```

That is the whole alignment for the tactical recording (the organisers' DATA.md, "Frame
alignment"). Frames missing from the file stay NaN.

## The file format

Two files, both under `<data>/tactical/`:

| file | contents |
|---|---|
| `BAR-ATH_tactical_atd.xml` | metadata: the two teams, and which team each track slot is on |
| `BAR-ATH_tactical_atd.txt` | one line per frame |

A line of the text file looks like this, shortened to two slots:

```
11186:0.4921,0.5003,1.25;NaN,NaN,NaN:0.5012,0.4998,0.00
```

| part | meaning |
|---|---|
| `11186` | `frame_id`, counting from 1 |
| `0.4921,0.5003,1.25` | slot 1: x, y (0-1 units) and speed (m/s) |
| `NaN,NaN,NaN` | slot 2: not tracked on this frame |
| `0.5012,0.4998,0.00` | the ball. Only the first two values, x and y, are used |

Lines that do not have three `:`-separated parts are skipped rather than guessed at.

### Which team a slot is on

The first `<Team>` in the XML is the home side. That is the FIFA/EPTS convention, and the
organisers' baseline relies on it too. Slots are listed as `<Player>` entries in the same order as
they appear on each line of the text file.

### Slots are not players

There are 46 slots for 22 players. A slot can follow one person, lose them, then pick up someone
else. The only thing a slot reliably tells you is its team, so nothing downstream tries to follow
an individual.

---

## Caching

Parsing the text file takes a minute or two. The parsed arrays are saved to `cache_dir` the first
time and reused after that.

The cache is reused only if it was written from a raw file of the same size and modification time.
Replace the data bundle and the cache is rebuilt on the next run.

The cache is derived match data, so it must never be committed. The project's `.gitignore`
excludes `cache/` and `*.npz`.

## Functions

| function | does |
|---|---|
| `load(data_dir, cache_dir)` | the whole thing: returns a `Tracking`, using the cache when it is current |
| `atd_paths(data_dir)` | the two file paths, or an error naming exactly which file is missing |
| `read_teams(meta_path)` | team of each slot, and the two club names |
| `parse_line(line, n_slots)` | one text line to (video frame, slot values, ball x, ball y) |
| `parse_raw(raw_path, n_slots)` | stream the whole text file into arrays |

Example of `parse_line`:

```python
parse_line("2:0.1,0.2,3.0;NaN,NaN,NaN:0.5,0.5,0", 2)
# -> (1, [[0.1, 0.2, 3.0], [nan, nan, nan]], 0.5, 0.5)
#     ^ frame_id 2 is video frame 1
```
