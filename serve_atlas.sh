#!/usr/bin/env bash
# Serve the Class A GPCR Atlas over HTTP. Standard Python only, no dependencies.
#
#   ./serve_atlas.sh            # serves the built site on port 8765
#   ./serve_atlas.sh 9000       # a different port
#   ./serve_atlas.sh 8765 dev   # serves the working tree instead of the build output
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
PORT="${1:-8765}"
MODE="${2:-site}"
if [ "$MODE" = "dev" ]; then
  ROOT="."
  ENTRY="app/index.html"
else
  ROOT="releases/phase5/site"
  ENTRY="index.html"
  if [ ! -f "$ROOT/index.html" ]; then
    echo "Build output not found. Run python3 pipeline/phase5/build_phase5.py first, or use: $0 $PORT dev" >&2
    exit 1
  fi
fi
echo "Serving $ROOT on http://localhost:$PORT/$ENTRY"
echo "Press Ctrl-C to stop."
exec python3 -m http.server "$PORT" --directory "$ROOT"
