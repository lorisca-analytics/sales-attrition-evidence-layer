"""Answer one question from the joined view and write the findings file.

Do sales teams lose more people when their team leader was promoted as a top
seller, and does the gap survive once branch, tenure, team size and month are
accounted for?

Run: python -m ael.analyze   (reads data/synthetic, writes data/clean and dashboard/data)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from patsy import dmatrix

from ael import generate, view  # generate supplies PARAMS for the findings file

FINDINGS_VERSION = "1.0.0"

# Cost of an exit, counted in months of one seller's sales. Assumptions, shown on the dashboard.
COST = {"vacancy_months": 1.0, "ramp_months": 3, "ramp_output_share": 0.5}

KNOWN = ["average seller", "top seller"]


def per100(x: pd.Series) -> float:
    """Exits per 100 sellers per year, from a 0/1 seller-month column."""
    return round(float(x.mean()) * 1200, 1)


def controlled(s: pd.DataFrame, draws: int = 400, seed: int = 7) -> dict:
    """Logistic model on seller-months, standard errors clustered by team.

    The controlled rates are average predictions with every row given one route,
    then the other, holding branch, tenure, team size and month as they are.
    """
    d = s[s["route"].isin(KNOWN) & ~s["incomplete"]].copy()
    d["top"] = (d["route"] == "top seller").astype(int)
    f = "left ~ top + C(branch_code) + C(tenure_band) + C(team_size_band) + C(month)"
    m = smf.logit(f, d).fit(disp=0, maxiter=200, cov_type="cluster", cov_kwds={"groups": pd.factorize(d["center_code"])[0]})
    X1, X0 = d.assign(top=1), d.assign(top=0)
    p1, p0 = m.predict(X1).mean(), m.predict(X0).mean()
    rng = np.random.default_rng(seed)
    beta = rng.multivariate_normal(m.params.values, m.cov_params().values, size=draws)
    rhs = f.split("~", 1)[1]
    M1 = np.asarray(dmatrix(rhs, X1, return_type="dataframe")[m.params.index])
    M0 = np.asarray(dmatrix(rhs, X0, return_type="dataframe")[m.params.index])
    sim = []
    for b in beta:
        q1 = (1 / (1 + np.exp(-(M1 @ b)))).mean()
        q0 = (1 / (1 + np.exp(-(M0 @ b)))).mean()
        sim.append((q1 - q0) * 1200)
    lo, hi = np.percentile(sim, [2.5, 97.5])
    return {
        "rows": int(len(d)),
        "teams": int(d["center_code"].nunique()),
        "rate_top": round(p1 * 1200, 1),
        "rate_average": round(p0 * 1200, 1),
        "gap": round((p1 - p0) * 1200, 1),
        "gap_ci": [round(float(lo), 1), round(float(hi), 1)],
        "odds_ratio": round(float(np.exp(m.params["top"])), 2),
        "odds_ratio_ci": [round(float(np.exp(m.conf_int().loc["top", 0])), 2), round(float(np.exp(m.conf_int().loc["top", 1])), 2)],
    }


def survival(s: pd.DataFrame, horizon: int = 12) -> pd.DataFrame:
    """Kaplan-Meier: share of new hires still in post by month of tenure, by first leader's route."""
    first = s[s["tenure_months"] == 1][["employee_id", "route"]].rename(columns={"route": "first_route"})
    h = s.merge(first, on="employee_id")
    h = h[h["first_route"].isin(KNOWN)]
    rows = []
    for route, g in h.groupby("first_route"):
        last = g.sort_values("tenure_months").groupby("employee_id").agg(t=("tenure_months", "max"), event=("left", "max"))
        surv = 1.0
        rows.append((route, 0, 1.0, int(len(last))))
        for t in range(1, horizon + 1):
            at_risk = int((last["t"] >= t).sum())
            events = int(((last["t"] == t) & (last["event"] == 1)).sum())
            if at_risk:
                surv *= 1 - events / at_risk
            rows.append((route, t, round(surv, 4), at_risk))
    return pd.DataFrame(rows, columns=["route", "tenure_month", "still_in_post", "at_risk"])


