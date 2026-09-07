// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { api, send } from "./api";
import ReviewHub from "./ReviewHub";
import type { Question, Session } from "./types";
import type { ReviewItem, ReviewSummary } from "./review-types";

vi.mock("./api", () => ({ api: vi.fn(), send: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const row = (id: string, topic: number, count: number): ReviewItem => ({
  id,
  count,
  updated: Date.now() / 1000,
  mastered: false,
  due_at: null,
  review_stage: 0,
  last_reviewed: null,
  question: {
    id,
    topic,
    number: count,
    type: "single",
    status: "ready",
    zh: "调查 " + id,
    en: "Investigate " + id,
    tags: ["Sentinel"],
    options: [],
    slots: [],
    assets: [],
    pages: [1],
    case_en: "",
    case_zh: "",
    domain: "",
    translation_status: "reviewed",
  } as Question,
});

it("用户筛选章节并按错误次数排序后，仅启动当前筛选中的题目", async () => {
  const rows = [
    row("other-topic", 2, 9),
    row("lower-count", 1, 1),
    row("higher-count", 1, 3),
  ];
  const summary: ReviewSummary = {
    due_count: 3,
    pending_count: 3,
    scheduled_count: 0,
    mastered_count: 0,
    recommendations: [],
    knowledge: [],
  };
  vi.mocked(api).mockImplementation(
    (path) =>
      Promise.resolve(path === "/mistakes" ? rows : summary) as ReturnType<
        typeof api
      >,
  );
  vi.mocked(send).mockResolvedValue({ id: "new-session" } as Session);
  render(
    <MemoryRouter>
      <ReviewHub />
    </MemoryRouter>,
  );
  await screen.findByText("调查 other-topic");
  fireEvent.change(screen.getByLabelText("章节"), { target: { value: "1" } });
  fireEvent.change(screen.getByLabelText("排序"), {
    target: { value: "count" },
  });
  expect(screen.queryByText("调查 other-topic")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "重练 2 题" }));
  await waitFor(() =>
    expect(send).toHaveBeenCalledWith("/sessions", {
      mode: "wrong",
      count: 2,
      feedback: true,
      question_ids: ["higher-count", "lower-count"],
    }),
  );
});
