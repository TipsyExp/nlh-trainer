from pathlib import Path
from backend.adapters.solver.texassolver_adapter import TexasSolverAdapter, SolveRequest

def test_write_input_script_flop_only(tmp_path: Path):
    adapter = TexasSolverAdapter()
    req = SolveRequest(
        street="flop",
        board=["Qs","Jh","2h"],
        pot=300,
        ip_stack=9900,
        oop_stack=9900,
        ip_range="AA,KK,QQ,JJ,TT,AKs,AQs",
        oop_range="AA,KK,QQ,JJ,TT,AKs,AQo",
        bucket_labels=["50%", "100%", "jam"],
        spot="SRP",
    )
    inp = tmp_path / "node_input.txt"
    out = tmp_path / "output_result.json"
    adapter._write_input_script(req, inp, out)  # type: ignore[attr-defined]

    text = inp.read_text(encoding="utf-8")
    # Current street configured
    assert "set_bet_sizes oop,flop,bet,50" in text
    assert "set_bet_sizes ip,flop,bet,100" in text
    assert "set_bet_sizes ip,flop,allin" in text

    # No turn / river programming
    assert "turn" not in text
    assert "river" not in text
