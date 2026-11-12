"""Check the record files against contract/tables.v1.json.

Run: python -m ael.contract data/synthetic   (exit code 1 and a list of problems on failure)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

CONTRACT = Path(__file__).resolve().parents[1] / "contract" / "tables.v1.json"


def check_table(name: str, df: pd.DataFrame, spec: dict) -> list[str]:
    problems = []
    want = list(spec["columns"])
    if list(df.columns) != want:
        return [f"{name}: columns {list(df.columns)} do not match contract {want}"]
    for col, rule in spec["columns"].items():
        v = df[col]
        if v.isna().any():
            problems.append(f"{name}.{col}: {int(v.isna().sum())} empty values")
            v = v.dropna()
        t = rule["type"]
        if t == "month":
            bad = ~v.str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])")
        elif t == "date":
            bad = pd.to_datetime(v, format="%Y-%m-%d", errors="coerce").isna()
        elif t == "number":
            num = pd.to_numeric(v, errors="coerce")
            bad = num.isna() | (num < rule.get("min", float("-inf"))) | (num > rule.get("max", float("inf")))
        else:
            bad = pd.Series(False, index=v.index)
            if "pattern" in rule:
                bad |= ~v.str.fullmatch(rule["pattern"].strip("^$"))
            if "allowed" in rule:
                bad |= ~v.isin(rule["allowed"])
        if bad.any():
            problems.append(f"{name}.{col}: {int(bad.sum())} values break the {t} rule, first: {v[bad].iloc[0]!r}")
        if "not_before" in rule:
            early = pd.to_datetime(df[col]) < pd.to_datetime(df[rule["not_before"]])
            if early.any():
                problems.append(f"{name}.{col}: {int(early.sum())} rows earlier than {rule['not_before']}")
    dup = df.duplicated(spec["key"])
    if dup.any():
        problems.append(f"{name}: {int(dup.sum())} duplicate keys on {spec['key']}")
    return problems


def check_links(tables: dict[str, pd.DataFrame], links: list[dict]) -> list[str]:
    problems = []
    for link in links:
        a, b = tables[link["from"]], tables[link.get("to_fallback", link["to"])]
        keys = link["on"]
        missing = ~a.set_index(keys).index.isin(b.set_index(keys).index)
        if missing.any():
            problems.append(f"{link['from']} -> {link['to']}: {int(missing.sum())} rows with no match ({link['rule']})")
    return problems


def check(dir_: Path) -> list[str]:
    contract = json.loads(CONTRACT.read_text())
    tables, problems = {}, []
    for name, spec in contract["tables"].items():
        f = dir_ / f"{name}.csv"
        if not f.exists():
            problems.append(f"{name}: file missing")
            continue
        tables[name] = pd.read_csv(f, dtype=str, keep_default_na=False, na_values=[""])
        problems += check_table(name, tables[name], spec)
    if len(tables) == len(contract["tables"]):
        problems += check_links(tables, contract["links"])
    return problems


def main() -> None:
    dir_ = Path(sys.argv[1] if len(sys.argv) > 1 else "data/synthetic")
    problems = check(dir_)
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    print(f"{dir_}: all files match contract version {json.loads(CONTRACT.read_text())['version']}")


if __name__ == "__main__":
    main()
