// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import QuestionTools from "./QuestionTools";
import type { Personal } from "./personal-types";
const mock = vi.hoisted(() => ({ api: vi.fn(), send: vi.fn() }));
vi.mock("./api", () => mock);
const saved: Personal = {
  question_id: "t1-q2",
  favorite: false,
  note: "",
  updated: 100,
  version: 1,
};
beforeEach(() => {
  localStorage.clear();
  mock.api.mockReset();
  mock.send.mockReset();
  mock.api.mockResolvedValue(saved);
});
afterEach(cleanup);
async function editNote(value: string) {
  await screen.findByRole("button", { name: "记笔记" });
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "记笔记" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false),
  );
  fireEvent.click(screen.getByRole("button", { name: "记笔记" }));
  fireEvent.change(screen.getByLabelText("我的学习笔记"), {
    target: { value },
  });
}
describe("personal learning tools", () => {
  it("locks note editing while a save is pending so a delayed response cannot erase new input", async () => {
    let resolveSave!: (value: Personal) => void;
    mock.send.mockReturnValueOnce(
      new Promise<Personal>((resolve) => {
        resolveSave = resolve;
      }),
    );
    render(<QuestionTools questionId="t1-q2" owner="learner" />);
    await editNote("提交中的笔记");
    fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));
    expect(
      (screen.getByLabelText("我的学习笔记") as HTMLTextAreaElement).disabled,
    ).toBe(true);
    resolveSave({ ...saved, note: "提交中的笔记", version: 2 });
    await screen.findByText("笔记已保存到账号。");
    expect(
      (screen.getByLabelText("我的学习笔记") as HTMLTextAreaElement).disabled,
    ).toBe(false);
  });
  it("keeps unsaved note text when a version conflict occurs and requires an explicit retry", async () => {
    mock.send.mockRejectedValueOnce(new Error("笔记已在其他页面更新"));
    render(<QuestionTools questionId="t1-q2" owner="learner" />);
    await editNote("我对 KQL 的理解");
    fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(
      (screen.getByLabelText("我的学习笔记") as HTMLTextAreaElement).value,
    ).toBe("我对 KQL 的理解");
    mock.api.mockResolvedValueOnce({
      ...saved,
      version: 2,
      note: "另一页面的笔记",
    });
    fireEvent.click(
      screen.getByRole("button", { name: "读取最新版本，保留草稿" }),
    );
    await screen.findByText(/再次保存将用此草稿替换/);
    expect(mock.send).toHaveBeenCalledTimes(1);
    mock.send.mockResolvedValueOnce({
      ...saved,
      version: 3,
      note: "我对 KQL 的理解",
    });
    fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));
    await screen.findByText("笔记已保存到账号。");
    expect(mock.send).toHaveBeenLastCalledWith(
      "/questions/t1-q2/personal",
      { note: "我对 KQL 的理解", version: 2 },
      "PATCH",
    );
    expect(localStorage.getItem("sc200.note.v1.learner.t1-q2")).toBeNull();
  });
  it("updates the note base version after favoriting without losing an unsaved draft", async () => {
    mock.send.mockResolvedValueOnce({ ...saved, favorite: true, version: 2 });
    render(<QuestionTools questionId="t1-q2" owner="learner" />);
    await editNote("尚未保存的草稿");
    fireEvent.click(screen.getByRole("button", { name: "收藏题目" }));
    await screen.findByText("已加入收藏。");
    expect(
      (screen.getByLabelText("我的学习笔记") as HTMLTextAreaElement).value,
    ).toBe("尚未保存的草稿");
    mock.send.mockResolvedValueOnce({
      ...saved,
      favorite: true,
      note: "尚未保存的草稿",
      version: 3,
    });
    fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));
    await screen.findByText("笔记已保存到账号。");
    expect(mock.send).toHaveBeenLastCalledWith(
      "/questions/t1-q2/personal",
      { note: "尚未保存的草稿", version: 2 },
      "PATCH",
    );
  });
  it("restores a draft only for its own account and question", async () => {
    localStorage.setItem(
      "sc200.note.v1.alice.t1-q2",
      JSON.stringify({ note: "Alice的私有草稿", version: 1 }),
    );
    const view = render(<QuestionTools questionId="t1-q2" owner="bob" />);
    await editNote("Bob的草稿");
    expect(localStorage.getItem("sc200.note.v1.alice.t1-q2")).toContain(
      "Alice",
    );
    view.unmount();
    render(<QuestionTools questionId="t1-q2" owner="alice" />);
    await screen.findByText(/已恢复这台设备/);
    expect(
      (screen.getByLabelText("我的学习笔记") as HTMLTextAreaElement).value,
    ).toBe("Alice的私有草稿");
  });
  it("does not show feedback as saved when the server rejects it", async () => {
    mock.send.mockRejectedValueOnce(new Error("服务暂时不可用"));
    render(<QuestionTools questionId="t1-q2" owner="learner" />);
    fireEvent.click(screen.getByRole("button", { name: "反馈题目问题" }));
    fireEvent.change(screen.getByLabelText("问题说明"), {
      target: { value: "这里的术语翻译有误" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存反馈" }));
    await screen.findByRole("alert");
    expect(
      (screen.getByLabelText("问题说明") as HTMLTextAreaElement).value,
    ).toBe("这里的术语翻译有误");
    expect(screen.queryByText(/纠错反馈已保存/)).toBeNull();
  });
});
