#!/bin/bash
#
# Print the current NLH trainer engine snapshot as JSON.

API_URL=${API_URL:-http://localhost:8000}

echo "Fetching engine snapshot..." >&2
curl -s "$API_URL/api/debug/engine/snapshot" | jq .