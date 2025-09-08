# THIRD-PARTY INTEGRATION

We keep upstreams “on top” of our codebase and integrate via thin adapters.

---

## Repos

- **PokerKit** — https://github.com/uoftcprg/pokerkit (GPL-3.0-or-later)
- **HenryRLee / PokerHandEvaluator** — https://github.com/HenryRLee/PokerHandEvaluator (Apache-2.0)  
- **TexasSolver** — https://github.com/bupticybee/TexasSolver (AGPL-3.0) *(M1+ only)*

---

## Layout

```
adapters/
engines/
pokerkit_adapter.py
evaluator/
pheval_adapter.py
solver/
texassolver_adapter.py # stub in M0; headless in M1

```

> We do **not** vendor upstream source in `third_party/` for M0.

---

## Install Modes

- **PokerKit** → `pip install pokerkit`
- **phevaluator** (optional) → `pip install phevaluator`
- **TexasSolver** (M1+) → User supplies local binary; set `TEXASSOLVER_PATH`.

---

## Compatibility Smoke (M0)

- **PokerKit**: deal N hands for 2/3/6/9/10; verify blinds/order/side pots vs goldens.

---

## Distribution (.zip)

- CI publishes a **slim .zip** (our source only). Third-party code is never included.  
- Post-unzip, run `pip install -r requirements.txt` to fetch extras.

---

## Licensing

See `docs/LICENSING-NOTES.md` (GPL/AGPL posture, adapters-only policy).