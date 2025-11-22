// frontend/types/meta.ts
// Types describing the backend capabilities exposed by GET /api/meta.
//
// The guidance overlay fetches a meta snapshot once per session to learn
// whether the equity engine supports range-based evaluations and how many
// players can be simulated. It also exposes the backend name so the UI
// can display a badge.
//
// As of M3 the meta payload also carries basic coach information,
// including whether the unified /api/coach/advice route is available and
// which advice payload version it serves. These fields are optional so
// that older backends remain compatible.

/** Supported equity backends. Additional backends may be added in the
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

/** Coach-related capabilities returned by GET /api/meta. */
export interface CoachMeta {
  /** Whether coaching features are enabled on the backend. */
  enabled: boolean;

  /**
   * Whether the unified /api/coach/advice endpoint is available.
   *
   * Older backends may omit this field; callers should treat `undefined`
   * as "advice route not advertised" and fall back to legacy behaviour.
   */
  advice_route?: boolean;

  /**
   * Version of the advice payload served by /api/coach/advice.
   *
   * When present, this corresponds to the `version` field in AdviceV1
   * (see docs/COACH-ADVICE-PAYLOAD.md). Undefined means the backend
   * does not report a version explicitly.
   */
  advice_version?: number;
}

/** Top-level meta object returned by GET /api/meta. */
export interface Meta {
  equity: EquityMeta;
  coach: CoachMeta;
}

export default Meta;
