# Memorization audit: clean window

55 weekly decisions (2025-10-03 to 2026-10-16); model us.anthropic.claude-opus-4-6-v1; contaminated control: False.
IC = rank correlation of conviction with forward return. Difference = named IC minus masked IC, with a paired block-bootstrap 95% interval.

| series | horizon | dates | named IC | masked IC | difference | 95% CI | verdict |
|---|---|---|---|---|---|---|---|
| fundamentals | 1w | 54 | -0.068 | -0.074 | +0.005 | [-0.021, +0.028] | no detectable memory effect |
| fundamentals | 4w | 51 | -0.080 | -0.083 | +0.003 | [-0.029, +0.032] | no detectable memory effect |
| geopolitics | 1w | 50 | -0.019 | +0.068 | -0.094 | [-0.255, +0.040] | no detectable memory effect |
| geopolitics | 4w | 47 | -0.078 | +0.011 | -0.103 | [-0.272, +0.066] | no detectable memory effect |
| macro | 1w | 54 | -0.048 | +0.006 | -0.053 | [-0.185, +0.090] | no detectable memory effect |
| macro | 4w | 51 | -0.183 | -0.049 | -0.134 | [-0.289, +0.013] | no detectable memory effect |
| sentiment | 1w | 50 | +0.009 | -0.004 | +0.016 | [-0.089, +0.075] | no detectable memory effect |
| sentiment | 4w | 47 | -0.009 | -0.037 | +0.022 | [-0.038, +0.070] | no detectable memory effect |
| strategy_weight | 1w | 54 | -0.074 | -0.029 | -0.045 | [-0.102, -0.005] | masked better |
| strategy_weight | 4w | 51 | -0.143 | -0.084 | -0.059 | [-0.136, +0.013] | no detectable memory effect |
| technical | 1w | 54 | -0.027 | -0.038 | +0.012 | [-0.017, +0.051] | no detectable memory effect |
| technical | 4w | 51 | -0.007 | -0.022 | +0.016 | [-0.037, +0.067] | no detectable memory effect |

Strategist weights, named vs masked: mean absolute difference 0.038; share of ticker-weeks differing by more than 5 points 31.1% (55 dates).

Verdict rule: CI lower bound > 0 is named better; CI upper bound < 0 is masked better; otherwise no detectable memory effect (low power with few dates is not proof of absence).
