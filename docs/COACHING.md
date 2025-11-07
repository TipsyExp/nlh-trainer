
# docs/COACHING.md

### Coach UI (Table Overlay)
•	Where: On the Table page (top-right panel). A toggle controls whether advice is shown.
•	Behavior:
o	When On, the UI calls GET /api/coach/advice?hand_id=…&idx=… for the current visible decision.
o	Advice shows:
	Recommended bucket (e.g., 100%)
	A strategy bar listing buckets and their probabilities
	Optional EV by action if available
•	Statuses:
o	On: Advice returned (meta.status="ok").
o	Disabled: Coach off via environment (COACH_ENABLED=false).
o	Unsupported: Node not supported (e.g., preflop, multi-way, or builder limits).
o	Timeout: Solver exceeded COACH_TS_TIMEOUT_S.
o	Unavailable: Network/500 errors.
•	Notes:
o	No polling; the panel refreshes when the decision index changes.
o	First solve may be slower; subsequent requests may be faster once caching (Task-18) is added.
