"""Fetch the pinned upstream Dexter source. Installs no global tools."""

import io
import os
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVISION = "534f6be455523c5926eba72bdaf4f914555be5c9"
DEST = Path(os.environ.get("DEXTER_SOURCE_DIR", ROOT / ".local/dexter"))


def main():
    marker = DEST / ".revision"
    DEST.mkdir(parents=True, exist_ok=True)
    modules = DEST / "node_modules"
    if not modules.exists() and not modules.is_symlink():
        modules.symlink_to(
            "../../backend/worker/node_modules", target_is_directory=True
        )
    if marker.exists() and marker.read_text().strip() == REVISION:
        print("Pinned Dexter source is ready.")
        return
    url = f"https://codeload.github.com/virattt/dexter/tar.gz/{REVISION}"
    with urllib.request.urlopen(url, timeout=60) as response:
        archive = response.read()
    DEST.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        for member in bundle.getmembers():
            relative = Path(*Path(member.name).parts[1:])
            if not member.isfile() or ".." in relative.parts:
                continue
            if not (
                str(relative).startswith("src/")
                or str(relative) in {"tsconfig.json", "SOUL.md", "package.json"}
            ):
                continue
            target = DEST / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as source:
                target.write_bytes(source.read())
    marker.write_text(REVISION + "\n")
    print("Pinned Dexter source downloaded into .local/dexter.")


if __name__ == "__main__":
    main()
