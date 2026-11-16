"""
APEX-EVCONTRIB125-2026-10-07 (owner, requested)
Scales ONLY the already-blended EV contribution (post Global25 blend) by
1.25x. Does not touch GLOBAL_BLEND_FRAC, category gates, Aces band
calibration, the probability term, attention bonus, ranking logic, board
logic, or Discord output.
"""
import re

PATH = "apex_edge_tracker.py"
with open(PATH) as f:
    src = f.read()

anchor = (
    '    ev = ev_calibrated + GLOBAL_BLEND_FRAC * (ev_fixed_manual - ev_calibrated)\n'
    '    score += ev\n'
)
assert src.count(anchor) == 1, f"anchor found {src.count(anchor)} times, expected 1"

replacement = (
    '    ev = ev_calibrated + GLOBAL_BLEND_FRAC * (ev_fixed_manual - ev_calibrated)\n'
    '    # APEX-EVCONTRIB125-2026-10-07 (owner, approved production configuration):\n'
    '    # Elite-6 root-cause + sensitivity study (2026-10-07) found the post-blend EV\n'
    '    # contribution underweighted relative to what the calibration data supports --\n'
    '    # scaling it by 1.25x improved Top 3 (78.0%->80.0%), Top 6 (67.74%->72.04%,\n'
    '    # passing Probability Top 6 at 70.97%), and Elite 6 (75.76%->76.47%) together,\n'
    '    # with no tradeoff found in testing. Only the final blended ev is scaled here --\n'
    '    # GLOBAL_BLEND_FRAC, the gates, Aces band calibration, the probability term,\n'
    '    # and the attention bonus below are all untouched.\n'
    '    EV_CONTRIBUTION_SCALE = 1.25\n'
    '    ev *= EV_CONTRIBUTION_SCALE\n'
    '    score += ev\n'
)

src2 = src.replace(anchor, replacement, 1)
with open(PATH, "w") as f:
    f.write(src2)

print("PATCH APPLIED OK")
