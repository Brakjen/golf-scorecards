"""CLI entrypoint for the golf-scorecards dev server."""

import uvicorn


def main() -> None:
    """Start the uvicorn development server with live reload."""
    uvicorn.run("golf_scorecards.main:app", host="golf.local", port=8000, reload=True)
