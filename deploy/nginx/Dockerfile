# syntax=docker/dockerfile:1
#
# nginx image for The Commons — fronts nextjs (3000) and backend/gunicorn
# (8000), and directly serves two BAKED build artifacts produced by other
# services' Dockerfiles, plus the media bind mount.
#
# This Dockerfile is never built standalone: `docker build -f
# deploy/nginx/Dockerfile deploy/nginx` would fail, because `backend-static`
# and `broadcast-spa` below are Buildx *named build contexts* wired up in
# docker-compose.yml's `nginx.build.additional_contexts`, bound to the
# `backend` and `broadcast-spa-build` compose services respectively (each
# building a specific stage of backendServer/Dockerfile and Dockerfile.frontend).
# Always build via `docker compose build nginx` (or `up --build`) — verified
# that compose resolves and builds those named-context services first even
# when only `nginx` is requested.
#
#   backend-static -> backendServer/Dockerfile `app` stage
#                      /app/staticfiles_build/static (collectstatic output)
#   broadcast-spa  -> Dockerfile.frontend `broadcast-build` stage
#                      /app/dist (compiled broadcastWeb SPA)
#
# Baking these in (rather than a volume) is deliberate: a volume here would
# let a stale build survive a fresh deploy. Both artifacts are pure build
# output, never mutated at runtime.
FROM nginx:1.27-alpine

COPY --from=backend-static /app/staticfiles_build/static /usr/share/nginx/html/static
COPY --from=broadcast-spa /app/dist /usr/share/nginx/html/broadcast

# Replace nginx's stock default server block with ours — the stock
# default.conf listens on 80 with its own catch-all server, which would
# otherwise compete with the HTTP->HTTPS redirect block below.
COPY thecommons.conf /etc/nginx/conf.d/thecommons.conf
RUN rm -f /etc/nginx/conf.d/default.conf

# nginx:1.27-alpine's own CMD/ENTRYPOINT (start nginx in the foreground) is
# unchanged — no override needed.
