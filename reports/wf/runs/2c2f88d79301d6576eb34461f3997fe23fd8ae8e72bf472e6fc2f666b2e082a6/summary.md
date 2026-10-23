# Run opus46_llm_execution

- spec_hash: `2c2f88d79301d6576eb34461f3997fe23fd8ae8e72bf472e6fc2f666b2e082a6`
- label: **model-clean**
- model: us.anthropic.claude-opus-4-6-v1 (training cutoff 2025-08)
- window: 2025-10-03 .. 2026-10-16, marked to 2026-10-22 (55 decisions)
- git_sha: a6f4a2b603d1c4ed60680817aaa465d5af59880a

## Metrics

```
                       total_return    cagr  max_drawdown  sharpe  final_equity      costs  turnover  n_fills  n_skipped  n_blocked
strategy                     0.0239  0.0227       -0.0900 -0.0476  1.023902e+06  9097.8225    0.4687    332.0      252.0        0.0
equal_weight_buy_hold        0.2288  0.2165       -0.0749  1.3329  1.228818e+06   499.8338    0.0179     10.0        1.0        0.0
equal_weight_weekly          0.2591  0.2450       -0.0790  1.5332  1.259111e+06   765.3215    0.0263     52.0      507.0        0.0
spy_buy_hold                 0.1371  0.1300       -0.0913  0.7645  1.137110e+06   499.8338    0.0179      1.0        1.0        0.0
momentum_12_1_top5           0.2687  0.2540       -0.0855  1.2415  1.268679e+06  5071.8464    0.1576     92.0      475.0        0.0
mechanical_seed              0.1517  0.1437       -0.1030  0.7794  1.151657e+06  9895.5166    0.3268    399.0      190.0        0.0
```

## Significance

```json
{
 "vs_equal_weight_buy_hold": {
  "excess_weekly_mean": -0.003350088677728145,
  "excess_lo": -0.0065384900687325154,
  "excess_hi": -0.0007635990312803237,
  "p_le_zero": 0.9945,
  "n_weeks": 55,
  "sharpe_diff": -1.4577724748078416,
  "sharpe_diff_lo": -2.818547673964677,
  "sharpe_diff_hi": -0.33772429903612095
 },
 "vs_equal_weight_weekly": {
  "excess_weekly_mean": -0.0038040499023537316,
  "excess_lo": -0.007245571811991189,
  "excess_hi": -0.0010435760366410728,
  "p_le_zero": 0.9945,
  "n_weeks": 55,
  "sharpe_diff": -1.5910605515751925,
  "sharpe_diff_lo": -2.9570188080548645,
  "sharpe_diff_hi": -0.43405427515630685
 },
 "vs_spy_buy_hold": {
  "excess_weekly_mean": -0.001949008651862399,
  "excess_lo": -0.005607572364532575,
  "excess_hi": 0.001407637366343723,
  "p_le_zero": 0.8935,
  "n_weeks": 55,
  "sharpe_diff": -0.7837990280718048,
  "sharpe_diff_lo": -2.5330304100761327,
  "sharpe_diff_hi": 0.6525756982349092
 },
 "vs_momentum_12_1_top5": {
  "excess_weekly_mean": -0.00402237007797619,
  "excess_lo": -0.008173425219425894,
  "excess_hi": -0.001331751121670481,
  "p_le_zero": 0.998,
  "n_weeks": 55,
  "sharpe_diff": -1.2863363853251966,
  "sharpe_diff_lo": -2.9572652695375647,
  "sharpe_diff_hi": -0.2778191510345794
 },
 "vs_mechanical_seed": {
  "excess_weekly_mean": -0.002227195695802558,
  "excess_lo": -0.005646798685259209,
  "excess_hi": 0.0004550568559993163,
  "p_le_zero": 0.9385,
  "n_weeks": 55,
  "sharpe_diff": -0.7462619970460935,
  "sharpe_diff_lo": -1.8524479292392293,
  "sharpe_diff_hi": 0.22570810449044268
 }
}
```
