# Built from the repo root: the image needs the workspace lockfile and packages/bdheal.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN useradd --create-home --uid 1000 app
WORKDIR /app
RUN chown app:app /app

USER app

COPY --chown=app:app pyproject.toml uv.lock ./
COPY --chown=app:app packages/bdheal ./packages/bdheal
COPY --chown=app:app api ./api
RUN uv sync --frozen --package ixq

# The corpus is a release artifact: the API only reads it, so it is baked in rather
# than mounted. Placed after the sync so refreshing it does not reinstall deps.
COPY --chown=app:app data ./data

EXPOSE 8000
# The venv was built by `uv sync --frozen` from this image's lockfile, so `uv run`
# could only re-verify what the build already guarantees — measured at 19s of a 31s
# cold start on the 0.1 CPU a free instance gets. Called directly, it boots in 12s.
CMD ["/app/.venv/bin/uvicorn", "ixq.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
