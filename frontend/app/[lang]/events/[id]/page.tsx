import Link from "next/link";
import { notFound } from "next/navigation";
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

function fmtTime(s: string | null | undefined) {
  if (!s) return "";
  return s.replace("T", " ").replace("Z", "");
}

function copyFor(lang: string) {
  if (lang === "zh") {
    return {
      back: "返回",
      eventPrefix: "事件 #",
      articles: "文章",
      sources: "来源",
      empty: "该事件暂无文章。",
    };
  }

  return {
    back: "Back",
    eventPrefix: "Event #",
    articles: "Articles",
    sources: "Sources",
    empty: "No articles for this event yet.",
  };
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

async function fetchEventTitleZh(id: string): Promise<EventTitleZhResponse | null> {
  const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  try {
    const res = await fetch(`${API_BASE}/api/events/${id}/title-zh`, {
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
  t,
}: {
  event: EventDetailResponse["event"];
  t: ReturnType<typeof copyFor>;
}) {
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
    <section className={styles.header}>
      <h1 className={styles.title}>{event.title}</h1>

      {timeLine ? (
        <div className={styles.timeLine}>{timeLine}</div>
      ) : null}

      <div className={styles.metaChips}>
        <span className={styles.chip}>
          {t.eventPrefix}
          {event.event_id}
        </span>
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

  const sortedGroups = Object.entries(groupedBySource).sort((a, b) => {
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
  if (!SUPPORTED_LANGS.has(lang)) {
    notFound();
  }
  if (!id) {
    throw new Error("Route param id is missing");
  }

  const t = copyFor(lang);
  const [data, translated] = await Promise.all([
    fetchEventDetail(id),
    lang === "zh" ? fetchEventTitleZh(id) : Promise.resolve(null),
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

      <EventHeader event={headerEvent} t={t} />
      <GroupedArticleList articles={data.articles} t={t} lang={lang} />
    </main>
  );
}
