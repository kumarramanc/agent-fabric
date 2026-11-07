"""Build a runtime archive from an explicit file list, excluding local/demo data."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "main.py",
    "requirements.txt", "README.md", ".env.example",
    "docs/agent-fabric-vision.html",
    "agents/customer_support/agent.json", "agents/customer_support/system.md",
    "agents/customer_support/skills/refunds.md"
]


def build_runtime(output_path=None):
    destination = Path(output_path) if output_path else ROOT / "dist" / "agent-fabric.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = [ROOT / name for name in FILES]
    files.extend(sorted((ROOT / "agent_runtime").rglob("*.py")))
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, file.relative_to(ROOT).as_posix())
    return destination


if __name__ == "__main__":
    print(build_runtime())
