#!/usr/bin/env bash
set -euo pipefail

echo "Tearing down dev environment..."

# Django runserver
pkill -f "manage.py runserver" 2>/dev/null && echo "  stopped: Django" || echo "  not running: Django"

# Vite / Next dev servers
pkill -f "theCommonsWeb" 2>/dev/null && echo "  stopped: Frontend" || echo "  not running: Frontend"
pkill -f "broadcastWeb" 2>/dev/null && echo "  stopped: Broadcast Web" || echo "  not running: Broadcast Web"

# Redis
pkill -f "redis-server" 2>/dev/null && echo "  stopped: Redis" || echo "  not running: Redis"

echo "Done."
