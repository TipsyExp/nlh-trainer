# PR Template (M0)

## What’s in this PR?
- [ ] Implements/updates TASK-XX from `docs/TASKS-M0.md`
- [ ] Adheres to `docs/M0-SPEC.md` scope (no solver/RL/multiway-solver)
- [ ] Updates relevant docs (API, Runbook, QA, etc.)

## Checklists

### Quality
- [ ] CI green (lint, type-check, tests)
- [ ] Added/updated unit tests and integration tests
- [ ] Updated QA checklist items where applicable
- [ ] Determinism preserved (seeded tests where relevant)

### Artifacts
- [ ] Attached the **slim .zip** build artifact (our source only, no vendored third-party code)
- [ ] Included lockfiles/requirements for reproducible installs

### Adapters & Third-Party
- [ ] I touched only **adapters** for third-party changes (no edits under `third_party/`)
- [ ] If ENGINE/EVALUATOR modes changed, I updated `docs/CONFIGURATION.md` and `docs/THIRD-PARTY-INTEGRATION.md`

### Scope Safety
- [ ] No solver calls or solver logic paths are active
- [ ] No RL
- [ ] No multiway solver approximations

## Screenshots / Demos (if UI)

## Notes for Reviewers
