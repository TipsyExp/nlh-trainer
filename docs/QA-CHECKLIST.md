# QA Checklist — M0

## Functional
- [ ] Full hand play-through for 2/3/6/9/10-max.
- [ ] HU blind rule: BTN posts SB; preflop SB acts first; postflop BTN acts last.
- [ ] Min-raise enforcement & re-opening rules correct.
- [ ] Buckets enforced; off-tree inputs snapped & logged.
- [ ] Side pots: 3p/4p multi-all-in scenarios distribute correctly.
- [ ] Walks (uncontested blinds) for each seat config.
- [ ] Export hand history; re-import or replay produces same result.
- [ ] UI: Table/Settings separation; knobs only on Settings.

## Determinism
- [ ] Same seed + same human actions ⇒ identical outcomes (deck, actions, pots).
- [ ] RNG seeds logged per decision.

## Non-functional
- [ ] Bot decisions <100 ms typical.
- [ ] 1,000-hand autoplay (bots-only) completes with zero crashes.
- [ ] UI smooth (no jank); action animations readable.

## Edge cases
- [ ] Short-stack jams; insufficient raises don’t reopen betting.
- [ ] Off-tree preflop sizes snapped, then tree stays consistent postflop.
- [ ] Dead blinds when seats empty.
- [ ] Correct card visibility; unique burns; no duplicate cards.

## Sign-off
- [ ] DoD items in `M0-SPEC.md` verified.
- [ ] Docs updated (API, schema, bet-trees, range format, runbook).