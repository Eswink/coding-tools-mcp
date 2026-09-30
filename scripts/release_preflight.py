"""Check version-matched release inputs before spending time on package builds."""
import argparse
import importlib
import json
from pathlib import Path


def verify_inputs(root: Path, channel: str = "auto", expected_sha: str | None = None) -> dict:
    """Validate inputs only; this never authorizes publication or substitutes for CI."""
    root = root.resolve(strict=True)
    rc = importlib.import_module("rc_version_gate")
    if channel not in {"auto", "rc", "stable"}:
        raise ValueError("unknown release channel")
    if channel == "auto":
        value = rc.load(root, "package.json").get("version")
        channel = "rc" if isinstance(value, str) and rc.RC_VERSION.fullmatch(value) else "stable"
    if channel == "rc":
        version, fields = rc.project_versions(root)
        guide = root / "docs/releases" / f"verification-v{version}.md"
        if (not guide.is_file() or guide.is_symlink()
                or not guide.resolve().is_relative_to(root)
                or not 0 < guide.stat().st_size <= 4 * 1024 * 1024
                or not guide.read_text(encoding="utf-8").strip()):
            raise ValueError("missing, unsafe or empty version-matched RC guide")
        if expected_sha is not None:
            rc.verify_source(root, expected_sha, version)
    else:
        versions = importlib.import_module("发布版本校验v4")
        publisher = importlib.import_module("聊天授权发布v26")
        version, fields = versions.project_versions(root)
        guide = publisher.release_guide(root, version)
        if expected_sha is not None:
            raise ValueError("--expect-sha is only supported for RC input validation")
    return {"scope": "release-inputs-only", "passed": True, "channel": channel,
            "version": version, "version_fields": len(fields),
            "guide": guide.relative_to(root).as_posix(),
            "source_verified": expected_sha is not None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--channel", choices=("auto", "rc", "stable"), default="auto")
    parser.add_argument("--expect-sha")
    args = parser.parse_args()
    print(json.dumps(verify_inputs(args.root, args.channel, args.expect_sha)))


if __name__ == "__main__":
    main()
