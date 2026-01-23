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
  coverage: any;
  gaps: any;
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

function fmtTime(s: string | null | undefined) {
  if (!s) return "N/A";
  // 直接展示 ISO，先不做时区花活，保证口径稳定
  return s.replace("T", " ").replace("Z", "");
}

async function fetchEventDetail(id: string): Promise<EventDetailResponse> {
  const res = await fetch(`http://localhost:3000/api/events/${id}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to fetch event detail: ${res.status} ${text}`);
  }
  return res.json();
}

function CoverageMatrixView({ coverage }: { coverage: any }) {
  // 你 2.2B 的 coverage 结构我不强行假设，先用“最安全的渲染”
  // v0：优先显示常见的 counts / rows / cols，如果没有就直接 JSON 预览
  const fact = coverage?.FACT ?? coverage?.fact;
  const interp = coverage?.INTERPRETATION ?? coverage?.interpretation;
  const comm = coverage?.COMMENTARY ?? coverage?.commentary;

  const hasSimple =
    typeof fact === "number" || typeof interp === "number" || typeof comm === "number";

  return (
    <section style={{ marginTop: 16 }}>
      <h2 style={{ fontSize: 16, fontWeight: 700 }}>Coverage Matrix</h2>

      {hasSimple ? (
        <div style={{ marginTop: 8, display: "grid", gap: 8 }}>
          <div style={{ border: "1px solid #ddd", borderRadius: 10, padding: 10 }}>
            <b>FACT</b>: {fact ?? 0}
          </div>
          <div style={{ border: "1px solid #ddd", borderRadius: 10, padding: 10 }}>
            <b>INTERPRETATION</b>: {interp ?? 0}
          </div>
          <div style={{ border: "1px solid #ddd", borderRadius: 10, padding: 10 }}>
            <b>COMMENTARY</b>: {comm ?? 0}
          </div>
        </div>
      ) : (
        <pre
          style={{
            marginTop: 8,
            padding: 12,
            border: "1px solid #ddd",
            borderRadius: 10,
            overflowX: "auto",
            fontSize: 12,
            background: "#111",
            color: "#eee",
          }}
        >
{JSON.stringify(coverage, null, 2)}
        </pre>
      )}
    </section>
  );
}

function GapHintsView({ gaps }: { gaps: any }) {
  // v0：默认折叠，避免焦虑
  const list: any[] = Array.isArray(gaps) ? gaps : (gaps?.items ?? gaps?.gaps ?? []);
  const count = Array.isArray(list) ? list.length : 0;

  return (
    <section style={{ marginTop: 16 }}>
      <details>
        <summary style={{ cursor: "pointer", fontWeight: 700 }}>
          Gaps (weak hint) · {count}
        </summary>

        <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
          {count === 0 ? (
            <div style={{ color: "#666" }}>No gap hints.</div>
          ) : (
            list.map((g, idx) => (
              <div
                key={idx}
                style={{
                  border: "1px solid #ddd",
                  borderRadius: 10,
                  padding: 10,
                  color: "#555",
                }}
              >
                <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
{typeof g === "string" ? g : JSON.stringify(g)}
                </pre>
              </div>
            ))
          )}
        </div>
      </details>
    </section>
  );
}

function ArticleList({ articles }: { articles: EventDetailResponse["articles"] }) {
  return (
    <section style={{ marginTop: 16 }}>
      <h2 style={{ fontSize: 16, fontWeight: 700 }}>Articles</h2>
      <div style={{ marginTop: 8, display: "grid", gap: 10 }}>
        {articles.map((a) => (
          <div
            key={a.article_id}
            style={{
              border: "1px solid #ddd",
              borderRadius: 10,
              padding: 12,
            }}
          >
            <div style={{ fontWeight: 700 }}>{a.title}</div>

            <div style={{ marginTop: 6, fontSize: 13, color: "#555" }}>
              {a.source?.name ?? "Unknown source"} · {fmtTime(a.published_at)}
            </div>

            <div style={{ marginTop: 6, fontSize: 12, color: "#777" }}>
              Type: {a.type ?? "N/A"}
              {a.type_reason ? ` · (${a.type_reason})` : ""}
            </div>

            <div style={{ marginTop: 8 }}>
              <a href={a.link} target="_blank" rel="noreferrer">
                Open original
              </a>
            </div>
          </div>
        ))}
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
  const e = data.event;


  return (
    <main style={{ maxWidth: 900, margin: "24px auto", padding: "0 16px" }}>
      <a href="/" style={{ textDecoration: "none" }}>
        ← Back
      </a>

      <h1 style={{ marginTop: 12, fontSize: 22, fontWeight: 800 }}>
        {e.title}
      </h1>

      <div style={{ marginTop: 10, color: "#555", fontSize: 13 }}>
        Event #{e.event_id} · Articles: {e.articles_count} · Sources:{" "}
        {e.sources_count}
      </div>

      <div style={{ marginTop: 6, color: "#777", fontSize: 12 }}>
        Start: {fmtTime(e.start_time)} · End: {fmtTime(e.end_time)} · Last
        seen: {fmtTime(e.last_seen_at)}
      </div>

      <CoverageMatrixView coverage={data.coverage} />
      <GapHintsView gaps={data.gaps} />
      <ArticleList articles={data.articles} />
    </main>
  );
}
