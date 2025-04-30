# Dockerfile

# ---- Builder Stage ----
FROM python:3.12-slim AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VERSION=2.1.1 
ENV POETRY_HOME="/opt/poetry"
ENV POETRY_VIRTUALENVS_IN_PROJECT=true

# System dependencies for poetry & potential build dependencies
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="$POETRY_HOME/bin:$PATH"

WORKDIR /app

# Copy dependency definition files
COPY pyproject.toml poetry.lock ./

# Install only runtime dependencies into the local .venv
# Using --no-dev ensures test/lint dependencies aren't included
# Using --no-root prevents installing the project itself as editable
RUN poetry install --no-root --only main

# Copy the rest of the application code (respects .dockerignore)
COPY . /app

# ---- Final Stage ----
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash appuser
USER appuser
WORKDIR /home/appuser/app

# Copy installed dependencies from builder stage's venv
COPY --from=builder --chown=appuser:appuser /app/.venv /home/appuser/app/.venv
# Copy application code
COPY --from=builder --chown=appuser:appuser /app/app /home/appuser/app/app
COPY --from=builder --chown=appuser:appuser /app/main.py /home/appuser/app/main.py
# Copy static frontend files
COPY --from=builder --chown=appuser:appuser /app/frontend /home/appuser/app/frontend

# Make sure the venv python is accessible
ENV PATH="/home/appuser/app/.venv/bin:$PATH"

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
# Use 0.0.0.0 to bind to all interfaces inside the container
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
