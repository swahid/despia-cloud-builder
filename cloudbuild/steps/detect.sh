#!/usr/bin/env bash
set -euo pipefail
REPO=$1
cd "$REPO"
PM="npm"
if [[ -f yarn.lock ]]; then PM="yarn"; fi
if [[ -f pnpm-lock.yaml ]]; then PM="pnpm"; fi

FRAMEWORK="unknown"
PKG_JSON=""
if [[ -f package.json ]]; then
  PKG_JSON="$(cat package.json)"
fi

# naive detection
if echo "$PKG_JSON" | grep -q "\"next\""; then FRAMEWORK="next"; fi
if echo "$PKG_JSON" | grep -q "\"react-scripts\""; then FRAMEWORK="react-scripts"; fi
if echo "$PKG_JSON" | grep -q "\"vite\""; then FRAMEWORK="vite"; fi
if echo "$PKG_JSON" | grep -q "\"vue\""; then FRAMEWORK="vue"; fi

cat <<EOF
{
  "package_manager":"$PM",
  "framework":"$FRAMEWORK"
}
EOF
