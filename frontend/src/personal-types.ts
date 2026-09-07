import type { Question } from "./types";

export type Personal = {
  question_id: string;
  favorite: boolean;
  note: string;
  updated: number | null;
  version: number;
};
export type LibraryItem = Personal & { question: Question };
export type ReportCategory = "translation" | "answer" | "image" | "other";
export type QuestionReport = {
  id: string;
  question_id: string;
  category: ReportCategory;
  content: string;
  status: "open" | "withdrawn";
  created: number;
};
export const reportLabels: Record<ReportCategory, string> = {
  translation: "中文翻译",
  answer: "参考答案",
  image: "题目附图",
  other: "其他问题",
};
