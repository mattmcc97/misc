"""Ball possession for More Than A Hack 2027, Phase 1.

The pipeline, one module per step:

    tracking.py       read the tracking files into arrays, in metres, one row per video frame
    observations.py   per frame: which team controls the ball, and does it look like a stoppage
    state_machine.py  turn those per-frame facts into H / A / D labels with a state machine
    submission.py     write the CSV, check it, count possessions
    config.py         every threshold, with what it means in football terms

`run.py` at the project root chains them together.
"""
