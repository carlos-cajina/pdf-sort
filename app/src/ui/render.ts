import type { Row } from "../state";

export type RenderState = {
  inputFolderName: string | null;
  outputFolderName: string | null;
  inputPermissionNeeded: boolean;
  outputPermissionNeeded: boolean;
  rows: Row[];
  scanned: boolean;
  progress: { done: number; total: number } | null;
  moveProcessed: boolean;
  summary: string | null;
  notice: string | null;
  busy: boolean;
};

export type RenderHandlers = {
  onPickInput: () => void;
  onPickOutput: () => void;
  onScan: () => void;
  onRename: () => void;
  onToggleRow: (original: string) => void;
  onManualName: (original: string, name: string) => void;
  onMoveProcessed: (move: boolean) => void;
};

/** Render the complete app surface. State transitions and IO stay in main.ts. */
export function renderApp(
  state: RenderState,
  handlers: RenderHandlers
): HTMLElement {
  const supported = "showDirectoryPicker" in window;
  const app = document.createElement("main");
  const heading = document.createElement("h1");
  heading.textContent = "PDF Sort";
  app.append(heading);

  if (!supported) {
    const banner = document.createElement("p");
    banner.className = "banner alert";
    banner.setAttribute("role", "alert");
    banner.textContent =
      "Folder picking requires Chrome or Edge. Use a current desktop version to scan and rename PDFs.";
    app.append(banner);
  }

  if (state.notice !== null) {
    const notice = document.createElement("p");
    notice.className = "banner notice";
    notice.setAttribute("role", "alert");
    notice.textContent = state.notice;
    app.append(notice);
  }

  const controls = document.createElement("section");
  controls.className = "controls";
  controls.setAttribute("aria-label", "Folders and actions");
  controls.append(
    folderControl(
      "Input",
      state.inputFolderName,
      state.inputPermissionNeeded,
      state.busy || !supported,
      handlers.onPickInput
    ),
    folderControl(
      "Output",
      state.outputFolderName,
      state.outputPermissionNeeded,
      state.busy || !supported,
      handlers.onPickOutput
    )
  );

  const scan = actionButton(
    "Scan",
    state.busy ||
      !supported ||
      state.inputFolderName === null ||
      state.outputFolderName === null,
    handlers.onScan
  );
  controls.append(scan);

  const renameCount = state.rows.filter(
    (row) =>
      row.status !== "excluded" &&
      row.status !== "done" &&
      (row.finalName !== null ||
        (row.status === "incomplete" && row.manualName.trim() !== ""))
  ).length;
  const rename = actionButton(
    `Rename ${renameCount} files`,
    state.busy ||
      !supported ||
      state.progress !== null ||
      state.inputFolderName === null ||
      state.outputFolderName === null ||
      renameCount === 0,
    handlers.onRename
  );
  rename.classList.add("primary");
  controls.append(rename);

  const moveLabel = document.createElement("label");
  const move = document.createElement("input");
  move.type = "checkbox";
  move.checked = state.moveProcessed;
  move.disabled = state.busy;
  move.setAttribute("aria-label", "Move originals to processed");
  move.addEventListener("change", () => {
    handlers.onMoveProcessed(move.checked);
  });
  moveLabel.append(move, document.createTextNode(" Move originals to processed"));
  controls.append(moveLabel);
  app.append(controls);

  if (state.progress !== null) {
    const progressLabel = document.createElement("label");
    progressLabel.className = "progress-row";
    progressLabel.textContent = `Parsing ${state.progress.done} of ${state.progress.total} PDFs `;
    const progress = document.createElement("progress");
    progress.max = state.progress.total;
    progress.value = state.progress.done;
    progress.setAttribute("aria-label", "Parsing PDFs");
    progressLabel.append(progress);
    app.append(progressLabel);
  }

  if (state.rows.length > 0) {
    app.append(renderRows(state.rows, state.busy, handlers));
  } else if (
    state.scanned &&
    state.progress === null &&
    state.notice === null
  ) {
    const empty = document.createElement("p");
    empty.textContent = "No PDFs found in input folder";
    app.append(empty);
  } else if (
    !state.scanned &&
    state.progress === null &&
    !state.busy &&
    state.notice === null
  ) {
    const empty = document.createElement("p");
    empty.textContent = "Choose input and output folders, then select Scan.";
    app.append(empty);
  }

  if (state.summary !== null) {
    const results = document.createElement("section");
    results.className = "results";
    const heading = document.createElement("h2");
    heading.textContent = "Done";
    results.append(heading);
    const dest = document.createElement("p");
    dest.className = "dest";
    dest.textContent = `Destination: ${state.outputFolderName ?? "(output folder)"} — renamed files are written there. (Originals ${state.moveProcessed ? "moved to input/processed/" : "left in the input folder"}.)`;
    results.append(dest);
    const renamed = state.rows
      .filter(
        (row): row is Row & { finalName: string } =>
          row.finalName !== null && row.status !== "excluded"
      )
      .map((row) => row.finalName);
    if (renamed.length > 0) {
      const list = document.createElement("ul");
      for (const name of renamed) {
        const item = document.createElement("li");
        item.textContent = name;
        list.append(item);
      }
      results.append(list);
    }
    const summary = document.createElement("p");
    summary.className = "summary";
    summary.textContent = state.summary;
    results.append(summary);
    app.append(results);
  }

  const hint = document.createElement("p");
  hint.className = "hint";
  hint.textContent =
    "Tip: renamed files are written to the output folder you chose; originals stay in the input folder unless “Move originals to processed” is checked.";
  app.append(hint);

  return app;
}

