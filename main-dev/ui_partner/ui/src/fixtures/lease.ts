// The one sample debate behind every mock screen. Everything here is invented:
// the question, the three files, the answers and the pace. Real speed on the GX10
// has not been measured and may be much slower.
import type { FileRef } from "../lib/events";
import { build, c, type Fixture, type Script, type TallySpec, type TurnSpec } from "./build";

const files: FileRef[] = [
  { id: "f1", name: "Lease 2025.pdf", pages: 14, from: "attachment" },
  { id: "f2", name: "Renewal letter 2026.pdf", pages: 2, from: "attachment" },
  { id: "f3", name: "House rules.docx", pages: 6, from: "attachment" },
];

const question = "Can I end my apartment lease early, and what would it cost me?";

// Example model names only. Real seats are chosen in Phase 3.
const models: Record<string, string> = {
  Phi: "Phi example model",
  Llama: "Llama example model",
  Qwen: "Qwen example model",
  Gemma: "Gemma example model",
  Mistral: "Mistral example model",
  Granite: "Granite example model",
  Hermes: "Hermes example model",
};
const seat = (shortName: string) => ({ shortName, modelName: models[shortName] ?? shortName });

// The four positions the council holds along the way.
const A = "60 days' written notice plus one month's rent at the new rate, $2,520.";
const B = "Two months' rent at the old rate, $4,800.";
const C = "Two months' rent at the new rate, $5,040.";
const D = "It cannot be said until the landlord countersigns the renewal letter.";

const LEASE = "Lease 2025.pdf";
const LETTER = "Renewal letter 2026.pdf";
const RULES = "House rules.docx";

const research: TurnSpec[] = [
  {
    seat: "Phi",
    round: 0,
    kind: "research",
    start: c(0, 0),
    end: c(0, 6),
    text: "Read the early-termination clause, section 14, in the lease.",
    cites: [{ file: LEASE, page: 9 }],
    says: [{ at: c(0, 1), text: "Reading Lease 2025.pdf, page 9" }],
  },
  {
    seat: "Llama",
    round: 0,
    kind: "research",
    start: c(0, 6),
    end: c(0, 12),
    text: "Read the rent on page 2 and the early-termination clause on page 9 of the lease.",
    cites: [
      { file: LEASE, page: 2 },
      { file: LEASE, page: 9 },
    ],
    says: [{ at: c(0, 7), text: "Reading Lease 2025.pdf, pages 2 and 9" }],
  },
  {
    seat: "Qwen",
    round: 0,
    kind: "research",
    start: c(0, 12),
    end: c(0, 19),
    text: "Read the renewal letter, then compared it with section 14 of the lease.",
    cites: [
      { file: LETTER, page: 1 },
      { file: LEASE, page: 9 },
    ],
    says: [{ at: c(0, 13), text: "Reading Renewal letter 2026.pdf, page 1" }],
  },
  {
    seat: "Gemma",
    round: 0,
    kind: "research",
    start: c(0, 19),
    end: c(0, 26),
    text: "Read the renewal letter and the notice rules in the house rules.",
    cites: [
      { file: LETTER, page: 1 },
      { file: RULES, page: 4 },
    ],
    says: [{ at: c(0, 20), text: "Reading House rules.docx, page 4" }],
  },
  {
    seat: "Mistral",
    round: 0,
    kind: "research",
    start: c(0, 26),
    end: c(0, 32),
    text: "Read section 14 of the lease and the new rent in the renewal letter.",
    cites: [
      { file: LEASE, page: 9 },
      { file: LETTER, page: 1 },
    ],
    says: [{ at: c(0, 27), text: "Reading Lease 2025.pdf, page 9" }],
  },
];

