#!/usr/bin/env bash
# Prepares the runner stage's runtime user for arbitrary-UID platforms
# (e.g. OpenShift, which ignores an image's own UID and always runs it
# under group 0): group-0 ownership plus group read/write/execute on
# every directory the app needs, and a numeric (not named) final USER in
# the Dockerfile. /opt/venv gets the equivalent treatment via COPY
# --chown/--chmod instead of a recursive chmod here, which would be slow
# over a whole venv.
set -euo pipefail

app_uid=$1

chmod +x /usr/local/bin/runner.sh
useradd --create-home --uid "$app_uid" --gid 0 appuser

chgrp -R 0 /app /home/appuser
chmod -R g+rwX /app /home/appuser
