# Run opus46_target_weight_execution

- spec_hash: `930deccb103324395aacb29a969de1d73fd7319963bdc15220dead0c81def5d4`
- label: **model-clean**
- model: us.anthropic.claude-opus-4-6-v1 (training cutoff 2025-08)
- window: 2025-10-03 .. 2026-10-16, marked to 2026-10-22 (55 decisions)
- git_sha: a6f4a2b603d1c4ed60680817aaa465d5af59880a

## Metrics

```
                       total_return    cagr  max_drawdown  sharpe  final_equity       costs  turnover  n_fills  n_skipped  n_blocked
strategy                     0.0609  0.0578       -0.0842  0.2632  1.060880e+06  12120.4644    0.4125    339.0      211.0        0.0
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
  "excess_weekly_mean": -0.002685516861053494,
  "excess_lo": -0.005130426334923715,
  "excess_hi": -0.000985900676292191,
  "p_le_zero": 1.0,
  "n_weeks": 55,
  "sharpe_diff": -1.174792403517742,
  "sharpe_diff_lo": -2.1779416491351093,
  "sharpe_diff_hi": -0.4497882301633224
 },
 "vs_equal_weight_weekly": {
  "excess_weekly_mean": -0.0031394780856790804,
  "excess_lo": -0.005889698715592814,
  "excess_hi": -0.0010970849002104321,
  "p_le_zero": 1.0,
  "n_weeks": 55,
  "sharpe_diff": -1.308080480285093,
  "sharpe_diff_lo": -2.360566311196673,
  "sharpe_diff_hi": -0.4644515851702448
 },
 "vs_spy_buy_hold": {
  "excess_weekly_mean": -0.001284436835187748,
  "excess_lo": -0.004526911807776159,
  "excess_hi": 0.0014393204264471324,
  "p_le_zero": 0.8555,
  "n_weeks": 55,
  "sharpe_diff": -0.5008189567817052,
  "sharpe_diff_lo": -1.9587254648066825,
  "sharpe_diff_hi": 0.6020575561939926
 },
 "vs_momentum_12_1_top5": {
  "excess_weekly_mean": -0.0033577982613015385,
  "excess_lo": -0.006678173104628722,
  "excess_hi": -0.0012626277000349466,
  "p_le_zero": 0.9975,
  "n_weeks": 55,
  "sharpe_diff": -1.003356314035097,
  "sharpe_diff_lo": -2.302277042394281,
  "sharpe_diff_hi": -0.24562993656056803
 },
 "vs_mechanical_seed": {
  "excess_weekly_mean": -0.0015626238791279072,
  "excess_lo": -0.004106128306957833,
  "excess_hi": 0.0003310741701774653,
  "p_le_zero": 0.954,
  "n_weeks": 55,
  "sharpe_diff": -0.4632819257559939,
  "sharpe_diff_lo": -1.0976314337837176,
  "sharpe_diff_hi": 0.11960841531298051
 }
}
```
