from pathlib import Path

import pandas as pd

from ael import contract

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic"


def test_committed_files_pass():
    assert contract.check(DATA) == []


def copy_with(tmp_path, name, edit):
    for f in DATA.glob("*.csv"):
        df = pd.read_csv(f, dtype=str, keep_default_na=False, na_values=[""])
        if f.stem == name:
            df = edit(df)
        df.to_csv(tmp_path / f.name, index=False)
    return contract.check(tmp_path)


def test_unknown_warning_stage_fails(tmp_path):
    def edit(df):
        df.loc[0, "warning_stage"] = "SP4"
        return df
    problems = copy_with(tmp_path, "kpi_monthly", edit)
    assert any("kpi_monthly.warning_stage" in p for p in problems)


def test_duplicate_key_fails(tmp_path):
    problems = copy_with(tmp_path, "roster_monthly", lambda df: pd.concat([df, df.head(1)]))
    assert any("duplicate keys" in p for p in problems)


def test_record_before_exit_fails(tmp_path):
    def edit(df):
        df.loc[0, "recorded_date"] = "2000-01-01"
        return df
    problems = copy_with(tmp_path, "resignations", edit)
    assert any("earlier than exit_date" in p for p in problems)


def test_renamed_column_fails(tmp_path):
    problems = copy_with(tmp_path, "probation", lambda df: df.rename(columns={"probation_result": "result"}))
    assert any("do not match contract" in p for p in problems)


def test_orphan_resignation_fails(tmp_path):
    def edit(df):
        df.loc[0, "employee_id"] = "E999999"
        return df
    problems = copy_with(tmp_path, "resignations", edit)
    assert any("resignations -> roster_monthly" in p for p in problems)