def reasons(s: pd.DataFrame, forms: pd.DataFrame) -> pd.DataFrame:
    ex = s[s["left"] == 1][["employee_id", "route"]]
    f = forms.merge(ex, on="employee_id", how="inner")
    f = f[f["route"].isin(KNOWN)]
    out = f.groupby(["route", "reason"]).size().rename("forms").reset_index()
    out["share"] = (out["forms"] / out.groupby("route")["forms"].transform("sum")).round(3)
    return out.sort_values(["route", "forms"], ascending=[True, False]).reset_index(drop=True)


def raw_rates(s: pd.DataFrame) -> pd.DataFrame:
    d = s[~s["incomplete"]]
    out = d.groupby("route").agg(seller_months=("left", "size"), exits=("left", "sum")).reset_index()
    out["exits_per_100_per_year"] = (out["exits"] / out["seller_months"] * 1200).round(1)
    return out


def region_rates(s: pd.DataFrame) -> pd.DataFrame:
    d = s[~s["incomplete"]]
    out = d.groupby("region").agg(seller_months=("left", "size"), exits=("left", "sum")).reset_index()
    out["exits_per_100_per_year"] = (out["exits"] / out["seller_months"] * 1200).round(1)
    top = d.assign(top=d["route"].eq("top seller")).groupby("region")["top"].mean().round(3).rename("share_under_top_seller_leaders")
    return out.merge(top, on="region").sort_values("exits_per_100_per_year", ascending=False).reset_index(drop=True)


def branch_overlap(s: pd.DataFrame) -> dict:
    """Share of seller-months under top-seller leaders, in the 30% of branches with the most exits vs the rest."""
    d = s[~s["incomplete"]]
    b = d.groupby("branch_code").agg(rate=("left", "mean"), top=("route", lambda x: (x == "top seller").mean()))
    busy = b["rate"] > b["rate"].quantile(0.7)
    return {"top_share_high_exit_branches": round(float(b.loc[busy, "top"].mean()), 3),
            "top_share_other_branches": round(float(b.loc[~busy, "top"].mean()), 3)}


def cost(ctrl: dict, s: pd.DataFrame) -> dict:
    d = s[(s["route"] == "top seller") & ~s["incomplete"]]
    seller_years = len(d) / 12 / 2  # two years of seller-months, per year
    extra_exits = ctrl["gap"] / 100 * seller_years
    months_lost = COST["vacancy_months"] + COST["ramp_months"] * (1 - COST["ramp_output_share"])
    return {
        "assumptions": COST,
        "seller_years_under_top_seller_leaders_per_year": round(seller_years),
        "extra_exits_per_year": round(extra_exits),
        "sales_months_lost_per_exit": months_lost,
        "full_time_sellers_of_sales_lost_per_year": round(extra_exits * months_lost / 12),
    }


def sensitivity(t: dict, s: pd.DataFrame) -> list[dict]:
    out = []
    vol = s.copy()
    vol["left"] = ((vol["left"] == 1) & (vol["exit_type"] == "Resign")).astype(int)
    out.append({"check": "Voluntary resignations only", **pick(controlled(vol))})
    out.append({"check": "Leave out each seller's first 3 months", **pick(controlled(s[s["tenure_months"] > 3]))})
    rules = dict(view.RULES, top_seller_share=0.30)
    s30, _, _ = view.seller_months(t, rules)
    out.append({"check": "Top seller = top 30% instead of top 20%", **pick(controlled(s30))})
    return out


def pick(c: dict) -> dict:
    return {k: c[k] for k in ("rate_top", "rate_average", "gap", "gap_ci")}


def null_summary(path: Path = Path("docs/null_calibration.json")) -> dict | None:
    """Summary of scripts/null_calibration.py, if it has been run."""
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    out = {k: d[k] for k in ("runs", "leader_effect", "mean_gap", "intervals_including_zero")}
    out["misses_above_zero"] = sum(1 for r in d["detail"] if r["gap_ci"][0] > 0)
    out["misses_below_zero"] = sum(1 for r in d["detail"] if r["gap_ci"][1] < 0)
    return out


