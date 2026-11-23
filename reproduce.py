import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = (
    "run_calibrated_study.py",
    "analyze_calibrated_study.py",
    "run_periodic_study.py",
    "analyze_periodic_study.py",
    "check_current_feasibility.py",
    "check_feasibility_certificates.py",
    "run_batch5_sensitivity.py",
)


def run(script):
    subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT, check=True)


def main():
    for script in STEPS:
        run(script)
    expected = json.loads((ROOT / "paper_output_hashes.json").read_text())
    for name, digest in expected.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Results differ from the saved paper output in {name}")
    print(f"Verified {len(expected)} numerical output files.", flush=True)
    run("plot_periodic_paper.py")
    run("website/build_site.py")


if __name__ == "__main__":
    main()

