export type EventCategory =
  | "Crime"
  | "Economy"
  | "Geopolitics"
  | "Politics"
  | "Sports"
  | "Technology"
  | "General";

export type EventBgInput = {
  event_id: number;
  category?: string | null;
};

const CATEGORIES: EventCategory[] = [
  "Crime",
  "Economy",
  "Geopolitics",
  "Politics",
  "Sports",
  "Technology",
  "General",
];

const CATEGORY_MAP = new Map<string, EventCategory>(
  CATEGORIES.map((c) => [c.toLowerCase(), c])
);

function normalizeCategory(category?: string | null): EventCategory {
  if (!category) return "General";
  const mapped = CATEGORY_MAP.get(category.toLowerCase());
  return mapped ?? "General";
}

function hashString(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function baseIndex(category: EventCategory, eventId: number): number {
  return hashString(`${category}:${eventId}`) % 5;
}

function fallbackOffset(category: EventCategory, eventId: number): number {
  return 1 + (hashString(`fallback:${category}:${eventId}`) % 4);
}

export function assignEventBackgrounds(events: EventBgInput[]): Record<number, string> {
  const used = new Map<EventCategory, Set<number>>();
  const out: Record<number, string> = {};

  for (const ev of events) {
    const cat = normalizeCategory(ev.category);
    const taken = used.get(cat) ?? new Set<number>();
    const base = baseIndex(cat, ev.event_id);
    let pick = base;

    if (taken.has(pick)) {
      const step = fallbackOffset(cat, ev.event_id);
      for (let i = 1; i <= 5; i += 1) {
        const candidate = (base + step * i) % 5;
        if (!taken.has(candidate)) {
          pick = candidate;
          break;
        }
      }
    }

    taken.add(pick);
    used.set(cat, taken);

    const folder = cat;
    const file = `${cat.toLowerCase()}${String(pick + 1).padStart(2, "0")}.jpg`;
    out[ev.event_id] = `/event-bg/${folder}/${file}`;
  }

  return out;
}
