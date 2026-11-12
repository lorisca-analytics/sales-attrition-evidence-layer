# Evidence

How each claim in the README can be checked, and why each call was made.

## Two kinds of claim

1. **What happened at the bank** comes from my own record of the work, which holds personal data and stays private: the field sales team had the highest turnover, hiring was fixed first and turnover stayed high, top sellers promoted on sales alone led teams with higher attrition, leadership pushed back, and the fix split across hiring, promotion assessment and manager training. The result is stated once, as I cut department turnover about 15% (2023) and 17% (2024).
2. **Every number about the synthetic records** is recomputed by `python -m ael.analyze` into `docs/findings.json`.

## Synthetic numbers and where they live

| README claim | Key in docs/findings.json |
|---|---|
| 72,644 seller-months, 7,189 sellers, 300 teams, 60 branches, 9 regions | `size` |
| R01 81.2 and R04 54.2 exits per 100 a year | `data/clean/region_rates.csv` |
| 64% vs 40% of seller-months under top-seller leaders, high-exit branches vs the rest | `branch_overlap` |
| Planted effect 1.5x | `params.leader_effect` |
| Raw 78.9 and 49.4, gap 29.5 | `raw` |
| Controlled 76.5 and 53.1, gap 23.3, interval 18.3 to 29.2 | `controlled` |
| 361 of 875 leaders with no seller history | `size.leaders_unknown_route`, `size.leaders_with_known_route` |
| 1,262 forms, 2,804 resignations, "Leadership" 12%, personal growth on top | `reasons` |
| R07, 20 roster exits, none recorded | `checks.incomplete_region_months` |
| 23.2, 21.4 and 23.3 in the sensitivity checks | `sensitivity` |
| 40% and 52% still in post after 12 months | `survival_12m` |
| 331 extra exits, 69 sellers' full-year sales | `cost` |
| Null check: average gap -0.4, 18 of 20 intervals include zero | `null_calibration` (detail in `docs/null_calibration.json`) |
| First single null run: gap 4.7, interval 0.4 to 8.9 | recorded in DECISIONS.md, decision 8 (that version of the script was replaced) |
| File row counts | `wc -l data/synthetic/*.csv` minus the header |

## Why each call was made

`DECISIONS.md` has one entry per choice: synthetic data, the center-code link, reading promotion from the roster, counting exits from the roster, holding out late months, which controls go in and which stay out, all exits versus resignations, the 20-run null check, cost in sales months, and no per-person score.
