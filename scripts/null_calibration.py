"""Run the full pipeline on many datasets generated with NO team leader effect.

A sound method should report a gap near zero, with the 95% interval missing zero
in about 1 run in 20. One null run can miss by chance, so one run proves little.
Writes docs/null_calibration.json.

Run: python scripts/null_calibration.py [runs]
"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ael import analyze, generate, view  # noqa: E402


def one(seed: int) -> dict:
    t = generate.generate(leader_effect=1.0, seed=seed)
    s, _, _ = view.seller_months(t)
    c = analyze.controlled(s, draws=300)
    return {"seed": seed, "gap": c["gap"], "gap_ci": c["gap_ci"], "includes_zero": c["gap_ci"][0] <= 0 <= c["gap_ci"][1]}


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    with ProcessPoolExecutor() as ex:
        runs = list(ex.map(one, range(1001, 1001 + n)))
    out = {
        "runs": n,
        "leader_effect": 1.0,
        "mean_gap": round(sum(r["gap"] for r in runs) / n, 1),
        "intervals_including_zero": sum(r["includes_zero"] for r in runs),
        "detail": runs,
    }
    Path("docs").mkdir(exist_ok=True)
    Path("docs/null_calibration.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "detail"}))


if __name__ == "__main__":
    main()
