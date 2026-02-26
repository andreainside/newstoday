// frontend/app/page.tsx
import Link from "next/link";
type TopEventItem = {
  event_id: number;
  title: string;
  start_time: string | null;
  end_time: string | null;
  last_seen_at: string;
  articles_count: number;
  sources_count: number;
  score: number;
  score_components: {
    hot: number;
    div: number;
    fresh: number;
    age_hours: number;
  };
};

type TopEventsResponse = {
  as_of: string;
  window_hours: number;
  tau_hours: number;
  weights: { hot: number; div: number; fresh: number };
  items: TopEventItem[];
};

async function fetchTopEvents(): Promise<TopEventsResponse> {
  const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  const res = await fetch(`${API_BASE}/api/events/top?limit=5`, { cache: "no-store" });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to fetch top events: ${res.status} ${text}`);
  }

  return res.json();
}

export default async function HomePage() {
  const data = await fetchTopEvents(5);
  const bgMap = assignEventBackgrounds(data.items);

  return (
    <main style={{ maxWidth: 900, margin: "24px auto", padding: "0 16px" }}>
      <h1 style={{ fontSize: 24, fontWeight: 700 }}>NewsToday</h1>
      <p style={{ marginTop: 8, color: "#555" }}>
        Top 5 events (as_of: {data.as_of}, window: {data.window_hours}h)
      </p>

      <div style={{ marginTop: 16, display: "grid", gap: 12 }}>
        {data.items.map((ev) => (
          <Link
            key={ev.event_id}
            href={`/events/${ev.event_id}`}
            style={{
              display: "block",
              padding: 14,
              border: "1px solid #ddd",
              borderRadius: 10,
              textDecoration: "none",
              color: "inherit",
            }}
          >
            <div style={{ fontSize: 16, fontWeight: 600 }}>{ev.title}</div>

            <div style={{ marginTop: 8, fontSize: 13, color: "#555" }}>
              Articles: {ev.articles_count} · Sources: {ev.sources_count} ·
              Score: {ev.score.toFixed(4)}
            </div>

            <div style={{ marginTop: 6, fontSize: 12, color: "#777" }}>
              Fresh(age_hours): {ev.score_components.age_hours.toFixed(1)} ·
              hot={ev.score_components.hot.toFixed(2)} · div=
              {ev.score_components.div.toFixed(2)} · fresh=
              {ev.score_components.fresh.toFixed(2)}
            </div>
          </Link>
        ))}
      </div>
    </main>
  );
}
