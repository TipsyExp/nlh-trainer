// frontend/types/meta.ts
// Types describing the backend capabilities exposed by GET /api/meta.
//
// The guidance overlay fetches a meta snapshot once per session to learn
// whether the equity engine supports range-based evaluations and how many
// players can be simulated.  It also exposes the backend name so the UI
// can display a badge.  These interfaces mirror the shape of the
// backend response but apply conservative defaults when fields are
// missing.

/** Supported equity backends.  Additional backends may be added in the
 *  future; unknown values should be treated as 'unknown'. */
export type EquityBackend = 'ompeval' | 'eval7' | 'pokerkit' | 'unknown';

/** Capabilities for the equity endpoint returned by GET /api/meta. */
export interface EquityMeta {
  /** Name of the backend performing equity calculations. */
  backend: EquityBackend;
  /** True when the backend can evaluate ranges vs hands. */
  supports_ranges: boolean;
  /** Maximum number of players supported for postflop equity. */
  max_players: number;
}

/** Top-level meta object returned by GET /api/meta. */
export interface Meta {
  equity: EquityMeta;
  coach: {
    /** Whether the coach endpoint is enabled. */
    enabled: boolean;
  };
}

export default Meta;