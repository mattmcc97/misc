# submission

Writes the submission file, checks it, and counts the possessions it claims.

```python
from possession import submission

labels = submission.full_match([(11185, first_half), (110808, second_half)])
submission.write("output/state_machine.csv", labels)     # checks first, then writes
submission.summarise(labels)                             # label counts and possessions
```

---

## The file

A header line and one row per video frame, 199,319 rows:

```
frame,label
0,X
...
11185,A
11186,A
...
199318,X
```

`full_match` builds the full-length array: it places each half's labels at its first frame and
writes `X` everywhere else. `X` outside the graded halves is never scored.

## Checking it

`check` raises an error if the organisers' validator would reject the file:

- exactly 199,319 labels
- every label is `H`, `A`, `D` or `X`

`write` always calls `check` first, so a broken file fails at the end of our pipeline instead of at
theirs. Still run the official `evaluation/validate_submission.py` before uploading: it is the one
that counts.

## The summary

`summarise` reads only our own labels, never a ground truth, so it is safe to look at as often as
you like. It counts possessions the way the ranking metric defines them: a maximal run of `H` or of
`A` inside one half.

| key | meaning |
|---|---|
| `frames` | how many graded frames got each label |
| `possessions` | number of maximal `H` or `A` runs, counted within each half |
| `mean_possession_s` | their mean length in seconds |
| `stoppages` | number of maximal `D` runs |

The number to look at first is `possessions`. The public 5 minutes have 17 possessions, about 3.4 a
minute. A full match that claims thousands is splitting possessions; one that claims a few dozen is
missing turnovers.

`runs` is the helper behind it:

```python
runs(["H", "H", "D", "A"])
# -> [("H", 0, 1), ("D", 2, 2), ("A", 3, 3)]    (label, first frame, last frame)
```

`H D H` is two possessions with a stoppage between them, not one.
