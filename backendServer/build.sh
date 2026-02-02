#!/bin/bash

# 1. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env

# 2. Install dependencies
uv sync

# 3. Collect static files (Required for Admin/DRF)
uv run python manage.py collectstatic --noinput

# 4. Create the output directory Vercel expects
mkdir -p staticfiles_build/static
cp -r static/* staticfiles_build/static/ || true