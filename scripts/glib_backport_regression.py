#!/usr/bin/env python3
"""Reproduce five optimized upstream SIGSEGVs and nine fixed tests on Linux.

Both builds use the same committed regression lock and source. Only the glib path
differs: checksum-pinned original archive versus verified exact backport. This is
an isolated dependency test, not a desktop application build or release gate.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import signal
import subprocess
import tempfile

import verify_glib_backport as gate

CASES = ("next", "nth", "last", "next_back", "nth_back")


def command(args, cwd, output, label):
    result = subprocess.run(args, cwd=cwd, capture_output=True, check=False)
    (output / (label + ".stdout")).write_bytes(result.stdout)
    (output / (label + ".stderr")).write_bytes(result.stderr)
    return result


def build(fixture, dependency, suite, output):
    suite.mkdir()
    (suite / "src").mkdir()
    shutil.copyfile(fixture / "src/lib.rs", suite / "src/lib.rs")
    shutil.copyfile(fixture / "Cargo.lock", suite / "Cargo.lock")
    (suite / "Cargo.toml").write_text(
        '[package]\nname="issue85-glib-regression"\nversion="0.0.0"\nedition="2021"\npublish=false\n'
        '[workspace]\n[dependencies]\nglib="=0.18.5"\n[patch.crates-io]\nglib={path=' + json.dumps(str(dependency)) + '}\n'
        '[profile.release]\ndebug=0\nincremental=false\n')
    args = ["cargo", "test", "--release", "--locked", "--no-run", "--message-format=json", "--manifest-path", str(suite / "Cargo.toml")]
    # Match the cwd whose Cargo config ancestry was checked before the build.
    result = command(args, fixture.parents[1], output, suite.name + "-build")
    gate.need(result.returncode == 0, suite.name + "_build_failed_not_a_runtime_negative")
    events = [gate.decode(line) for line in result.stdout.splitlines() if line]
    gate.need(events[-1] == {"reason": "build-finished", "success": True}, "incomplete_regression_build")
    artifacts = [event for event in events if event.get("reason") == "compiler-artifact"]
    glib = [event for event in artifacts if event["target"]["name"] == "glib"]
    gate.need(len(glib) == 1 and glib[0]["manifest_path"] == str(dependency / "Cargo.toml") and
              glib[0]["profile"]["opt_level"] == "3" and glib[0]["profile"]["debug_assertions"] is False,
              "wrong_glib_build")
    tests = [event for event in artifacts if event.get("executable") and event["profile"]["test"]]
    gate.need(len(tests) == 1, "wrong_regression_test_binary")
    binary = Path(tests[0]["executable"])
    return binary, {"command": args, "binary_sha256": gate.sha(gate.read(binary)),
                    "glib_package_id": glib[0]["package_id"], "glib_features": glib[0]["features"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    gate.need(platform.system() == "Linux", "negative_control_requires_linux_sigsegv")
    gate.need(not output.exists() and not output.is_relative_to(root), "output_must_be_new_and_external")
    gate.verify_configuration(root, os.environ)
    source = gate.verify_source(root, args.archive)
    output.mkdir(parents=True)
    versions = {}
    for tool in ("rustc", "cargo"):
        result = command([tool, "--version"], root, output, tool)
        gate.need(result.returncode == 0 and result.stdout.decode().startswith(tool + " 1.98.1 "), "wrong_regression_toolchain")
        versions[tool] = result.stdout.decode().strip()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    fixture = root / "tests/glib-variant-regression"
    with tempfile.TemporaryDirectory(prefix="glib-backport-control-") as temp:
        work = Path(temp)
        upstream = work / "glib-0.18.5"
        for name, data in gate.upstream_files(args.archive).items():
            path = upstream / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        red, red_build = build(fixture, upstream, work / "upstream", output)
        red_results = []
        for case in CASES:
            result = command([str(red), "--exact", "tests::" + case, "--nocapture"], work, output, "upstream-" + case)
            red_results.append({"test": case, "exit": result.returncode})
        # Write all outcomes before asserting, so unexpected controls are retained.
        (output / "upstream-results.json").write_text(json.dumps(red_results, indent=2) + "\n")
        gate.need(all(r["exit"] == -signal.SIGSEGV for r in red_results), "upstream_negative_not_reproduced")
        green, green_build = build(fixture, root / gate.VENDOR, work / "patched", output)
        listing = command([str(green), "--list"], work, output, "patched-list")
        gate.need(listing.returncode == 0 and listing.stdout.decode().count(": test\n") == 9, "wrong_regression_test_count")
        result = command([str(green), "--nocapture"], work, output, "patched-tests")
        gate.need(result.returncode == 0 and "9 passed; 0 failed; 0 ignored" in result.stdout.decode(), "patched_regression_failed")
        gate.need(red_build["glib_features"] == green_build["glib_features"], "regression_feature_disagreement")
        report = {"toolchain": versions, "source": source, "test_source_sha256": gate.sha(gate.read(fixture / "src/lib.rs")),
                  "regression_lock_sha256": gate.sha(gate.read(fixture / "Cargo.lock")), "upstream_build": red_build,
                  "upstream_results": red_results, "patched_build": green_build, "patched_tests_passed": 9,
                  "scope": "standalone_optimized_glib_regression_not_product_build", "release_approved": False}
        (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (gate.VerificationError, ValueError, KeyError, TypeError, OSError) as exc:
        raise SystemExit("FAIL: " + str(exc))
