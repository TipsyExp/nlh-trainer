# Preflop Preset Format

You may supply **YAML** or **CSV** preflop presets. YAML is recommended for readability and hierarchical overrides.

> Bucket labels **must** match the discrete action space defined in [BET-TREES.md](./BET-TREES.md):  
> `2.2x`, `2.5x`, `3.0x`, `2.5xR`, `3.0xR`, `jam`.

---

## YAML Structure (per seat count)

```yaml
metadata:
  seat_count: 6
  stack_bb: [100]    # optional: list of supported stacks for this set

positions:
  UTG:
    opens:
      - hands: ["AA","KK","QQ","AKs"]
        freq: 1.0
        size: "2.5x"         # preflop open bucket
      - hands: ["JJ","TT","AQs","AJs","KQs"]
        freq: 0.8
        size: "2.5x"
    vs_open: {}               # optional: responses facing an open
    vs_3bet: {}               # optional: responses facing a 3-bet

  MP:
    opens:
      - hands: ["AA-99","AKs-AJs","KQs-KJs","AQo"]
        freq: 1.0
        size: "2.5x"

  CO: { }
  BTN: { }
  SB:  { }
  BB:  { }

# Optional stack-specific overrides (take precedence when active)
overrides:
  "40bb":
    BTN:
      opens:
        - hands: ["ATo-AQo","KJo-KQo"]
          freq: 0.5
          size: "2.2x"
    BB:
      vs_open:
        - hands: ["TT-88","AQs-ATs"]
          freq: 0.6
          size: "2.5xR"      # raise bucket facing an open

Conventions

hands supports:

ranges: AA-99

suited/offsuit: AKs, AQo

groups: A5s-A2s

explicit combos: AsKd (rare; use only if needed)

freq: 0.0–1.0 (mixing weight). The engine samples with a seeded RNG for determinism.

size: one of the allowed bucket labels from BET-TREES.md

CSV Alternative

A flat representation is also supported. Each row describes one mapping.
seat_count,position,spot,hands,freq,size,stack
6,BTN,open,"AA-22, AKs-A2s, AKo-ATo, KQs-KTs",1.0,2.2x,100
6,SB,vs_open,"TT-88, AQs-ATs",0.6,3.0xR,100

spot ∈ {open, vs_open, vs_3bet} (extendable).

stack (in big blinds) is optional; if provided, it narrows applicability of the row.

Runtime Rules

Lookup order: use overrides[<active_stack>] if present, otherwise fall back to top-level positions.

Snapping: any off-tree numeric input is snapped to the nearest allowed bucket before lookup.

Determinism: mixing uses a seeded RNG (session/hand seed) so the same seed + same spot ⇒ identical choices.

Validation:

Unknown bucket labels → schema error.

Unknown positions or malformed hand ranges → schema error.

Overlapping hand ranges are allowed; later entries override earlier ones for the same (position, spot).

Missing entries: if no mapping exists, the bot falls back conservatively (e.g., call/fold) and logs a warning.