function folderControl(
  label: string,
  folderName: string | null,
  permissionNeeded: boolean,
  disabled: boolean,
  onPick: () => void
): HTMLElement {
  const container = document.createElement("div");
  container.className = "folder";
  const name = document.createElement("span");
  name.className = folderName === null ? "folder-name empty" : "folder-name";
  name.textContent = `${label}: ${folderName ?? "no folder selected"}`;
  container.append(name);

  if (folderName !== null && permissionNeeded) {
    const permission = document.createElement("span");
    permission.className = "folder-hint";
    permission.textContent = `${label} permission needed on Scan`;
    container.append(permission);
  }

  container.append(
    actionButton(
      folderName === null ? `Choose ${label.toLowerCase()} folder` : `Change ${label.toLowerCase()} folder`,
      disabled,
      onPick
    )
  );
  return container;
}

function actionButton(
  label: string,
  disabled: boolean,
  onClick: () => void
): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.disabled = disabled;
  button.addEventListener("click", onClick);
  return button;
}

function renderRows(
  rows: Row[],
  busy: boolean,
  handlers: RenderHandlers
): HTMLTableElement {
  const table = document.createElement("table");
  const head = document.createElement("thead");
  const headerRow = document.createElement("tr");
  for (const label of ["Include", "Status", "Original", "", "New name"]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = label;
    if (label === "") {
      // The arrow column has no header text; keep it out of the a11y tree.
      cell.setAttribute("aria-hidden", "true");
    }
    headerRow.append(cell);
  }
  head.append(headerRow);
  table.append(head);

  const body = document.createElement("tbody");
  for (const row of rows) {
    const tableRow = document.createElement("tr");

    const includeCell = document.createElement("td");
    const include = document.createElement("input");
    include.type = "checkbox";
    include.checked = row.status !== "excluded";
    include.disabled = busy;
    include.setAttribute("aria-label", `Include ${row.original}`);
    include.addEventListener("change", () => {
      handlers.onToggleRow(row.original);
    });
    includeCell.append(include);
    tableRow.append(includeCell);

    const status = document.createElement("td");
    status.textContent = statusGlyph(row);
    status.className = `status ${row.status}`;
    status.title = row.writeError ?? row.detail ?? row.status;
    tableRow.append(status);

    const original = document.createElement("td");
    original.textContent = row.original;
    tableRow.append(original);

    const arrow = document.createElement("td");
    arrow.textContent = "→";
    tableRow.append(arrow);

    const name = document.createElement("td");
    if (
      row.status === "incomplete" &&
      row.finalName === null &&
      row.writeError === undefined
    ) {
      // No final name committed yet: show an input for the user to type one.
      const input = document.createElement("input");
      input.type = "text";
      input.value = pendingManualEdit(row.original) ?? row.manualName;
      input.disabled = busy;
      input.placeholder = "Enter filename.pdf";
      input.setAttribute("aria-label", `New name for ${row.original}`);
      input.dataset.manualNameFor = row.original;
      input.addEventListener("change", () => {
        handlers.onManualName(row.original, input.value);
      });
      name.append(input);
      if (row.detail) {
        const detail = document.createElement("p");
        detail.className = "row-detail";
        detail.textContent = row.detail;
        name.append(detail);
      }
    } else if (row.status === "error" && row.writeError === undefined) {
      name.textContent = row.error ?? "Unable to parse PDF";
    } else if (row.status === "parsing") {
      name.textContent = "Parsing…";
    } else {
      name.textContent = row.finalName ?? row.proposed ?? row.manualName;
    }

    if (row.collision) {
      const collision = document.createElement("span");
      collision.className = "collision";
      collision.textContent = "collision — bumped to avoid overwrite";
      name.append(collision);
    }

    // A write error from the last Rename run: keep the proposed name visible
    // and surface the error below it so the failure isn't lost.
    if (row.writeError !== undefined) {
      const writeError = document.createElement("p");
      writeError.className = "row-detail row-error";
      writeError.textContent = row.writeError;
      name.append(writeError);
    }
    tableRow.append(name);
    body.append(tableRow);
  }
  table.append(body);
  return table;
}

function statusGlyph(row: Row): string {
  switch (row.status) {
    case "ready":
      return "✓";
    case "incomplete":
      return "⚠";
    case "error":
      return "✕";
    case "excluded":
      return "—";
    case "parsing":
      return "…";
    case "done":
      // Already renamed in a prior run.
      return "✓";
    default:
      // Compile-time exhaustiveness: a new RowStatus fails this assignment.
      const exhaustive: never = row.status;
      // Runtime fallback: an unexpected status degrades to "?" instead of
      // crashing the whole render.
      void exhaustive;
      return "?";
  }
}

/**
 * An in-progress (uncommitted) manual-name edit for `original`, if the user is
 * typing it right now. Commits happen on change/blur, so a re-render in
 * between must not wipe what has been typed so far.
 */
function pendingManualEdit(original: string): string | undefined {
  const active = document.activeElement;
  if (
    active instanceof HTMLInputElement &&
    active.dataset.manualNameFor === original
  ) {
    return active.value;
  }
  return undefined;
}
