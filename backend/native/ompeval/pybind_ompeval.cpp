// backend/native/ompeval/pybind_ompeval.cpp
//
// Pybind11 bindings for OMPEval (https://github.com/zekyll/OMPEval)
// Exposes a small, stable surface for NLH equity calc with ranges.
//
// Build notes:
// - Requires OMPEval headers/libs in your include/link path.
// - Requires pybind11 (headers).
// - Intended module name: `ompeval` (importable as backend.native.ompeval).
//
// Exposed functions:
//   - calc_equity_ranges(players, board=[], dead=[], exact=False,
//                       iters=-1, threads=0, stderr_target=0.0,
//                       update_interval=0.25, timeout_ms=-1) -> dict
//   - supports_ranges() -> bool
//   - max_players() -> int
//
// Returned dict (shape meant to be normalized upstream by Python adapter):
// {
//   "backend": "ompeval",
//   "mode": "ranges",
//   "n_players": N,
//   "board": ["As","Kd","2c"],            // as passed
//   "dead":  [...],                       // as passed
//   "exact": bool,
//   "iters": int,                         // -1 if not bounded by iters
//   "players": [                          // per-player summary
//      {"win": int, "tie": int, "equity": float}, ...
//   ],
//   "raw": {                              // diagnostics (stable-ish keys)
//      "hands": uint64,                   // samples actually processed
//      "time_sec": double,
//      "boards_per_sec": double,
//      "stdev": double,                   // MC only
//      "stderr_target": double,
//      "timeout_ms": int,
//      "iters_target": int,
//      "threads": int,
//      "update_interval": double,
//      "stopped_early": bool,
//      "stop_reason": "timeout|iters|stderr|complete|unknown",
//      "simulations": uint64              // alias for hands
//   }
// }

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <omp/EquityCalculator.h>
#include <omp/HandEvaluator.h>
#include <chrono>
#include <atomic>
#include <string>
#include <vector>
#include <sstream>
#include <algorithm>

namespace py = pybind11;

// Join ["As","Kd","2c"] -> "AsKd2c"
static std::string join_cards(const std::vector<std::string>& cards) {
    std::ostringstream oss;
    for (const auto& c : cards) {
        oss << c;
    }
    return oss.str();
}

// Convert card list to OMPEval bitmask via CardRange helper.
static uint64_t cards_to_mask(const std::vector<std::string>& cards) {
    const std::string joined = join_cards(cards);
    if (joined.empty()) return 0ULL;
    return omp::CardRange::getCardMask(joined.c_str());
}

