export type TopEvent = {
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

export type TopEventsResponse = {
  as_of: string;
  window_hours: number;
  tau_hours: number;
  weights: { hot: number; div: number; fresh: number };
  items: TopEvent[];
};

export async function fetchTopEvents(limit = 5): Promise<TopEventsResponse> {
  const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  const res = await fetch(`${API_BASE}/api/events/top?limit=${limit}`, { cache: "no-store" });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to fetch top events: ${res.status} ${text}`);
  }

  return res.json();
}
