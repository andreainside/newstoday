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

function emptyTopEventsResponse(): TopEventsResponse {
  return {
    as_of: new Date().toISOString(),
    window_hours: 24,
    tau_hours: 6,
    weights: { hot: 1, div: 1, fresh: 1 },
    items: [],
  };
}

export async function fetchTopEvents(limit = 5): Promise<TopEventsResponse> {
  const API_BASE = process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  const timeoutMs = 5000;

  try {
    const res = await fetch(`${API_BASE}/api/events/top?limit=${limit}`, {
      next: { revalidate: 30 },
      signal: AbortSignal.timeout(timeoutMs),
    });

    if (!res.ok) {
      const text = await res.text();
      console.error(`Failed to fetch top events: ${res.status} ${text}`);
      return emptyTopEventsResponse();
    }

    return res.json();
  } catch (error) {
    if (error instanceof Error && error.name === "TimeoutError") {
      console.error(`Fetching top events timed out after ${timeoutMs}ms`);
      return emptyTopEventsResponse();
    }
    console.error("Failed to fetch top events:", error);
    return emptyTopEventsResponse();
  }
}
