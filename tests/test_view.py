"""The joining rules on a tiny hand-made set of records."""
import pandas as pd

from ael import view

RULES = dict(view.RULES, window_start="2023-01", window_end="2023-12")


def roster_row(month, pid, title, center="C001", branch="B01", region="R01", join="2022-01-01"):
    return (month, pid, title, center, branch, region, join, "Contract")


def tables(roster, kpi=None, resignations=None):
    cols = ["month", "employee_id", "job_title", "center_code", "branch_code", "region", "join_date", "employment_type"]
    r = pd.DataFrame(roster, columns=cols)
    if kpi is None:
        kpi = [(m, p, "100.0", "B", "None") for m, p, *_ in roster]
    k = pd.DataFrame(kpi, columns=["month", "employee_id", "kpi_achievement_pct", "kpi_rating", "warning_stage"])
    res = pd.DataFrame(resignations or [], columns=["employee_id", "job_title", "exit_date", "center_code", "branch_code", "region", "exit_type", "recorded_date"])
    empty = pd.DataFrame(columns=["employee_id", "join_date", "probation_result"])
    forms = pd.DataFrame(columns=["submitted_date", "employee_id", "exit_date", "reason", "would_return"])
    return {"roster_monthly": r, "kpi_monthly": k, "probation": empty, "resignations": res, "exit_interviews": forms}


def test_gone_next_month_counts_as_exit_and_last_month_is_not_scored():
    roster = [roster_row("2023-01", "E000001", "Team Leader"),
              roster_row("2023-02", "E000001", "Team Leader"),
              roster_row("2023-01", "E000002", "Sales Officer"),
              roster_row("2023-01", "E000003", "Sales Officer"),
              roster_row("2023-02", "E000003", "Sales Officer")]
    res = [("E000002", "Sales Officer", "2023-01-20", "C001", "B01", "R01", "Resign", "2023-01-25")]
    s, _, _ = view.seller_months(tables(roster, resignations=res), RULES)
    assert s.loc[s.employee_id == "E000002", "left"].tolist() == [1]
    assert s.loc[s.employee_id == "E000003", "left"].tolist() == [0]
    assert "2023-02" not in s["month"].tolist()


def test_promotion_is_not_an_exit():
    roster = [roster_row("2023-01", "E000009", "Team Leader", center="C002"),
              roster_row("2023-01", "E000004", "Sales Officer"),
              roster_row("2023-02", "E000004", "Team Leader"),
              roster_row("2023-02", "E000009", "Team Leader", center="C002"),
              roster_row("2023-03", "E000004", "Team Leader")]
    s, _, _ = view.seller_months(tables(roster), RULES)
    assert s.loc[s.employee_id == "E000004", "left"].tolist() == [0]


def test_leader_comes_from_same_center_and_route_from_history():
    months = [f"2023-{m:02d}" for m in range(1, 9)]
    roster = []
    kpi = []
    for i, m in enumerate(months):
        if i < 6:
            # E000005 is the best seller in the branch for six months, then becomes leader of C001.
            roster.append(roster_row(m, "E000005", "Sales Officer", center="C002"))
            kpi.append((m, "E000005", "180.0", "A", "None"))
            for j in range(6, 11):
                roster.append(roster_row(m, f"E00000{j}" if j < 10 else "E000010", "Sales Officer", center="C002"))
                kpi.append((m, f"E00000{j}" if j < 10 else "E000010", "90.0", "C", "None"))
        else:
            roster.append(roster_row(m, "E000005", "Team Leader", center="C001"))
            kpi.append((m, "E000005", "100.0", "B", "None"))
        roster.append(roster_row(m, "E000011", "Sales Officer", center="C001"))
        kpi.append((m, "E000011", "100.0", "B", "None"))
    s, routes, _ = view.seller_months(tables(roster, kpi), RULES)
    assert routes.set_index("leader_id").loc["E000005", "route"] == "top seller"
    row = s[(s.employee_id == "E000011") & (s.month == "2023-07")].iloc[0]
    assert row.leader_id == "E000005" and row.route == "top seller"
    early = s[(s.employee_id == "E000011") & (s.month == "2023-01")].iloc[0]
    assert early.route == "no leader"


def test_missing_resignation_records_mark_region_month_incomplete():
    roster = [roster_row("2023-01", f"E00010{i}", "Sales Officer") for i in range(4)]
    roster.append(roster_row("2023-02", "E000200", "Sales Officer"))
    res = [("E000100", "Sales Officer", "2023-01-10", "C001", "B01", "R01", "Resign", "2023-01-12")]
    s, _, gap = view.seller_months(tables(roster, resignations=res), RULES)
    g = gap.set_index(["region", "month"]).loc[("R01", "2023-01")]
    assert g.roster_exits == 4 and g.unrecorded == 3 and bool(g.incomplete)
    assert s.loc[s.month == "2023-01", "incomplete"].all()
