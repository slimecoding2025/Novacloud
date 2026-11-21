import { useEffect, useState } from "react";

type Verify = { entries: number; valid: boolean };

export default function App() {
  const [health, setHealth] = useState<string>("...");
  const [audit, setAudit] = useState<Verify | null>(null);

  useEffect(() => {
    fetch("/api/health").then(r => r.json()).then(d => setHealth(d.status)).catch(() => setHealth("unreachable"));
    fetch("/api/audit/verify").then(r => r.json()).then(setAudit).catch(() => setAudit(null));
  }, []);

  return (
    <main style={{ fontFamily: "sans-serif", padding: 24 }}>
      <h1>NOVACLOUD</h1>
      <p>API: {health}</p>
      <p>Audit chain: {audit ? `${audit.entries} entries, ${audit.valid ? "valid" : "INVALID"}` : "n/a"}</p>
    </main>
  );
}
