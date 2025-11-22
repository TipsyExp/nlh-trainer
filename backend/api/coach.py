# backend/api/coach.py
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Literal, Optional, cast

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.adapters.engines import get_adapter
from backend.api.session import get_session_state
from backend.api.hand import (
    _auto_advance_bots,
    _to_public_state,
)
from backend.adapters.solver.texassolver_adapter import (
    TexasSolverAdapter,
    SolveRequest,
    CoachDisabledError,
    UnsupportedSpotError,
)
from backend.coach.preflop.service import PreflopAdvisorService
from backend.coach import decision_context as _decision_context
from backend.coach.postflop import service as _postflop_service
from backend.schemas.advice import (
    AdviceMeta,
    AdviceRecommendation,
    AdviceV1,
    StrategyPart,
)
from backend.config import COACH_ENABLED as CONFIG_COACH_ENABLED
from backend.services.equity.service import EquityService
from backend.logger import log_preflop_advice, log_coach_advice

router = APIRouter(tags=["coach"])

StreetLiteral = Literal["preflop", "flop", "turn", "river", "showdown", "unknown"]


def _normalize_street(value: str) -> StreetLiteral:
    """
    Normalize arbitrary street strings into the AdviceMeta street literal set.
    """
    s = value.lower()
    if s in ("preflop", "flop", "turn", "river", "showdown", "unknown"):
        return cast(StreetLiteral, s)
    return "unknown"


def _coach_enabled() -> bool:
    """
    Determine whether the coach is enabled.

    Priority:
      1. Explicit COACH_ENABLED environment variable (for tests / runtime overrides).
      2. backend.config.COACH_ENABLED (loaded from .env at startup).

    This helper is used to gate both `/api/coach/preflop` and `/api/coach/advice`.
    """
    env_val = os.environ.get("COACH_ENABLED")
    if env_val is not None:
        v = env_val.strip().lower()
        return v in {"1", "true", "yes", "on"}
    return bool(CONFIG_COACH_ENABLED)


def _get_preflop_service() -> Optional[PreflopAdvisorService]:
    """
    Construct a fresh PreflopAdvisorService.

    This is intentionally *not* cached so tests that tweak environment
    variables (e.g. PREFLOP_CHART_PATHS) see effects per-request.
    Any construction error is treated as "charts not configured".
    """
    try:
        return PreflopAdvisorService(equity_service=EquityService())
    except Exception:
        return None


def _current_hand_id_str() -> str:
    """Return current adapter hand id in 'H#' form; raise if none."""
    h = getattr(get_adapter(), "hand_id", None)
    if not h:
        raise RuntimeError("no hand in progress")
    return f"H{h}" if isinstance(h, int) else str(h)


# -------------------------
# GET /api/coach/preflop
# -------------------------
@router.get("/coach/preflop")
def get_preflop_advice(
    hand_id: str = Query(...),
    idx: int = Query(0),
) -> JSONResponse:
    """
    Preflop advisor endpoint (chart-first, equity fallback when available).

    Behaviour:
      - 501 if COACH_ENABLED is false.
      - 501 if no charts are configured / loadable.
      - 200 with advice payload otherwise (source ∈ {"chart","equity","rule"}).

    Response shape (legacy, preflop-only):

        {
          "source": "chart" | "equity" | "rule",
          "bucket": "2.5x" | "jam" | "fold" | ...,
          "rationale": "...",
          "strategy_bar": { [bucketLabel: string]: number }
        }

    New UI work should prefer `/api/coach/advice` and the unified Advice
    payload; this route is retained for compatibility.
    """
    if not _coach_enabled():
        return JSONResponse(
            {"detail": "preflop coach is disabled"},
            status_code=501,
        )

    svc = _get_preflop_service()
    if svc is None or not svc.has_charts:
        return JSONResponse(
            {"detail": "preflop coach charts not configured"},
            status_code=501,
        )

    try:
        advice = svc.get_advice(hand_id=hand_id, idx=idx)
    except LookupError as e:
        # No matching chart entry and no usable fallback
        return JSONResponse({"detail": str(e)}, status_code=404)
    except ValueError as e:
        # Bad input/context formation
        return JSONResponse({"detail": str(e)}, status_code=400)
    except Exception as e:
        # Generic advisor failure
        return JSONResponse(
            {"detail": f"preflop coach error: {e}"},
            status_code=500,
        )

    payload: Dict[str, Any] = {
        "source": advice.source,
        "bucket": advice.bucket,
        "rationale": advice.rationale,
        "strategy_bar": advice.strategy_bar,
    }

    # Best-effort snapshot logging (gated by config in backend.logger).
    try:
        log_preflop_advice(hand_id=str(hand_id), idx=int(idx), advice=payload)
    except Exception:
        # Never fail the request on logging errors.
        pass

    return JSONResponse(payload, status_code=200)


