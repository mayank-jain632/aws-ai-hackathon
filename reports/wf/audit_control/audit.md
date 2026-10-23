# Memorization audit: control window

17 weekly decisions (2025-03-07 to 2025-06-27); model us.anthropic.claude-opus-4-6-v1; contaminated control: True.
IC = rank correlation of conviction with forward return. Difference = named IC minus masked IC, with a paired block-bootstrap 95% interval.

| series | horizon | dates | named IC | masked IC | difference | 95% CI | verdict |
|---|---|---|---|---|---|---|---|
| fundamentals | 1w | 17 | +0.121 | +0.126 | -0.005 | [-0.043, +0.022] | no detectable memory effect |
| fundamentals | 4w | 17 | +0.269 | +0.301 | -0.032 | [-0.073, +0.007] | no detectable memory effect |
| geopolitics | 1w | 16 | -0.213 | -0.052 | -0.176 | [-0.322, +0.013] | no detectable memory effect |
| geopolitics | 4w | 16 | -0.234 | -0.019 | -0.210 | [-0.484, +0.079] | no detectable memory effect |
| macro | 1w | 17 | +0.092 | -0.061 | +0.154 | [-0.081, +0.369] | no detectable memory effect |
| macro | 4w | 17 | +0.093 | -0.157 | +0.250 | [+0.014, +0.384] | named better: possible memory effect |
| sentiment | 1w | 17 | +0.127 | +0.163 | -0.036 | [-0.109, +0.035] | no detectable memory effect |
| sentiment | 4w | 17 | +0.362 | +0.290 | +0.072 | [+0.010, +0.221] | named better: possible memory effect |
| strategy_weight | 1w | 17 | +0.081 | +0.072 | +0.009 | [-0.080, +0.074] | no detectable memory effect |
| strategy_weight | 4w | 17 | +0.161 | +0.174 | -0.013 | [-0.072, +0.058] | no detectable memory effect |
| technical | 1w | 17 | +0.020 | +0.038 | -0.017 | [-0.051, +0.026] | no detectable memory effect |
| technical | 4w | 17 | +0.121 | +0.093 | +0.028 | [-0.001, +0.050] | no detectable memory effect |

Strategist weights, named vs masked: mean absolute difference 0.027; share of ticker-weeks differing by more than 5 points 20.6% (17 dates).

Verdict rule: CI lower bound > 0 is named better; CI upper bound < 0 is masked better; otherwise no detectable memory effect (low power with few dates is not proof of absence).
