from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_step(name: str, command: list[str]) -> None:
    print(f"[verify] {name}: {' '.join(command)}")
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        print(f"[verify] FAILED: {name} (exit {result.returncode})")
        sys.exit(result.returncode)


def main() -> None:
    venv_python = Path(".venv") / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else sys.executable

    scenarios = ["baseline", "famine", "deficit", "warlord"]
    out_dir = Path("out")
    out_dir.mkdir(parents=True, exist_ok=True)

    for scenario in scenarios:
        out_path = out_dir / f"run_{scenario}.jsonl"
        if scenario == "baseline":
            out_path = out_dir / "run_baseline.jsonl"
        run_step(
            f"run_sim {scenario}",
            [
                python,
                "-m",
                "scripts.run_sim",
                "--turns",
                "120",
                "--seed",
                "42",
                "--scenario",
                scenario,
                "--out",
                str(out_path),
            ],
        )

    run_step(
        "sweep",
        [
            python,
            "-m",
            "scripts.sweep",
            "--turns",
            "120",
            "--seeds",
            "0",
            "99",
            "--out",
            "out/sweep_latest",
        ],
    )

    run_step(
        "demo_run",
        [
            python,
            "-m",
            "scripts.demo_run",
            "--scenario",
            "warlord",
            "--seed",
            "42",
            "--turns",
            "120",
            "--out",
            "out/demo_report.md",
        ],
    )

    run_step("pytest", [python, "-m", "pytest"])


if __name__ == "__main__":
    main()
