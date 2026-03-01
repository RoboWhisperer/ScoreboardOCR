"""Build script for creating a Windows GUI executable with PyInstaller."""

from pathlib import Path
import PyInstaller.__main__


def main() -> None:
    icon = Path("app.ico")
    args = [
        "ocr_scoreboard.py",
        "--name=ScoreboardOCR",
        "--onefile",
        "--windowed",
        "--clean",
    ]
    if icon.exists():
        args.append(f"--icon={icon}")
    PyInstaller.__main__.run(args)


if __name__ == "__main__":
    main()
