# Walk-forward results

```
                          total_return    cagr  max_drawdown  sharpe  final_equity      costs  mean_weekly_turnover  n_fills  n_skipped
pipeline                        0.0408  0.2980       -0.0390  1.8869  1.040803e+06  1364.7874                0.4185     44.0       41.0
pipeline_no_protective          0.0493  0.3689       -0.0421  2.0085  1.049318e+06   786.5039                0.2813     36.0       44.0
pipeline_naive_execution        0.0517  0.3895       -0.0512  1.8921  1.051726e+06  1469.7156                0.3203     43.0       37.0
mechanical_seed                 0.0562  0.4282       -0.0603  1.8216  1.056164e+06  1433.6056                0.3149     56.0       29.0
equal_weight_buy_hold           0.0419  0.3069       -0.0473  1.5989  1.041889e+06   499.8338                0.1111     10.0        1.0
equal_weight_weekly             0.0409  0.2991       -0.0473  1.5724  1.040931e+06   517.1580                0.1148     13.0       68.0
spy_buy_hold                    0.0172  0.1176       -0.0507  0.5976  1.017187e+06   499.8338                0.1111      1.0        1.0
momentum_12_1_top5              0.0655  0.5122       -0.0571  1.7804  1.065462e+06   746.5577                0.1651     13.0       69.0
```

```json
{
 "window": "dev",
 "decisions": 8,
 "llm": {
  "calls": 0,
  "cache_hits": 0,
  "input_tokens": 0,
  "output_tokens": 0
 },
 "significance": {
  "vs_equal_weight_buy_hold": {
   "excess_weekly_mean": -0.00013091917354003668,
   "excess_lo": -0.004584171561056005,
   "excess_hi": 0.004322333213975932,
   "p_le_zero": 0.3795,
   "sharpe_diff": -0.049411114206276086,
   "sharpe_diff_lo": -3.4267409331448535,
   "sharpe_diff_hi": 0.967336721489257
  },
  "vs_spy_buy_hold": {
   "excess_weekly_mean": 0.002889045427739087,
   "excess_lo": -0.00691966616702136,
   "excess_hi": 0.012697757022499534,
   "p_le_zero": 0.1285,
   "sharpe_diff": 0.889571902099408,
   "sharpe_diff_lo": -4.2292215395492505,
   "sharpe_diff_hi": 4.878504399155139
  },
  "vs_mechanical_seed": {
   "excess_weekly_mean": -0.0019518715304290002,
   "excess_lo": -0.003961206656679261,
   "excess_hi": 0.0027857843300083673,
   "p_le_zero": 0.689,
   "sharpe_diff": -0.2145526831178317,
   "sharpe_diff_lo": -3.3311383237852716,
   "sharpe_diff_hi": 0.7240176252241145
  },
  "vs_momentum_12_1_top5": {
   "excess_weekly_mean": -0.0031473767902332056,
   "excess_lo": -0.004729207213199804,
   "excess_hi": -0.0003951307231020995,
   "p_le_zero": 1.0,
   "sharpe_diff": -0.26813275730760866,
   "sharpe_diff_lo": -3.6196651740554127,
   "sharpe_diff_hi": 1.1930344053470558
  },
  "random_policy_percentile": 54.6,
  "random_policy_n": 500
 },
 "research_ic": {
  "technical@1w": {
   "mean_ic": 0.10189274042782323,
   "t_stat": 0.9476884954262067,
   "hit_rate": 0.625,
   "n": 8
  },
  "fundamentals@1w": {
   "mean_ic": -0.06617698369706741,
   "t_stat": -0.5596494578178032,
   "hit_rate": 0.25,
   "n": 8
  },
  "macro@1w": {
   "mean_ic": -0.1620604508631197,
   "t_stat": -1.2005210631508814,
   "hit_rate": 0.375,
   "n": 8
  },
  "sentiment@1w": {
   "mean_ic": 0.12434262441755055,
   "t_stat": 0.684192749454695,
   "hit_rate": 0.6,
   "n": 5
  },
  "geopolitics@1w": {
   "mean_ic": 0.01334378189943021,
   "t_stat": 0.09937846848765676,
   "hit_rate": 0.5,
   "n": 8
  },
  "strategy_weight@1w": {
   "mean_ic": -0.00246677597990623,
   "t_stat": -0.016217040195632932,
   "hit_rate": 0.625,
   "n": 8
  },
  "technical@4w": {
   "mean_ic": 0.2339343098434991,
   "t_stat": 2.8951592367159944,
   "hit_rate": 0.875,
   "n": 8
  },
  "fundamentals@4w": {
   "mean_ic": 0.016993583315795743,
   "t_stat": 0.1832589574851263,
   "hit_rate": 0.5,
   "n": 8
  },
  "macro@4w": {
   "mean_ic": -0.35015844247387073,
   "t_stat": -3.917685527140879,
   "hit_rate": 0.125,
   "n": 8
  },
  "sentiment@4w": {
   "mean_ic": 0.0893357444571331,
   "t_stat": 1.5721217163043466,
   "hit_rate": 0.6,
   "n": 5
  },
  "geopolitics@4w": {
   "mean_ic": -0.11711315391265739,
   "t_stat": -1.0850155293828048,
   "hit_rate": 0.5,
   "n": 8
  },
  "strategy_weight@4w": {
   "mean_ic": 0.06754903660757675,
   "t_stat": 0.8210471385697206,
   "hit_rate": 0.75,
   "n": 8
  }
 }
}
```
