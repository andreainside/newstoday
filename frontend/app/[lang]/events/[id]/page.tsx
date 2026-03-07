import Link from "next/link";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { getRequestOriginFromHeaders } from "../../../lib/apiBase";
import { toSourceNameZh } from "../../../lib/sourceNameZh";
import SourceNewspaperCard from "../../../events/[id]/components/SourceNewspaperCard";
import {
  copyFor,
  fetchEventDetail,
  fetchEventTitleZh,
  fmtTimeToMinute,
  groupArticlesBySource,
  resolveCoverageRange,
  type EventDetailResponse,
} from "../../../events/[id]/eventDetailShared";
import styles from "../../../events/[id]/eventDetail.module.css";

const SUPPORTED_LANGS = new Set(["en", "zh"]);

function EventHeader({
  event,
  articles,
  lang,
}: {
  event: EventDetailResponse["event"];
  articles: EventDetailResponse["articles"];
  lang: string;
}) {
  const t = copyFor(lang);
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

function GroupedArticleList({
  articles,
  lang,
}: {
  articles: EventDetailResponse["articles"];
  lang: string;
}) {
  const t = copyFor(lang);
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
              sourceName={lang === "zh" ? toSourceNameZh(sourceName) : sourceName}
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

export default async function LocalizedEventDetailPage({
  params,
}: {
  params: Promise<{ lang: string; id: string }>;
}) {
  const { lang, id } = await params;

  if (!SUPPORTED_LANGS.has(lang)) {
    notFound();
  }

  if (!id) {
    throw new Error("Route param id is missing");
  }

  const t = copyFor(lang);
  const requestHeaders = await headers();
  const requestOrigin = getRequestOriginFromHeaders(requestHeaders);
  const data = await fetchEventDetail(id, requestOrigin);

  if (lang === "zh") {
    const zhTitle = await fetchEventTitleZh(data.event.event_id, requestOrigin);
    if (zhTitle) {
      data.event.title = zhTitle;
    }
  }

  return (
    <main className={styles.page}>
      <Link href={`/${lang}`} className={styles.backLink}>
        {t.back}
      </Link>

      <EventHeader event={data.event} articles={data.articles} lang={lang} />
      <GroupedArticleList articles={data.articles} lang={lang} />
    </main>
  );
}
