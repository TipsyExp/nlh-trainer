// frontend/utils/hash.ts
// Stable hashing helper for equity caching.
//
// The equity overlay caches results by a combination of hand id,
// decision index, street and an input signature.  To compute the
// signature we take a JSON serialisation of the relevant inputs and
// reduce it into a numeric hash.  This helper returns a string to
// ensure uniform keys in the cache.  The algorithm used here is a
// simple 32‑bit additive hash that is fast and deterministic.

export function stableHash(value: unknown): string {
  const json = JSON.stringify(value);
  let hash = 0;
  for (let i = 0; i < json.length; i++) {
    const ch = json.charCodeAt(i);
    hash = (hash + ch) | 0;
  }
  // Convert to unsigned 32‑bit representation to avoid negative keys.
  return String(hash >>> 0);
}
