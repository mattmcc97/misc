"""Ball possession for More Than A Hack 2027, Phase 1.

The pipeline, one folder per step, each with its own README.md:

    tracking/        read the tracking files into arrays, in metres, one row per video frame
    observations/    per frame: which team controls the ball, and does it look like a stoppage
    state_machine/   turn those per-frame facts into H / A / D labels
    submission/      write the CSV, check it, count possessions
    config/          every threshold, with what it means in football terms

`run.py` at the project root chains them together.
"""
