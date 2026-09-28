#!/usr/bin/env python3
"""Run unchanged browser acceptance with allowlisted failure diagnostics."""
import json
from run_service_acceptance import main
from service_diagnostics import failure_report


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        report = failure_report(exc)
        print(json.dumps(report))
        raise SystemExit(78 if report["result"] == "BLOCKED" else 1) from None
