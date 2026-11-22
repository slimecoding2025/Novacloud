import { ReactNode, useCallback, useEffect, useState } from "react";

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(() => {
    setLoading(true);
    fn().then(d => { setData(d); setError(null); }).catch(e => setError(e.message)).finally(() => setLoading(false));
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(reload, [reload]);
  return { data, error, loading, reload };
}

export const Section = ({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) => (
  <section className="card"><div className="row"><h2>{title}</h2><div>{actions}</div></div>{children}</section>
);

// Real states only: loading, error, empty. Nothing is ever fabricated.
export function State({ loading, error, empty }: { loading: boolean; error: string | null; empty?: boolean }) {
  if (loading) return <p className="muted">Loading…</p>;
  if (error) return <p className="error" role="alert">Unavailable: {error}</p>;
  if (empty) return <p className="muted">Nothing here yet.</p>;
  return null;
}

export const Badge = ({ v }: { v: string }) => <span className={`badge ${v}`}>{v}</span>;
