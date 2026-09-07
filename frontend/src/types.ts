export type User = { username: string; timezone: string; csrf: string };
export type Option = { id: string; en: string; zh: string };
export type Slot = { id: string; en: string; zh: string; options: Option[] };
export type Question = {
  id: string;
  topic: number;
  number: number;
  pages: number[];
  type: "single" | "multiple" | "matching" | "hotspot" | "ordering";
  en: string;
  zh: string;
  options: Option[];
  slots: Slot[];
  assets: string[];
  answer_assets?: string[];
  case_assets?: string[];
  case_en: string;
  case_zh: string;
  tags: string[];
  domain: string;
  status: string;
  translation_status: string;
  answer?: string[];
  explanation_en?: string;
  explanation_zh?: string;
  reference?: string[];
  issues?: string[];
};
export type Session = {
  id: string;
  mode: string;
  started: number;
  deadline: number | null;
  server_time: number;
  finished: number | null;
  version: number;
  feedback: boolean;
  answers: Record<string, string[]>;
  flags: string[];
  questions: Question[];
  results: Record<
    string,
    { correct: boolean; earned: number; possible: number }
  >;
  score: number | null;
  seconds: number;
};
export type History = {
  id: string;
  mode: string;
  started: number;
  finished: number | null;
  count: number;
  score: number | null;
  seconds: number;
};
export type Stats = {
  total: number;
  correct: number;
  accuracy: number;
  exam_average: number;
  exam_count: number;
  trend: { id: string; date: string; score: number }[];
  daily: Record<string, { count: number; correct: number; seconds: number }>;
  topics: Record<string, { count: number; correct: number }>;
  seconds: number;
  wrong: number;
};
export type Bank = {
  version: string;
  total: number;
  ready: number;
  review: number;
  translated: number;
  topics: { id: number; total: number; ready: number }[];
  tags: string[];
  domains: Record<string, number>;
  domain_note: string;
};
