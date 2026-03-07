import Link from "next/link";
import { headers } from "next/headers";
import { getRequestOriginFromHeaders } from "../../lib/apiBase";
import SourceNewspaperCard from "./components/SourceNewspaperCard";
import {
  copyFor,
  fetchEventDetail,
  fmtTimeToMinute,
  groupArticlesBySource,
  resolveCoverageRange,
  type EventDetailResponse,
} from "./eventDetailShared";
import styles from "./eventDetail.module.css";

function EventHeader({
  event,
  articles,
}: {
  event: EventDetailResponse["event"];
  articles: EventDetailResponse["articles"];
}) {
  const t = copyFor("en");
  const coverage = resolveCoverageRange(event, articles);
  const eventRange = coverage.start && coverage.end
    ? `${coverage.start} ~ ${coverage.end}`
    : coverage.start || coverage.end;
  const lastSeen = fmtTimeToMinute(event.last_seen_at);

  return (
    <section className={styles.header}>
      <h1 className={styles.title}>{event.title}</h1>

      {eventRange ? (
        <div className={styles.timeLine}>{t.eventCoverage}: {eventRange}</div>
      ) : null}

      {lastSeen ? (
        <div className={styles.timeLine}>{t.lastArticleUpdate}: {lastSeen}</div>
      ) : null}

      <div className={styles.metaChips}>
        <span className={styles.chip}>{t.articles} {event.articles_count}</span>
        <span className={styles.chip}>{t.sources} {event.sources_count}</span>
      </div>
    </section>
  );
}

function GroupedArticleList({ articles }: { articles: EventDetailResponse["articles"] }) {
  const t = copyFor("en");
  const { sortedGroups, featuredSourceName } = groupArticlesBySource(articles);

  return (
    <section className={styles.groupedSection}>
      {sortedGroups.length === 0 ? (
        <div className={styles.emptyCard}>{t.noArticles}</div>
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
              articleCountLabel={t.articleCountLabel}
              showMoreLabel={t.showMore}
              showLessLabel={t.showLess}
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
  const requestHeaders = await headers();
  const requestOrigin = getRequestOriginFromHeaders(requestHeaders);

  if (!id) {
    throw new Error("Route param id is missing");
  }

  const data = await fetchEventDetail(id, requestOrigin);

  return (
    <main className={styles.page}>
      <Link href="/" className={styles.backLink}>
        {copyFor("en").back}
      </Link>

      <EventHeader event={data.event} articles={data.articles} />
      <GroupedArticleList articles={data.articles} />
    </main>
  );
}
