import type { Question } from "./types";

export type ReviewItem = {
  id: string;
  count: number;
  mastered: boolean;
  updated: number;
  question: Question;
  due_at: number | null;
  review_stage: number;
  last_reviewed: number | null;
};

export type KnowledgePoint = {
  tag: string;
  count: number;
  correct: number;
  accuracy: number;
  previous_accuracy: number | null;
  trend: { week: string; accuracy: number; count: number }[];
};

export type ReviewSummary = {
  due_count: number;
  pending_count: number;
  scheduled_count: number;
  mastered_count: number;
  recommendations: {
    topic: number;
    attempts: number;
    accuracy: number;
    ready_count: number;
  }[];
  knowledge: KnowledgePoint[];
};

export type ReviewFilters = {
  state: "pending" | "due" | "mastered" | "all";
  days: "all" | "7" | "30";
  topic: string;
  tag: string;
  minimum: number;
  search: string;
  sort: "recent" | "count" | "due";
};