const round1: TurnSpec[] = [
  {
    seat: "Qwen",
    round: 1,
    kind: "position",
    start: c(0, 32),
    end: c(0, 42),
    text: "Yes, you can leave early. The renewal letter replaces section 14: it asks for 60 days' written notice and a fee of one month's rent at the new rate, which is $2,520.",
    cites: [{ file: LETTER, page: 1, quote: "replaces section 14" }],
    says: [{ at: c(0, 34), text: "Says the fee is one month at the new rent, $2,520." }],
  },
  {
    seat: "Llama",
    round: 1,
    kind: "position",
    start: c(0, 42),
    end: c(0, 51),
    text: "The lease itself is what binds you. Section 14 sets the fee at two months' rent, and the rent in the lease is $2,400, so the cost is $4,800.",
    cites: [
      { file: LEASE, page: 9 },
      { file: LEASE, page: 2 },
    ],
    says: [{ at: c(0, 44), text: "Says the lease sets two months' rent, $4,800." }],
  },
  {
    seat: "Gemma",
    round: 1,
    kind: "position",
    start: c(0, 51),
    end: c(1, 1),
    text: "I read it as Qwen does. The letter changes the fee to one month's rent, and the house rules say notice must be in writing. So: 60 days' written notice and $2,520.",
    cites: [
      { file: LETTER, page: 1 },
      { file: RULES, page: 4 },
    ],
    says: [{ at: c(0, 53), text: "Agrees with Qwen: one month, with written notice." }],
  },
  {
    seat: "Phi",
    round: 1,
    kind: "position",
    start: c(1, 1),
    end: c(1, 11),
    text: "I would not give a figure yet. Page 2 of the renewal letter has a line for the landlord's signature and it is empty. Until it is countersigned we cannot say which terms apply.",
    cites: [{ file: LETTER, page: 2 }],
    says: [{ at: c(1, 3), text: "Says the landlord has not signed the letter." }],
  },
  {
    seat: "Mistral",
    round: 1,
    kind: "position",
    start: c(1, 11),
    end: c(1, 20),
    text: "Section 14 still sets two months, but the rent it applies to is now the new one. Two months at $2,520 is $5,040.",
    cites: [
      { file: LEASE, page: 9 },
      { file: LETTER, page: 1 },
    ],
    says: [{ at: c(1, 13), text: "Says two months at the new rent, $5,040." }],
  },
];

const round2: TurnSpec[] = [
  {
    seat: "Llama",
    round: 2,
    kind: "reply",
    to: ["Qwen"],
    start: c(1, 31),
    end: c(1, 41),
    text: "Qwen, a letter cannot rewrite a signed lease by itself. Unless the lease says it can be amended by letter, section 14 stands as written.",
    cites: [{ file: LEASE, page: 9 }],
    says: [
      { at: c(1, 34), text: "Answers Qwen: the lease still stands as written." },
      { at: c(1, 41), text: "Holds that a letter cannot change the lease." },
    ],
  },
  {
    seat: "Gemma",
    round: 2,
    kind: "reply",
    to: ["Llama"],
    start: c(1, 41),
    end: c(1, 48),
    text: "Llama, the letter says so itself. Page 1: this letter replaces section 14 of your lease, and the early-termination fee is one month's rent.",
    cites: [{ file: LETTER, page: 1, quote: "replaces section 14" }],
    says: [{ at: c(1, 44), text: "Cites the renewal letter, page 1: fee is one month." }],
  },
  {
    seat: "Qwen",
    round: 2,
    kind: "reply",
    to: ["Mistral"],
    start: c(1, 48),
    end: c(1, 58),
    text: "Mistral, you are right that the new rent applies, but the letter also changes the number of months. It is one month at the new rate, not two.",
    cites: [{ file: LETTER, page: 1 }],
    says: [{ at: c(1, 49.5), text: "Tells Mistral the fee is one month at the new rent." }],
  },
  {
    seat: "Mistral",
    round: 2,
    kind: "reply",
    start: c(1, 58),
    end: c(2, 8),
    text: "I have re-read page 1. The letter does replace section 14, including the number of months. I now agree: one month's rent at the new rate.",
    cites: [{ file: LETTER, page: 1 }],
    says: [{ at: c(2, 0), text: "Now agrees: one month, not two." }],
  },
  {
    seat: "Phi",
    round: 2,
    kind: "reply",
    to: ["Gemma"],
    start: c(2, 8),
    end: c(2, 20),
    text: "Gemma, the letter can only replace section 14 if both sides agreed to it. Page 2 carries one signature, the tenant's. That is my difficulty.",
    cites: [{ file: LETTER, page: 2 }],
    says: [{ at: c(2, 10), text: "Tells Gemma page 2 has only one signature." }],
  },
  {
    seat: "Llama",
    round: 2,
    kind: "reply",
    to: ["Gemma"],
    start: c(2, 20),
    end: c(2, 32),
    text: "Gemma, I accept that the letter says it replaces section 14. I am not yet sure it was validly made, for the reason Phi gives.",
    says: [{ at: c(2, 22), text: "Accepts the wording, doubts the letter is valid." }],
  },
];

