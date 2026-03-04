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
  CATEGORIES.map((c) => [c.toLowerCase(), c]),
);

const CATEGORY_POOLS: Record<EventCategory, string[]> = {
  Crime: [
    "/event-bg/Crime/Crime01.jpg",
    "/event-bg/Crime/Crime02.jpg",
    "/event-bg/Crime/Crime03.jpg",
    "/event-bg/Crime/Crime04.jpg",
    "/event-bg/Crime/Crime05.jpg",
    "/event-bg/General/general01.jpg",
    "/event-bg/General/general02.jpg",
    "/event-bg/General/general03.jpg",
    "/event-bg/General/general04.jpg",
    "/event-bg/General/general05.jpg",
  ],
  Economy: [
    "/event-bg/Economy/Economy01.jpg",
    "/event-bg/Economy/Economy02.jpg",
    "/event-bg/Economy/Economy03.jpg",
    "/event-bg/Economy/Economy04.jpg",
    "/event-bg/Economy/Economy05.jpg",
    "/event-bg/General/general01.jpg",
    "/event-bg/General/general02.jpg",
    "/event-bg/General/general03.jpg",
    "/event-bg/General/general04.jpg",
    "/event-bg/General/general05.jpg",
  ],
  Geopolitics: [
    "/event-bg/Geopolitics/Geopolitics01.jpg",
    "/event-bg/Geopolitics/Geopolitics02.jpg",
    "/event-bg/Geopolitics/Geopolitics03.jpg",
    "/event-bg/Geopolitics/Geopolitics04.jpg",
    "/event-bg/Geopolitics/Geopolitics05.jpg",
    "/event-bg/General/general01.jpg",
    "/event-bg/General/general02.jpg",
    "/event-bg/General/general03.jpg",
    "/event-bg/General/general04.jpg",
    "/event-bg/General/general05.jpg",
  ],
  Politics: [
    "/event-bg/Politics/politics01.jpg",
    "/event-bg/Politics/politics02.jpg",
    "/event-bg/Politics/politics03.jpg",
    "/event-bg/Politics/politics04.jpg",
    "/event-bg/Politics/politics05.jpg",
    "/event-bg/General/general01.jpg",
    "/event-bg/General/general02.jpg",
    "/event-bg/General/general03.jpg",
    "/event-bg/General/general04.jpg",
    "/event-bg/General/general05.jpg",
  ],
  Sports: [
    "/event-bg/Sports/Sports01.jpg",
    "/event-bg/Sports/Sports02.jpg",
    "/event-bg/Sports/Sports03.jpg",
    "/event-bg/Sports/Sports04.jpg",
    "/event-bg/Sports/Sports05.jpg",
    "/event-bg/General/general01.jpg",
    "/event-bg/General/general02.jpg",
    "/event-bg/General/general03.jpg",
    "/event-bg/General/general04.jpg",
    "/event-bg/General/general05.jpg",
  ],
  Technology: [
    "/event-bg/Technology/Technology01.jpg",
    "/event-bg/Technology/Technology02.jpg",
    "/event-bg/Technology/Technology03.jpg",
    "/event-bg/Technology/Technology04.jpg",
    "/event-bg/Technology/Technology05.jpg",
    "/event-bg/General/general01.jpg",
    "/event-bg/General/general02.jpg",
    "/event-bg/General/general03.jpg",
    "/event-bg/General/general04.jpg",
    "/event-bg/General/general05.jpg",
  ],
  General: [
    "/event-bg/General/general01.jpg",
    "/event-bg/General/general02.jpg",
    "/event-bg/General/general03.jpg",
    "/event-bg/General/general04.jpg",
    "/event-bg/General/general05.jpg",
    "/event-bg/Crime/Crime01.jpg",
    "/event-bg/Crime/Crime02.jpg",
    "/event-bg/Crime/Crime03.jpg",
    "/event-bg/Economy/Economy01.jpg",
    "/event-bg/Economy/Economy02.jpg",
    "/event-bg/Geopolitics/Geopolitics01.jpg",
    "/event-bg/Geopolitics/Geopolitics02.jpg",
    "/event-bg/Politics/politics01.jpg",
    "/event-bg/Sports/Sports01.jpg",
    "/event-bg/Technology/Technology01.jpg",
  ],
};

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

function daySeed(): string {
  return new Date().toISOString().slice(0, 10);
}

function pickWithCollisionAvoidance(pool: string[], key: string, taken: Set<string>): string {
  const base = hashString(key) % pool.length;
  if (!taken.has(pool[base])) {
    return pool[base];
  }

  const step = 1 + (hashString(`step:${key}`) % (pool.length - 1));
  for (let i = 1; i <= pool.length; i += 1) {
    const candidate = pool[(base + step * i) % pool.length];
    if (!taken.has(candidate)) {
      return candidate;
    }
  }

  return pool[base];
}

export function assignEventBackgrounds(events: EventBgInput[]): Record<number, string> {
  const out: Record<number, string> = {};
  const usedByCategory = new Map<EventCategory, Set<string>>();
  const today = daySeed();

  for (const ev of events) {
    const cat = normalizeCategory(ev.category);
    const pool = CATEGORY_POOLS[cat];
    const used = usedByCategory.get(cat) ?? new Set<string>();
    const key = `${today}:${cat}:${ev.event_id}`;
    const picked = pickWithCollisionAvoidance(pool, key, used);

    used.add(picked);
    usedByCategory.set(cat, used);
    out[ev.event_id] = picked;
  }

  return out;
}
