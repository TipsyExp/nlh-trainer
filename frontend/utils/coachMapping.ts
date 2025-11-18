// frontend/utils/coachMapping.ts
// Mapping helper for coach bucket labels to UI action keys.
//
// The coach returns high-level buckets such as 'fold', 'call', 'raise_2.5x',
// and 'jam'.  The UI presents buttons for specific actions, which may
// include dynamic raise sizes based on presets (e.g. 2.5x, 3x).  This
// function normalises the coach bucket into an action key used by the
// action bar.  When the bucket specifies a raise size that is not
// present in the presets, the nearest available size is chosen.  If
// nothing matches a reasonable fallback the function returns null to
// indicate that no highlight should be applied.

/**
 * Convert a coach bucket into a UI action key.
 *
 * @param bucket The bucket returned by the coach (e.g. 'fold', 'raise_2.5x').
 * @param toCall The amount required to call; determines whether 'call' or 'check' is appropriate.
 * @param presets The list of preset raise multipliers available to the player (e.g. ['2x','2.5x','3x']).
 * @returns A string matching one of the UI button keys (e.g. 'fold', 'call', 'check', '2.5x', 'jam') or null if none applies.
 */
export function mapCoachToAction(
  bucket: string | undefined,
  toCall: number,
  presets: string[]
): string | null {
  if (!bucket) return null;
  const b = bucket.toLowerCase();
  if (b === 'fold') return 'fold';
  if (b === 'call' || b === 'check') {
    return toCall > 0 ? 'call' : 'check';
  }
  // Normalise jam/all-in labels
  if (b === 'jam' || b === 'all_in' || b === 'allin' || b === 'all-in') {
    return 'jam';
  }
  // Match raise sizes like 'raise_2.5x', 'raise2.5x', or 'raise-2.5x'
  const m = b.match(/^raise[_-]?(\d+(?:\.\d+)?x?)$/);
  if (m) {
    let size = m[1];
    // Ensure a trailing 'x' suffix for comparison
    if (!/x$/.test(size)) {
      size = `${size}x`;
    }
    // Direct match
    if (presets.includes(size)) {
      return size;
    }
    // Find nearest available size by numeric difference
    const target = parseFloat(size.replace(/x$/, ''));
    let best: string | null = null;
    let bestDiff = Infinity;
    for (const p of presets) {
      const n = parseFloat(p.replace(/x$/, ''));
      const diff = Math.abs(n - target);
      if (diff < bestDiff) {
        bestDiff = diff;
        best = p;
      }
    }
    return best;
  }
  return null;
}