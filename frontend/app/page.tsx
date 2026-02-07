// frontend/app/page.tsx
import styles from "./page.module.css";
import { fetchTopEvents } from "./lib/topEvents";
import { assignEventBackgrounds } from "./lib/eventBg";

export default async function HomePage() {
  const data = await fetchTopEvents(5);
  const bgMap = assignEventBackgrounds(data.items);

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <header className={styles.header}>
          <div className={styles.kicker}>NewsToday</div>
          <h1>What's going on?</h1>
          <p className={styles.subtitle}>
            A compact view of the most active events right now.
          </p>
        </header>

        <section className={styles.railSection}>
          <div className={styles.railMeta}>
            <div className={styles.railTitle}>Top events</div>
            <div className={styles.railAsOf}>Updated recently</div>
          </div>

          <div className={styles.rail} role="list">
            {data.items.map((ev) => (
              <a
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
                      {ev.articles_count} articles · {ev.sources_count} sources
                    </div>
                  </div>
                </div>
              </a>
            ))}
            <div className={`${styles.card} ${styles.placeholderCard}`} role="listitem">
              <div className={styles.placeholderBg} aria-hidden="true" />
              <div className={styles.placeholderText}>
                Start with these.
                <br />
                Then look deeper.
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
