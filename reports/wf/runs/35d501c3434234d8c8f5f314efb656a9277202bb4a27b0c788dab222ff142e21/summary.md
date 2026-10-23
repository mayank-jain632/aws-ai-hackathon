# Run opus46_synthesis_planner

- spec_hash: `35d501c3434234d8c8f5f314efb656a9277202bb4a27b0c788dab222ff142e21`
- label: **model-clean**
- model: us.anthropic.claude-opus-4-6-v1 (training cutoff 2025-08)
- window: 2025-10-03 .. 2026-10-16, marked to 2026-10-22 (55 decisions)
- git_sha: a6f4a2b603d1c4ed60680817aaa465d5af59880a

## Metrics

```
                       total_return    cagr  max_drawdown  sharpe  final_equity       costs  turnover  n_fills  n_skipped  n_blocked
strategy                     0.0556  0.0528       -0.0825  0.2235  1.055582e+06  11522.9491    0.3925    326.0       40.0        0.0
equal_weight_buy_hold        0.2288  0.2165       -0.0749  1.3329  1.228818e+06    499.8338    0.0179     10.0        1.0        0.0
equal_weight_weekly          0.2591  0.2450       -0.0790  1.5332  1.259111e+06    765.3215    0.0263     52.0      507.0        0.0
spy_buy_hold                 0.1371  0.1300       -0.0913  0.7645  1.137110e+06    499.8338    0.0179      1.0        1.0        0.0
momentum_12_1_top5           0.2687  0.2540       -0.0855  1.2415  1.268679e+06   5071.8464    0.1576     92.0      475.0        0.0
mechanical_seed              0.1517  0.1437       -0.1030  0.7794  1.151657e+06   9895.5166    0.3268    399.0      190.0        0.0
```

## Significance

```json
{
 "vs_equal_weight_buy_hold": {
  "excess_weekly_mean": -0.0027806159863354167,
  "excess_lo": -0.005354579474196207,
  "excess_hi": -0.0009043662369989957,
  "p_le_zero": 0.9995,
  "n_weeks": 55,
  "sharpe_diff": -1.2097727986318159,
  "sharpe_diff_lo": -2.20092576677254,
  "sharpe_diff_hi": -0.4315365635727395
 },
 "vs_equal_weight_weekly": {
  "excess_weekly_mean": -0.003234577210961003,
  "excess_lo": -0.006130231314435677,
  "excess_hi": -0.000985460970708992,
  "p_le_zero": 0.9985,
  "n_weeks": 55,
  "sharpe_diff": -1.3430608753991669,
  "sharpe_diff_lo": -2.433369849083483,
  "sharpe_diff_hi": -0.4089278840426186
 },
 "vs_spy_buy_hold": {
  "excess_weekly_mean": -0.001379535960469671,
  "excess_lo": -0.004577388676513575,
  "excess_hi": 0.001436407825386979,
  "p_le_zero": 0.8565,
  "n_weeks": 55,
  "sharpe_diff": -0.535799351895779,
  "sharpe_diff_lo": -1.9315355855529392,
  "sharpe_diff_hi": 0.614817764720255
 },
 "vs_momentum_12_1_top5": {
  "excess_weekly_mean": -0.0034528973865834613,
  "excess_lo": -0.006779763315400667,
  "excess_hi": -0.0011590624497328623,
  "p_le_zero": 0.997,
  "n_weeks": 55,
  "sharpe_diff": -1.0383367091491706,
  "sharpe_diff_lo": -2.276399362395247,
  "sharpe_diff_hi": -0.2501047802596968
 },
 "vs_mechanical_seed": {
  "excess_weekly_mean": -0.00165772300440983,
  "excess_lo": -0.004323805603004975,
  "excess_hi": 0.00038403906855858646,
  "p_le_zero": 0.9385,
  "n_weeks": 55,
  "sharpe_diff": -0.4982623208700677,
  "sharpe_diff_lo": -1.0950902086119634,
  "sharpe_diff_hi": 0.1564218429604028
 }
}
```
