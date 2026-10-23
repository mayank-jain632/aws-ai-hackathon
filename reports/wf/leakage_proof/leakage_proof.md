# Leakage proof on real data

PASS: 55 decision dates; failures: none.

For each date the exact analyst prompts, execution context and last closes were rebuilt from the real
data, from data truncated at the date, and from data whose future rows were overwritten with 9.99e12.

| date | truncated identical | poisoned identical | poison present | latest date in prompts |
|---|---|---|---|---|
| 2025-10-03 | True | True | True | 2025-10-03 |
| 2025-10-10 | True | True | True | 2025-10-10 |
| 2025-10-17 | True | True | True | 2025-10-17 |
| 2025-10-24 | True | True | True | 2025-10-24 |
| 2025-10-31 | True | True | True | 2025-10-31 |
| 2025-11-07 | True | True | True | 2025-11-07 |
| 2025-11-14 | True | True | True | 2025-11-14 |
| 2025-11-21 | True | True | True | 2025-11-21 |
| 2025-11-28 | True | True | True | 2025-11-28 |
| 2025-12-05 | True | True | True | 2025-12-05 |
| 2025-12-12 | True | True | True | 2025-12-12 |
| 2025-12-19 | True | True | True | 2025-12-19 |
| 2025-12-26 | True | True | True | 2025-12-26 |
| 2026-01-02 | True | True | True | 2026-01-02 |
| 2026-01-09 | True | True | True | 2026-01-09 |
| 2026-01-16 | True | True | True | 2026-01-16 |
| 2026-01-23 | True | True | True | 2026-01-23 |
| 2026-01-30 | True | True | True | 2026-01-30 |
| 2026-02-06 | True | True | True | 2026-02-06 |
| 2026-02-13 | True | True | True | 2026-02-13 |
| 2026-02-20 | True | True | True | 2026-02-20 |
| 2026-02-27 | True | True | True | 2026-02-27 |
| 2026-03-06 | True | True | True | 2026-03-06 |
| 2026-03-13 | True | True | True | 2026-03-13 |
| 2026-03-20 | True | True | True | 2026-03-20 |
| 2026-03-27 | True | True | True | 2026-03-27 |
| 2026-04-02 | True | True | True | 2026-04-02 |
| 2026-04-10 | True | True | True | 2026-04-10 |
| 2026-04-17 | True | True | True | 2026-04-17 |
| 2026-04-24 | True | True | True | 2026-04-24 |
| 2026-05-01 | True | True | True | 2026-05-01 |
| 2026-05-08 | True | True | True | 2026-05-08 |
| 2026-05-15 | True | True | True | 2026-05-15 |
| 2026-05-22 | True | True | True | 2026-05-22 |
| 2026-05-29 | True | True | True | 2026-05-29 |
| 2026-06-05 | True | True | True | 2026-06-05 |
| 2026-06-12 | True | True | True | 2026-06-12 |
| 2026-06-18 | True | True | True | 2026-06-18 |
| 2026-06-26 | True | True | True | 2026-06-26 |
| 2026-07-02 | True | True | True | 2026-07-02 |
| 2026-07-10 | True | True | True | 2026-07-10 |
| 2026-07-17 | True | True | True | 2026-07-17 |
| 2026-07-24 | True | True | True | 2026-07-24 |
| 2026-07-31 | True | True | True | 2026-07-31 |
| 2026-08-07 | True | True | True | 2026-08-07 |
| 2026-08-14 | True | True | True | 2026-08-14 |
| 2026-08-21 | True | True | True | 2026-08-21 |
| 2026-08-28 | True | True | True | 2026-08-28 |
| 2026-09-04 | True | True | True | 2026-09-04 |
| 2026-09-11 | True | True | True | 2026-09-11 |
| 2026-09-18 | True | True | True | 2026-09-18 |
| 2026-09-25 | True | True | True | 2026-09-25 |
| 2026-10-02 | True | True | True | 2026-10-02 |
| 2026-10-09 | True | True | True | 2026-10-09 |
| 2026-10-16 | True | True | True | 2026-10-16 |
