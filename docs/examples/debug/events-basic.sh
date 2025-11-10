#!/bin/bash
#
# Follow the NLH trainer engine events stream.
# Requires jq for pretty printing.

API_URL=${API_URL:-http://localhost:8000}
SINCE=${SINCE:-0}
LIMIT=${LIMIT:-100}

echo "Fetching events since seq=$SINCE (limit $LIMIT)..." >&2
curl -s "$API_URL/api/debug/engine/events?since=$SINCE&limit=$LIMIT" | jq .