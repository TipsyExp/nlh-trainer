// frontend/hooks/useMeta.ts
// React hook to fetch and cache backend capabilities (/api/meta).
//
// This hook wraps the getMeta() client and exposes its state as
// { meta, loading, error }.  It automatically aborts the request when
// the component unmounts to avoid setting state on an unmounted
// component.  Consumers should use this hook once near the root of
// their overlay logic; subsequent calls will reuse the cached meta.

import { useEffect, useState, useRef } from 'react';
import { getMeta } from '../utils/meta';
import type { Meta } from '../types/meta';

export interface MetaState {
  meta: Meta | null;
  loading: boolean;
  error?: string;
}

export function useMeta(): MetaState {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(undefined);
    const controller = new AbortController();
    abortRef.current = controller;
    getMeta({ signal: controller.signal })
      .then((m) => {
        setMeta(m);
        setLoading(false);
      })
      .catch((e: any) => {
        setError(e?.message || String(e));
        setLoading(false);
      });
    return () => {
        // Abort in-flight request on unmount
        controller.abort();
    };
  }, []);

  return { meta, loading, error };
}

export default useMeta;
