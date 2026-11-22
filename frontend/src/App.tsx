import { FormEvent, useEffect, useState } from "react";
import { api, setCsrf } from "./api";
import { Audit, Instances, Jobs, Members, Networks, Objects, Overview } from "./pages";
import { Me } from "./types";

const TABS = ["Overview", "Instances", "Jobs", "Objects", "Networks", "Audit", "Members"] as const;
type Tab = (typeof TABS)[number];

function Login({ onLogin }: { onLogin: (m: Me) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [f, setF] = useState({ organization: "", email: "", password: "" });
  const [err, setErr] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      if (mode === "register") await api("POST", "/api/v1/auth/register", f);
      const m = await api<Me>("POST", "/api/v1/auth/login", { email: f.email, password: f.password });
      setCsrf(m.csrf_token); onLogin(m);
    } catch (x) { setErr((x as Error).message); }
  };
  return (<div className="auth">
    <div className="hero"><span className="logo" /><h1>NOVACLOUD</h1>
      <p>Open-source cloud management for developers, labs and small organizations.</p>
      <ul><li>Containers with audited lifecycle</li><li>Multi-tenant roles and sessions</li><li>Tamper-evident audit log</li><li>100% local, zero budget</li></ul></div>
    <form onSubmit={submit}>
      <h2>{mode === "login" ? "Sign in" : "Create your organization"}</h2>
      {mode === "register" && <input aria-label="organization" placeholder="Organization name" value={f.organization} onChange={e => setF({ ...f, organization: e.target.value })} required />}
      <input aria-label="email" type="email" placeholder="Email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} required />
      <input aria-label="password" type="password" placeholder={mode === "register" ? "Password (12+ chars, upper/lower, digit)" : "Password"} value={f.password} onChange={e => setF({ ...f, password: e.target.value })} required />
      {err && <p className="error" role="alert">{err}</p>}
      <button>{mode === "login" ? "Sign in" : "Create organization"}</button>
      <a href="#" onClick={e => { e.preventDefault(); setMode(mode === "login" ? "register" : "login"); setErr(""); }}>
        {mode === "login" ? "New here? Create an organization" : "I already have an account"}</a>
    </form></div>);
}

export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [tab, setTab] = useState<Tab>("Overview");
  useEffect(() => { api<Me>("GET", "/api/v1/auth/me").then(m => { setCsrf(m.csrf_token); setMe(m); }).catch(() => setMe(null)); }, []);
  if (me === undefined) return <p className="muted" style={{ padding: 24 }}>Loading…</p>;
  if (me === null) return <Login onLogin={setMe} />;
  const logout = async () => { await api("POST", "/api/v1/auth/logout"); setMe(null); };
  return (<div className="shell">
    <aside>
      <div className="brand"><span className="logo" />NOVACLOUD</div>
      <nav>{TABS.map(t => <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>{t}</button>)}</nav>
      <div className="who"><span className="muted">Role: <strong>{me.role}</strong></span><button onClick={logout}>Sign out</button></div>
    </aside>
    <main className="content">
      <div className="pagehead"><h1>{tab}</h1></div>
      {tab === "Overview" && <Overview />}{tab === "Instances" && <Instances me={me} />}{tab === "Jobs" && <Jobs />}
      {tab === "Objects" && <Objects me={me} />}{tab === "Networks" && <Networks me={me} />}
      {tab === "Audit" && <Audit />}{tab === "Members" && <Members me={me} />}
    </main></div>);
}