const round3: TurnSpec[] = [
  {
    seat: "Qwen",
    round: 3,
    kind: "reply",
    to: ["Llama"],
    start: c(2, 47),
    end: c(2, 58),
    text: "Llama, the landlord sent the letter, so the landlord's offer is in writing, and the tenant signed it. To be out by the end of February the notice has to go by 30 December 2026.",
    cites: [{ file: LETTER, page: 1, quote: "replaces section 14" }],
    says: [{ at: c(2, 49), text: "Says notice must go by 30 December 2026." }],
  },
  {
    seat: "Llama",
    round: 3,
    kind: "reply",
    to: ["Qwen"],
    start: c(2, 58),
    end: c(3, 8),
    text: "That settles it for me. An offer from the landlord, accepted in writing by the tenant, changes the lease. I agree: 60 days' notice and one month's rent, $2,520.",
    says: [{ at: c(3, 0), text: "Now agrees with Qwen: one month, $2,520." }],
  },
  {
    seat: "Phi",
    round: 3,
    kind: "reply",
    start: c(3, 8),
    end: c(3, 18),
    text: "I still cannot agree. A signature line was left for the landlord and it is empty. I would ask the landlord to countersign before relying on the new terms.",
    cites: [{ file: LETTER, page: 2 }],
    says: [{ at: c(3, 10), text: "Still wants the landlord's signature first." }],
  },
  {
    seat: "Gemma",
    round: 3,
    kind: "reply",
    start: c(3, 18),
    end: c(3, 27),
    text: "One practical point for the answer: the house rules say an email counts as written notice.",
    cites: [{ file: RULES, page: 4 }],
    says: [{ at: c(3, 20), text: "Adds that an email counts as written notice." }],
  },
  {
    seat: "Mistral",
    round: 3,
    kind: "reply",
    start: c(3, 27),
    end: c(3, 36),
    text: "Agreed on all of it: written notice by 30 December, one month's rent at the new rate.",
    says: [{ at: c(3, 29), text: "Agrees: notice by 30 December, one month's rent." }],
  },
];

const answerText =
  "Yes. You can end the lease early by giving 60 days' written notice and paying one month's rent at the new rate, $2,520.\n\nTo be out by the end of February, send the notice by 30 December 2026. An email counts as written notice.";
// the two and three seat debates never hear the owner's note or the house rules' email point
const shortAnswerText =
  "Yes. You can end the lease early by giving 60 days' written notice and paying one month's rent at the new rate, $2,520.";
const dissentText = "The renewal letter has one signature (page 2), so the old terms may still apply.";

const closing: TurnSpec[] = [
  {
    seat: "Qwen",
    round: 3,
    kind: "answer",
    start: c(3, 40),
    end: c(3, 40),
    afterStop: { start: 1000, end: 12000 },
    text: answerText,
    cites: [
      { file: LETTER, page: 1, quote: "replaces section 14" },
      { file: LEASE, page: 9 },
      { file: RULES, page: 4 },
    ],
  },
  {
    seat: "Phi",
    round: 3,
    kind: "dissent",
    start: c(3, 40),
    end: c(3, 40),
    afterStop: { start: 12000, end: 15000 },
    text: dissentText,
    cites: [{ file: LETTER, page: 2 }],
  },
];

const vote1: TallySpec = {
  clock: c(1, 24),
  round: 1,
  groups: [
    { answerId: "A", statement: A, seats: ["Qwen", "Gemma"] },
    { answerId: "B", statement: B, seats: ["Llama"] },
    { answerId: "C", statement: C, seats: ["Mistral"] },
    { answerId: "D", statement: D, seats: ["Phi"] },
  ],
};
const vote2: TallySpec = {
  clock: c(2, 40),
  round: 2,
  groups: [
    { answerId: "A", statement: A, seats: ["Qwen", "Gemma", "Mistral"] },
    { answerId: "B", statement: B, seats: ["Llama"] },
    { answerId: "D", statement: D, seats: ["Phi"] },
  ],
};
const vote3: TallySpec = {
  clock: c(3, 40),
  round: 3,
  groups: [
    { answerId: "A", statement: A, seats: ["Qwen", "Gemma", "Mistral", "Llama"] },
    { answerId: "D", statement: D, seats: ["Phi"] },
  ],
};

