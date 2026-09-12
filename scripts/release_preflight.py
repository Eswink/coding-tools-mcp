"""Check version-matched release inputs before spending time on package builds."""
import importlib
import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    versions = importlib.import_module("发布版本校验v4")
    publisher = importlib.import_module("聊天授权发布v26")
    version, fields = versions.project_versions(root)
    guide = publisher.release_guide(root, version)
    print(json.dumps({"scope": "release-inputs-only", "passed": True, "version": version,
                      "version_fields": len(fields), "guide": guide.relative_to(root).as_posix()}))


if __name__ == "__main__":
    main()