def run(src: Path) -> tuple[dict, dict[str, pd.DataFrame]]:
    t = view.load(src)
    s, routes, gap = view.seller_months(t)
    raw = raw_rates(s)
    ctrl = controlled(s)
    tables = {
        "seller_month": s,
        "leader_routes": routes,
        "record_gaps": gap,
        "route_rates": raw,
        "region_rates": region_rates(s),
        "survival": survival(s),
        "exit_reasons": reasons(s, t["exit_interviews"]),
    }
    rr = raw.set_index("route")["exits_per_100_per_year"]
    reasons_all = tables["exit_reasons"].groupby("reason")["forms"].sum()
    resign_exits = int(((s["left"] == 1) & (s["exit_type"] == "Resign") & s["route"].isin(KNOWN)).sum())
    findings = {
        "version": FINDINGS_VERSION,
        "synthetic": True,
        "params": {"leader_effect": generate.PARAMS["leader_effect"], "seed": generate.PARAMS["seed"]},
        "window": [view.RULES["window_start"], view.RULES["window_end"]],
        "size": {
            "seller_months": int(len(s)), "sellers": int(s["employee_id"].nunique()), "teams": int(s["center_code"].nunique()),
            "branches": int(s["branch_code"].nunique()), "regions": int(s["region"].nunique()),
            "exits": int(s["left"].sum()), "leaders_with_known_route": int(routes["route"].isin(KNOWN).sum()),
            "leaders_unknown_route": int((routes["route"] == "unknown").sum()),
            "seller_months_unknown_route_share": round(float((s["route"] == "unknown").mean()), 3),
            "seller_months_no_leader_share": round(float((s["route"] == "no leader").mean()), 3),
        },
        "overall_exits_per_100_per_year": per100(s[~s["incomplete"]]["left"]),
        "raw": {"rate_top": float(rr["top seller"]), "rate_average": float(rr["average seller"]),
                "rate_unknown": float(rr.get("unknown", np.nan)), "gap": round(float(rr["top seller"] - rr["average seller"]), 1)},
        "controlled": ctrl,
        "reasons": {
            "forms_matched": int(reasons_all.sum()),
            "resign_exits_known_route": resign_exits,
            "leadership_share": round(float(reasons_all.get("Leadership", 0) / reasons_all.sum()), 3),
            "top_reason": str(reasons_all.idxmax()),
        },
        "survival_6m": {r: float(tables["survival"].query("route == @r and tenure_month == 6")["still_in_post"].iloc[0]) for r in KNOWN},
        "survival_12m": {r: float(tables["survival"].query("route == @r and tenure_month == 12")["still_in_post"].iloc[0]) for r in KNOWN},
        "cost": cost(ctrl, s),
        "branch_overlap": branch_overlap(s),
        "checks": {
            "incomplete_region_months": gap[gap["incomplete"]][["region", "month", "roster_exits", "unrecorded"]].to_dict("records"),
            "roster_exits_without_record": int(((s["left"] == 1) & ~s["recorded"]).sum()),
        },
        "sensitivity": sensitivity(t, s),
    }
    findings["null_calibration"] = null_summary()
    return findings, tables


def main() -> None:
    findings, tables = run(Path("data/synthetic"))
    clean = Path("data/clean")
    clean.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(clean / f"{name}.csv", index=False, lineterminator="\n")
    dash = Path("dashboard/data")
    dash.mkdir(parents=True, exist_ok=True)
    for name in ("route_rates", "region_rates", "survival", "exit_reasons", "record_gaps"):
        tables[name].to_csv(dash / f"{name}.csv", index=False, lineterminator="\n")
    text = json.dumps(findings, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)) + "\n"
    (dash / "findings.json").write_text(text)
    Path("docs").mkdir(exist_ok=True)
    (Path("docs") / "findings.json").write_text(text)
    print(json.dumps({k: findings[k] for k in ("raw", "controlled", "reasons", "survival_12m", "cost")}, indent=1))
    print(json.dumps(findings["null_calibration"], indent=1))
    print(json.dumps(findings["sensitivity"], indent=1))


if __name__ == "__main__":
    main()
