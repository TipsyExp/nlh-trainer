# backend/adapters/solver/texassolver_adapter.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, TypedDict, Optional, cast
import json
import os
import re
import subprocess
import tempfile


class CoachDisabledError(RuntimeError):
    """Raised when COACH is off or the solver path is not configured."""


class UnsupportedSpotError(RuntimeError):
    """Raised for preflop, multi-way, or otherwise unsupported configurations."""


class AdvicePayload(TypedDict):
    recommended_bucket: str
    strategy: Dict[str, float]
    ev_map: Dict[str, float]


@dataclass(frozen=True)
class SolveRequest:
    """
    Canonical minimal inputs we need to call the solver.
    NOTE: We'll gradually expand this as our canonical node grows.
    """

    street: str  # "flop" | "turn" | "river"
    board: List[str]  # ["Ah", "Kd", "3s"] etc.
    pot: int  # current pot size (chips)
    ip_stack: int  # stack behind IP (chips)
    oop_stack: int  # stack behind OOP (chips)
    ip_range: str  # solver-native text, e.g. "AA,KK,AKs:0.5,..."
    oop_range: str  # same format as ip_range
    bucket_labels: List[str]  # our labels; e.g. ["33%", "66%", "pot", "jam"]
    spot: str = "SRP"  # "SRP" | "3BP" (limited scope for Task-16)


def _require_solver_enabled() -> Path:
    if os.getenv("COACH_ENABLED", "false").lower() != "true":
        raise CoachDisabledError("COACH_ENABLED is not true")

    raw = os.getenv("TEXASSOLVER_PATH")
    if not raw:
        raise CoachDisabledError("TEXASSOLVER_PATH not set")

    p = Path(raw)
    if not p.is_absolute():
        raise CoachDisabledError("TEXASSOLVER_PATH must be an absolute path")
    if not p.exists():
        raise CoachDisabledError(f"TEXASSOLVER_PATH not found: {p}")
    if not os.access(p, os.X_OK):
        # On Windows this may still succeed if extension is .exe; we check existence anyway.
        # We'll still allow it but warn by raising a clearer message if the process fails later.
        pass
    return p


def _map_bucket_to_pot_percent(label: str) -> Optional[int]:
    """
    TexasSolver uses *percent of pot* integers in `set_bet_sizes` (e.g., 50 => 50% pot).
    We accept a few common styles and translate:
      - "33%", "66%", "75%", "100%" -> 33/66/75/100
      - "half" -> 50, "two_thirds" -> 66, "pot" -> 100
      - "Nx" like "2.2x" -> 220 (percent)
      - "jam" / "allin" -> None (handled via 'allin' command line, not a percent)
    Return None for "jam"/"allin".
    """
    s = label.strip().lower()
    if s.endswith("%"):
        try:
            return int(round(float(s[:-1])))
        except ValueError:
            return None
    if s in {"half"}:
        return 50
    if s in {"two_thirds", "two-thirds"}:
        return 66
    if s in {"pot"}:
        return 100
    if s in {"jam", "allin", "all-in"}:
        return None
    if s.endswith("x"):  # e.g., "2.2x"
        try:
            n = float(s[:-1])
            return int(round(n * 100))
        except ValueError:
            return None
    return None


def _is_supported(req: SolveRequest) -> bool:
    # Task-16 scope: HU postflop (SRP or 3BP). We don't handle preflop or multi-way.
    if req.street not in {"flop", "turn", "river"}:
        return False
    if len(req.board) not in {3, 4, 5}:
        return False
    if req.spot not in {"SRP", "3BP"}:
        return False
    return True


