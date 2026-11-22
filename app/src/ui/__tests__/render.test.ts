// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";
import type { Row } from "../../state";
import {
  renderApp,
  type RenderHandlers,
  type RenderState,
} from "../render";

function makeRow(overrides: Partial<Row> = {}): Row {
  return {
    original: "original.pdf",
    status: "ready",
    proposed: "proposed.pdf",
    manualName: "",
    finalName: "proposed.pdf",
    collision: false,
    ...overrides,
  };
}

function makeState(overrides: Partial<RenderState> = {}): RenderState {
  return {
    inputFolderName: "in",
    outputFolderName: "out",
    inputPermissionNeeded: false,
    outputPermissionNeeded: false,
    rows: [],
    scanned: false,
    progress: null,
    moveProcessed: false,
    summary: null,
    notice: null,
    busy: false,
    ...overrides,
  };
}

function makeHandlers(): RenderHandlers {
  return {
    onPickInput: vi.fn(),
    onPickOutput: vi.fn(),
    onScan: vi.fn(),
    onRename: vi.fn(),
    onToggleRow: vi.fn(),
    onManualName: vi.fn(),
    onMoveProcessed: vi.fn(),
  };
}

function stubDirectoryPicker(supported: boolean): void {
  if (supported) {
    Object.defineProperty(window, "showDirectoryPicker", {
      configurable: true,
      value: vi.fn(),
    });
  } else {
    Reflect.deleteProperty(window, "showDirectoryPicker");
  }
}

afterEach(() => {
  Reflect.deleteProperty(window, "showDirectoryPicker");
});