# -------------------------
# GET /api/coach/advice
# -------------------------
@router.get("/coach/advice")
def get_advice(hand_id: str = Query(...), idx: int = Query(0)) -> JSONResponse:
    """
    Unified coach endpoint (AdviceV1).

    Behaviour:

      * When COACH_ENABLED is false:
          - Returns 501 with status="disabled".

      * When a valid decision context can be built:
          - Preflop:
              - Delegates to the preflop advisor and wraps its output into
                AdviceV1 (source ∈ {"chart","equity","rule"}).
          - Postflop (flop/turn/river, HU + multiway):
              - Delegates to the postflop coach v1 (equity-based).
          - Other spots:
              - Returns AdviceV1 with status="unsupported".

      * When the decision context cannot be resolved:
          - Returns 400 with status="not_found" for hand/index mismatches.
          - Returns 500 with status="error" for unexpected failures.
    """

    def _respond_with_logging(advice: AdviceV1, status_code: int) -> JSONResponse:
        """
        Wrap AdviceV1 into a JSONResponse and best-effort log it as a
        coach_advice snapshot. Logging is gated by LOG_COACH_ADVICE inside
        backend.logger and never affects the HTTP response.
        """
        try:
            log_coach_advice(
                hand_id=str(hand_id),
                idx=int(idx),
                advice=advice.model_dump(),
            )
        except Exception:
            # Logging must never affect primary control flow.
            pass
        return JSONResponse(advice.model_dump(), status_code=status_code)

    if not _coach_enabled():
        advice = AdviceV1(
            version=1,
            status="disabled",
            meta=AdviceMeta(
                street="unknown",
                n_players=0,
                hero_seat=0,
                source="rule",
            ),
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale="Coach is disabled by configuration.",
        )
        return _respond_with_logging(advice, status_code=501)

    # Build a shared decision context. Errors here are treated as input
    # / state issues rather than 500s.
    try:
        ctx = _decision_context.build_decision_context(hand_id=hand_id, idx=idx)
    except ValueError as e:
        advice = AdviceV1(
            version=1,
            status="not_found",
            meta=AdviceMeta(
                street="unknown",
                n_players=0,
                hero_seat=0,
                source="rule",
            ),
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale=f"Decision context not found: {e}",
        )
        return _respond_with_logging(advice, status_code=400)
    except RuntimeError as e:
        advice = AdviceV1(
            version=1,
            status="not_found",
            meta=AdviceMeta(
                street="unknown",
                n_players=0,
                hero_seat=0,
                source="rule",
            ),
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale=f"No active hand in progress: {e}",
        )
        return _respond_with_logging(advice, status_code=400)
    except Exception as e:
        advice = AdviceV1(
            version=1,
            status="error",
            meta=AdviceMeta(
                street="unknown",
                n_players=0,
                hero_seat=0,
                source="rule",
            ),
            recommendation=None,
            equity=None,
            thresholds=None,
            rationale=f"Failed to build decision context: {e}",
        )
        return _respond_with_logging(advice, status_code=500)

    street = ctx.street.lower()

    # Preflop: delegate to existing preflop advisor and wrap into AdviceV1.
    if street == "preflop":
        svc = _get_preflop_service()
        if svc is None or not svc.has_charts:
            advice = AdviceV1(
                version=1,
                status="unsupported",
                meta=AdviceMeta(
                    street="preflop",
                    n_players=ctx.n_players,
                    hero_seat=ctx.hero_seat,
                    source="rule",
                ),
                recommendation=None,
                equity=None,
                thresholds=None,
                rationale="Preflop coach charts are not configured.",
            )
            return _respond_with_logging(advice, status_code=200)

        try:
            pre = svc.get_advice(hand_id=hand_id, idx=idx)
        except LookupError as e:
            advice = AdviceV1(
                version=1,
                status="not_found",
                meta=AdviceMeta(
                    street="preflop",
                    n_players=ctx.n_players,
                    hero_seat=ctx.hero_seat,
                    source="rule",
                ),
                recommendation=None,
                equity=None,
                thresholds=None,
                rationale=str(e),
            )
            return _respond_with_logging(advice, status_code=200)
        except ValueError as e:
            advice = AdviceV1(
                version=1,
                status="error",
                meta=AdviceMeta(
                    street="preflop",
                    n_players=ctx.n_players,
                    hero_seat=ctx.hero_seat,
                    source="rule",
                ),
                recommendation=None,
                equity=None,
                thresholds=None,
                rationale=f"Preflop coach input error: {e}",
            )
            return _respond_with_logging(advice, status_code=200)
        except Exception as e:
            advice = AdviceV1(
                version=1,
                status="error",
                meta=AdviceMeta(
                    street="preflop",
                    n_players=ctx.n_players,
                    hero_seat=ctx.hero_seat,
                    source="rule",
                ),
                recommendation=None,
                equity=None,
                thresholds=None,
                rationale=f"Preflop coach failure: {e}",
            )
            return _respond_with_logging(advice, status_code=200)

        strategy_bar_list = [
            StrategyPart(action=action, weight=float(weight))
            for action, weight in pre.strategy_bar.items()
        ]

        advice = AdviceV1(
            version=1,
            status="ok",
            meta=AdviceMeta(
                street="preflop",
                n_players=ctx.n_players,
                hero_seat=ctx.hero_seat,
                source=pre.source,
            ),
            recommendation=AdviceRecommendation(
                bucket=pre.bucket,
                strategy_bar=strategy_bar_list,
            ),
            equity=None,
            thresholds=None,
            rationale=pre.rationale,
        )
        return _respond_with_logging(advice, status_code=200)

    # Postflop (HU + multiway): delegate to postflop coach v1.
    if street in {"flop", "turn", "river"}:
        advice = _postflop_service.get_postflop_advice(ctx)
        # Postflop coach v1 always returns a well-formed AdviceV1. The status
        # field indicates whether the spot was actually supported.
        return _respond_with_logging(advice, status_code=200)

    # Everything else (unknown street, showdown, etc.) is currently unsupported.
    advice = AdviceV1(
        version=1,
        status="unsupported",
        meta=AdviceMeta(
            street=_normalize_street(street),
            n_players=ctx.n_players,
            hero_seat=ctx.hero_seat,
            source="rule",
        ),
        recommendation=None,
        equity=None,
        thresholds=None,
        rationale="Coach does not yet support this spot.",
    )
    return _respond_with_logging(advice, status_code=200)


