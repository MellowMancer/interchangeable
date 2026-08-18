FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN useradd --create-home --uid 1000 app
WORKDIR /app
RUN chown app:app /app

USER app

COPY --chown=app:app pyproject.toml uv.lock ./
COPY --chown=app:app src ./src
RUN uv sync --frozen

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "preward.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
