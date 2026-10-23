"""Show cleanup targets by default. --apply moves generated files to Trash."""

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Perform the displayed cleanup"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    manifest_path = root / "backend/resources.json"
    if args.apply and manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if not manifest.get("cleanup_complete"):
            parser.error(
                "Run scripts/cleanup_cloud.py --apply with workshop-run first. Local credentials are needed for cloud cleanup."
            )
    generated = [
        root / name
        for name in (
            ".venv",
            "node_modules",
            ".ruff_cache",
            ".pytest_cache",
            "__pycache__",
            ".local/dexter",
            ".dexter",
        )
    ]
    generated.extend(
        root / name
        for name in (
            "frontend/node_modules",
            "frontend/dist",
            "backend/.bedrock_agentcore",
            "backend/__pycache__",
            "backend/app/__pycache__",
            "backend/worker/node_modules",
            "backend/worker/__pycache__",
            "scripts/__pycache__",
        )
    )
    credentials_local = root / ".env.local"
    credentials = [
        Path.home() / ".aws" / name
        for name in ("aws-hackathon-2026.credentials", "aws-hackathon-2026.config")
    ]
    credentials.append(credentials_local)
    generated = [p for p in generated if p.exists() or p.is_symlink()]
    credentials = [p for p in credentials if p.exists() or p.is_symlink()]
    for path in generated:
        print(f"Move to Trash: {path}")
    for path in credentials:
        print(f"Delete temporary workshop credential/config file: {path}")
    if not args.apply:
        print(
            "\nPreview only. Close the project terminals, then rerun with --apply to clean up."
        )
    else:
        if generated:
            destination = (
                Path.home()
                / ".Trash"
                / (
                    "AWS-Hackathon-"
                    + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                    + "-"
                    + uuid4().hex[:8]
                )
            )
            destination.mkdir(parents=True, mode=0o700)
            for path in generated:
                target = destination / path.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(target))
            print(f"\nGenerated files moved to: {destination}")
        for path in credentials:
            path.unlink()
        print("Temporary workshop credential/config files removed.")
    print(
        "\nSource files, research notes, settings, and dependency lockfiles are kept."
    )
    print(
        "The VS Code 'AWS Hackathon' profile can be deleted in VS Code > Profiles after switching to Default."
    )
    print(
        "Other AWS profiles, shell startup files, system tools, and shared package caches are not touched."
    )
    print("No AWS cloud resources are deleted by this command.")


if __name__ == "__main__":
    main()
