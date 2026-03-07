import { makeApiUrl } from "../../lib/apiBase";
import type { SourceArticle } from "./components/SourceNewspaperCard";

export type EventDetailResponse = {
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

export type EventTitleZhResponse = {
  title: string | null;
  status: string;
};

export function copyFor(lang: string) {
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

export function parseTime(s: string | null | undefined): Date | null {
  if (!s) return null;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function fmtTimeToMinute(s: string | null | undefined) {
  const d = parseTime(s);
  if (!d) return "";
  return d.toISOString().slice(0, 16).replace("T", " ");
}

export function resolveCoverageRange(
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

export function groupArticlesBySource(articles: EventDetailResponse["articles"]) {
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

  return {
    sortedGroups,
    featuredSourceName: sortedGroups.length > 0 ? sortedGroups[0][0] : null,
  };
}

export async function fetchEventTitleZh(eventId: number, origin?: string): Promise<string | null> {
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

export async function fetchEventDetail(id: string, origin?: string): Promise<EventDetailResponse> {
  const res = await fetch(makeApiUrl(`/api/events/${id}`, origin), {
    cache: "no-store",
  });

  if (!res.ok) {
    return {
      event: {
        event_id: Number(id),
        title: "Event temporarily unavailable",
        start_time: null,
        end_time: null,
        last_seen_at: new Date().toISOString(),
        articles_count: 0,
        sources_count: 0,
      },
      articles: [],
    };
  }
  return res.json();
}