# -------------------------
# Dev/Test endpoint to exercise the adapter directly
# POST /api/coach/test_solve
# -------------------------


class SolveRequestModel(BaseModel):
    street: Literal["flop", "turn", "river"]
    board: List[str] = Field(..., description='["Ah","Kd","3s"]')
    pot: int
    ip_stack: int
    oop_stack: int
    ip_range: str
    oop_range: str
    bucket_labels: List[str]
    spot: Literal["SRP", "3BP"] = "SRP"


@router.post("/coach/test_solve")
def post_test_solve(req: SolveRequestModel = Body(...)) -> JSONResponse:
    """
    Dev-only endpoint to exercise the TexasSolver adapter directly.

    This bypasses the per-hand context builder and unified advice shape and is
    intended purely for local experimentation and QA. The response shape
    mirrors the current solver payload used historically by /api/coach/advice.
    """
    if not _coach_enabled():
        return JSONResponse({"meta": {"status": "disabled"}}, status_code=501)

    # Intentionally uncached for a clean dev endpoint
    adapter = TexasSolverAdapter()
    started = time.perf_counter()
    try:
        advice_raw = adapter.solve(
            SolveRequest(
                street=req.street,
                board=req.board,
                pot=req.pot,
                ip_stack=req.ip_stack,
                oop_stack=req.oop_stack,
                ip_range=req.ip_range,
                oop_range=req.oop_range,
                bucket_labels=req.bucket_labels,
                spot=req.spot,
            )
        )
        advice = dict(advice_raw)  # type: ignore[arg-type]
        latency_ms = (time.perf_counter() - started) * 1000.0

        recommended_bucket = advice.get("recommended_bucket", "")
        strategy = advice.get("strategy", {})
        ev_map = advice.get("ev_map", {})

        payload: Dict[str, Any] = {
            "recommended_bucket": recommended_bucket,
            "strategy": strategy,
            "ev_map": ev_map,
            "meta": {
                "status": "ok",
                "cached": False,
                "latency_ms": round(latency_ms, 3),
                "node_key": None,
            },
        }
        return JSONResponse(payload, status_code=200)

    except CoachDisabledError:
        return JSONResponse({"meta": {"status": "disabled"}}, status_code=501)

    except UnsupportedSpotError as e:
        msg = str(e).lower()
        if "timed out" in msg or "timeout" in msg:
            return JSONResponse({"meta": {"status": "timeout"}}, status_code=504)
        return JSONResponse({"meta": {"status": "unsupported"}}, status_code=501)

    except Exception:
        return JSONResponse({"meta": {"status": "error"}}, status_code=500)


# ------------------------------------------
# POST /api/coach/ensure_progress (production)
# ------------------------------------------
@router.post("/coach/ensure_progress")
def post_ensure_progress() -> JSONResponse:
    """
    Production-safe bot trigger: if it's a bot's turn, advance bots until it's
    the human's turn (or hand ends). Returns the updated state plus the list of
    bot actions taken. If it's already the human's turn, no-ops and returns
    the current state with an empty list.

    This endpoint is orthogonal to the coaching payload shape; it simply
    coordinates engine progress.
    """
    adapter = get_adapter()
    ss = get_session_state()
    human_seat = ss.human_seat

    # Resolve current hand id (error if none)
    try:
        hand_id = _current_hand_id_str()
    except RuntimeError:
        return JSONResponse(
            {
                "ok": False,
                "bots_applied": [],
                "state": {},
                "meta": {"status": "no_hand"},
            },
            status_code=400,
        )

    # If it's a bot to act, advance; otherwise just return state
    actor = adapter.next_actor()
    bots: List[Dict[str, Any]] = []
    if actor and int(actor.get("seat", -1)) != int(human_seat):
        try:
            bots = _auto_advance_bots(hand_id, human_seat)
        except RuntimeError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

    # Return current snapshot (post-bot if any advanced)
    state = _to_public_state(human_seat)
    return JSONResponse(
        {"ok": True, "bots_applied": bots, "state": state}, status_code=200
    )
