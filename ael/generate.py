"""Write the five synthetic HR record files.

The files are modeled on the layout of a bank's HR records (a monthly roster,
monthly KPI and warning stage, a probation tracker, a resignation list and an
exit interview form), simplified to the columns the analysis needs. Every
value is made up. The size of the team leader
effect is a setting here, so the analysis cannot "discover" anything this file
did not put in. What the analysis can show is whether the method finds the
effect, and whether it stays quiet when the effect is switched off.

Run: python -m ael.generate [--leader-effect 1.5] [--out data/synthetic]
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# Every assumption lives here so DECISIONS.md and the README can point at one place.
PARAMS = {
    "seed": 20231,
    "start": "2020-01",          # roster history starts here
    "months": 49,                # 2020-01 to 2024-01. Analysis uses 2022-01 to 2023-12
    "snapshot_date": "2024-02-10",  # the day the files were "exported"
    "regions": 9,
    "branches": 60,
    "centers": 300,              # one center = one sales team = one team leader
    "team_size": (8, 12),
    "busy_branch_share": 0.30,   # big-city branches with higher churn for everyone
    "busy_branch_factor": 1.35,
    "base_monthly_exit": 0.030,  # voluntary exit chance per month for an experienced seller
    "early_tenure_factor": {1: 1.9, 2: 1.8, 3: 1.6, 4: 1.4, 5: 1.25, 6: 1.15},
    "leader_effect": 1.5,        # exit chance multiplier under a team leader promoted as a top seller
    "top_seller_promotion_share": {"busy": 0.85, "quiet": 0.60},  # how often the old rule picked a top seller
    "top_seller_busy_branch_bias": 0.85,  # initial leaders in busy branches: share who were top sellers
    "top_seller_quiet_branch_bias": 0.55,
    "leader_monthly_exit": 0.035,
    "transfer_monthly": 0.0025,
    "form_submission_rate": 0.45,
    "late_region": "R07",        # one region's resignation list runs late at the end
    "late_lag_days": (60, 95),
    "normal_lag_days": (0, 25),
}

REASONS = ["Personal growth", "Career path", "Unsupportive scope of work", "Leadership"]
REASON_P_AVERAGE = [0.38, 0.33, 0.20, 0.09]
REASON_P_TOP = [0.36, 0.32, 0.20, 0.12]
STAGES = ["None", "PIP1", "PIP2", "SP1", "SP2", "SP3"]


@dataclass
class Person:
    pid: str
    title: str
    center: int
    join: int                 # month index
    skill: float
    top_seller_leader: bool = False   # truth for leaders, never written to a file
    kpi_history: list = field(default_factory=list)
    stage: int = 0
    low_months: int = 0


def month_label(start: pd.Period, i: int) -> str:
    return str(start + i)


def generate(leader_effect: float | None = None, seed: int | None = None, centers: int | None = None) -> dict[str, pd.DataFrame]:
    p = dict(PARAMS)
    if leader_effect is not None:
        p["leader_effect"] = leader_effect
    if seed is not None:
        p["seed"] = seed
    if centers is not None:
        p["centers"] = centers
        p["branches"] = max(9, centers // 5)
    rng = np.random.default_rng(p["seed"])
    start = pd.Period(p["start"], freq="M")
    n_months = p["months"]

    regions = [f"R{i + 1:02d}" for i in range(p["regions"])]
    branch_region = {b: regions[b % len(regions)] for b in range(p["branches"])}
    busy = set(rng.choice(p["branches"], int(p["branches"] * p["busy_branch_share"]), replace=False).tolist())
    branch_factor = {b: rng.lognormal(0, 0.12) * (p["busy_branch_factor"] if b in busy else 1.0) for b in range(p["branches"])}
    center_branch = {c: c % p["branches"] for c in range(p["centers"])}
    target = {c: int(rng.integers(p["team_size"][0], p["team_size"][1] + 1)) for c in range(p["centers"])}

    counter = iter(range(100000, 999999))

    def new_id() -> str:
        return f"E{next(counter)}"

    people: dict[str, Person] = {}
    leader_of: dict[int, str] = {}

    # Starting state: everyone already in post. Leaders promoted before the data starts.
    for c in range(p["centers"]):
        b = center_branch[c]
        bias = p["top_seller_busy_branch_bias"] if b in busy else p["top_seller_quiet_branch_bias"]
        tl = Person(new_id(), "Team Leader", c, -int(rng.integers(6, 60)), rng.normal(0.15, 0.1), bool(rng.random() < bias))
        people[tl.pid] = tl
        leader_of[c] = tl.pid
        for _ in range(target[c]):
            s = Person(new_id(), "Sales Officer", c, -int(rng.integers(1, 40)), rng.normal(0, 0.15))
            people[s.pid] = s

    roster, kpi, probation, exits, forms = [], [], [], [], []
    snapshot = pd.Timestamp(p["snapshot_date"])

    def exit_date(m: int) -> pd.Timestamp:
        per = start + m
        return per.start_time + pd.Timedelta(days=int(rng.integers(0, per.days_in_month)))

    for m in range(n_months):
        label = month_label(start, m)
        active = [x for x in people.values()]
        leaving: list[tuple[Person, str]] = []

        for x in active:
            b = center_branch[x.center]
            roster.append((label, x.pid, x.title, f"C{x.center:03d}", f"B{b:02d}", branch_region[b],
                           str((start + x.join).start_time.date()) if x.join >= 0 else str((start + x.join).start_time.date()),
                           "Contract" if (m - x.join) < 12 else "Permanent"))
            tenure = m - x.join + 1
            ramp = min(1.0, 0.45 + 0.18 * tenure)
            ach = float(np.clip(100 * (0.95 + x.skill) * ramp + rng.normal(0, 12), 5, 250))
            x.kpi_history.append(ach)
            if ach < 70:
                x.low_months += 1
            elif ach >= 85:
                x.low_months = 0
                x.stage = max(0, x.stage - 1)
            if x.low_months >= 2 and x.title == "Sales Officer" and tenure > 3:
                x.stage = min(len(STAGES), x.stage + 1)
                x.low_months = 0
            rating = "A" if ach >= 120 else "B" if ach >= 100 else "C" if ach >= 85 else "D" if ach >= 70 else "E"
            kpi.append((label, x.pid, round(ach, 1), rating, STAGES[min(x.stage, 5)]))

            if x.title == "Team Leader":
                if rng.random() < p["leader_monthly_exit"] * branch_factor[b]:
                    leaving.append((x, "Resign"))
                continue

            # Sales officer: involuntary exits first, then probation, then voluntary.
            if x.stage > 5:
                leaving.append((x, "Terminated after SP3"))
                continue
            if tenure == 3:
                passed = ach >= 60 or rng.random() < 0.5
                result = "Passed" if passed else "Failed & Resign"
                if passed and rng.random() < 0.06:
                    result = "Exception"
                probation.append((x.pid, str((start + x.join).start_time.date()), result))
                if result == "Failed & Resign":
                    leaving.append((x, "Failed probation"))
                    continue
            leader = people.get(leader_of.get(x.center, ""))
            hazard = p["base_monthly_exit"] * p["early_tenure_factor"].get(tenure, 1.0) * branch_factor[b]
            if leader is not None and leader.top_seller_leader:
                hazard *= p["leader_effect"]
            if rng.random() < min(hazard, 0.9):
                leaving.append((x, "Resign"))
            elif rng.random() < p["transfer_monthly"]:
                same_branch = [c for c in range(p["centers"]) if center_branch[c] == b and c != x.center]
                if same_branch:
                    x.center = int(rng.choice(same_branch))

        for x, kind in leaving:
            d = exit_date(m)
            b = center_branch[x.center]
            region = branch_region[b]
            late = region == p["late_region"] and m >= n_months - 3
            lag = rng.integers(*(p["late_lag_days"] if late else p["normal_lag_days"]))
            recorded = d + pd.Timedelta(days=int(lag))
            if recorded <= snapshot:
                exits.append((x.pid, x.title, str(d.date()), f"C{x.center:03d}", f"B{b:02d}", region, kind, str(recorded.date())))
            if kind == "Resign" and x.title == "Sales Officer" and rng.random() < p["form_submission_rate"]:
                leader = people.get(leader_of.get(x.center, ""))
                probs = REASON_P_TOP if (leader is not None and leader.top_seller_leader and p["leader_effect"] != 1.0) else REASON_P_AVERAGE
                reason = REASONS[int(rng.choice(len(REASONS), p=probs))]
                submitted = d + pd.Timedelta(days=int(rng.integers(-5, 10)))
                if submitted <= snapshot:
                    forms.append((str(submitted.date()), x.pid, str(d.date()), reason, "Yes" if rng.random() < 0.3 else "No"))
            del people[x.pid]
            if leader_of.get(x.center) == x.pid:
                del leader_of[x.center]

        # Fill empty leader seats by the old rule: usually the branch's best recent seller.
        for c in range(p["centers"]):
            if c in leader_of:
                continue
            b = center_branch[c]
            pool = [x for x in people.values() if x.title == "Sales Officer" and center_branch[x.center] == b and len(x.kpi_history) >= 6]
            if not pool:
                tl = Person(new_id(), "Team Leader", c, m + 1, rng.normal(0.1, 0.1), bool(rng.random() < 0.5))
                people[tl.pid] = tl
                leader_of[c] = tl.pid
                continue
            pool.sort(key=lambda x: np.mean(x.kpi_history[-6:]), reverse=True)
            cutoff = max(1, int(len(pool) * 0.2))
            if rng.random() < p["top_seller_promotion_share"]["busy" if b in busy else "quiet"]:
                pick = pool[int(rng.integers(0, cutoff))]
                top = True
            else:
                rest = pool[cutoff:] or pool
                pick = rest[int(rng.integers(0, len(rest)))]
                top = False
            pick.title = "Team Leader"
            pick.center = c
            pick.top_seller_leader = top
            pick.stage = 0
            leader_of[c] = pick.pid

        # Backfill sellers to each team's target size. New hires start next month.
        counts: dict[int, int] = {}
        for x in people.values():
            if x.title == "Sales Officer":
                counts[x.center] = counts.get(x.center, 0) + 1
        for c in range(p["centers"]):
            for _ in range(target[c] - counts.get(c, 0)):
                s = Person(new_id(), "Sales Officer", c, m + 1, rng.normal(0, 0.15))
                people[s.pid] = s

    out = {
        "roster_monthly": pd.DataFrame(roster, columns=["month", "employee_id", "job_title", "center_code", "branch_code", "region", "join_date", "employment_type"]),
        "kpi_monthly": pd.DataFrame(kpi, columns=["month", "employee_id", "kpi_achievement_pct", "kpi_rating", "warning_stage"]),
        "probation": pd.DataFrame(probation, columns=["employee_id", "join_date", "probation_result"]),
        "resignations": pd.DataFrame(exits, columns=["employee_id", "job_title", "exit_date", "center_code", "branch_code", "region", "exit_type", "recorded_date"]),
        "exit_interviews": pd.DataFrame(forms, columns=["submitted_date", "employee_id", "exit_date", "reason", "would_return"]),
    }
    # Records join at month level. Keep only probation rows whose join date is in the files' range.
    first = str(start.start_time.date())
    out["probation"] = out["probation"][out["probation"]["join_date"] >= first].reset_index(drop=True)
    return out


def write(tables: dict[str, pd.DataFrame], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False, lineterminator="\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--leader-effect", type=float, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", default="data/synthetic")
    a = ap.parse_args()
    tables = generate(a.leader_effect, a.seed)
    write(tables, Path(a.out))
    for name, df in tables.items():
        print(f"{name}: {len(df):,} rows")


if __name__ == "__main__":
    main()