const five = ["Phi", "Llama", "Qwen", "Gemma", "Mistral"].map(seat);
const readyFive = { Llama: 3000, Phi: 6000, Gemma: 9000, Qwen: 13000, Mistral: 18000 };

const main: Script = {
  id: "lease",
  question,
  files,
  seats: five,
  limitMs: c(5, 0),
  readyAt: readyFive,
  pauses: [{ clock: c(2, 2), forMs: 15000 }],
  phases: [
    { clock: 0, phase: "research" },
    { clock: c(0, 32), phase: "debate" },
    { clock: c(1, 20), phase: "vote" },
    { clock: c(1, 30), phase: "debate" },
    { clock: c(2, 36), phase: "vote" },
    { clock: c(2, 46), phase: "debate" },
    { clock: c(3, 36), phase: "vote" },
    { clock: c(3, 40), phase: "writing", afterStop: 500 },
    { clock: c(3, 40), phase: "released", afterStop: 15000 },
  ],
  rounds: [
    { clock: c(0, 32), round: 1 },
    { clock: c(1, 30), round: 2 },
    { clock: c(2, 46), round: 3 },
  ],
  turns: [...research, ...round1, ...round2, ...round3, ...closing],
  tallies: [vote1, vote2, vote3],
  notes: [{ text: "I want to be out by the end of February.", queued: c(2, 14), queuedRound: 2, delivered: c(2, 46) }],
  release: {
    clock: c(3, 40),
    afterStop: 15000,
    outcome: "agreed",
    tallyRound: 3,
    rounds: 3,
    answerSeat: "Qwen",
    dissentSeats: ["Phi"],
  },
};

// ---- variants: each reuses the main story where it can ----

const only = (turns: TurnSpec[], names: string[]) =>
  turns
    .filter((t) => names.includes(t.seat))
    .map((t) => ({ ...t, to: t.to === "all" || !t.to ? t.to : t.to.filter((n) => names.includes(n)) }))
    .map((t) => (Array.isArray(t.to) && t.to.length === 0 ? { ...t, to: "all" as const } : t));

const three: Script = {
  id: "lease-3",
  question,
  files,
  seats: ["Llama", "Qwen", "Gemma"].map(seat),
  limitMs: c(5, 0),
  readyAt: { Llama: 3000, Gemma: 9000, Qwen: 13000 },
  phases: [
    { clock: 0, phase: "research" },
    { clock: c(0, 32), phase: "debate" },
    { clock: c(1, 20), phase: "vote" },
    { clock: c(1, 30), phase: "debate" },
    { clock: c(2, 6), phase: "vote" },
    { clock: c(2, 10), phase: "writing", afterStop: 500 },
    { clock: c(2, 10), phase: "released", afterStop: 12500 },
  ],
  rounds: [
    { clock: c(0, 32), round: 1 },
    { clock: c(1, 30), round: 2 },
  ],
  turns: [
    ...only(research, ["Llama", "Qwen", "Gemma"]),
    ...only(round1, ["Llama", "Qwen", "Gemma"]),
    ...only(round2.slice(0, 2), ["Llama", "Qwen", "Gemma"]),
    {
      seat: "Llama",
      round: 2,
      kind: "reply",
      to: ["Gemma"],
      start: c(1, 50),
      end: c(2, 2),
      text: "Gemma, you are right. The letter says it replaces section 14, and both of you read it the same way. I agree: one month's rent at the new rate.",
      says: [{ at: c(1, 52), text: "Now agrees: one month, $2,520." }],
    },
    {
      seat: "Qwen",
      round: 2,
      kind: "answer",
      start: c(2, 10),
      end: c(2, 10),
      afterStop: { start: 1000, end: 12000 },
      text: shortAnswerText,
      cites: [
        { file: LETTER, page: 1 },
        { file: LEASE, page: 9 },
        { file: RULES, page: 4 },
      ],
    },
  ],
  tallies: [
    {
      clock: c(1, 24),
      round: 1,
      groups: [
        { answerId: "A", statement: A, seats: ["Qwen", "Gemma"] },
        { answerId: "B", statement: B, seats: ["Llama"] },
      ],
    },
    { clock: c(2, 10), round: 2, groups: [{ answerId: "A", statement: A, seats: ["Qwen", "Gemma", "Llama"] }] },
  ],
  release: {
    clock: c(2, 10),
    afterStop: 12500,
    outcome: "agreed",
    tallyRound: 2,
    rounds: 2,
    answerSeat: "Qwen",
    dissentSeats: [],
  },
};

