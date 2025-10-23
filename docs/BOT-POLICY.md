# Bot Policy

This document summarises the behaviour of the built‑in bots in the
NLH Trainer.  The bots are intentionally simple for early milestones;
they serve as predictable opponents to allow the human trainee to
focus on decision making rather than modelling complex opponent
strategies.

## Baseline Behaviour

- **Posting blinds** – Bots post blinds automatically when a hand starts.
  The small blind and big blind are deducted from their stacks and
  logged as `post_blind` actions.
- **Action selection** – At each decision point a bot examines the
  `to_call` value returned by the engine:
  - If `to_call` is `0` (no bet pending), the bot **checks**.
  - If `to_call` is greater than `0`, the bot **calls**.
- **No raises or bets** – The baseline bots never bet or raise on
  their own.  They only respond to human bets by calling or checking.
  This ensures that the human trainee encounters straightforward
  situations and can practise basic bet sizing without facing
  re‑raises.

## Limitations

- **No hand evaluation** – Bots do not consider their hole cards or the
  board.  They always call when facing a bet regardless of the
  equity of their hand.
- **No bluffing or aggression** – There is no logic for semibluffing,
  value betting or bluff catching.  Bots cannot fold to bets, so
  human trainees should be aware that they will always be called
  when betting.
- **Street progression** – The stubbed engine currently transitions
  from preflop to the flop when both players have called and
  checked.  Later streets (`turn`, `river`, `showdown`) are
  placeholders for future milestones.

## Future Extensions

Milestones beyond M0/M1 will introduce more sophisticated bot
profiles with configurable aggression and adaptive strategies.  The
`BOT-POLICY.md` will be expanded accordingly to document those
profiles and the knobs that control their behaviour.
