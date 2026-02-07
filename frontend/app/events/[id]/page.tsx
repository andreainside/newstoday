// frontend/app/events/[id]/page.tsx

type EventDetailResponse = {
  event: {
    event_id: number;
    title: string;
    start_time: string | null;
    end_time: string | null;
    last_seen_at: string;
    articles_count: number;
    sources_count: number;
  };
  coverage: {
    types: string[];
    rows: Array<{
      source_id: number;
      source_name: string;
      counts: Record<string, number>;
    }>;
    totals: Record<string, number>;
  };
  gaps: {
    status: string;
    gap_codes?: string[];
    gaps?: Array<{
      code: string;
      message: string;
      evidence: Record<string, unknown> | unknown;
    }>;
  };
  articles: Array<{
    article_id: number;
    published_at: string | null;
    title: string;
    link: string;
    type: string | null;
    type_reason: string | null;
    source: {
      source_id: number;
      name: string;
      url: string;
    };
  }>;
};

// JSON shape (observed from /api/events/{id})
// {
//   event: {
//     event_id: number;
//     title: string;
//     start_time: string | null;
//     end_time: string | null;
//     last_seen_at: string;
//     articles_count: number;
//     sources_count: number;
//   };
//   coverage: {
//     event_id: number;
//     types: string[];
//     rows: Array<{
//       source_id: number;
//       source_name: string;
//       counts: { FACT: number; INTERPRETATION: number; COMMENTARY: number };
//       article_ids: { FACT: number[]; INTERPRETATION: number[]; COMMENTARY: number[] };
//     }>;
//     totals: { FACT: number; INTERPRETATION: number; COMMENTARY: number };
//   };
//   gaps: {
//     event_id: number;
//     status: string;
//     message: string;
//     gaps: Array<{
//       code: string;
//       message: string;
//       evidence: Record<string, unknown>;
//     }>;
//     gap_codes: string[];
//     hints: Array<Record<string, unknown>>;
//     evidence_summary: Record<string, unknown>;
//   };
//   articles: Array<{
//     article_id: number;
//     published_at: string | null;
//     title: string;
//     link: string;
//     type: string | null;
//     type_reason: string | null;
//     source: {
//       source_id: number;
//       name: string;
//       url: string;
//     };
//   }>;
// }

function fmtTime(s: string | null | undefined) {
  if (!s) return "";
  return s.replace("T", " ").replace("Z", "");
}