const sevenSeats = ["Phi", "Llama", "Granite", "Qwen", "Gemma", "Hermes", "Mistral"].map(seat);
const readySeven = { Llama: 3000, Phi: 6000, Gemma: 9000, Granite: 11000, Qwen: 13000, Hermes: 16000, Mistral: 18000 };
const extraResearch: TurnSpec[] = [
  {
    seat: "Granite",
    round: 0,
    kind: "research",
    start: c(0, 32),
    end: c(0, 37),
    text: "Read the renewal letter, both pages.",
    cites: [{ file: LETTER, page: 1 }],
    says: [{ at: c(0, 33), text: "Reading Renewal letter 2026.pdf, page 1" }],
  },
  {
    seat: "Hermes",
    round: 0,
    kind: "research",
    start: c(0, 37),
    end: c(0, 42),
    text: "Read the rent clause and section 14 of the lease.",
    cites: [{ file: LEASE, page: 9 }],
    says: [{ at: c(0, 38), text: "Reading Lease 2025.pdf, page 9" }],
  },
];
const later = (turns: TurnSpec[], by: number): TurnSpec[] =>
  turns.map((t) => ({
    ...t,
    start: t.start + by,
    end: t.end + by,
    says: t.says?.map((s) => ({ ...s, at: s.at + by })),
  }));
const extraRound1: TurnSpec[] = [
  {
    seat: "Granite",
    round: 1,
    kind: "position",
    start: c(1, 30),
    end: c(1, 38),
    text: "The letter replaces section 14. One month's rent at the new rate, $2,520, with 60 days' written notice.",
    cites: [{ file: LETTER, page: 1 }],
    says: [{ at: c(1, 32), text: "Says one month at the new rent, $2,520." }],
  },
  {
    seat: "Hermes",
    round: 1,
    kind: "position",
    start: c(1, 38),
    end: c(1, 46),
    text: "Which rent is the fee based on? If the letter is not in force, it is the old rent and two months: $4,800.",
    cites: [{ file: LEASE, page: 9 }],
    says: [{ at: c(1, 40), text: "Asks which rent the fee is based on." }],
  },
];
const seven: Script = {
  id: "lease-7",
  question,
  files,
  seats: sevenSeats,
  limitMs: c(5, 0),
  readyAt: readySeven,
  phases: [
    { clock: 0, phase: "research" },
    { clock: c(0, 42), phase: "debate" },
    { clock: c(1, 46), phase: "vote" },
    { clock: c(1, 56), phase: "debate" },
  ],
  rounds: [
    { clock: c(0, 42), round: 1 },
    { clock: c(1, 56), round: 2 },
  ],
  turns: [
    ...research,
    ...extraResearch,
    ...later(round1, 10000),
    ...extraRound1,
    {
      seat: "Qwen",
      round: 2,
      kind: "reply",
      to: ["Hermes"],
      start: c(1, 57),
      end: c(2, 9),
      text: "Hermes, the new rent. The letter sets both the rent and the fee, and says it replaces section 14.",
      cites: [{ file: LETTER, page: 1 }],
      says: [{ at: c(1, 59), text: "Tells Hermes the letter sets the rent and the fee." }],
    },
  ],
  tallies: [
    {
      clock: c(1, 50),
      round: 1,
      groups: [
        { answerId: "A", statement: A, seats: ["Qwen", "Gemma", "Granite", "Mistral"] },
        { answerId: "B", statement: B, seats: ["Llama", "Hermes"] },
        { answerId: "D", statement: D, seats: ["Phi"] },
      ],
    },
  ],
};

// ---- two, four and six seats: the sizes the top bar's slider reaches (with three and five) ----

