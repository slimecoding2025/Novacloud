import { FormEvent, ReactNode, useState } from "react";
import { api, newKey } from "./api";
import { AuditRow, Instance, Job, Me, Member, Network, Obj } from "./types";
import { Badge, Section, State, useLoad } from "./ui";

const can = (me: Me, ...roles: Me["role"][]) => roles.includes(me.role);

export function Instances({ me }: { me: Me }) {
  const { data, error, loading, reload } = useLoad(() => api<Instance[]>("GET", "/api/v1/instances"));
  const nets = useLoad(() => api<Network[]>("GET", "/api/v1/networks"));
  const [name, setName] = useState(""); const [tpl, setTpl] = useState("alpine-small"); const [subnet, setSubnet] = useState(""); const [msg, setMsg] = useState("");
  const options = (nets.data ?? []).flatMap(n => n.subnets.map(s => ({ value: `${n.id}|${s.id}`, label: `${n.name} / ${s.name} (${s.cidr})` })));
  const act = async (f: () => Promise<unknown>) => { try { await f(); setMsg(""); setTimeout(reload, 1500); } catch (e) { setMsg((e as Error).message); } };
  const create = (e: FormEvent) => {
    e.preventDefault();
    const [network_id, subnet_id] = subnet ? subnet.split("|") : [undefined, undefined];
    act(() => api("POST", "/api/v1/instances", { name, template: tpl, network_id, subnet_id }, { "Idempotency-Key": newKey() }));
  };
  return (
    <Section title="Instances (containers)" actions={<button onClick={reload}>Refresh</button>}>
      {can(me, "owner", "admin", "member") && (
        <form onSubmit={create} className="row">
          <input aria-label="name" placeholder="name (a-z, 0-9, -)" value={name} onChange={e => setName(e.target.value)} required />
          <select aria-label="template" value={tpl} onChange={e => setTpl(e.target.value)}>
            <option>alpine-small</option><option>nginx-small</option></select>
          <select aria-label="subnet" value={subnet} onChange={e => setSubnet(e.target.value)}>
            <option value="">No network (isolated)</option>{options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
          <button>Create</button>
        </form>)}
      {msg && <p className="error" role="alert">{msg}</p>}
      <State loading={loading} error={error} empty={data?.length === 0} />
      <table><tbody>{data?.map(i => (
        <tr key={i.id}><td>{i.name}</td><td>{i.template}</td><td>{i.ip ? <code>{i.ip}</code> : <span className="muted">no network</span>}</td><td><Badge v={i.state} />{i.error && <small className="error"> {i.error}</small>}</td>
          <td>
            {i.state === "stopped" && <button onClick={() => act(() => api("POST", `/api/v1/instances/${i.id}/start`, undefined, { "Idempotency-Key": newKey() }))}>Start</button>}
            {i.state === "running" && <button onClick={() => act(() => api("POST", `/api/v1/instances/${i.id}/stop`, undefined, { "Idempotency-Key": newKey() }))}>Stop</button>}
            {can(me, "owner", "admin") && <button className="danger" onClick={() => {
              const c = prompt(`Type "${i.name}" to confirm deletion`);
              if (c) act(() => api("DELETE", `/api/v1/instances/${i.id}?confirm_name=${encodeURIComponent(c)}`, undefined, { "Idempotency-Key": newKey() }));
            }}>Delete</button>}
          </td></tr>))}</tbody></table>
    </Section>);
}

export function Jobs() {
  const { data, error, loading, reload } = useLoad(() => api<Job[]>("GET", "/api/v1/jobs"));
  return (<Section title="Jobs" actions={<button onClick={reload}>Refresh</button>}>
    <State loading={loading} error={error} empty={data?.length === 0} />
    <table><tbody>{data?.map(j => <tr key={j.id}><td>{j.kind}</td><td><Badge v={j.status} /></td><td>{j.attempts}</td><td className="error">{j.error}</td></tr>)}</tbody></table>
  </Section>);
}

export function Objects({ me }: { me: Me }) {
  const { data, error, loading, reload } = useLoad(() => api<Obj[]>("GET", "/api/v1/objects"));
  const usage = useLoad(() => api<{ used_bytes: number; quota_bytes: number }>("GET", "/api/v1/objects/usage"));
  const [msg, setMsg] = useState("");
  const upload = async (f?: File) => { if (!f) return; try { await api("POST", `/api/v1/objects?name=${encodeURIComponent(f.name)}`, f); setMsg(""); reload(); usage.reload(); } catch (e) { setMsg((e as Error).message); } };
  return (<Section title="Objects">
    {usage.data && <p className="muted">{usage.data.used_bytes} / {usage.data.quota_bytes} bytes used</p>}
    {can(me, "owner", "admin", "member") && <input type="file" aria-label="upload" onChange={e => upload(e.target.files?.[0])} />}
    {msg && <p className="error" role="alert">{msg}</p>}
    <State loading={loading} error={error} empty={data?.length === 0} />
    <table><tbody>{data?.map(o => <tr key={o.id}><td>{o.name}</td><td>{o.size} B</td><td><code>{o.sha256.slice(0, 12)}…</code></td>
      <td><a href={`/api/v1/objects/${o.id}/content`}>Download</a>{can(me, "owner", "admin") &&
        <button className="danger" onClick={async () => { await api("DELETE", `/api/v1/objects/${o.id}`); reload(); usage.reload(); }}>Delete</button>}</td></tr>)}</tbody></table>
  </Section>);
}

export function Networks({ me }: { me: Me }) {
  const { data, error, loading, reload } = useLoad(() => api<Network[]>("GET", "/api/v1/networks"));
  const [name, setName] = useState(""); const [cidr, setCidr] = useState("10.0.0.0/16"); const [msg, setMsg] = useState("");
  const [sub, setSub] = useState({ network: "", name: "", cidr: "10.0.1.0/24" });
  const create = async (e: FormEvent) => { e.preventDefault(); try { await api("POST", "/api/v1/networks", { name, cidr }); setMsg(""); reload(); } catch (x) { setMsg((x as Error).message); } };
  const createSub = async (e: FormEvent) => { e.preventDefault(); try { await api("POST", `/api/v1/networks/${sub.network}/subnets`, { name: sub.name, cidr: sub.cidr }); setMsg(""); reload(); } catch (x) { setMsg((x as Error).message); } };
  const del = async (path: string) => { try { await api("DELETE", path); setMsg(""); reload(); } catch (x) { setMsg((x as Error).message); } };
  return (<Section title="Networks">
    <p className="muted">Each subnet is a real Docker bridge (internal): instances in the same subnet reach each other; other subnets and the internet are not reachable. CIDRs must be unique on the host.</p>
    {can(me, "owner", "admin", "member") && <form onSubmit={create} className="row">
      <input aria-label="network name" placeholder="name" value={name} onChange={e => setName(e.target.value)} required />
      <input aria-label="cidr" value={cidr} onChange={e => setCidr(e.target.value)} required /><button>Create</button></form>}
    {can(me, "owner", "admin", "member") && (data?.length ?? 0) > 0 && <form onSubmit={createSub} className="row">
      <select aria-label="parent network" value={sub.network} onChange={e => setSub({ ...sub, network: e.target.value })} required>
        <option value="">Parent network…</option>{data?.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}</select>
      <input aria-label="subnet name" placeholder="subnet name" value={sub.name} onChange={e => setSub({ ...sub, name: e.target.value })} required />
      <input aria-label="subnet cidr" value={sub.cidr} onChange={e => setSub({ ...sub, cidr: e.target.value })} required /><button>Add subnet</button></form>}
    {msg && <p className="error" role="alert">{msg}</p>}
    <State loading={loading} error={error} empty={data?.length === 0} />
    {data?.map(n => <div key={n.id}><h3>{n.name} <code>{n.cidr}</code>
      {can(me, "owner", "admin") && <button className="danger" onClick={() => del(`/api/v1/networks/${n.id}`)}>Delete</button>}</h3>
      <ul>{n.subnets.map(s => <li key={s.id}>{s.name} <code>{s.cidr}</code> gw {s.gateway} · {s.allocated} allocated
        {can(me, "owner", "admin") && <button className="danger" onClick={() => del(`/api/v1/networks/${n.id}/subnets/${s.id}`)}>Delete</button>}</li>)}</ul></div>)}
  </Section>);
}

export function Audit() {
  const { data, error, loading } = useLoad(() => api<AuditRow[]>("GET", "/api/v1/audit?limit=100"));
  const v = useLoad(() => api<{ entries: number; valid: boolean }>("GET", "/api/v1/audit/verify"));
  return (<Section title="Audit log">
    {v.data && <p>Chain: {v.data.entries} entries, <Badge v={v.data.valid ? "valid" : "INVALID"} /></p>}
    <State loading={loading} error={error} empty={data?.length === 0} />
    <table><tbody>{data?.slice().reverse().map((a, i) => <tr key={i}><td>{a.timestamp}</td><td>{a.action}</td><td>{a.resource_type}:{a.resource_id.slice(0, 8)}</td><td><Badge v={a.result} /></td></tr>)}</tbody></table>
  </Section>);
}

export function Members({ me }: { me: Me }) {
  const { data, error, loading, reload } = useLoad(() => api<Member[]>("GET", "/api/v1/members"));
  const [f, setF] = useState({ email: "", password: "", role: "member" }); const [msg, setMsg] = useState("");
  const add = async (e: FormEvent) => { e.preventDefault(); try { await api("POST", "/api/v1/members", f); setMsg(""); setF({ ...f, email: "", password: "" }); reload(); } catch (x) { setMsg((x as Error).message); } };
  return (<Section title="Members">
    {can(me, "owner", "admin") && <form onSubmit={add} className="row">
      <input aria-label="email" type="email" placeholder="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} required />
      <input aria-label="password" type="password" placeholder="password (12+ chars)" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} required />
      <select aria-label="role" value={f.role} onChange={e => setF({ ...f, role: e.target.value })}><option>viewer</option><option>member</option><option>admin</option></select>
      <button>Add</button></form>}
    {msg && <p className="error" role="alert">{msg}</p>}
    <State loading={loading} error={error} empty={data?.length === 0} />
    <table><tbody>{data?.map(m => <tr key={m.user_id}><td>{m.email}</td><td><Badge v={m.role} /></td></tr>)}</tbody></table>
  </Section>);
}

