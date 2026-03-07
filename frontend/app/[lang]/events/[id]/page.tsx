import Link from "next/link";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { getRequestOriginFromHeaders, makeApiUrl } from "../../../lib/apiBase";
import { toSourceNameZh } from "../../../lib/sourceNameZh";
import SourceNewspaperCard, { type SourceArticle } from "./components/SourceNewspaperCard";
import styles from "./eventDetail.module.css";

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

function copyFor(lang: string) {
  if (lang === "zh") {
    return {
      back: "返回",
      articles: "文章",
      sources: "来源",
      empty: "该事件暂无文章。",
      eventCoverage: "事件覆盖时间",
      lastArticleUpdate: "最后一篇文章更新时间",
    };
  }

  return {
    back: "Back",
    articles: "Articles",
    sources: "Sources",
    empty: "No articles for this event yet.",
    eventCoverage: "Event coverage",
    lastArticleUpdate: "Last article update",
  };
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

async function fetchEventTitleZh(id: string, origin?: string): Promise<EventTitleZhResponse | null> {
  try {
    const res = await fetch(makeApiUrl(`/api/events/${id}/title-zh`, origin), {
      cache: "no-store",
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

function EventHeader({
  event,
  articles,
  t,
}: {
  event: EventDetailResponse["event"];
  articles: EventDetailResponse["articles"];
  t: ReturnType<typeof copyFor>;
}) {
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
        <span className={styles.chip}>
          {t.articles} {event.articles_count}
        </span>
        <span className={styles.chip}>
          {t.sources} {event.sources_count}
        </span>
      </div>
    </section>
  );
}

function GroupedArticleList({
  articles,
  t,
  lang,
}: {
  articles: EventDetailResponse["articles"];
  t: ReturnType<typeof copyFor>;
  lang: string;
}) {
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
      {sortedGroups.length === 0 ? <div className={styles.emptyCard}>{t.empty}</div> : null}

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
  const requestHeaders = await headers();
  const requestOrigin = getRequestOriginFromHeaders(requestHeaders);
  if (!SUPPORTED_LANGS.has(lang)) {
    notFound();
  }
  if (!id) {
    throw new Error("Route param id is missing");
  }

  const t = copyFor(lang);
  const [data, translated] = await Promise.all([
    fetchEventDetail(id, requestOrigin),
    lang === "zh" ? fetchEventTitleZh(id, requestOrigin) : Promise.resolve(null),
  ]);

  const headerEvent = {
    ...data.event,
    title: translated?.title || data.event.title,
  };

  return (
    <main className={styles.page}>
      <Link href={`/${lang}`} className={styles.backLink}>
        {t.back}
      </Link>

      <EventHeader event={headerEvent} articles={data.articles} t={t} />
      <GroupedArticleList articles={data.articles} t={t} lang={lang} />
    </main>
  );
}
