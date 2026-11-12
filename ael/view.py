"""Join the five record files into one seller-month view.

One row per sales officer per month in the analysis window, with:
- whether they left that month (from the roster, checked against the resignation list)
- their team leader that month (the team leader on the same center code)
- that leader's promotion route, read from the leader's own job-title history
- tenure, team size, branch, region, KPI and warning stage

No file links a seller to a leader directly, and none records promotions. Both
are rebuilt here. DECISIONS.md explains each rule.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RULES = {
    "window_start": "2022-01",
    "window_end": "2023-12",
    "top_seller_share": 0.20,     # top fifth of the branch's sellers before promotion
    "pre_promotion_months": 6,    # KPI months averaged before the title change
    "late_gap_share": 0.25,       # region-month is incomplete if this share of roster exits has no record
}


def load(dir_: Path) -> dict[str, pd.DataFrame]:
    names = ["roster_monthly", "kpi_monthly", "probation", "resignations", "exit_interviews"]
    return {n: pd.read_csv(dir_ / f"{n}.csv", dtype=str, keep_default_na=False, na_values=[""]) for n in names}


def leader_routes(roster: pd.DataFrame, kpi: pd.DataFrame, rules: dict = RULES) -> pd.DataFrame:
    """One row per team leader: route = top seller, average seller, or unknown.

    A leader's route is known only when the roster shows them as a Sales Officer
    before their first month as Team Leader. Their mean KPI over the months before
    the change is ranked against the other sellers in the same branch in the
    same months. Leaders already in post when the files start are "unknown".
    """
    r = roster.merge(kpi, on=["month", "employee_id"], how="left")
    r["kpi"] = r["kpi_achievement_pct"].astype(float)
    leaders = r[r["job_title"] == "Team Leader"].groupby("employee_id")["month"].min().rename("first_tl_month")
    first_month = roster["month"].min()
    rows = []
    sellers = r[r["job_title"] == "Sales Officer"]
    for pid, m0 in leaders.items():
        hist = sellers[(sellers["employee_id"] == pid) & (sellers["month"] < m0)].sort_values("month")
        if m0 == first_month or hist.empty:
            rows.append((pid, m0, "unknown", np.nan, np.nan))
            continue
        hist = hist.tail(rules["pre_promotion_months"])
        months = hist["month"].tolist()
        branch = hist["branch_code"].iloc[-1]
        peers = sellers[(sellers["branch_code"] == branch) & (sellers["month"].isin(months))]
        peer_mean = peers.groupby("employee_id")["kpi"].mean()
        own = hist["kpi"].mean()
        pct = float((peer_mean < own).mean())
        route = "top seller" if pct >= 1 - rules["top_seller_share"] else "average seller"
        rows.append((pid, m0, route, round(own, 1), round(pct, 3)))
    return pd.DataFrame(rows, columns=["leader_id", "first_tl_month", "route", "pre_kpi", "pre_kpi_pct"])


def seller_months(t: dict[str, pd.DataFrame], rules: dict = RULES) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    roster, kpi = t["roster_monthly"], t["kpi_monthly"]
    months = sorted(roster["month"].unique())
    nxt = dict(zip(months[:-1], months[1:]))

    # Who is on the roster the following month. Gone next month = left this month.
    present = set(zip(roster["month"], roster["employee_id"]))
    r = roster.copy()
    r["next_month"] = r["month"].map(nxt)
    r["left"] = [(nm is not None and isinstance(nm, str) and (nm, pid) not in present) for nm, pid in zip(r["next_month"], r["employee_id"])]
    # A promoted seller is still on the roster as Team Leader, so promotion is never counted as an exit.
    r = r[r["next_month"].notna()]

    leaders = r[r["job_title"] == "Team Leader"][["month", "center_code", "employee_id"]].rename(columns={"employee_id": "leader_id"})
    leaders = leaders.drop_duplicates(["month", "center_code"])
    routes = leader_routes(roster, kpi, rules)

    s = r[r["job_title"] == "Sales Officer"].merge(kpi, on=["month", "employee_id"], how="left")
    s = s.merge(leaders, on=["month", "center_code"], how="left")
    s = s.merge(routes[["leader_id", "route"]], on="leader_id", how="left")
    s["route"] = s["route"].fillna("no leader")
    team = s.groupby(["month", "center_code"]).size().rename("team_size").reset_index()
    s = s.merge(team, on=["month", "center_code"], how="left")

    per = pd.PeriodIndex(s["month"], freq="M")
    joined = pd.PeriodIndex(pd.to_datetime(s["join_date"]).dt.to_period("M"), freq="M")
    s["tenure_months"] = (per - joined).map(lambda d: d.n) + 1
    s["tenure_band"] = pd.cut(s["tenure_months"], [0, 3, 6, 12, 24, 10_000], labels=["1-3", "4-6", "7-12", "13-24", "25+"]).astype(str)
    s["team_size_band"] = pd.cut(s["team_size"], [0, 8, 10, 100], labels=["8 or fewer", "9-10", "11+"]).astype(str)

    # Exit type and record check against the resignation list.
    res = t["resignations"].copy()
    res["month"] = pd.to_datetime(res["exit_date"]).dt.to_period("M").astype(str)
    res = res[["employee_id", "month", "exit_type"]]
    s = s.merge(res, on=["employee_id", "month"], how="left")
    s["recorded"] = s["exit_type"].notna()
    s.loc[s["left"] & ~s["recorded"], "exit_type"] = "Not on resignation list"

    # Region-months where many roster exits have no resignation record are marked incomplete.
    ex = s[s["left"]]
    gap = ex.groupby(["region", "month"]).agg(roster_exits=("left", "size"), unrecorded=("recorded", lambda x: int((~x).sum()))).reset_index()
    gap["unrecorded_share"] = (gap["unrecorded"] / gap["roster_exits"]).round(3)
    gap["incomplete"] = gap["unrecorded_share"] >= rules["late_gap_share"]
    s = s.merge(gap[["region", "month", "incomplete"]], on=["region", "month"], how="left")
    s["incomplete"] = s["incomplete"].eq(True)

    s = s[(s["month"] >= rules["window_start"]) & (s["month"] <= rules["window_end"])].copy()
    s["kpi_achievement_pct"] = s["kpi_achievement_pct"].astype(float)
    s["left"] = s["left"].astype(int)
    cols = ["month", "employee_id", "center_code", "branch_code", "region", "leader_id", "route", "team_size", "team_size_band",
            "tenure_months", "tenure_band", "kpi_achievement_pct", "kpi_rating", "warning_stage", "left", "exit_type", "recorded", "incomplete"]
    s = s[cols].sort_values(["month", "employee_id"]).reset_index(drop=True)
    gap = gap[(gap["month"] >= rules["window_start"]) & (gap["month"] <= rules["window_end"])].sort_values(["month", "region"]).reset_index(drop=True)
    return s, routes, gap
