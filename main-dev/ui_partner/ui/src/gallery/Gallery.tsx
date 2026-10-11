// Every component on one page, in the theme that is on. #/gallery?only=<folder or entry name>
// shows one part alone (for a close look). The first sections show the tokens,
// the type scale and the seven figures; the rest is gathered from `*.gallery.tsx` files.
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { useTheme } from "../components/frame/hooks";
import { SeatFigure } from "../components/shared/SeatFigure";
import { seatLabel } from "../components/shared/seatName";
import { Switch } from "../components/shared/Switch";
import { wght } from "../components/shared/words";
import { type GalleryEntry, sampleSeats } from "./entry";

const found = import.meta.glob<{ entries?: GalleryEntry[] }>("../**/*.gallery.tsx", { eager: true });

/** One section per folder, folders in a fixed order, entries in the order each file lists them. */
function gathered(): { section: string; entries: GalleryEntry[] }[] {
  const byFolder = new Map<string, GalleryEntry[]>();
  for (const path of Object.keys(found).sort()) {
    const folder = path.split("/").at(-2) ?? "other";
    byFolder.set(folder, [...(byFolder.get(folder) ?? []), ...(found[path]?.entries ?? [])]);
  }
  return [...byFolder].map(([section, entries]) => ({ section, entries })).filter((s) => s.entries.length > 0);
}

// class names are written out in full so the stylesheet keeps them
const SWATCHES: { name: string; fill: string }[] = [
  { name: "page", fill: "bg-page" },
  { name: "surface", fill: "bg-surface" },
  { name: "hover", fill: "bg-hover" },
  { name: "hairline", fill: "bg-hairline" },
  { name: "line", fill: "bg-line" },
  { name: "muted", fill: "bg-muted" },
  { name: "ink", fill: "bg-ink" },
  { name: "accent", fill: "bg-accent" },
  { name: "accent-hover", fill: "bg-accent-hover" },
  { name: "on-accent", fill: "bg-on-accent" },
  { name: "table", fill: "bg-table" },
  { name: "agreed", fill: "bg-agreed" },
  { name: "error", fill: "bg-error" },
  { name: "seat-1", fill: "bg-seat-1" },
  { name: "seat-2", fill: "bg-seat-2" },
  { name: "seat-3", fill: "bg-seat-3" },
  { name: "seat-4", fill: "bg-seat-4" },
  { name: "seat-5", fill: "bg-seat-5" },
  { name: "seat-6", fill: "bg-seat-6" },
  { name: "seat-7", fill: "bg-seat-7" },
  { name: "on-seat", fill: "bg-on-seat" },
  { name: "cv-paper", fill: "bg-cv-paper" },
  { name: "cv-ink", fill: "bg-cv-ink" },
  { name: "cv-grey", fill: "bg-cv-grey" },
  { name: "cv-rule", fill: "bg-cv-rule" },
  { name: "cv-faint", fill: "bg-cv-faint" },
];

const TYPE: { name: string; spec: string; cls: string; weight?: number; sample: string }[] = [
  {
    name: "title",
    spec: "24 / 30, weight 620",
    cls: "text-title",
    weight: 620,
    sample: "What should the council settle?",
  },
  { name: "heading", spec: "20 / 26, weight 650", cls: "text-heading", weight: 650, sample: "Agreed 4 of 5" },
  {
    name: "body",
    spec: "16 / 26",
    cls: "text-body",
    sample: "Yes. You can end the lease early by giving 60 days' notice.",
  },
  { name: "chat", spec: "15 / 24", cls: "text-chat", sample: "The letter says it replaces section 14." },
  { name: "label", spec: "14 / 20, weight 500", cls: "text-label", weight: 500, sample: "Add to next round" },
  {
    name: "bubble",
    spec: "13 / 18, weight 450",
    cls: "text-bubble",
    weight: 450,
    sample: "Cites the renewal letter, page 1.",
  },
  { name: "meta", spec: "12 / 16, muted", cls: "text-meta text-muted", sample: "3 rounds, 3:40" },
];

