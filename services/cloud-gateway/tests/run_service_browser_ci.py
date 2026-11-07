#!/usr/bin/env python3
"""Run unchanged browser acceptance with allowlisted failure diagnostics."""
import json
import sys
from run_service_acceptance import main
from service_diagnostics import ci_exception_summary, failure_report


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        report = failure_report(exc)
        print(json.dumps(report))
        summary = ci_exception_summary(exc)
        if summary:
            print(summary, file=sys.stderr)
        raise SystemExit(78 if report["result"] == "BLOCKED" else 1) from None
