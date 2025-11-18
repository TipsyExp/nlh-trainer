//frontend/hooks/useDecisionContext.ts
// Placeholder hook for computing decision context.
//
// In the current implementation the table page computes the decision
// context and passes it directly to the guidance overlay.  A
// future iteration may lift this logic into a context provider and
// implement this hook to read from that provider.  For now it
// returns null and is unused.

import type { DecisionContext } from '../types/decision';

export function useDecisionContext(): DecisionContext | null {
  return null;
}

export default useDecisionContext;