# Walk-forward results

```
                          total_return    cagr  max_drawdown  sharpe  final_equity       costs  mean_weekly_turnover  n_fills  n_skipped
pipeline                        0.0239  0.0227       -0.0900 -0.0476  1.023902e+06   9097.8225                0.4687    332.0      252.0
pipeline_no_protective          0.0354  0.0336       -0.0882  0.0618  1.035399e+06   6832.9428                0.3771    306.0      243.0
pipeline_naive_execution        0.0609  0.0578       -0.0842  0.2632  1.060880e+06  12120.4644                0.4125    339.0      211.0
mechanical_seed                 0.1517  0.1437       -0.1030  0.7794  1.151657e+06   9895.5166                0.3268    399.0      190.0
equal_weight_buy_hold           0.2288  0.2165       -0.0749  1.3329  1.228818e+06    499.8338                0.0179     10.0        1.0
equal_weight_weekly             0.2591  0.2450       -0.0790  1.5332  1.259111e+06    765.3215                0.0263     52.0      507.0
spy_buy_hold                    0.1371  0.1300       -0.0913  0.7645  1.137110e+06    499.8338                0.0179      1.0        1.0
momentum_12_1_top5              0.2687  0.2540       -0.0855  1.2415  1.268679e+06   5071.8464                0.1576     92.0      475.0
```

```json
{
 "window": "all",
 "decisions": 55,
 "llm": {
  "calls": 353,
  "cache_hits": 32,
  "input_tokens": 1077188,
  "output_tokens": 368197
 },
 "significance": {
  "vs_equal_weight_buy_hold": {
   "excess_weekly_mean": -0.003350088677728145,
   "excess_lo": -0.0065384900687325154,
   "excess_hi": -0.0007635990312803237,
   "p_le_zero": 0.9945,
   "sharpe_diff": -1.4577724748078416,
   "sharpe_diff_lo": -2.818547673964677,
   "sharpe_diff_hi": -0.33772429903612095
  },
  "vs_spy_buy_hold": {
   "excess_weekly_mean": -0.001949008651862399,
   "excess_lo": -0.005607572364532575,
   "excess_hi": 0.001407637366343723,
   "p_le_zero": 0.8935,
   "sharpe_diff": -0.7837990280718048,
   "sharpe_diff_lo": -2.5330304100761327,
   "sharpe_diff_hi": 0.6525756982349092
  },
  "vs_mechanical_seed": {
   "excess_weekly_mean": -0.002227195695802558,
   "excess_lo": -0.005646798685259209,
   "excess_hi": 0.0004550568559993163,
   "p_le_zero": 0.9385,
   "sharpe_diff": -0.7462619970460935,
   "sharpe_diff_lo": -1.8524479292392293,
   "sharpe_diff_hi": 0.22570810449044268
  },
  "vs_momentum_12_1_top5": {
   "excess_weekly_mean": -0.00402237007797619,
   "excess_lo": -0.008173425219425894,
   "excess_hi": -0.001331751121670481,
   "p_le_zero": 0.998,
   "sharpe_diff": -1.2863363853251966,
   "sharpe_diff_lo": -2.9572652695375647,
   "sharpe_diff_hi": -0.2778191510345794
  },
  "random_policy_percentile": 12.8,
  "random_policy_n": 500
 },
 "research_ic": {
  "technical@1w": {
   "mean_ic": -0.026578706635570454,
   "t_stat": -0.5888889777847379,
   "hit_rate": 0.5,
   "n": 54
  },
  "fundamentals@1w": {
   "mean_ic": -0.06842049609832747,
   "t_stat": -1.1681853420489525,
   "hit_rate": 0.35185185185185186,
   "n": 54
  },
  "macro@1w": {
   "mean_ic": -0.0475937412682116,
   "t_stat": -0.905867030059821,
   "hit_rate": 0.5,
   "n": 54
  },
  "sentiment@1w": {
   "mean_ic": 0.009333859534605228,
   "t_stat": 0.18685856502671416,
   "hit_rate": 0.56,
   "n": 50
  },
  "geopolitics@1w": {
   "mean_ic": -0.019112297820484087,
   "t_stat": -0.32725335777675285,
   "hit_rate": 0.5185185185185185,
   "n": 54
  },
  "strategy_weight@1w": {
   "mean_ic": -0.07385728460978157,
   "t_stat": -1.8125256487430361,
   "hit_rate": 0.42592592592592593,
   "n": 54
  },
  "technical@4w": {
   "mean_ic": -0.00685168627880917,
   "t_stat": -0.14713334120167837,
   "hit_rate": 0.5098039215686274,
   "n": 51
  },
  "fundamentals@4w": {
   "mean_ic": -0.07983859901021904,
   "t_stat": -1.6628494212552338,
   "hit_rate": 0.4117647058823529,
   "n": 51
  },
  "macro@4w": {
   "mean_ic": -0.1828888159243333,
   "t_stat": -3.7024066547378696,
   "hit_rate": 0.29411764705882354,
   "n": 51
  },
  "sentiment@4w": {
   "mean_ic": -0.009374919682963799,
   "t_stat": -0.19829267077325102,
   "hit_rate": 0.3829787234042553,
   "n": 47
  },
  "geopolitics@4w": {
   "mean_ic": -0.07775485907008695,
   "t_stat": -1.5937611866217696,
   "hit_rate": 0.39215686274509803,
   "n": 51
  },
  "strategy_weight@4w": {
   "mean_ic": -0.14295955621771816,
   "t_stat": -3.620775169267165,
   "hit_rate": 0.35294117647058826,
   "n": 51
  }
 }
}
```
