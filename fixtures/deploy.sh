#!/usr/bin/env bash
# Render the fixture site and publish it to GitHub Pages.
#
#   fixtures/deploy.sh                       # publish to origin's repository
#   fixtures/deploy.sh git@github.com:me/x.git
#
# The site is pushed straight to the `gh-pages` branch rather than through a Pages
# Actions workflow. That is deliberate: publishing via Actions needs the `workflow`
# OAuth scope, which a `gh auth login` does not grant by default, and discovering that
# costs a failed run. A direct branch push needs only `repo`.
#
# The push is a force-push onto a branch this script owns end to end. It contains
# generated output and nothing else — never source, never history worth keeping.
#
# Pages serves through a CDN. Allow 30-60 seconds after this exits before pointing a
# collector at the site, or the collector reads the previous markup and whatever it then
# measures is meaningless.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="gh-pages"
REMOTE_URL="${1:-$(git -C "$ROOT" remote get-url origin)}"

echo "rendering fixture site"
uv run --package bdheal python "$ROOT/fixtures/render.py"

if [ ! -f "$ROOT/fixtures/site/.nojekyll" ]; then
  echo "refusing to publish: .nojekyll is missing and Jekyll would eat the site" >&2
  exit 1
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$ROOT/fixtures/site/." "$STAGE/"

cd "$STAGE"
git init -q
git checkout -qb "$BRANCH"
git add -A
git -c user.name="bdheal-fixtures" -c user.email="bdheal-fixtures@users.noreply.github.com" \
  commit -q -m "deploy: bdheal benchmark fixtures"
git remote add origin "$REMOTE_URL"
git push -qf origin "$BRANCH"

SLUG="$(sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##' <<<"$REMOTE_URL")"
OWNER="${SLUG%%/*}"
REPO="${SLUG##*/}"

cat <<EOF

published to $BRANCH on $SLUG

  https://${OWNER}.github.io/${REPO}/

Next:
  1. Enable Pages for this repository: Settings -> Pages -> Source: deploy from
     branch -> $BRANCH / (root). Only needed once.
  2. Wait 30-60s for the CDN before running any collector against it.
  3. Build each benchmark collector with a description that says THIS PAGE ONLY,
     follow no links, no pagination. See fixtures/README.md.
EOF
