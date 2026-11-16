# KNOWLEDGE BASE (generated 2026-08-30 22:40)

## Known Strengths
NOT AVAILABLE -- requires validated positive findings.

## Known Weaknesses
- dfs projections run low by 1.53 on average (10 occ, Moderate)
- games_won projections run low by 1.72 on average (5 occ, Low)
- dfs losses classified VARIANCE (4 occ, Very Low)

## Open Questions
- Does the APEX score separate winners from losers? (Phase 0)
- Are projections biased by category? (Phase 1)
- Model error vs variance share? (Phase 2)

## Validated Fixes
NOT AVAILABLE -- requires Phase 4 evidence.

## Failed Fixes
NOT AVAILABLE -- no fix adopted and measured.

## Recurring Failure Patterns
- `bias:dfs` x10 [Supported]
- `bias:games_won` x5 [Observed]
- `cause:VARIANCE:dfs` x4 [Observed]
- `cause:VARIANCE:total_games` x2 [Hypothesis]
- `cause:VARIANCE:games_won` x1 [Hypothesis]
- `cause:MODEL_ERROR:total_games` x1 [Hypothesis]
- `cause:CATEGORY_ERROR:games_won` x1 [Hypothesis]
- `cause:MODEL_ERROR:dfs` x1 [Hypothesis]
- `cause:MODEL_ERROR:aces` x1 [Hypothesis]
