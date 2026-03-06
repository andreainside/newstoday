import Link from "next/link";
import { notFound } from "next/navigation";
import SourceNewspaperCard, { type SourceArticle } from "./components/SourceNewspaperCard";
import styles from "./eventDetail.module.css";

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
  articles: Array<SourceArticle>;
};

function fmtTime(s: string | null | undefined) {
  if (!s) return "";
  return s.replace("T", " ").replace("Z", "");
}

async function fetchEventDetail(id: string): Promise<EventDetailResponse> {
  const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  const res = await fetch(`${API_BASE}/api/events/${id}`, {
    cache: "no-store",
  });

  if (res.status === 404) {
    notFound();
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to fetch event detail: ${res.status} ${text}`);
  }
  return res.json();
}

function EventHeader({ event }: { event: EventDetailResponse["event"] }) {
  const hasStart = !!event.start_time;
  const hasEnd = !!event.end_time;
  const eventRange = hasStart && hasEnd
    ? `${fmtTime(event.start_time)} ~ ${fmtTime(event.end_time)}`
    : hasStart
      ? fmtTime(event.start_time)
      : hasEnd
        ? fmtTime(event.end_time)
        : "";
  const lastSeen = fmtTime(event.last_seen_at);

  return (
    <section className={styles.header}>
      <h1 className={styles.title}>{event.title}</h1>

      {eventRange ? (
        <div className={styles.timeLine}>Event coverage: {eventRange}</div>
      ) : null}

      {lastSeen ? (
        <div className={styles.timeLine}>Last article update: {lastSeen}</div>
      ) : null}

      <div className={styles.metaChips}>
        <span className={styles.chip}>Articles {event.articles_count}</span>
        <span className={styles.chip}>Sources {event.sources_count}</span>
      </div>
    </section>
  );
}

function GroupedArticleList({ articles }: { articles: EventDetailResponse["articles"] }) {
  const groupedBySource = articles.reduce<Record<string, EventDetailResponse["articles"]>>((acc, article) => {
    const sourceName = article.source?.name || "Unknown";
    if (!acc[sourceName]) {
      acc[sourceName] = [];
    }
    acc[sourceName].push(article);
    return acc;
  }, {});

  const sortedGroups = Object.entries(groupedBySource).sort((a, b) => {
    const countDiff = b[1].length - a[1].length;
    if (countDiff !== 0) return countDiff;
    return a[0].localeCompare(b[0]);
  });
  const featuredSourceName = sortedGroups.length > 0 ? sortedGroups[0][0] : null;

  return (
    <section className={styles.groupedSection}>
      {sortedGroups.length === 0 ? (
        <div className={styles.emptyCard}>No articles for this event yet.</div>
      ) : null}

      <div className={styles.groupList}>
        {sortedGroups.map(([sourceName, sourceArticles]) => (
          <div
            key={sourceName}
            className={
              sourceName === featuredSourceName
                ? `${styles.sourceCardWrap} ${styles.featuredCardWrap}`
                : styles.sourceCardWrap
            }
          >
            <SourceNewspaperCard
              sourceName={sourceName}
              articles={sourceArticles}
              isFeatured={sourceName === featuredSourceName}
            />
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

  return (
    <main className={styles.page}>
      <Link href="/" className={styles.backLink}>
        Back
      </Link>

      <EventHeader event={data.event} />
      <GroupedArticleList articles={data.articles} />
    </main>
  );
}
