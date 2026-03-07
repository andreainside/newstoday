import Link from "next/link";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import styles from "../page.module.css";
import { assignEventBackgrounds } from "../lib/eventBg";
import { fetchTopEvents } from "../lib/topEvents";
import { getRequestOriginFromHeaders, makeApiUrl } from "../lib/apiBase";

const SUPPORTED_LANGS = new Set(["en", "zh"]);

function copyFor(lang: string) {
  if (lang === "zh") {
    return {
      kicker: "NewsToday",
      title: "正在发生什么？",
      subtitle: "时下最热议事件的综合视图。",
      railTitle: "热点事件",
      railAsOf: "刚刚更新",
      cardMetaSeparator: " · ",
      placeholderLine1: "循此而下，",
      placeholderLine2: "上下求索。",
    };
  }

  return {
    kicker: "NewsToday",
    title: "What's going on?",
    subtitle: "A compact view of the most active events right now.",
    railTitle: "Top events",
    railAsOf: "Updated recently",
    cardMetaSeparator: " · ",
    placeholderLine1: "Start with these.",
    placeholderLine2: "Then look deeper.",
  };
}

type EventTitleZhResponse = {
  title: string | null;
  status: string;
};

async function fetchEventTitleZh(eventId: number, origin?: string): Promise<string | null> {
  // First-time translations can take a few seconds when cache is cold.
  // Keep the request bounded, but avoid falling back to English too early.
  const timeoutMs = 6000;

  try {
    const res = await fetch(makeApiUrl(`/api/events/${eventId}/title-zh`, origin), {
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as EventTitleZhResponse;
    return data.title || null;
  } catch (error) {
    if (error instanceof Error && error.name === "TimeoutError") {
      console.warn(`Fetching zh title for event ${eventId} timed out after ${timeoutMs}ms`);
      return null;
    }
    return null;
  }
}

export default async function LocalizedHomePage({
  params,
}: {
  params: Promise<{ lang: string }>;
}) {
  const { lang } = await params;
  if (!SUPPORTED_LANGS.has(lang)) {
    notFound();
  }

  const t = copyFor(lang);
  const requestHeaders = await headers();
  const requestOrigin = getRequestOriginFromHeaders(requestHeaders);
  const data = await fetchTopEvents(5, requestOrigin);
  const localizedItems = lang === "zh"
    ? await Promise.all(
      data.items.map(async (ev) => {
        const zhTitle = await fetchEventTitleZh(ev.event_id, requestOrigin);
        return {
          ...ev,
          title: zhTitle || ev.title,
        };
      }),
    )
    : data.items;
  const bgMap = assignEventBackgrounds(data.items);

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <header className={styles.header}>
          <div className={styles.headerTopRow}>
            <div className={styles.kicker}>{t.kicker}</div>
            <nav className={styles.langSwitch} aria-label="Language switcher">
              <Link
                href="/en"
                className={`${styles.langPill} ${lang === "en" ? styles.langPillActive : ""}`}
              >
                EN
              </Link>
              <Link
                href="/zh"
                className={`${styles.langPill} ${lang === "zh" ? styles.langPillActive : ""}`}
              >
                中文
              </Link>
            </nav>
          </div>
          <h1>{t.title}</h1>
          <p className={styles.subtitle}>{t.subtitle}</p>
        </header>

        <section className={styles.railSection}>
          <div className={styles.railMeta}>
            <div className={styles.railTitle}>{t.railTitle}</div>
            <div className={styles.railAsOf}>{t.railAsOf}</div>
          </div>

          <div className={styles.rail} role="list">
            {localizedItems.map((ev) => (
              <Link
                key={ev.event_id}
                href={`/events/${ev.event_id}`}
                className={styles.card}
                style={{
                  backgroundImage: `url(${bgMap[ev.event_id]})`,
                }}
                role="listitem"
              >
                <div
                  className={styles.imageLayer}
                  style={{ backgroundImage: `url(${bgMap[ev.event_id]})` }}
                  aria-hidden="true"
                />
                <div className={styles.blendLayer} aria-hidden="true" />
                <div className={styles.solidLayer}>
                  <div className={styles.cardBody}>
                    <div className={styles.cardTitle}>{ev.title}</div>
                    <div className={styles.cardMeta}>
                      {ev.articles_count} articles
                      {t.cardMetaSeparator}
                      {ev.sources_count} sources
                    </div>
                  </div>
                </div>
              </Link>
            ))}
            <div className={`${styles.card} ${styles.placeholderCard}`} role="listitem">
              <div className={styles.placeholderBg} aria-hidden="true" />
              <div className={styles.placeholderText}>
                {t.placeholderLine1}
                <br />
                {t.placeholderLine2}
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