static py::dict calc_equity_ranges(
    const std::vector<std::string>& player_ranges,
    const std::vector<std::string>& board_cards = {},
    const std::vector<std::string>& dead_cards = {},
    bool exact = false,
    // Target number of samples for MC; -1 means "no explicit iters target"
    long long iters = -1,
    int threads = 0,
    double stderr_target = 0.0,
    double update_interval = 0.25,
    // Soft timeout; -1 disables. Enforced in callback.
    long long timeout_ms = -1
) {
    // Basic input checks (let Python-side do the rest).
    if (player_ranges.size() < 2) {
        throw std::invalid_argument("at least two player ranges are required");
    }
    if (player_ranges.size() > 6) {
        throw std::invalid_argument("ompeval supports up to 6 players");
    }

    omp::EquityCalculator eq;

    const uint64_t board_mask = cards_to_mask(board_cards);
    const uint64_t dead_mask  = cards_to_mask(dead_cards);

    std::atomic<bool> stopped(false);
    std::string stop_reason = "complete";

    const auto t0 = std::chrono::steady_clock::now();
    const auto timeout_enabled = (timeout_ms >= 0);
    const auto iters_enabled = (iters >= 0);

    // Normalize targets
    const double std_err_target = std::max(0.0, stderr_target);
    const double cb_interval    = std::max(0.01, update_interval);

    // Callback to enforce timeout/iters/early-stop-by-stdErr (MC only)
    auto callback = [&](const omp::EquityCalculator::Results& r) {
        if (stopped.load()) return;
        // Timeout check
        if (timeout_enabled) {
            const auto now     = std::chrono::steady_clock::now();
            const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(now - t0).count();
            if (elapsed >= timeout_ms) {
                stop_reason = "timeout";
                stopped.store(true);
                eq.stop();
                return;
            }
        }
        // Iters (samples) check
        if (!exact && iters_enabled && static_cast<long long>(r.hands) >= iters) {
            stop_reason = "iters";
            stopped.store(true);
            eq.stop();
            return;
        }
        // Std error check (only meaningful for MC)
        if (!exact && std_err_target > 0.0) {
            if (r.stdev <= std_err_target && r.hands > 0) {
                stop_reason = "stderr";
                stopped.store(true);
                eq.stop();
                return;
            }
        }
    };

    // Start calculation
    // Signature: start(ranges, boardMask, deadMask, enumerateAll, stdErrMargin, callback, updateInterval, threads)
    eq.start(player_ranges, board_mask, dead_mask, exact, std_err_target, callback, cb_interval, static_cast<unsigned>(std::max(0, threads)));
    eq.wait();

    auto results = eq.getResults();

    // Prepare per-player summary (tie count not provided by OMPEval; set 0)
    py::list players_out;
    const size_t n = player_ranges.size();
    for (size_t i = 0; i < n; ++i) {
        py::dict p;
        uint64_t win = (i < results.wins.size() ? results.wins[i] : 0ULL);
        double   eqi = (i < results.equity.size() ? results.equity[i] : 0.0);
        p["win"]    = py::int_(win);
        p["tie"]    = py::int_(0);
        p["equity"] = py::float_(eqi);
        players_out.append(p);
    }

    // Compute boards/sec independent of internal "speed"
    const double boards_per_sec = (results.time > 0.0)
        ? static_cast<double>(results.hands) / results.time
        : 0.0;

    // If we didn't hit any explicit stop condition and not exact, leave "complete"
    if (!stopped.load()) {
        stop_reason = "complete";
    }

    // raw diagnostics blob
    py::dict raw;
    raw["hands"]           = py::int_(results.hands);
    raw["time_sec"]        = py::float_(results.time);
    raw["boards_per_sec"]  = py::float_(boards_per_sec);
    raw["stdev"]           = py::float_(results.stdev);
    raw["stderr_target"]   = py::float_(std_err_target);
    raw["timeout_ms"]      = py::int_(timeout_ms);
    raw["iters_target"]    = py::int_(iters);
    raw["threads"]         = py::int_(threads);
    raw["update_interval"] = py::float_(cb_interval);
    raw["stopped_early"]   = py::bool_(stopped.load());
    raw["stop_reason"]     = py::str(stop_reason);
    raw["simulations"]     = py::int_(results.hands); // alias for compatibility

    // Top-level dict (normalized upstream by Python adapter)
    py::dict out;
    out["backend"]    = py::str("ompeval");
    out["mode"]       = py::str("ranges");
    out["n_players"]  = py::int_(static_cast<int>(n));
    out["board"]      = py::cast(board_cards);
    out["dead"]       = py::cast(dead_cards);
    out["exact"]      = py::bool_(exact);
    out["iters"]      = py::int_(iters);
    out["players"]    = std::move(players_out);
    out["raw"]        = std::move(raw);

    return out;
}

PYBIND11_MODULE(ompeval, m) {
    m.doc() = "OMPEval Python bindings for NLH equity (ranges, multiway)";

    m.def(
        "calc_equity_ranges",
        &calc_equity_ranges,
        py::arg("players"),
        py::arg("board") = std::vector<std::string>{},
        py::arg("dead") = std::vector<std::string>{},
        py::arg("exact") = false,
        py::arg("iters") = -1,
        py::arg("threads") = 0,
        py::arg("stderr_target") = 0.0,
        py::arg("update_interval") = 0.25,
        py::arg("timeout_ms") = -1,
        R"pbdoc(
            Calculate multiway equity using OMPEval.

            Parameters:
              players         List[str]   Range strings per player (Equilab-like).
              board           List[str]   Optional board cards (["As","Kd","2c"]).
              dead            List[str]   Optional dead cards list.
              exact           bool        True for full enumeration when feasible.
              iters           int         Target samples for MC; -1 to disable.
              threads         int         Worker threads (0 = auto).
              stderr_target   float       Early-stop MC when stdev <= target (<=0 disables).
              update_interval float       Callback polling interval in seconds.
              timeout_ms      int         Soft timeout; -1 disables.

            Returns:
              dict with backend='ompeval', mode='ranges', per-player equities, and diagnostics in 'raw'.
        )pbdoc"
    );

    m.def("supports_ranges", []() { return true; }, "Whether ranges are supported (always true).");
    m.def("max_players",     []() { return 6;    }, "Maximum supported players for OMPEval (6).");
    m.attr("__version__") = "0.1.0";
}