// Two seats: both must agree. The three-seat story without Gemma; Qwen makes her point himself.
const two: Script = {
  ...three,
  id: "lease-2",
  seats: ["Llama", "Qwen"].map(seat),
  readyAt: { Llama: 3000, Qwen: 13000 },
  turns: [
    ...only(research, ["Llama", "Qwen"]),
    ...only(round1, ["Llama", "Qwen"]),
    ...only(round2.slice(0, 1), ["Llama", "Qwen"]),
    {
      seat: "Qwen",
      round: 2,
      kind: "reply",
      to: ["Llama"],
      start: c(1, 41),
      end: c(1, 50),
      text: "Llama, the letter says so itself. Page 1: this letter replaces section 14 of your lease, and the early-termination fee is one month's rent.",
      cites: [{ file: LETTER, page: 1, quote: "replaces section 14" }],
      says: [{ at: c(1, 44), text: "Cites the renewal letter, page 1: fee is one month." }],
    },
    {
      seat: "Llama",
      round: 2,
      kind: "reply",
      to: ["Qwen"],
      start: c(1, 50),
      end: c(2, 2),
      text: "Qwen, you are right. Page 1 of the letter says it replaces section 14. I agree: one month's rent at the new rate.",
      says: [{ at: c(1, 52), text: "Now agrees: one month, $2,520." }],
    },
    {
      seat: "Qwen",
      round: 2,
      kind: "answer",
      start: c(2, 10),
      end: c(2, 10),
      afterStop: { start: 1000, end: 12000 },
      text: shortAnswerText,
      cites: [
        { file: LETTER, page: 1 },
        { file: LEASE, page: 9 },
      ],
    },
  ],
  tallies: [
    {
      clock: c(1, 24),
      round: 1,
      groups: [
        { answerId: "A", statement: A, seats: ["Qwen"] },
        { answerId: "B", statement: B, seats: ["Llama"] },
      ],
    },
    { clock: c(2, 10), round: 2, groups: [{ answerId: "A", statement: A, seats: ["Qwen", "Llama"] }] },
  ],
};

// Four seats: the main story without Phi, so nobody is left to disagree and all four must agree.
const fourNames = ["Llama", "Qwen", "Gemma", "Mistral"];
const four: Script = {
  ...main,
  id: "lease-4",
  seats: fourNames.map(seat),
  readyAt: { Llama: 3000, Gemma: 9000, Qwen: 13000, Mistral: 18000 },
  turns: only([...research, ...round1, ...round2, ...round3, ...closing], fourNames).map((t) =>
    // in the main story Llama leans on Phi's doubt here; without Phi the doubt is his own
    t.seat === "Llama" && t.start === c(2, 20)
      ? {
          ...t,
          text: "Gemma, I accept that the letter says it replaces section 14. I am not yet sure a letter alone can change a signed lease.",
          says: [{ at: c(2, 22), text: "Accepts the wording, doubts a letter is enough." }],
        }
      : t,
  ),
  tallies: [
    {
      clock: c(1, 24),
      round: 1,
      groups: [
        { answerId: "A", statement: A, seats: ["Qwen", "Gemma"] },
        { answerId: "B", statement: B, seats: ["Llama"] },
        { answerId: "C", statement: C, seats: ["Mistral"] },
      ],
    },
    {
      clock: c(2, 40),
      round: 2,
      groups: [
        { answerId: "A", statement: A, seats: ["Qwen", "Gemma", "Mistral"] },
        { answerId: "B", statement: B, seats: ["Llama"] },
      ],
    },
    {
      clock: c(3, 40),
      round: 3,
      groups: [{ answerId: "A", statement: A, seats: ["Qwen", "Gemma", "Mistral", "Llama"] }],
    },
  ],
  release: main.release ? { ...main.release, dissentSeats: [] } : undefined,
};

