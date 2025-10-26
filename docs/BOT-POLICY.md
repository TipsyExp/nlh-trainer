# Bot Policy

The NLH Trainer includes a simple deterministic bot used for automatic opponent actions in test scenarios and in the examples captured in `docs/examples`.  This section documents its behaviour and hints at potential future extensions.

## Current Behaviour (M1)

The bot’s decision policy is intentionally minimalist to provide a stable baseline for unit tests:

* If the amount to call (`to_call`) is **zero**, the bot will **check**.
* Otherwise (if there is a call amount), the bot will **call** the full amount.

This policy means that the bot never folds, never raises, and never bluffs.  As a result, hands proceed quickly to showdown once a human player begins betting.

### Example

In the pre‑flop example contained in `docs/examples/hand_action.json`, the human checks.  The bot responds with a check on the pre‑flop street and then, because there is still no amount to call on the flop, checks again.  This deterministic behaviour makes hand replays deterministic when the RNG seed is fixed.

## Future Extensions

While the current bot is extremely simple, the infrastructure supports richer policies.  Potential enhancements include:

* **Mixing Strategies**: Introducing randomised thresholds for betting or folding to simulate variance in decision making.
* **Aggression Multipliers**: Scaling bucket sizes up or down to create loose or tight opponents.
* **Positional Awareness**: Choosing different buckets based on whether the bot is in or out of position.

These features are not enabled in milestone M1 to keep the environment deterministic.  When such knobs are introduced, they will be documented in this file and exposed via configuration flags.
