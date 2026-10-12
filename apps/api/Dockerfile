FROM ghcr.io/astral-sh/uv:0.12.5-python3.13-trixie-slim AS base
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN uv sync --directory backend --frozen --no-dev --no-install-project
COPY backend ./backend
COPY apps/api ./apps/api
RUN uv sync --directory backend --frozen --no-dev
ENV PATH="/app/backend/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "main:app", "--app-dir", "/app/apps/api", "--host", "0.0.0.0", "--port", "8000"]
