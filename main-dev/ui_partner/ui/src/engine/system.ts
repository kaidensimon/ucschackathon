// What the machine is doing: which models exist, which are loaded, how much memory is used.
// Reads the council's /system routes (council/api/system_routes.py). Any failure gives an
// empty list or null, so a screen never breaks because the box is slow.

export interface ModelCard {
  id: string;
  display: string;
  lab: string;
  params_b: number | null;
  /** true when the model is loaded in memory right now */
  resident: boolean;
  memory_gib: number | null;
  tps: number | null;
  /** "active" runs; anything else cannot run */
  status: string;
  probe: { active: boolean; auroc: number | null } | null;
}

export interface MemoryInfo {
  meminfo: { total_gib: number | null; available_gib: number | null; used_gib: number | null };
  plan: unknown;
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function str(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asCard(raw: unknown): ModelCard | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const id = str(r.id);
  if (!id) return null;
  const p = r.probe && typeof r.probe === "object" ? (r.probe as Record<string, unknown>) : null;
  return {
    id,
    display: str(r.display, id) || id,
    lab: str(r.lab),
    params_b: num(r.params_b),
    resident: r.resident === true,
    memory_gib: num(r.memory_gib),
    tps: num(r.tps),
    status: str(r.status, "active"),
    probe: p ? { active: p.active === true, auroc: num(p.auroc) } : null,
  };
}

async function getJson(url: string): Promise<unknown> {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`status ${response.status}`);
  return response.json();
}

export async function fetchModels(baseUrl: string): Promise<ModelCard[]> {
  try {
    const body = await getJson(`${baseUrl.replace(/\/+$/, "")}/system/models`);
    if (!Array.isArray(body)) return [];
    return body.map(asCard).filter((c): c is ModelCard => c !== null);
  } catch {
    return [];
  }
}

export async function fetchMemory(baseUrl: string): Promise<MemoryInfo | null> {
  try {
    const body = await getJson(`${baseUrl.replace(/\/+$/, "")}/system/memory`);
    if (!body || typeof body !== "object") return null;
    const m = (body as { meminfo?: unknown; plan?: unknown }).meminfo;
    const mi = m && typeof m === "object" ? (m as Record<string, unknown>) : {};
    return {
      meminfo: { total_gib: num(mi.total_gib), available_gib: num(mi.available_gib), used_gib: num(mi.used_gib) },
      plan: (body as { plan?: unknown }).plan ?? null,
    };
  } catch {
    return null;
  }
}
