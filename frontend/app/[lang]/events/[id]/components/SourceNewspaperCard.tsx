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
  const [isHovered, setIsHovered] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const [isMobileExpanded, setIsMobileExpanded] = useState(false);

  const isTouchDevice = typeof window !== "undefined"
    && window.matchMedia("(hover: none), (pointer: coarse)").matches;

  const fmtTime = (s: string | null | undefined) => {
    if (!s) return "";
    return s.replace("T", " ").replace("Z", "");
  };

  const isExpanded = isTouchDevice ? isMobileExpanded : isHovered || isFocused;
  const visibleCount = isExpanded ? articles.length : COLLAPSED_LIST_COUNT;
  const visibleItems = articles.slice(0, visibleCount);

  return (
    <article
      className={`${styles.sourceCard} ${isFeatured ? styles.featuredCard : ""} ${
        isMobileExpanded ? styles.expanded : ""
      }`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onFocusCapture={() => setIsFocused(true)}
      onBlurCapture={(event) => {
        const nextTarget = event.relatedTarget as Node | null;
        if (!event.currentTarget.contains(nextTarget)) {
          setIsFocused(false);
        }
      }}
    >
      <div className={styles.sourceHeader}>
        <h2 className={styles.sourceName}>{sourceName}</h2>
        <span className={styles.articleCountBadge}>{articles.length} articles</span>
      </div>

      <div className={styles.listViewport}>
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
          onClick={() => setIsMobileExpanded((prev) => !prev)}
        >
          {isMobileExpanded ? "Show less" : "Show more"}
        </button>
      ) : null}
    </article>
  );
}
