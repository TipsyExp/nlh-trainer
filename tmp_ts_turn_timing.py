# tmp_ts_turn_timing.py
import time
from backend.adapters.solver.texassolver_adapter import TexasSolverAdapter, SolveRequest
from backend.coach.postflop.ranges import get_default_villain_range

adapter = TexasSolverAdapter()

street = "turn"
board = ["9h", "Jh", "Jc", "3s"]
pot = 940
ip_stack = 9530
oop_stack = 9530

ip_range = get_default_villain_range(street=street, role="ip")
oop_range = get_default_villain_range(street=street, role="oop")

req = SolveRequest(
    street=street,
    board=board,
    pot=pot,
    ip_stack=ip_stack,
    oop_stack=oop_stack,
    ip_range=ip_range,
    oop_range=oop_range,
    bucket_labels=["25%", "40%", "67%", "jam"],
    spot="SRP",
)

print("Solving turn node...")
t0 = time.time()
res = adapter.solve(req)
dt = time.time() - t0
print("Result:", res)
print("Elapsed: %.3f seconds" % dt)
