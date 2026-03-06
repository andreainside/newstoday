"use client";

import { useState } from "react";
import styles from "./sourceNewspaperCard.module.css";

const COLLAPSED_LIST_COUNT = 4;

export type SourceArticle = {
  article_id: number;
  published_at: string | null;
  title: string;
  link: string;
  description?: string | null;
  summary?: string | null;
  type: string | null;
  type_reason: string | null;
  source: {
    source_id: number;
    name: string;
    url: string;
  };
};

type Props = {
  sourceName: string;
  articles: SourceArticle[];
  isFeatured?: boolean;
};

export default function SourceNewspaperCard({
  sourceName,
  articles,
  isFeatured = false,
}: Props) {
  const [isExpanded, setIsExpanded] = useState(false);

  const fmtTime = (s: string | null | undefined) => {
    if (!s) return "";
    const d = new Date(s);
    if (Number.isNaN(d.getTime())) return "";
    return d.toISOString().slice(0, 16).replace("T", " ");
  };

  const visibleCount = isExpanded ? articles.length : COLLAPSED_LIST_COUNT;
  const visibleItems = articles.slice(0, visibleCount);

  return (
    <article
      className={`${styles.sourceCard} ${isFeatured ? styles.featuredCard : ""} ${
        isExpanded ? styles.expanded : ""
      }`}
    >
      <div className={styles.sourceHeader}>
        <h2 className={styles.sourceName}>{sourceName}</h2>
        <span className={styles.articleCountBadge}>{articles.length} articles</span>
      </div>

      <div
        className={`${styles.listViewport} ${isExpanded ? styles.listViewportExpanded : ""}`}
      >
        <div className={styles.articleList}>
          {visibleItems.map((a) => (
            <article key={a.article_id} className={styles.articleItem}>
              <a href={a.link} target="_blank" rel="noreferrer" className={styles.articleLink}>
                {a.title}
              </a>
              <div className={styles.articleTime}>{fmtTime(a.published_at)}</div>
            </article>
          ))}
        </div>
      </div>

      {articles.length > COLLAPSED_LIST_COUNT ? (
        <button
          type="button"
          className={styles.mobileToggle}
          onClick={() => setIsExpanded((prev) => !prev)}
        >
          {isExpanded ? "Show less" : "Show more"}
        </button>
      ) : null}
    </article>
  );
}
