export type Me = { user_id: string; organization_id: string; role: "owner" | "admin" | "member" | "viewer"; csrf_token: string };
export type Instance = { id: string; name: string; template: string; state: string; error: string | null };
export type Job = { id: string; kind: string; status: string; attempts: number; error: string | null };
export type Obj = { id: string; name: string; size: number; sha256: string };
export type Subnet = { id: string; name: string; cidr: string; gateway: string; allocated: number };
export type Network = { id: string; name: string; cidr: string; subnets: Subnet[] };
export type AuditRow = { timestamp: string; actor_id: string; action: string; resource_type: string; resource_id: string; result: string };
export type Member = { user_id: string; email: string; role: string };
