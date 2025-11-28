// frontend/utils/coachMapping.ts
// Mapping helper for coach bucket labels to UI action keys.
//
// The coach returns high-level buckets such as 'fold', 'call', '2.5x',
// '2.5xR', '3.0xR', 'raise_2.5x', 'jam', and (postflop) pot-percentage
// labels such as '33%', 'bet_50%', 'raise_75%'.
//
// The UI presents buttons for specific actions, which may include
// dynamic raise sizes based on presets (e.g. ['2x','2.5x','3x'] for
// preflop, ['33%','50%','75%','100%'] for postflop). This function
// normalises the coach bucket into an action key used by the action
// bar. When the bucket specifies a size that is not present in the
// presets, the nearest available size is chosen. If nothing matches a
// reasonable fallback the function returns null to indicate that no
// highlight should be applied.

/**
 * Extract a simple "<number>%" label from a bucket, e.g.:
 *   "33%"         -> "33%"
 *   "bet_50%"     -> "50%"
 *   "raise-75%ps" -> "75%"
 *
 * Returns null if no percentage is present.
 */
function extractPercentLabel(bucket: string): string | null {
  const m = String(bucket).match(/(\d+(?:\.\d+)?)%/);
  if (!m) return null;
  const n = Number(m[1]);
  if (!Number.isFinite(n) || n <= 0) return null;
  // Normalise formatting (no spaces, canonical "%").
  return `${n}%`;
}

/**
 * Convert a coach bucket into a UI action key.
 *
 * @param bucket  The bucket returned by the coach
 *                (e.g. 'fold', '2.5x', '2.5xR', 'raise_2.5x', '75%', 'bet_50%').
 * @param toCall  The amount required to call; determines whether 'call' or 'check' is appropriate.
 * @param presets The list of preset raise multipliers / percentages available
 *                to the player (e.g. ['2x','2.5x','3x'] or ['33%','50%','75%','100%']).
 * @returns       A string matching one of the UI button keys
 *                (e.g. 'fold', 'call', 'check', '2.5x', '75%', 'jam')
 *                or null if none applies.
 */
export function mapCoachToAction(
  bucket: string | undefined,
  toCall: number,
  presets: string[]
): string | null {
  if (!bucket) return null;
  const b = bucket.toLowerCase();

  // Simple one-to-one mappings.
  if (b === "fold") return "fold";
  if (b === "call" || b === "check") {
    return toCall > 0 ? "call" : "check";
  }

  // Normalise jam/all-in labels.
  if (b === "jam" || b === "all_in" || b === "allin" || b === "all-in") {
    return "jam";
  }

  // ---------------------------------------------------------------------------
  // Percentage buckets (postflop pot-based sizing).
  // ---------------------------------------------------------------------------
  // First, try to interpret the bucket as some "<number>%" size; this
  // covers "75%", "bet_75%", "raise-50%", etc.
  const percentLabel = extractPercentLabel(bucket);
  if (percentLabel) {
    const target = parseFloat(percentLabel.replace("%", ""));
    let direct: string | null = null;

    // Try direct match first (case-insensitive, whitespace-agnostic).
    for (const p of presets) {
      if (p && p.toLowerCase().replace(/\s+/g, "") === percentLabel.toLowerCase()) {
        direct = p;
        break;
      }
    }
    if (direct) return direct;

    // Otherwise, find the nearest percentage preset by numeric distance.
    let best: string | null = null;
    let bestDiff = Infinity;
    for (const p of presets) {
      const pm = String(p).match(/(\d+(?:\.\d+)?)%/);
      if (!pm) continue;
      const n = parseFloat(pm[1]);
      if (!Number.isFinite(n)) continue;
      const diff = Math.abs(n - target);
      if (diff < bestDiff) {
        bestDiff = diff;
        best = p;
      }
    }
    if (best) return best;
  }

  // ---------------------------------------------------------------------------
  // Direct preset-style buckets for X-multipliers (preflop) or literal labels.
  // ---------------------------------------------------------------------------
  const directMatch = presets.find((p) => {
    const pl = p.toLowerCase();
    return pl === b || `${pl}r` === b;
  });
  if (directMatch) {
    return directMatch;
  }

  // ---------------------------------------------------------------------------
  // Match raise sizes like 'raise_2.5x', 'raise2.5x', 'raise-2.5x',
  // and tolerate a trailing "r" suffix (e.g. 'raise_2.5xr').
  // ---------------------------------------------------------------------------
  const base = b.endsWith("r") ? b.slice(0, -1) : b;
  const m = base.match(/^raise[_-]?(\d+(?:\.\d+)?x?)$/);
  if (m) {
    let size = m[1];
    // Ensure a trailing 'x' suffix for comparison.
    if (!/x$/.test(size)) {
      size = `${size}x`;
    }
    // Direct match.
    if (presets.includes(size)) {
      return size;
    }
    // Find nearest available size by numeric difference.
    const target = parseFloat(size.replace(/x$/, ""));
    if (!isFinite(target)) {
      return null;
    }
    let best: string | null = null;
    let bestDiff = Infinity;
    for (const p of presets) {
      const n = parseFloat(p.replace(/x$/, ""));
      if (!isFinite(n)) continue;
      const diff = Math.abs(n - target);
      if (diff < bestDiff) {
        bestDiff = diff;
        best = p;
      }
    }
    return best;
  }

  // Unknown / unsupported bucket label.
  return null;
}
