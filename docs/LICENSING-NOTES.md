# LICENSING NOTES

We keep upstream projects **isolated** (adapters only; no source modification).
This section summarizes third-party licenses and our integration posture.

---

## Third-Party Licenses in Scope

- **PokerKit** — GPL-3.0-or-later  
  - Used as a Python library via an adapter (`adapters/engines/pokerkit_adapter.py`).
  - Not vendored. Installed via `pip` for dev/test/runtime. If we patch, we publish a fork/patch files.

- **HenryRLee / PokerHandEvaluator** — Apache-2.0  
  - Optional evaluator; used for QA cross-checks and headless sampling in M0. Not vendored.

- **TexasSolver** — AGPL-3.0 (M1+ only; **not used in M0**)  
  - We do not bundle nor host it. Users supply a local binary path.
  - We will not operate solver as a *network service*. Any local changes must be published as required by AGPL.

---

## Policy Highlights

- **Adapters-only** integration in `adapters/*`, with zero edits in `third_party/*`.
- CI produces a **slim .zip** artifact (our code only). Third-party code is never included in the zip.
- Any local patches to upstreams must be distributed as patch files or forks.
- For AGPL components (TexasSolver), we avoid SaaS exposure; the binary is invoked locally.
- Removing any upstream leaves our project functional (minus that feature).