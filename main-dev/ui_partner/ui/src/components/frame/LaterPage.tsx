// One page for every sidebar item that is not built in Phase 1: one sentence on what will be
// there and in which phase.
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router";
import { useEngineLive } from "../../engine/EngineProvider";
import { engineUrl } from "../../engine/http";
import { fetchMemory, fetchModels, type ModelCard } from "../../engine/system";
import { wght } from "../shared/words";
import { AppFrame } from "./AppFrame";
import { useUrlState } from "./hooks";
import { TopBar } from "./TopBar";
import { useShortcuts } from "./useShortcuts";

export const LATER: Record<string, { title: string; line: string }> = {
  history: { title: "History", line: "A searchable list of your past chats arrives here in Phase 2." },
  library: { title: "Library", line: "Files you want the council to use again will be kept here, from Phase 2." },
  models: {
    title: "Models",
    line: "Downloading models and choosing who sits at the table arrives here in Phase 3.",
  },
  settings: { title: "Settings", line: "Settings for the app arrive here in Phase 2." },
};

const REFRESH_MS = 5000;

function gib(n: number | null): string {
  return n === null ? "-" : n.toFixed(1);
}

function loadedWord(m: ModelCard): string {
  if (m.status !== "active") return "can't run";
  return m.resident ? "loaded" : "not loaded";
}

/** The real models and what is in memory. Only drawn when the real engine answers. */
function ModelsPanel() {
  const models = useQuery({
    queryKey: ["system", "models"],
    queryFn: () => fetchModels(engineUrl()),
    refetchInterval: REFRESH_MS,
  });
  const memory = useQuery({
    queryKey: ["system", "memory"],
    queryFn: () => fetchMemory(engineUrl()),
    refetchInterval: REFRESH_MS,
  });
  const rows = models.data ?? [];
  const mi = memory.data?.meminfo;
  const memLine =
    mi && mi.used_gib !== null && mi.total_gib !== null
      ? `${Math.round(mi.used_gib)} of ${Math.round(mi.total_gib)} GiB in use`
      : "Memory use is not known yet.";
  const loaded = rows.filter((m) => m.resident && m.status === "active").length;
  return (
    <div data-part="models-live" className="mt-6">
      <p className="text-label text-muted">
        {memLine}
        {rows.length > 0 ? ` · ${loaded} of ${rows.length} models loaded` : ""}
      </p>
      {rows.length === 0 ? (
        <p className="mt-4 text-body text-muted">No models reported yet.</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full border-collapse text-left text-label text-ink">
            <thead className="text-meta text-muted">
              <tr className="border-line border-b">
                <th className="py-2 pr-4 font-medium">Model</th>
                <th className="py-2 pr-4 font-medium">Lab</th>
                <th className="py-2 pr-4 font-medium">Size</th>
                <th className="py-2 pr-4 font-medium">Speed</th>
                <th className="py-2 pr-4 font-medium">Memory</th>
                <th className="py-2 pr-4 font-medium">State</th>
                <th className="py-2 font-medium">Lie detector</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id} className="border-line border-b">
                  <td style={wght.name} className="py-2 pr-4">
                    {m.display}
                  </td>
                  <td className="py-2 pr-4 text-muted">{m.lab || "-"}</td>
                  <td className="py-2 pr-4">{m.params_b === null ? "-" : `${m.params_b}B`}</td>
                  <td className="py-2 pr-4">{m.tps === null ? "-" : `${m.tps.toFixed(1)} tok/s`}</td>
                  <td className="py-2 pr-4">{m.memory_gib === null ? "-" : `${gib(m.memory_gib)} GiB`}</td>
                  <td className="py-2 pr-4">{loadedWord(m)}</td>
                  <td className="py-2">{m.probe && m.probe.auroc !== null ? m.probe.auroc.toFixed(2) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function LaterPage() {
  const live = useEngineLive();
  const { what = "" } = useParams();
  const [, change] = useUrlState();
  const page = LATER[what] ?? { title: "Not built yet", line: "This screen arrives in a later phase." };
  const wideModels = what === "models" && live;
  useShortcuts((s) => {
    if (s.kind === "help") change({ help: "1" });
    else if (s.kind === "close") change({ help: null });
    else return false;
    return true;
  });
  return (
    <AppFrame top={<TopBar seats={[]} />}>
      <section
        data-part="later-page"
        className={`mx-auto flex h-full flex-col px-6 pb-24 ${wideModels ? "max-w-240 justify-start pt-12" : "max-w-160 justify-center"}`}
      >
        <h1 style={wght.title} className="text-ink text-title">
          {page.title}
        </h1>
        {wideModels ? <ModelsPanel /> : <p className="mt-2 text-body text-muted">{page.line}</p>}
      </section>
    </AppFrame>
  );
}