function Tokens({ theme }: { theme: string }) {
  const [values, setValues] = useState<Record<string, string>>({});
  // the values are read from the page, so the gallery can never show a colour the app does not use
  // biome-ignore lint/correctness/useExhaustiveDependencies: read again when the theme flips
  useEffect(() => {
    const style = getComputedStyle(document.documentElement);
    setValues(Object.fromEntries(SWATCHES.map((s) => [s.name, style.getPropertyValue(`--${s.name}`).trim()])));
  }, [theme]);
  return (
    <ul className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4 lg:grid-cols-6">
      {SWATCHES.map((s) => (
        <li key={s.name} className="flex items-center gap-2.5">
          <span className={`size-9 shrink-0 rounded-control border border-line ${s.fill}`} />
          <span className="flex min-w-0 flex-col">
            <span className="font-medium text-ink text-label">{s.name}</span>
            <span className="text-meta text-muted">{values[s.name] ?? ""}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function TypeScale() {
  return (
    <dl className="flex flex-col gap-3">
      {TYPE.map((t) => (
        <div key={t.name} className="flex items-baseline gap-6">
          <dt className="w-44 shrink-0 text-meta text-muted">
            {t.name}, {t.spec}
          </dt>
          <dd className={`text-ink ${t.cls}`} style={t.weight ? { fontWeight: t.weight } : undefined}>
            {t.sample}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Figures() {
  const seats = sampleSeats(7);
  return (
    <div className="flex flex-col gap-8">
      <ul aria-label="Seven seats, table size" className="flex flex-wrap items-end gap-6">
        {seats.map((seat) => (
          <li key={seat.id}>
            <SeatFigure seat={seat} index={seat.index} headD={72} />
          </li>
        ))}
      </ul>
      <ul aria-label="Seven seats, small" className="flex flex-wrap items-end gap-6">
        {seats.map((seat) => (
          <li key={seat.id} className="flex w-12 flex-col items-center gap-1 font-medium text-ink text-meta">
            <SeatFigure seat={seat} index={seat.index} headD={22} size="small" />
            {seatLabel(seat)}
          </li>
        ))}
      </ul>
      <ul aria-label="Seven seats, tiny" className="flex flex-wrap items-center gap-5">
        {seats.map((seat) => (
          <li key={seat.id} className="inline-flex items-center gap-1.5 font-medium text-bubble text-ink">
            <SeatFigure seat={seat} index={seat.index} headD={14} size="tiny" />
            {seatLabel(seat)}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Box({ entry }: { entry: GalleryEntry }) {
  return (
    <section
      data-gallery-entry={entry.name}
      className={`flex min-w-0 flex-col gap-4 rounded-card border border-hairline p-5 ${entry.wide ? "col-span-full" : ""}`}
    >
      <header>
        <h3 className="font-semibold text-ink text-label">{entry.name}</h3>
        {entry.note ? <p className="text-meta text-muted">{entry.note}</p> : null}
      </header>
      <div className="min-w-0">{entry.render()}</div>
    </section>
  );
}

const THEMES = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
] as const;

export function Gallery() {
  const [theme, setTheme] = useTheme();
  const [search] = useSearchParams();
  const only = search.get("only")?.toLowerCase() ?? "";
  const shows = (section: string, entry: GalleryEntry) =>
    !only || section === only || entry.name.toLowerCase().startsWith(only);
  const base: GalleryEntry[] = [
    {
      name: "Colours",
      note: "The tokens of the theme that is on.",
      wide: true,
      render: () => <Tokens theme={theme} />,
    },
    { name: "Type scale", note: "One family: Archivo.", wide: true, render: () => <TypeScale /> },
    {
      name: "Seat figures",
      note: "Seven seats at three sizes. Small and tiny carry no name inside: it is written beside.",
      wide: true,
      render: () => <Figures />,
    },
  ];
  const groups = gathered()
    .map((g) => ({ section: g.section, entries: g.entries.filter((entry) => shows(g.section, entry)) }))
    .filter((g) => g.entries.length > 0);
  return (
    <main data-part="gallery" className="min-h-full bg-page px-8 py-8 text-ink">
      <div className="mx-auto flex max-w-300 flex-col gap-10">
        <header className="flex items-center justify-between gap-6">
          <div>
            <h1 style={wght.title} className="text-title">
              Every component
            </h1>
            <p className="text-label text-muted">Look C, Cut-Out Council. Sample data.</p>
          </div>
          <Switch label="Theme" value={theme} options={THEMES} onChange={setTheme} />
        </header>
        <section aria-label="Foundations" className="grid grid-cols-1 gap-5">
          {base
            .filter((entry) => shows("foundations", entry))
            .map((entry) => (
              <Box key={entry.name} entry={entry} />
            ))}
        </section>
        {groups.map((group) => (
          <section key={group.section} aria-labelledby={`g-${group.section}`} className="flex flex-col gap-4">
            <h2 id={`g-${group.section}`} style={wght.name} className="text-heading">
              {group.section}
            </h2>
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              {group.entries.map((entry) => (
                <Box key={entry.name} entry={entry} />
              ))}
            </div>
          </section>
        ))}
      </div>
    </main>
  );
}
