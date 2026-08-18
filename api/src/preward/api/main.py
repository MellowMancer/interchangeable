"""FastAPI application entrypoint."""

from fastapi import FastAPI

app = FastAPI(title="rf-pre")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
