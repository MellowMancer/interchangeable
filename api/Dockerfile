# Built from the repo root: the image needs the workspace lockfile and packages/bdheal.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN useradd --create-home --uid 1000 app
WORKDIR /app
RUN chown app:app /app

USER app

COPY --chown=app:app pyproject.toml uv.lock ./
COPY --chown=app:app packages/bdheal ./packages/bdheal
COPY --chown=app:app api ./api
RUN uv sync --frozen --package preward

EXPOSE 8000
CMD ["uv", "run", "--frozen", "--package", "preward", "uvicorn", "preward.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