function Stat({ label, value, sub, loading, error, children }: { label: string; value?: string | number; sub?: string; loading: boolean; error: string | null; children?: ReactNode }) {
  return (<div className="stat"><div className="label">{label}</div>
    {loading ? <div className="value muted">…</div> : error ? <div className="value muted" title={error}>n/a</div> : <div className="value">{value}</div>}
    <div className="sub">{error ? `Unavailable: ${error}` : sub}</div>{children}</div>);
}

// Every figure comes from a live API call; if a call fails the card says "n/a", never a made-up number.
export function Overview() {
  const inst = useLoad(() => api<Instance[]>("GET", "/api/v1/instances"));
  const jobs = useLoad(() => api<Job[]>("GET", "/api/v1/jobs"));
  const usage = useLoad(() => api<{ used_bytes: number; quota_bytes: number }>("GET", "/api/v1/objects/usage"));
  const chain = useLoad(() => api<{ entries: number; valid: boolean }>("GET", "/api/v1/audit/verify"));
  const running = inst.data?.filter(i => i.state === "running").length ?? 0;
  const failedI = inst.data?.filter(i => i.state === "failed").length ?? 0;
  const pending = jobs.data?.filter(j => j.status === "queued" || j.status === "running").length ?? 0;
  const failedJ = jobs.data?.filter(j => j.status === "failed").length ?? 0;
  const pct = usage.data ? Math.min(100, (usage.data.used_bytes / usage.data.quota_bytes) * 100) : 0;
  return (<>
    <div className="stats">
      <Stat label="Instances" value={inst.data?.length} sub={`${running} running · ${failedI} failed`} loading={inst.loading} error={inst.error} />
      <Stat label="Jobs" value={pending} sub={`pending · ${failedJ} failed (recent)`} loading={jobs.loading} error={jobs.error} />
      <Stat label="Storage" value={usage.data ? `${pct.toFixed(1)}%` : undefined} sub={usage.data ? `${usage.data.used_bytes} of ${usage.data.quota_bytes} bytes` : ""} loading={usage.loading} error={usage.error}>
        <div className="bar"><i style={{ width: `${pct}%` }} /></div></Stat>
      <Stat label="Audit chain" value={chain.data ? (chain.data.valid ? "Valid" : "BROKEN") : undefined} sub={chain.data ? `${chain.data.entries} entries verified` : ""} loading={chain.loading} error={chain.error} />
    </div>
  </>);
}
