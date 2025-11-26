# test_texas_solver_runner.py
from __future__ import annotations

from typing import Any, Dict

import pytest

from backend.solvers.texas_solver import runner


# --- helpers ---------------------------------------------------------------


def _get_runner_cls():
    """
    Resolve the runner class in a tolerant way so small refactors
    don't immediately break tests.
    """
    if hasattr(runner, "TexasSolverRunner"):
        return runner.TexasSolverRunner  # type: ignore[attr-defined]
    if hasattr(runner, "Runner"):
        return runner.Runner  # type: ignore[attr-defined]
    pytest.skip(
        "No TexasSolver runner class exposed in backend.solvers.texas_solver.runner"
    )


# --- tests -----------------------------------------------------------------


def test_default_profile_discoverable() -> None:
    """
    The runner module should expose at least one profile, and if a
    DEFAULT_PROFILE_NAME is defined, that profile must be discoverable.
    """
    if not hasattr(runner, "available_profiles"):
        pytest.skip("runner.available_profiles() not implemented")

    profiles = runner.available_profiles()  # type: ignore[attr-defined]
    assert isinstance(profiles, list)
    # At least one profile should be present (e.g. 'hu_100bb_default')
    assert profiles, "expected at least one TexasSolver profile"

    default_name = getattr(runner, "DEFAULT_PROFILE_NAME", None)
    if isinstance(default_name, str) and default_name:
        assert default_name in profiles

        if hasattr(runner, "get_profile"):
            profile = runner.get_profile(default_name)  # type: ignore[attr-defined]
            # Basic shape checks; we don't care about exact dataclass type here.
            assert getattr(profile, "name", None) == default_name
            tpl_path = getattr(profile, "template_path", None)
            # Template path should either be a real file or at least a Path-like object
            if tpl_path is not None:
                try:
                    # tolerate Path-like objects
                    exists = tpl_path.exists()  # type: ignore[attr-defined]
                except Exception:
                    exists = False
                assert (
                    exists
                ), f"template_path for profile {default_name!r} does not exist"


def test_build_input_script_includes_dynamic_lines() -> None:
    """
    The runner's script builder should embed key dynamic fields (pot, board,
    ranges) into the output script, regardless of what the static template
    contains.
    """
    RunnerCls = _get_runner_cls()
    runner_obj = RunnerCls()  # type: ignore[call-arg]

    build = getattr(runner_obj, "build_input_script", None)
    if build is None:
        pytest.skip("TexasSolverRunner.build_input_script() not implemented")

    # Try to pass profile_name if the signature accepts it; otherwise omit.
    kw: Dict[str, Any] = dict(
        street="flop",
        pot=10,
        board=["Ah", "Kd", "3s"],
        ip_stack=90,
        oop_stack=80,
        ip_range="AA,KK,QQ",
        oop_range="JJ,TT,99",
        bucket_labels=["check", "33%", "75%", "jam"],
        output_json="out.json",
    )

    default_name = getattr(runner, "DEFAULT_PROFILE_NAME", None)
    code = getattr(build, "__code__", None)
    varnames = list(code.co_varnames) if code is not None else []

    if default_name and "profile_name" in varnames:
        kw["profile_name"] = default_name

    script = build(**kw)  # type: ignore[misc]
    assert isinstance(script, str)

    # Core dynamic expectations:
    # - pot size should be explicitly set
    assert "set_pot 10" in script

    # - board cards should appear in a set_board line (allowing for optional spaces)
    assert "set_board Ah,Kd,3s" in script or "set_board Ah, Kd, 3s" in script

    # - ranges must be wired through
    assert "set_range_ip AA,KK,QQ" in script
    assert "set_range_oop JJ,TT,99" in script

    # It's okay if stack / dump_result / bet size config comes from the template;
    # we don't assert on those here to keep the test flexible.
