#!/usr/bin/env bash
set -euo pipefail
REPO=$1
DETECTED_JSON=$2
cd "$REPO"


PM=$(jq -r .package_manager "$DETECTED_JSON")
FW=$(jq -r .framework "$DETECTED_JSON")


echo "Using PM=$PM FW=$FW"


if [[ "$PM" == "yarn" ]]; then yarn install --frozen-lockfile; fi
if [[ "$PM" == "pnpm" ]]; then pnpm install --frozen-lockfile; fi
if [[ "$PM" == "npm" ]]; then npm ci; fi


if [[ "$FW" == "next" ]]; then
npm run build || true
npm run export || true
if [[ -d out ]]; then
cp -r out dist || true
fi
else
npm run build || true
fi


if [[ -d dist ]]; then
zip -r bundle.zip dist
elif [[ -d out ]]; then
zip -r bundle.zip out
elif [[ -d .next ]]; then
zip -r bundle.zip .next
else
echo "No common build output (dist/out/.next). Listing files:"
ls -la
exit 1
fi