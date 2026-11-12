# Decisions

Each entry: what I had to choose, the options, what I picked, and what it cost.

## 1. Data: synthetic, built to the shape of the real records

- **Options:** (a) the real records with names removed, (b) a public HR dataset, (c) synthetic records modeled on the layout of the real files.
- **Picked:** (c).
- **Why:** The real exit, warning-letter and probation files hold personal data, so (a) is out even with names removed. Branch, join date and exit date together still point at a person. Public HR datasets don't have the piece that mattered here: a monthly roster where a seller's job title changes to team leader. So I wrote a generator that produces five files modeled on the layout of the bank's files (monthly roster, monthly KPI and warning stage, probation tracker, resignation list, exit form), simplified to the columns the analysis needs, with the same kinds of gaps.
- **Gave up:** a result about a real company. The team leader effect is a setting in `ael/generate.py`, so this repo cannot discover it. What it can show is the method, whether the method finds an effect that is there (`tests/test_generate.py`), and whether it stays quiet when there is none (decision 8).

## 2. A seller's leader comes from the center code

- **Options:** (a) ask managers for a reporting-line list, (b) use the branch, (c) use the center code that seller and leader rows both carry.
- **Picked:** (c). In each month, a seller's leader is the Team Leader on the same center code.
- **Why:** No file has a "reports to" column. A branch has several teams, so (b) would blur good and bad leaders together. A list from managers (a) would be a one-off snapshot, and it would come from the people being measured.
- **Gave up:** sellers in a month when their center has no leader (a seat left empty after a leader quits) get no route. They show as "no leader" and are left out of the comparison.

## 3. Promotion route comes from job-title history

- **Options:** (a) a promotion register, (b) leaders' own account of how they were picked, (c) the roster: a person who is a Sales Officer one month and a Team Leader the next was promoted, and their KPI before the change says what kind of seller they were.
- **Picked:** (c). A leader's route is "top seller" when their average KPI over the 6 months before the change is in the top fifth of the sellers in their branch over the same months. Otherwise "average seller".
- **Why:** No file records promotions. The roster does, indirectly, every month.
- **Gave up:** leaders already in post when the records start, and leaders hired from outside, have no seller history to read. They are "unknown" and left out of the comparison: 361 of the 875 leaders in the files, and 31% of seller-months in the analysis window. The cutoff is a judgment call. At the top 30% the result barely moves (see the sensitivity table).

## 4. An exit is someone missing from next month's roster

- **Options:** (a) count rows on the resignation list, (b) count people who drop off the roster.
- **Picked:** (b), with the resignation list used for the exit type and as a check.
- **Why:** The resignation list depends on someone filing each exit on time. The roster is rebuilt every month for payroll. A promoted seller stays on the roster under a new title, so a promotion is never counted as an exit.
- **Gave up:** the last month in the files can't be scored, because there is no next month to look at. The files run one month past the analysis window for that reason.

## 5. A month with missing resignation rows is held out, not trusted

- **Options:** (a) trust the resignation list, (b) trust the roster and ignore the list, (c) compare them and hold out region-months where they disagree.
- **Picked:** (c). A region-month is held out when a quarter or more of the people who left the roster have no resignation row yet.
- **Why:** In this data one region's list runs about two to three months late at the end of the period. Option (a) would read that region's last months as people staying.
- **Gave up:** a held-out region-month leaves the rates entirely. One region-month is held out here.

## 6. Controls: branch, tenure, team size and month. Not KPI.

- **Options:** compare raw rates, or adjust for things that differ between teams.
- **Picked:** a logistic model on seller-months with branch, tenure band, team size band and month, standard errors clustered by team. The controlled rates are the model's average prediction with every seller-month given one route, then the other.
- **Why:** Busy branches lose more people for everyone, and they promote top sellers more often. Without branch in the model, part of the branch effect lands on the leaders. KPI and warning stage stay out on purpose: a poor leader can push a seller's KPI down before they quit, so adjusting for KPI would hide part of the leader's effect. Clustering by team, because sellers on one team share a leader and are not independent rows.
- **Gave up:** a single number for "the leader effect" that ignores the other causes. The raw gap is shown next to the controlled one, so a reader sees how much the controls take out.

## 7. All exits in the main result, resignations alone as a check

- **Options:** count every exit, or only resignations.
- **Picked:** every exit (resignations, failed probation and dismissal after the last warning letter) in the main result. Resignations alone in the sensitivity table.
- **Why:** A team that loses people, for any reason, has to rehire and retrain. The business cost is the same.
- **Gave up:** a cleaner reading of "people who chose to leave". The check shows the gap is the same size either way.

## 8. One no-effect run proves little, so I ran twenty

- **Options:** (a) one run with the effect switched off, (b) many.
- **Picked:** (b). `scripts/null_calibration.py` generates 20 datasets with no leader effect and runs the same steps on each.
- **Why:** My first version ran the no-effect data once. Its 95% interval missed zero, a gap of 4.7 with an interval of 0.4 to 8.9. A fair method should miss in about 1 run of 20, so one miss could be chance or a leak in the method. I checked three more seeds (odds ratios 0.89, 1.05 and 0.95, scattered around no effect), then made the 20-run version the standing check. I did not pick a seed that happens to pass. Result (`docs/null_calibration.json`): an average gap of -0.4 exits per 100 a year, 18 of 20 intervals include zero, and the two misses fall on opposite sides (+4.3 and -4.9).
- **Gave up:** about 10 minutes of compute each time the calibration is rerun. It runs on demand, not in CI.

## 9. Cost counted in sales months, not money

- **Options:** a currency figure, or months of one seller's sales.
- **Picked:** months of sales. Each extra exit costs 1 month with the seat empty plus 3 months at half output while the new hire ramps up, 2.5 months in all.
- **Why:** Leadership's objection was "we can't slow down sales". Sales months answer that objection in its own terms, and they don't need salary or commission figures I don't have.
- **Gave up:** a currency figure a finance team could drop into a budget. The three assumptions sit in `ael/analyze.py` (`COST`) for anyone who has better ones.

## 10. No score for individual people

- **Options:** add a model that gives each seller a flight-risk score, or stop at teams and leaders.
- **Picked:** stop at teams and leaders.
- **Why:** The fix that worked was a change to how leaders are picked and trained. A per-person score would point managers at individual sellers, which is the opposite of the finding, and it invites misuse.
- **Gave up:** a list of "who is about to leave". I wouldn't build that on these records.