describe("renderApp", () => {
  it("renders a ready row with its glyph, original name, and proposed name as text", () => {
    stubDirectoryPicker(true);
    const row = makeRow({
      original: "receipt.pdf",
      proposed: "transfBBVA_to_Banamex_x128.00_May2026.pdf",
      finalName: null,
    });

    const app = renderApp(makeState({ rows: [row] }), makeHandlers());
    const renderedRow = app.querySelector("tbody tr");

    expect(renderedRow?.textContent).toContain("✓");
    expect(renderedRow?.textContent).toContain("receipt.pdf");
    expect(renderedRow?.textContent).toContain(
      "transfBBVA_to_Banamex_x128.00_May2026.pdf"
    );
    expect(renderedRow?.querySelector('input[type="text"]')).toBeNull();
  });

  it("renders an incomplete row with a warning glyph and an editable name input", () => {
    stubDirectoryPicker(true);
    const row = makeRow({
      status: "incomplete",
      proposed: null,
      finalName: null,
      manualName: "typed-name.pdf",
    });

    const app = renderApp(makeState({ rows: [row] }), makeHandlers());
    const renderedRow = app.querySelector("tbody tr");
    const input = renderedRow?.querySelector<HTMLInputElement>(
      'input[type="text"]'
    );

    expect(renderedRow?.textContent).toContain("⚠");
    expect(input?.value).toBe("typed-name.pdf");
    expect(input?.disabled).toBe(false);
  });

  it("disables Rename and labels it zero when no included row has a final or pending manual name", () => {
    stubDirectoryPicker(true);
    const rows = [
      makeRow({
        status: "excluded",
        finalName: "stale.pdf",
        manualName: "pending.pdf",
      }),
      makeRow({
        original: "blank.pdf",
        status: "incomplete",
        proposed: null,
        finalName: null,
        manualName: "   ",
      }),
    ];

    const app = renderApp(makeState({ rows }), makeHandlers());
    const rename = Array.from(app.querySelectorAll("button")).find((button) =>
      button.textContent?.startsWith("Rename")
    ) as HTMLButtonElement | undefined;

    expect(rename?.textContent).toBe("Rename 0 files");
    expect(rename?.disabled).toBe(true);
  });

  it("enables Rename for an incomplete row with a pending manual name", () => {
    stubDirectoryPicker(true);
    const row = makeRow({
      status: "incomplete",
      proposed: null,
      finalName: null,
      manualName: "typed-name.pdf",
    });

    const app = renderApp(makeState({ rows: [row] }), makeHandlers());
    const rename = Array.from(app.querySelectorAll("button")).find(
      (button) => button.textContent === "Rename 1 files"
    ) as HTMLButtonElement | undefined;

    expect(rename).toBeDefined();
    expect(rename?.disabled).toBe(false);
  });

  it("shows the graceful browser banner when showDirectoryPicker is absent", () => {
    stubDirectoryPicker(false);

    const app = renderApp(makeState(), makeHandlers());

    expect(app.textContent).toContain(
      "Folder picking requires Chrome or Edge"
    );
  });

  it("does not show the browser banner when directory picking is supported", () => {
    stubDirectoryPicker(true);

    const app = renderApp(makeState(), makeHandlers());

    expect(app.textContent).not.toContain(
      "Folder picking requires Chrome or Edge"
    );
  });

  it("shows the bumped final name and a collision marker for a collision row", () => {
    stubDirectoryPicker(true);
    const row = makeRow({
      proposed: "receipt.pdf",
      finalName: "receipt_2.pdf",
      collision: true,
    });

    const app = renderApp(makeState({ rows: [row] }), makeHandlers());
    const renderedRow = app.querySelector("tbody tr");

    expect(renderedRow?.textContent).toContain("receipt_2.pdf");
    expect(renderedRow?.textContent).toMatch(/collision/i);
    expect(renderedRow?.textContent).toMatch(/bumped/i);
  });

  it("enables Rename with the planned-file count when rows are writable", () => {
    stubDirectoryPicker(true);
    const rows = [
      makeRow(),
      makeRow({ original: "second.pdf", finalName: "second-new.pdf" }),
    ];

    const app = renderApp(makeState({ rows }), makeHandlers());
    const rename = Array.from(app.querySelectorAll("button")).find(
      (button) => button.textContent === "Rename 2 files"
    ) as HTMLButtonElement | undefined;

    expect(rename).toBeDefined();
    expect(rename?.disabled).toBe(false);
  });

  it("renders parsing progress, the empty scan state, and a post-run summary", () => {
    stubDirectoryPicker(true);
    const parsing = renderApp(
      makeState({ progress: { done: 2, total: 5 } }),
      makeHandlers()
    );
    const progress = parsing.querySelector<HTMLProgressElement>("progress");
    expect(progress?.value).toBe(2);
    expect(progress?.max).toBe(5);

    const empty = renderApp(
      makeState({ rows: [], scanned: true }),
      makeHandlers()
    );
    expect(empty.textContent).toContain("No PDFs found in input folder");

    const completed = renderApp(
      makeState({ summary: "2 renamed, 1 skipped, 0 failed" }),
      makeHandlers()
    );
    expect(completed.textContent).toContain("2 renamed, 1 skipped, 0 failed");
  });

  it("hides the choose-folders instruction while scanning is busy or progressing", () => {
    stubDirectoryPicker(true);

    const parsing = renderApp(
      makeState({ progress: { done: 0, total: 3 } }),
      makeHandlers()
    );
    expect(parsing.textContent).toContain("Parsing 0 of 3 PDFs");
    expect(parsing.textContent).not.toContain(
      "Choose input and output folders"
    );

    const busy = renderApp(makeState({ busy: true }), makeHandlers());
    expect(busy.textContent).not.toContain("Choose input and output folders");

    const idle = renderApp(makeState(), makeHandlers());
    expect(idle.textContent).toContain("Choose input and output folders");
  });

  it("marks the empty arrow column header aria-hidden", () => {
    stubDirectoryPicker(true);

    const app = renderApp(makeState({ rows: [makeRow()] }), makeHandlers());
    const headers = Array.from(app.querySelectorAll("thead th"));
    const arrow = headers.find((header) => header.textContent === "");

    expect(arrow).toBeDefined();
    expect(arrow?.getAttribute("aria-hidden")).toBe("true");
  });

  it("does not claim the folder is empty when scanning failed", () => {
    stubDirectoryPicker(true);

    const app = renderApp(
      makeState({ scanned: true, notice: "Permission denied" }),
      makeHandlers()
    );

    expect(app.textContent).toContain("Permission denied");
    expect(app.textContent).not.toContain("No PDFs found in input folder");
  });

  it("wires row edits, inclusion toggles, and the move-processed checkbox", () => {
    stubDirectoryPicker(true);
    const handlers = makeHandlers();
    const rows = [
      makeRow({
        status: "incomplete",
        proposed: null,
        finalName: null,
      }),
    ];
    const app = renderApp(
      makeState({ rows, moveProcessed: true }),
      handlers
    );

    const nameInput = app.querySelector<HTMLInputElement>(
      'input[type="text"]'
    );
    if (!nameInput) {
      throw new Error("manual-name input was not rendered");
    }
    nameInput.value = "manual.pdf";
    nameInput.dispatchEvent(new Event("change", { bubbles: true }));
    expect(handlers.onManualName).toHaveBeenCalledWith(
      "original.pdf",
      "manual.pdf"
    );

    const include = app.querySelector<HTMLInputElement>(
      'input[aria-label="Include original.pdf"]'
    );
    include?.dispatchEvent(new Event("change", { bubbles: true }));
    expect(handlers.onToggleRow).toHaveBeenCalledWith("original.pdf");

    const move = app.querySelector<HTMLInputElement>(
      'input[aria-label="Move originals to processed"]'
    );
    expect(move?.checked).toBe(true);
    move?.dispatchEvent(new Event("change", { bubbles: true }));
    expect(handlers.onMoveProcessed).toHaveBeenCalledWith(true);
  });

  it("shows saved folder names and permission hints", () => {
    stubDirectoryPicker(true);

    const app = renderApp(
      makeState({
        inputFolderName: "receipts-in",
        outputFolderName: "receipts-out",
        inputPermissionNeeded: true,
      }),
      makeHandlers()
    );

    expect(app.textContent).toContain("receipts-in");
    expect(app.textContent).toContain("receipts-out");
    expect(app.textContent).toContain("Input permission needed on Scan");
  });

  it("shows writeError on a ready row with the error below the name", () => {
    stubDirectoryPicker(true);
    const row = makeRow({
      finalName: "transfBBVA_to_Banamex_x128.00_May2026.pdf",
      writeError: "Permission denied: cannot write to output folder",
    });

    const app = renderApp(makeState({ rows: [row] }), makeHandlers());
    const renderedRow = app.querySelector("tbody tr");
    const nameCell = renderedRow?.querySelector("td:last-child");

    expect(renderedRow?.textContent).toContain(
      "transfBBVA_to_Banamex_x128.00_May2026.pdf"
    );
    expect(nameCell?.querySelector(".row-error")?.textContent).toBe(
      "Permission denied: cannot write to output folder"
    );
    expect(renderedRow?.textContent).toContain("✓");
  });

  it("does not show writeError on a done row after a successful retry", () => {
    stubDirectoryPicker(true);
    const row = makeRow({
      finalName: "transfBBVA_to_Banamex_x128.00_May2026.pdf",
      status: "done",
      writeError: undefined,
    });

    const app = renderApp(makeState({ rows: [row] }), makeHandlers());
    const renderedRow = app.querySelector("tbody tr");
    const nameCell = renderedRow?.querySelector("td:last-child");

    expect(renderedRow?.textContent).toContain(
      "transfBBVA_to_Banamex_x128.00_May2026.pdf"
    );
    expect(nameCell?.querySelector(".row-error")).toBeNull();
  });
});
