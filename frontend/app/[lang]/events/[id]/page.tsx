import Link from "next/link";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { getRequestOriginFromHeaders, makeApiUrl } from "../../../lib/apiBase";
import { toSourceNameZh } from "../../../lib/sourceNameZh";
import SourceNewspaperCard, {
  type SourceArticle,
} from "../../../events/[id]/components/SourceNewspaperCard";
import styles from "../../../events/[id]/eventDetail.module.css";

const SUPPORTED_LANGS = new Set(["en", "zh"]);

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

type EventTitleZhResponse = {
  title: string | null;
  status: string;
};

function copyFor(lang: string) {
  if (lang === "zh") {
    return {
      back: "返回",
      eventCoverage: "事件覆盖时间",
      lastArticleUpdate: "最后文章更新时间",
      articles: "篇文章",
      sources: "个来源",
      noArticles: "该事件暂时没有文章。",
      articleCountLabel: "篇",
      showMore: "展开更多",
      showLess: "收起",
    };
  }

  return {
    back: "Back",
    eventCoverage: "Event coverage",
    lastArticleUpdate: "Last article update",
    articles: "Articles",
    sources: "Sources",
    noArticles: "No articles for this event yet.",
    articleCountLabel: "articles",
    showMore: "Show more",
    showLess: "Show less",
  };
}

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

async function fetchEventTitleZh(eventId: number, origin?: string): Promise<string | null> {
  try {
    const res = await fetch(makeApiUrl(`/api/events/${eventId}/title-zh`, origin), {
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as EventTitleZhResponse;
    return data.title || null;
  } catch {
    return null;
  }
}

async function fetchEventDetail(id: string, origin?: string): Promise<EventDetailResponse> {
  const res = await fetch(makeApiUrl(`/api/events/${id}`, origin), {
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