class TexasSolverAdapter:
    """
    Env-gated adapter around the TexasSolver console binary.

    - Constructs a temporary input script for a single node.
    - Invokes the solver (`console_solver -i <script>`).
    - Reads the emitted JSON file and maps it into AdvicePayload.

    For Task-16 in CI: this adapter is present but effectively NO-OP unless:
      COACH_ENABLED=true AND TEXASSOLVER_PATH is an absolute executable path.

    Parsing is intentionally robust to multiple JSON shapes.
    """

    def __init__(self) -> None:
        self._solver_path: Optional[Path] = None  # lazily validated

        # Tuning knobs (deterministic by default)
        self._threads = int(os.getenv("COACH_TS_THREADS", "1"))
        self._accuracy = float(os.getenv("COACH_TS_ACCURACY", "1.0"))
        self._max_iters = int(os.getenv("COACH_TS_MAX_ITERS", "200"))
        self._timeout_s = int(os.getenv("COACH_TS_TIMEOUT_S", "90"))

    def solve(self, req: SolveRequest) -> AdvicePayload:
        # Gate & support checks
        solver_path = self._solver_path or _require_solver_enabled()
        self._solver_path = solver_path  # cache after first check

        if not _is_supported(req):
            raise UnsupportedSpotError(
                "Only HU postflop SRP/3BP on flop/turn/river are supported"
            )

        # Build a temp workdir with input + output files
        with tempfile.TemporaryDirectory(prefix="texassolver_node_") as tmp:
            tmpdir = Path(tmp)
            input_path = tmpdir / "node_input.txt"
            output_path = tmpdir / "output_result.json"

            self._write_input_script(req, input_path, output_path)

            # Run solver
            cmd = [str(solver_path), "-i", str(input_path)]
            try:
                subprocess.run(
                    cmd,
                    cwd=str(tmpdir),
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_s,
                )
            except subprocess.TimeoutExpired as e:
                raise UnsupportedSpotError(
                    f"TexasSolver timed out after {self._timeout_s}s"
                ) from e
            except subprocess.CalledProcessError as e:
                raise UnsupportedSpotError(
                    f"TexasSolver failed (exit={e.returncode}): {e.stderr or e.stdout}"
                ) from e

            output = (
                output_path if output_path.exists() else (tmpdir / "output_result.json")
            )
            if not output.exists():
                raise UnsupportedSpotError("TexasSolver produced no output JSON")

            # Read JSON tolerating optional UTF-8 BOM (common on Windows)
            data = output.read_bytes()
            try:
                raw = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                # If a BOM slipped in, this will strip it
                raw = json.loads(data.decode("utf-8-sig"))

        # Parse into our AdvicePayload
        return self._parse_output(req, raw)

    # ---------- internals ----------

    def _write_input_script(
        self, req: SolveRequest, input_path: Path, output_path: Path
    ) -> None:
        """
        Emit a *street-focused* HU script aligned with our bucket labels.
        We only configure the street in `req.street` to keep the tree minimal and deterministic.
        """
        eff = min(req.ip_stack, req.oop_stack)

        # Map our bucket labels to solver pot-%; detect if user asked for jam/allin.
        def _labels_to_sizes(labels: List[str]) -> tuple[list[int], bool]:
            sizes: list[int] = []
            has_allin = False
            for b in labels:
                pct = _map_bucket_to_pot_percent(b)
                if pct is None:
                    # treat jam/allin/all-in as "add allin"
                    if b.strip().lower() in {"jam", "allin", "all-in"}:
                        has_allin = True
                else:
                    if pct > 0:
                        sizes.append(int(pct))
            sizes = sorted(set(sizes))
            return sizes, has_allin

        bet_sizes, has_allin = _labels_to_sizes(req.bucket_labels)

        if req.street not in {"flop", "turn", "river"}:
            raise UnsupportedSpotError(
                f"Unsupported street for TexasSolver: {req.street}"
            )

        board_str = ",".join(req.board)

        lines: list[str] = []
        lines.append(f"set_pot {req.pot}")
        lines.append(f"set_effective_stack {eff}")
        lines.append(f"set_board {board_str}")

        # Ranges are solver-native strings (caller supplies valid format)
        lines.append(f"set_range_ip {req.ip_range}")
        lines.append(f"set_range_oop {req.oop_range}")

        # Configure ONLY the current street to keep graph tiny.
        st = req.street  # "flop" | "turn" | "river"
        for p in ("oop", "ip"):
            for pct in bet_sizes:
                lines.append(f"set_bet_sizes {p},{st},bet,{pct}")
                # Thin slice: mirror the same size as raise option (TexasSolver accepts this)
                lines.append(f"set_bet_sizes {p},{st},raise,{pct}")
            if has_allin:
                lines.append(f"set_bet_sizes {p},{st},allin")

        # Solver controls (thread=1 for determinism; other knobs from env)
        lines.append("set_allin_threshold 0.67")
        lines.append("build_tree")
        lines.append(f"set_thread_num {self._threads}")  # default 1
        lines.append(f"set_accuracy {self._accuracy}")  # default 1.0
        lines.append(f"set_max_iteration {self._max_iters}")  # default 200
        lines.append("set_print_interval 10")
        lines.append("set_use_isomorphism 1")
        lines.append("start_solve")
        lines.append("set_dump_rounds 1")
        lines.append(f"dump_result {output_path.name}")

        input_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _parse_output(self, req: SolveRequest, raw: object) -> AdvicePayload:
        """
        Convert solver JSON to our AdvicePayload.

        Tolerates:
          - root.strategy as a dict {action_name: prob, ...}  (numeric or nested dict with 'prob')
          - root.strategy as a list [p0,p1,...] aligned with root.actions/action_labels/actionNames
          - TexasSolver tree dumps that include:
              * actions: ["CHECK", "BET 2.000000", ...]
              * strategy: { "actions": [...], "strategy": { "AcKd": [..], ... } }
            → we aggregate combo-level vectors into a root policy (equal-weight average).
          - alternate containers: infosets[0], nodes[0], or the root object itself
          - ev as dict OR as list aligned with actions
          - if no numeric strategy found, fallback to regret_sum; if still none, uniform.

        Also tolerates uppercase + spacey labels like "BET 2.000000" and maps them to nearest buckets.
        """
        if not isinstance(raw, dict):
            raise UnsupportedSpotError("Unexpected solver output (not a JSON object)")

        # 1) Find a plausible "root" node
        root: Optional[dict] = None
        if isinstance(raw.get("root"), dict):
            root = raw["root"]
        elif (
            isinstance(raw.get("infosets"), list)
            and raw["infosets"]
            and isinstance(raw["infosets"][0], dict)
        ):
            root = raw["infosets"][0]
        elif (
            isinstance(raw.get("nodes"), list)
            and raw["nodes"]
            and isinstance(raw["nodes"][0], dict)
        ):
            root = raw["nodes"][0]
        else:
            root = raw  # fall back to the top object

        if not isinstance(root, dict):
            raise UnsupportedSpotError(
                "Could not locate a root object in solver output"
            )

        # 2) Determine action labels (prefer explicit; fallback to childrens keys)
        action_labels: Optional[List[str]] = None
        val = root.get("actions")
        if isinstance(val, list) and len(val) > 0:
            action_labels = [str(x).strip() for x in val]

        if (not action_labels) and isinstance(root.get("childrens"), dict):
            kids = root["childrens"]
            if kids:
                action_labels = [str(k).strip() for k in kids.keys()]

        # 3) Extract strategy (many shapes)
        strategy_kv: Optional[Dict[str, float]] = None

        def _kv_from_list(lst: list, labels: List[str]) -> Dict[str, float]:
            n = min(len(lst), len(labels))
            return {
                labels[i]: float(lst[i])
                for i in range(n)
                if isinstance(lst[i], (int, float))
            }

        def _find_first_list_of_len(
            d: dict, keys: List[str], n: int
        ) -> Optional[List[float]]:
            for k in keys:
                v = d.get(k)
                if (
                    isinstance(v, list)
                    and len(v) >= n
                    and all(isinstance(x, (int, float)) for x in v[:n])
                ):
                    return [float(x) for x in v[:n]]
            return None

        def _find_first_dict_numeric(
            d: dict, keys: List[str]
        ) -> Optional[Dict[str, float]]:
            # Accept dict of numeric values OR dict of dicts with 'prob-like' numeric
            prob_keys = {"prob", "p", "probability", "weight", "w"}
            for k in keys:
                v = d.get(k)
                if isinstance(v, dict):
                    out: Dict[str, float] = {}
                    for kk, vv in v.items():
                        if isinstance(vv, (int, float)):
                            out[str(kk)] = float(vv)
                        elif isinstance(vv, dict):
                            # nested: look for a single numeric prob-like field
                            for pk in prob_keys:
                                pv = vv.get(pk)
                                if isinstance(pv, (int, float)):
                                    out[str(kk)] = float(pv)
                                    break
                    if out:
                        return out
            return None

        # --- Canonical: root["strategy"] can be several shapes ---
        strat_raw = root.get("strategy")

        # (A) Dict of numeric or dict-of-dicts w/ prob-like fields
        if isinstance(strat_raw, dict):
            # Special handling for TexasSolver tree dumps:
            # strat_raw may look like: {"actions":[...], "strategy": { "AcKd":[p0,p1,...], ... } }
            if (
                "strategy" in strat_raw
                and isinstance(strat_raw["strategy"], dict)
                and isinstance(action_labels, list)
                and len(action_labels) > 0
            ):
                per_combo = strat_raw["strategy"]
                # aggregate equal-weight across all combos present
                m = len(action_labels)
                acc = [0.0] * m
                cnt = 0
                for vec in per_combo.values():
                    if isinstance(vec, list) and len(vec) >= m:
                        ok = True
                        tmp = [
                            float(x) if isinstance(x, (int, float)) else None
                            for x in vec[:m]
                        ]
                        if any(x is None for x in tmp):
                            ok = False
                        if ok:
                            for i in range(m):
                                # mypy: tmp[i] is Optional[float]; we've checked it's all not None
                                val = cast(float, tmp[i])
                                acc[i] += val
                            cnt += 1
                if cnt > 0:
                    # mean over combos
                    acc = [x / cnt for x in acc]
                    strategy_kv = _kv_from_list(acc, action_labels)

            # If we still don't have strategy_kv, try generic numeric/nested-prob dicts
            if strategy_kv is None:
                direct = _find_first_dict_numeric({"strategy": strat_raw}, ["strategy"])
                if direct:
                    strategy_kv = direct

        # (B) List aligned with actions
        if strategy_kv is None and isinstance(strat_raw, list) and action_labels:
            strategy_kv = _kv_from_list(strat_raw, action_labels)

        # (C) Alternate keys (list-like first, then dict-like)
        if strategy_kv is None:
            if action_labels:
                alt_list = _find_first_list_of_len(
                    root,
                    [
                        "probs",
                        "policy",
                        "policies",
                        "avg_strategy",
                        "average_strategy",
                        "strategy_sum",
                        "sum_strategy",
                        "sigma",
                    ],
                    len(action_labels),
                )
                if alt_list:
                    strategy_kv = _kv_from_list(alt_list, action_labels)
            if strategy_kv is None:
                alt_dict = _find_first_dict_numeric(
                    root,
                    [
                        "probs",
                        "policy",
                        "policies",
                        "avg_strategy",
                        "average_strategy",
                        "strategy_sum",
                        "sum_strategy",
                    ],
                )
                if alt_dict:
                    strategy_kv = alt_dict

        # (D) Derive from regrets if present (regret matching)
        if strategy_kv is None and action_labels:
            regrets = _find_first_list_of_len(
                root, ["regret_sum", "regretsum", "regret"], len(action_labels)
            )
            if regrets:
                positives = [max(0.0, r) for r in regrets]
                s = sum(positives)
                if s > 0:
                    strategy_kv = {
                        action_labels[i]: positives[i] / s
                        for i in range(len(action_labels))
                    }
                else:
                    u = 1.0 / len(action_labels)
                    strategy_kv = {a: u for a in action_labels}

        # (E) Absolute last resort: uniform over legal actions
        if strategy_kv is None and action_labels:
            u = 1.0 / len(action_labels)
            strategy_kv = {a: u for a in action_labels}

        if not strategy_kv:
            raise UnsupportedSpotError("Solver output missing root strategy")

        # 4) Normalize action names → our bucket labels
        def nearest_bucket_of_percent(p: int) -> str:
            # Build (bucket_label, percent_int) pairs up-front to avoid Optional math
            pairs: list[tuple[str, int]] = []
            for b in req.bucket_labels:
                mp = _map_bucket_to_pot_percent(b)
                if mp is not None:
                    pairs.append((b, mp))

            if not pairs:
                return (
                    "jam"
                    if any(b.lower() == "jam" for b in req.bucket_labels)
                    else "call"
                )
            best_b, best_pp = pairs[0]
            best_d = abs(best_pp - p)
            for b, bp in pairs[1:]:
                d = abs(bp - p)
                if d < best_d:
                    best_d, best_b = d, b
            return best_b

        def map_action_to_label(a: str) -> Optional[str]:
            s = a.strip().lower()
            if s in {"check", "call", "fold"}:
                return s
            if "allin" in s or "all-in" in s or s == "all in":
                return (
                    "jam"
                    if any(b.lower() == "jam" for b in req.bucket_labels)
                    else "allin"
                )

            # e.g., "bet_66", "raise_100", "bet 2.000000", "raise 0.5"
            digits = re.findall(r"(\d+(?:\.\d+)?)", s)
            pct: Optional[int] = None
            if digits:
                try:
                    x = float(digits[-1])
                    if x <= 5.0:
                        pct = int(round(x * 100))  # treat as pot-multiple
                    else:
                        pct = int(round(x))  # treat as percent
                except ValueError:
                    pct = None
            if pct is not None:
                return nearest_bucket_of_percent(pct)

            if "bet" in s or "raise" in s:
                return nearest_bucket_of_percent(100)
            return None

        # Collapse any duplicate bucket mappings by summing probabilities
        bucket_strategy: Dict[str, float] = {}
        for act, p in strategy_kv.items():
            label = map_action_to_label(str(act))
            if label is None:
                continue
            bucket_strategy[label] = bucket_strategy.get(label, 0.0) + float(p)

        if not bucket_strategy:
            raise UnsupportedSpotError(
                "No usable strategy entries found in solver output"
            )

        # Normalize to 1 if necessary
        ssum = sum(bucket_strategy.values())
        if ssum > 0 and abs(ssum - 1.0) > 1e-6:
            for k in list(bucket_strategy.keys()):
                bucket_strategy[k] /= ssum

        # 5) Optional EVs (dict OR list aligned with actions) — map to buckets by averaging
        ev_map: Dict[str, float] = {}
        ev_dict = None
        if isinstance(root.get("ev"), dict):
            ev_dict = root["ev"]
        elif isinstance(root.get("ev"), list) and action_labels:
            ev_list = root["ev"]
            ev_dict = {
                action_labels[i]: float(ev_list[i])
                for i in range(min(len(ev_list), len(action_labels)))
                if isinstance(ev_list[i], (int, float))
            }
        if isinstance(ev_dict, dict):
            tmp_sum: Dict[str, float] = {}
            tmp_cnt: Dict[str, int] = {}
            for act, ev in ev_dict.items():
                if not isinstance(ev, (int, float)):
                    continue
                label = map_action_to_label(str(act))
                if label is None:
                    continue
                tmp_sum[label] = tmp_sum.get(label, 0.0) + float(ev)
                tmp_cnt[label] = tmp_cnt.get(label, 0) + 1
            for b, s_ev in tmp_sum.items():
                c = max(1, tmp_cnt.get(b, 1))
                ev_map[b] = s_ev / c

        # 6) Recommend argmax
        best = max(bucket_strategy.items(), key=lambda kv: kv[1])[0]
        return AdvicePayload(
            recommended_bucket=best, strategy=bucket_strategy, ev_map=ev_map
        )
