import { describe, expect, it } from "vitest";
import type { Question } from "./types";
import type { ReviewItem } from "./review-types";
import {
  defaultReviewFilters,
  filterReviews,
  isDue,
  reviewSelection,
} from "./review-utils";

const now = 2_000_000;
const make = (id: string, changes: Partial<ReviewItem> = {}): ReviewItem => ({
  id,
  count: 1,
  mastered: false,
  updated: now,
  due_at: now,
  review_stage: 0,
  last_reviewed: null,
  question: {
    id,
    status: "ready",
    topic: 1,
    number: 2,
    zh: "事件调查",
    en: "Investigate alerts",
    tags: ["Sentinel"],
  } as Question,
  ...changes,
});

describe("复习筛选", () => {
  it("到期包含首次复习和恰好到时的题目，不包含未来和已掌握题", () => {
    expect(isDue(make("new", { due_at: null }), now)).toBe(true);
    const rows = [
      make("due"),
      make("future", { due_at: now + 1 }),
      make("mastered", { mastered: true }),
    ];
    expect(
      filterReviews(rows, { ...defaultReviewFilters, state: "due" }, now).map(
        (x) => x.id,
      ),
    ).toEqual(["due"]);
  });

  it("交叉应用最近错误、章节、标签、次数和搜索，不混入其他题", () => {
    const target = make("t1-q2", { count: 3 });
    const rows = [
      target,
      make("old", { updated: now - 86400 * 8, count: 3 }),
      make("infrequent"),
      make("other", { count: 4, question: { ...target.question, topic: 2 } }),
    ];
    expect(
      filterReviews(
        rows,
        {
          ...defaultReviewFilters,
          days: "7",
          topic: "1",
          tag: "Sentinel",
          minimum: 3,
          search: "ALERTS",
        },
        now,
      ).map((x) => x.id),
    ).toEqual(["t1-q2"]);
    expect(
      filterReviews(
        rows,
        { ...defaultReviewFilters, search: "  事件调查  " },
        now,
      ),
    ).toHaveLength(4);
    expect(
      filterReviews(
        rows,
        { ...defaultReviewFilters, search: "t1-q2" },
        now,
      ).map((x) => x.id),
    ).toEqual(["t1-q2"]);
  });

  it("按错误次数与到期时间排序且保持源数组不变", () => {
    const rows = [
      make("later", { due_at: now + 10 }),
      make("earlier", { count: 3, updated: now - 1, due_at: now - 10 }),
      make("new", { due_at: null }),
    ];
    expect(
      filterReviews(rows, { ...defaultReviewFilters, sort: "count" }, now)[0]
        .id,
    ).toBe("earlier");
    expect(
      filterReviews(rows, { ...defaultReviewFilters, sort: "due" }, now).map(
        (x) => x.id,
      ),
    ).toEqual(["new", "earlier", "later"]);
    expect(rows.map((x) => x.id)).toEqual(["later", "earlier", "new"]);
  });

  it("全部模式下将已掌握的题放在复习时间排序末尾", () => {
    const rows = [
      make("mastered", { mastered: true, due_at: null }),
      make("scheduled", { due_at: now + 100 }),
    ];
    expect(
      filterReviews(
        rows,
        { ...defaultReviewFilters, state: "all", sort: "due" },
        now,
      ).map((x) => x.id),
    ).toEqual(["scheduled", "mastered"]);
  });

  it("重练使用当前筛选排序后的可用ID，支持已掌握，排除待核对并去重", () => {
    const hidden = make("hidden", {
      question: { ...make("a").question, topic: 2 },
    });
    const rows = [
      hidden,
      make("mastered", { mastered: true, count: 5 }),
      make("review", {
        question: { ...make("a").question, status: "review" },
        count: 10,
      }),
      make("wanted", { count: 4 }),
      make("wanted", { count: 4 }),
      make("third"),
    ];
    const filtered = filterReviews(
      rows,
      { ...defaultReviewFilters, state: "all", topic: "1", sort: "count" },
      now,
    );
    expect(reviewSelection(filtered, 2)).toEqual(["mastered", "wanted"]);
    expect(reviewSelection(filtered, 20)).toEqual([
      "mastered",
      "wanted",
      "third",
    ]);
    expect(reviewSelection([], 20)).toEqual([]);
  });
});
