import Link from "next/link";
import { notFound } from "next/navigation";
import { makeApiUrl } from "../../lib/apiBase";
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

function parseTime(s: string | null | undefined): Date | null {
  if (!s) return null;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

function fmtTimeToMinute(s: string | null | undefined) {
  const d = parseTime(s);
  if (!d) return "";
  return d.toISOString().slice(0, 16).replace("T", " ");
}

function resolveCoverageRange(
  event: EventDetailResponse["event"],
  articles: EventDetailResponse["articles"],
) {
  const articleTimes = articles
    .map((a) => parseTime(a.published_at))
    .filter((t): t is Date => t !== null)
    .sort((a, b) => a.getTime() - b.getTime());

  const start = articleTimes[0] || parseTime(event.start_time);
  const endCandidates = [
    articleTimes.length > 0 ? articleTimes[articleTimes.length - 1] : null,
    parseTime(event.end_time),
    parseTime(event.last_seen_at),
  ].filter((t): t is Date => t !== null);
  const end = endCandidates.length > 0
    ? endCandidates.reduce((latest, cur) => (cur.getTime() > latest.getTime() ? cur : latest))
    : null;

  return {
    start: start ? fmtTimeToMinute(start.toISOString()) : "",
    end: end ? fmtTimeToMinute(end.toISOString()) : "",
  };
}

async function fetchEventDetail(id: string): Promise<EventDetailResponse> {
  const res = await fetch(makeApiUrl(`/api/events/${id}`), {
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

  const latestArticleTs = (items: EventDetailResponse["articles"]) => {
    const firstWithTs = items.find((it) => !!it.published_at);
    return firstWithTs?.published_at ? Date.parse(firstWithTs.published_at) : Number.NEGATIVE_INFINITY;
  };

  const sortedGroups = Object.entries(groupedBySource).sort((a, b) => {
    const latestDiff = latestArticleTs(b[1]) - latestArticleTs(a[1]);
    if (latestDiff !== 0) return latestDiff;

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

      <EventHeader event={data.event} articles={data.articles} />
      <GroupedArticleList articles={data.articles} />
    </main>
  );
}
