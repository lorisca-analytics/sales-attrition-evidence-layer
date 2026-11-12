# Data contract, version 1.0.0

The five record files in `data/synthetic/` are the input to everything else. Their exact shape is in `contract/tables.v1.json`. `python -m ael.contract data/synthetic` checks every file against it, and CI runs that check on every push.

## The five files and who would own them

In a real company each file has a different owner and arrives on its own schedule. That is why they need a contract before they can be joined.

| File | One row per | Real-world owner | Refreshed |
|---|---|---|---|
| `roster_monthly` | person and month | HR operations (payroll roster) | monthly |
| `kpi_monthly` | person and month | sales performance team | monthly |
| `probation` | new hire, at the end of probation | recruiting and HR | when probation ends |
| `resignations` | person who left | HR operations, filed by branches | whenever someone files it |
| `exit_interviews` | exit form submitted | HR, filled in by the person leaving | when they fill it in, if they do |

## Rules

1. A column is never renamed or removed inside a major version. New columns go at the end of a file and bump the minor version (1.1.0).
2. A breaking change gets a new file (`tables.v2.json`) and a new major version. The old one stays until nothing reads it.
3. `employee_id` is the key across files. `center_code` links a seller to their team leader. Both are pseudonymous codes.
4. Months are `yyyy-mm`. Dates are `yyyy-mm-dd`.
5. Warning stages are a shortened version of the bank's escalation ladder: PIP1, PIP2, then warning letters SP1, SP2, SP3. A seller past SP3 is dismissed.
6. The resignation list may run late. A missing row is a data gap, not a person staying (DECISIONS.md, decision 5).

## What the checker refuses

- A missing file, a missing column, a renamed column, or columns in a different order
- A value of the wrong type, outside its allowed list, or not matching its pattern
- A duplicate key
- A resignation recorded before the exit date
- A KPI row, resignation or exit form for someone who never appears on the roster

## Outputs

`python -m ael.analyze` writes the joined view and the result tables to `data/clean/` and the files the dashboard reads to `dashboard/data/`. `findings.json` carries a `version` field. The dashboard reads only that file and the small CSV tables next to it.