// Six seats: the main story with Granite seated third. Granite reads and gives a position after
// the other five, so everything from the first vote on happens SIX_LATE later than in the main story.
const SIX_LATE = 13000;
const sixNames = ["Phi", "Llama", "Granite", "Qwen", "Gemma", "Mistral"];
const lateBy = (clock: number) => clock + SIX_LATE;
const six: Script = {
  ...main,
  id: "lease-6",
  seats: sixNames.map(seat),
  readyAt: { Llama: 3000, Phi: 6000, Gemma: 9000, Granite: 11000, Qwen: 13000, Mistral: 18000 },
  pauses: main.pauses?.map((p) => ({ ...p, clock: lateBy(p.clock) })),
  phases: [
    { clock: 0, phase: "research" },
    { clock: c(0, 37), phase: "debate" },
    ...main.phases.slice(2).map((p) => ({ ...p, clock: lateBy(p.clock) })),
  ],
  rounds: [{ clock: c(0, 37), round: 1 }, ...main.rounds.slice(1).map((r) => ({ ...r, clock: lateBy(r.clock) }))],
  turns: [
    ...research,
    ...extraResearch.slice(0, 1),
    ...later(round1, 5000),
    ...later(extraRound1.slice(0, 1), -5000),
    ...later([...round2, ...round3, ...closing], SIX_LATE),
  ],
  tallies: [
    {
      clock: lateBy(vote1.clock),
      round: 1,
      groups: [
        { answerId: "A", statement: A, seats: ["Qwen", "Gemma", "Granite"] },
        { answerId: "B", statement: B, seats: ["Llama"] },
        { answerId: "C", statement: C, seats: ["Mistral"] },
        { answerId: "D", statement: D, seats: ["Phi"] },
      ],
    },
    {
      clock: lateBy(vote2.clock),
      round: 2,
      groups: [
        { answerId: "A", statement: A, seats: ["Qwen", "Gemma", "Granite", "Mistral"] },
        { answerId: "B", statement: B, seats: ["Llama"] },
        { answerId: "D", statement: D, seats: ["Phi"] },
      ],
    },
    {
      clock: lateBy(vote3.clock),
      round: 3,
      groups: [
        { answerId: "A", statement: A, seats: ["Qwen", "Gemma", "Granite", "Mistral", "Llama"] },
        { answerId: "D", statement: D, seats: ["Phi"] },
      ],
    },
  ],
  notes: main.notes?.map((n) => ({
    ...n,
    queued: lateBy(n.queued),
    delivered: n.delivered === undefined ? undefined : lateBy(n.delivered),
  })),
  release: main.release ? { ...main.release, clock: lateBy(main.release.clock) } : undefined,
};

// Layout stress only: five seats talking over each other. Shown, and labelled, because the
// engine has not decided whether seats speak one at a time.
const busyTurn = (name: string, start: number, text: string, line: string): TurnSpec => ({
  seat: name,
  round: 2,
  kind: "reply",
  start: c(1, start),
  end: c(2, 30),
  open: true,
  text,
  says: [{ at: c(1, start + 2), text: line }],
});
const sevenBusy: Script = {
  ...seven,
  id: "lease-7-busy",
  phases: [
    { clock: 0, phase: "research" },
    { clock: c(0, 42), phase: "debate" },
    { clock: c(1, 30), phase: "vote" },
    { clock: c(1, 38), phase: "debate" },
  ],
  rounds: [
    { clock: c(0, 42), round: 1 },
    { clock: c(1, 38), round: 2 },
  ],
  turns: [
    ...research,
    ...extraResearch,
    busyTurn(
      "Llama",
      40,
      "A letter cannot rewrite a signed lease by itself.",
      "Holds that a letter cannot change the lease.",
    ),
    busyTurn("Granite", 41, "The letter says it replaces section 14.", "Says the letter replaces section 14."),
    busyTurn(
      "Qwen",
      42,
      "It is one month at the new rate, not two.",
      "Tells Mistral the fee is one month at the new rent.",
    ),
    busyTurn(
      "Gemma",
      43,
      "Page 1 sets the fee at one month's rent.",
      "Cites the renewal letter, page 1: fee is one month.",
    ),
    busyTurn("Hermes", 44, "Which rent is the fee based on?", "Asks which rent the fee is based on."),
  ],
  tallies: [
    {
      clock: c(1, 34),
      round: 1,
      groups: [
        { answerId: "A", statement: A, seats: ["Qwen", "Gemma", "Granite", "Mistral"] },
        { answerId: "B", statement: B, seats: ["Llama", "Hermes"] },
        { answerId: "D", statement: D, seats: ["Phi"] },
      ],
    },
  ],
};