async function fetchEventDetail(id: string): Promise<EventDetailResponse> {
  const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  const res = await fetch(`${API_BASE}/api/events/${id}`, {
    cache: "no-store",
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to fetch event detail: ${res.status} ${text}`);
  }
  return res.json();
}

function EventHeader({ event }: { event: EventDetailResponse["event"] }) {
  const hasStart = !!event.start_time;
  const hasEnd = !!event.end_time;
  const timeLine = hasStart && hasEnd
    ? `${fmtTime(event.start_time)} ~ ${fmtTime(event.end_time)}`
    : hasStart
      ? fmtTime(event.start_time)
      : hasEnd
        ? fmtTime(event.end_time)
        : "";

  return (
    <section>
      <h1 style={{ marginTop: 12, fontSize: 26, fontWeight: 800, color: "#1e1b16" }}>
        {event.title}
      </h1>

      {timeLine ? (
        <div style={{ marginTop: 8, fontSize: 12, color: "#6a5f53" }}>
          {timeLine}
        </div>
      ) : null}

      <div style={{ marginTop: 8, fontSize: 13, color: "#4b433a" }}>
        Event #{event.event_id}
      </div>

      <div style={{ marginTop: 6, fontSize: 13, color: "#4b433a" }}>
        Articles: {event.articles_count} · Sources: {event.sources_count}
      </div>
    </section>
  );
}

function GapPanel({ gaps }: { gaps: EventDetailResponse["gaps"] }) {
  const gapCodesRaw = Array.isArray(gaps?.gap_codes) ? gaps.gap_codes : [];
  const gapCodes = Array.from(new Set(gapCodesRaw));
  const gapList = Array.isArray(gaps?.gaps) ? gaps.gaps : [];

  const renderEvidence = (evidence: any) => {
    if (!evidence || typeof evidence !== "object" || Array.isArray(evidence)) {
      return (
        <pre style={{ margin: 0, fontSize: 11, color: "#6a5f53", whiteSpace: "pre-wrap" }}>
{JSON.stringify(evidence, null, 2)}
        </pre>
      );
    }

    const missingTypes = Array.isArray(evidence.missing_types) ? evidence.missing_types : null;
    const typeCounts = evidence.type_counts ?? null;
    const totalArticles = typeof evidence.total_articles === "number" ? evidence.total_articles : null;
    const distinctSources = typeof evidence.distinct_sources === "number" ? evidence.distinct_sources : null;

    return (
      <div style={{ display: "grid", gap: 10 }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#1e1b16" }}>Type evidence</div>
          <div style={{ marginTop: 6, display: "grid", gap: 6, fontSize: 12, color: "#6a5f53" }}>
            {missingTypes ? (
              <div>missing_types: {missingTypes.join(", ")}</div>
            ) : null}
            {typeCounts ? (
              <div>
                type_counts: FACT {typeCounts.FACT ?? 0}, INTERPRETATION {typeCounts.INTERPRETATION ?? 0}, COMMENTARY {typeCounts.COMMENTARY ?? 0}
              </div>
            ) : null}
          </div>
        </div>

        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#1e1b16" }}>Event scale indicators</div>
          <div style={{ marginTop: 6, display: "grid", gap: 6, fontSize: 12, color: "#6a5f53" }}>
            {totalArticles !== null ? <div>total_articles: {totalArticles}</div> : null}
            {distinctSources !== null ? <div>distinct_sources: {distinctSources}</div> : null}
          </div>
        </div>
      </div>
    );
  };

  return (
    <section style={{ marginTop: 20 }}>
      <details>
        <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 13, color: "#1e1b16" }}>
          {gaps?.status ?? "UNKNOWN"}
          {gapCodes.length > 0 ? ` · ${gapCodes.join(" · ")}` : ""}
        </summary>

        <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
          {gapList.map((g, idx) => (
            <div
              key={idx}
              style={{
                border: "1px solid #e3dbd0",
                borderRadius: 12,
                padding: 12,
                background: "#fffdf9",
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 600, color: "#1e1b16" }}>{g.code}</div>
              <div style={{ marginTop: 8, fontSize: 12, fontWeight: 600, color: "#1e1b16" }}>
                Why this gap was flagged
              </div>
              <div style={{ marginTop: 6, fontSize: 12, color: "#4b433a" }}>{g.message}</div>

              <div style={{ marginTop: 10, fontSize: 12, fontWeight: 600, color: "#1e1b16" }}>
                Evidence (for audit)
              </div>
              <div style={{ marginTop: 6 }}>
                {renderEvidence(g.evidence)}
              </div>
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}

function CoverageMatrix({ coverage }: { coverage: EventDetailResponse["coverage"] }) {
  const types = Array.isArray(coverage?.types) ? coverage.types : [];
  const rows = Array.isArray(coverage?.rows) ? coverage.rows : [];

  return (
    <section style={{ marginTop: 20 }}>
      <details>
        <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: 13, color: "#1e1b16" }}>
          Coverage Matrix
        </summary>

        <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: `1.5fr repeat(${types.length}, minmax(0, 1fr))`,
              gap: 8,
              fontSize: 12,
              color: "#6a5f53",
            }}
          >
            <div>Source</div>
            {types.map((t) => (
              <div key={t}>{t}</div>
            ))}
          </div>

          {rows.map((r) => (
            <div
              key={r.source_id}
              style={{
                display: "grid",
                gridTemplateColumns: `1.5fr repeat(${types.length}, minmax(0, 1fr))`,
                gap: 8,
                alignItems: "center",
                border: "1px solid #e3dbd0",
                borderRadius: 10,
                padding: 10,
                fontSize: 12,
              }}
            >
              <div style={{ fontWeight: 600, color: "#1e1b16" }}>{r.source_name}</div>
              {types.map((t) => (
                <div key={t} style={{ color: "#4b433a" }}>
                  {r.counts?.[t] ?? 0}
                </div>
              ))}
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}

function ArticleList({ articles }: { articles: EventDetailResponse["articles"] }) {
  return (
    <section style={{ marginTop: 20 }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: "#1e1b16" }}>Article List</div>
      <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
        {articles.map((a) => {
          const effectiveType = (a as any).effective_type ?? a.type ?? "N/A";
          return (
            <div
              key={a.article_id}
              style={{
                border: "1px solid #e3dbd0",
                borderRadius: 12,
                padding: 12,
                background: "#fffdf9",
              }}
            >
              <div style={{ fontWeight: 700, color: "#1e1b16" }}>{a.title}</div>
              <div style={{ marginTop: 6, fontSize: 12, color: "#4b433a" }}>
                {a.source?.name ?? "Unknown"} · {fmtTime(a.published_at)}
              </div>
              <div style={{ marginTop: 6, fontSize: 12, color: "#6a5f53" }}>
                {effectiveType}
              </div>
              <div style={{ marginTop: 8 }}>
                <a href={a.link} target="_blank" rel="noreferrer" style={{ color: "#1e1b16" }}>
                  Open original
                </a>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default async function EventDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  if (!id) {
    throw new Error("Route param id is missing");
  }

  const data = await fetchEventDetail(id);

  return (
    <main style={{ maxWidth: 900, margin: "24px auto", padding: "0 16px" }}>
      <a href="/" style={{ textDecoration: "none", color: "#1e1b16", fontSize: 13 }}>
        Back
      </a>

      <EventHeader event={data.event} />
      <GapPanel gaps={data.gaps} />
      <CoverageMatrix coverage={data.coverage} />
      <ArticleList articles={data.articles} />
    </main>
  );
}
