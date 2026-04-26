"""CLI entrypoint for the golf-scorecards dev server."""

import os
import sys

import uvicorn


def main() -> None:
    """Start the uvicorn development server with live reload."""
    # WeasyPrint (PDF export) needs Homebrew's shared libraries on macOS.
    if sys.platform == "darwin" and os.path.isdir("/opt/homebrew/lib"):
        os.environ.setdefault("DYLD_LIBRARY_PATH", "/opt/homebrew/lib")

    uvicorn.run("golf_scorecards.main:app", host="golf.local", port=8000, reload=True)
