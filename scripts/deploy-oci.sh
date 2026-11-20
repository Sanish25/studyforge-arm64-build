#!/usr/bin/env bash
# Deploy the Django API on the OCI VM (studyforge-api).
# Run ON the VM from the repo root, or via:
#   ssh -i ~/.ssh/studyforge-oci.key ubuntu@<PUBLIC_IP> 'bash -s' < scripts/deploy-oci.sh
#
# Expects:
#   - Repo at ~/studyforge (or set STUDYFORGE_ROOT)
#   - backend/.venv
#   - /etc/studyforge.env (mode 600) loaded by this script for manage.py
# Does not print secret values.

set -euo pipefail

ROOT="${STUDYFORGE_ROOT:-$HOME/studyforge}"
ENV_FILE="${STUDYFORGE_ENV_FILE:-/etc/studyforge.env}"
HEALTH_URL="${STUDYFORGE_HEALTH_URL:-https://studyforge-rodians.duckdns.org/api/v1/health/}"
BRANCH="${STUDYFORGE_DEPLOY_BRANCH:-}"

cd "$ROOT"

echo "==> Repo: $ROOT"
if [[ -n "$BRANCH" ]]; then
  echo "==> Checking out $BRANCH"
  git fetch origin
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
else
  echo "==> Pulling current branch ($(git branch --show-current))"
  git pull --ff-only
fi

cd "$ROOT/backend"
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing Python deps"
pip install -r requirements.txt

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

echo "==> Loading $ENV_FILE"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

echo "==> migrate + collectstatic"
python manage.py migrate --noinput
python manage.py collectstatic --noinput

echo "==> Restart Gunicorn"
sudo systemctl restart studyforge-gunicorn

echo "==> Health check"
curl -fsS -i "$HEALTH_URL" | head -n 20

echo "==> Deploy finished"