// Time runs out on the 2-minute preset: the answer with the most support is released, marked "No consensus".
const timeUp: Script = {
  id: "lease-timeup",
  question,
  files,
  seats: five,
  limitMs: c(2, 0),
  readyAt: readyFive,
  phases: [
    { clock: 0, phase: "research" },
    { clock: c(0, 32), phase: "debate" },
    { clock: c(1, 20), phase: "vote" },
    { clock: c(1, 30), phase: "debate" },
    { clock: c(2, 0), phase: "writing", afterStop: 500 },
    { clock: c(2, 0), phase: "released", afterStop: 21000 },
  ],
  rounds: [
    { clock: c(0, 32), round: 1 },
    { clock: c(1, 30), round: 2 },
  ],
  turns: [
    ...research,
    ...round1,
    ...round2.slice(0, 3).map((t, i) => (i === 2 ? { ...t, end: c(1, 58) } : t)),
    {
      seat: "Qwen",
      round: 2,
      kind: "answer",
      start: c(2, 0),
      end: c(2, 0),
      afterStop: { start: 1000, end: 12000 },
      text: "Probably yes: 60 days' written notice and one month's rent at the new rate, $2,520. The council did not agree on this in the time allowed, so treat it with care.",
      cites: [
        { file: LETTER, page: 1 },
        { file: LEASE, page: 9 },
      ],
    },
    {
      seat: "Llama",
      round: 2,
      kind: "dissent",
      start: c(2, 0),
      end: c(2, 0),
      afterStop: { start: 12000, end: 15000 },
      text: "The lease sets two months' rent at the old rate, $4,800; a letter cannot change that by itself.",
      cites: [{ file: LEASE, page: 9 }],
    },
    {
      seat: "Mistral",
      round: 2,
      kind: "dissent",
      start: c(2, 0),
      end: c(2, 0),
      afterStop: { start: 15000, end: 18000 },
      text: "Two months' rent still applies, at the new rate: $5,040.",
      cites: [{ file: LEASE, page: 9 }],
    },
    {
      seat: "Phi",
      round: 2,
      kind: "dissent",
      start: c(2, 0),
      end: c(2, 0),
      afterStop: { start: 18000, end: 21000 },
      text: dissentText,
      cites: [{ file: LETTER, page: 2 }],
    },
  ],
  tallies: [vote1],
  release: {
    clock: c(2, 0),
    afterStop: 21000,
    outcome: "no-consensus",
    tallyRound: 1,
    rounds: 2,
    answerSeat: "Qwen",
    dissentSeats: ["Llama", "Mistral", "Phi"],
  },
};

// One model fails to load. The stage stops and asks: Try again, Continue with 4, or Stop.
const failed: Script = {
  id: "lease-failed",
  question,
  files,
  seats: five,
  limitMs: c(5, 0),
  readyAt: { Llama: 3000, Gemma: 9000, Qwen: 13000, Mistral: 18000 },
  failed: { seat: "Phi", at: 6000, reason: "Not enough free memory on the GX10. It needs 9 GB and 6 GB is free." },
  phases: [],
  rounds: [],
  turns: [],
  tallies: [],
};

export const lease: Fixture = build(main);
export const lease2: Fixture = build(two);
export const lease3: Fixture = build(three);
export const lease4: Fixture = build(four);
export const lease6: Fixture = build(six);
export const lease7: Fixture = build(seven);
export const lease7Busy: Fixture = build(sevenBusy);
export const leaseTimeUp: Fixture = build(timeUp);
export const leaseFailed: Fixture = build(failed);

export const fixtures: Record<string, Fixture> = {
  lease,
  "lease-2": lease2,
  "lease-3": lease3,
  "lease-4": lease4,
  "lease-6": lease6,
  "lease-7": lease7,
  "lease-7-busy": lease7Busy,
  "lease-timeup": leaseTimeUp,
  "lease-failed": leaseFailed,
};

/** The sample debate for each council size the top bar's slider reaches. */
export const COUNCIL_MIN = 2;
export const COUNCIL_MAX = 6;
export const bySeats: Record<number, string> = { 2: "lease-2", 3: "lease-3", 4: "lease-4", 5: "lease", 6: "lease-6" };

export const sample = { question, files, positions: { A, B, C, D }, answerText, shortAnswerText, dissentText };
