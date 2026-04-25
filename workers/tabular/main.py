"""CLI entry: ``python -m workers.tabular.main`` (expects ``JOB_ID`` in the environment)."""

import argparse
import os
import sys

from workers.tabular.worker import run_tabular_job


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the tabular MinIO job worker")
    _ = parser.add_argument("--job-id", default=os.environ.get("JOB_ID"))
    args = parser.parse_args()
    if not args.job_id:
        print("ERROR: JOB_ID (or --job-id) is required", file=sys.stderr)
        raise SystemExit(1)
    run_tabular_job(str(args.job_id))


if __name__ == "__main__":
    main()
