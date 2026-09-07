import type { ReviewFilters, ReviewItem } from "./review-types";

export const defaultReviewFilters: ReviewFilters = {
  state: "pending",
  days: "all",
  topic: "all",
  tag: "all",
  minimum: 1,
  search: "",
  sort: "recent",
};

export function isDue(item: ReviewItem, now: number): boolean {
  return !item.mastered && (item.due_at === null || item.due_at <= now);
}

export function filterReviews(
  rows: ReviewItem[],
  filters: ReviewFilters,
  now: number,
): ReviewItem[] {
  const search = filters.search.trim().toLocaleLowerCase();
  const since = filters.days === "all" ? 0 : now - Number(filters.days) * 86400;
  return rows
    .filter((item) => {
      if (filters.state === "pending" && item.mastered) return false;
      if (filters.state === "mastered" && !item.mastered) return false;
      if (filters.state === "due" && !isDue(item, now)) return false;
      if (filters.days !== "all" && item.updated < since) return false;
      if (
        filters.topic !== "all" &&
        String(item.question.topic) !== filters.topic
      )
        return false;
      if (filters.tag !== "all" && !item.question.tags.includes(filters.tag))
        return false;
      if (item.count < filters.minimum) return false;
      return (
        !search ||
        [
          item.id,
          "Topic",
          item.question.topic,
          "第",
          item.question.number,
          "题",
          item.question.zh,
          item.question.en,
          ...item.question.tags,
        ]
          .join(" ")
          .toLocaleLowerCase()
          .includes(search)
      );
    })
    .sort((a, b) => {
      if (filters.sort === "count" && a.count !== b.count)
        return b.count - a.count;
      if (filters.sort === "due") {
        const aDue = a.mastered ? Infinity : (a.due_at ?? 0);
        const bDue = b.mastered ? Infinity : (b.due_at ?? 0);
        if (aDue !== bDue) return aDue < bDue ? -1 : 1;
      }
      return b.updated - a.updated || a.id.localeCompare(b.id);
    });
}

export function reviewSelection(rows: ReviewItem[], limit: number): string[] {
  return [
    ...new Set(
      rows
        .filter((row) => row.question.status === "ready")
        .map((row) => row.id),
    ),
  ].slice(0, Math.max(0, Math.min(50, Math.floor(limit))));
}
