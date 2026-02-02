#!/bin/bash
# Install uv if not present (though Vercel usually has it)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env

# Sync dependencies
uv sync

# Run collectstatic using the uv environment
uv run python manage.py collectstatic --noinput