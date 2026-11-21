import {
  getPermission,
  loadHandle,
  pickFolder,
  requestPermission,
  requestPersistentStorage,
  saveHandle,
} from "./fs/handles";
import { scanInputFolder, type ScanEntry } from "./fs/scan";
import {
  executeRenames,
  readExistingNames,
  type RenameRow,
  type RowOutcome,
} from "./fs/write";
import {
  computePlan,
  defaultParseFile,
  parseAll,
  setManualName,
  summary,
  toggleRow,
  type Row,
} from "./state";
import "./styles.css";
import { flushFocusedManualName } from "./ui/manual-name";
import {
  renderApp,
  type RenderHandlers,
  type RenderState,
} from "./ui/render";

const app = document.querySelector<HTMLDivElement>("#app");
let mouseDown = false;

function setMouseDown(value: boolean): void {
  mouseDown = value;
}

app?.addEventListener("mousedown", () => {
  setMouseDown(true);
}, true);
window.addEventListener("mouseup", () => {
  setMouseDown(false);
}, true);
document.addEventListener("mouseup", () => {
  setMouseDown(false);
}, true);
window.addEventListener("blur", () => {
  setMouseDown(false);
}, true);

let inputDir: FileSystemDirectoryHandle | null = null;
let outputDir: FileSystemDirectoryHandle | null = null;
let scannedEntries: ScanEntry[] = [];
let existingOutputNames = new Set<string>();

let state: RenderState = {
  inputFolderName: null,
  outputFolderName: null,
  inputPermissionNeeded: false,
  outputPermissionNeeded: false,
  rows: [],
  scanned: false,
  progress: null,
  moveProcessed: false,
  summary: null,
  notice: null,
  busy: false,
};

const handlers: RenderHandlers = {
  onPickInput: () => {
    void chooseFolder("input");
  },
  onPickOutput: () => {
    void chooseFolder("output");
  },
  onScan: () => {
    void scan();
  },
  onRename: () => {
    void rename();
  },
  onToggleRow: (original) => {
    flushManualName();
    const toggled = toggleRow(state.rows, original);
    state = {
      ...state,
      rows: computePlan(toggled, existingOutputNames),
      summary: null,
      notice: null,
    };
    render();
  },
  onManualName: (original, name) => {
    if (commitManualName(original, name)) {
      renderAfterManualNameEdit();
    }
  },
  onMoveProcessed: (moveProcessed) => {
    flushManualName();
    state = { ...state, moveProcessed };
    render();
  },
};

function commitManualName(original: string, name: string): boolean {
  const trimmed = name.trim();
  const row = state.rows.find((candidate) => candidate.original === original);
  if (row === undefined || row.manualName === trimmed) {
    return false;
  }
  const edited = setManualName(state.rows, original, trimmed);
  state = {
    ...state,
    rows: computePlan(edited, existingOutputNames),
    summary: null,
    notice: null,
  };
  return true;
}

function flushManualName(): void {
  flushFocusedManualName(state.rows, commitManualName);
}

function renderAfterManualNameEdit(): void {
  if (!mouseDown) {
    render();
    return;
  }
  window.addEventListener(
    "mouseup",
    () => {
      window.setTimeout(render, 0);
    },
    { once: true }
  );
}

function render(): void {
  const active = document.activeElement;
  const manualOriginal =
    active instanceof HTMLInputElement
      ? active.dataset.manualNameFor
      : undefined;
  const selectionStart =
    active instanceof HTMLInputElement ? active.selectionStart : null;
  const selectionEnd =
    active instanceof HTMLInputElement ? active.selectionEnd : null;
  app?.replaceChildren(renderApp(state, handlers));

  if (app && manualOriginal !== undefined) {
    const input = Array.from(
      app.querySelectorAll<HTMLInputElement>("input[data-manual-name-for]")
    ).find((candidate) => candidate.dataset.manualNameFor === manualOriginal);
    input?.focus();
    if (selectionStart !== null && selectionEnd !== null) {
      input?.setSelectionRange(selectionStart, selectionEnd);
    }
  }
}

async function restoreHandles(): Promise<void> {
  try {
    await restoreHandlesInner();
  } catch (error) {
    // Never leave module handles populated while the UI shows nothing: a
    // failed restore must leave both handles and the visible state null so
    // scan/rename cannot run against handles the user cannot see.
    inputDir = null;
    outputDir = null;
    scannedEntries = [];
    existingOutputNames = new Set<string>();
    state = {
      ...state,
      inputFolderName: null,
      outputFolderName: null,
      inputPermissionNeeded: false,
      outputPermissionNeeded: false,
      rows: [],
      scanned: false,
      progress: null,
      notice: errorMessage(error),
    };
  } finally {
    render();
  }
}

async function restoreHandlesInner(): Promise<void> {
  // Restore each saved handle independently: a failure on one side must not
  // discard a still-valid other. Only the same-directory conflict invalidates
  // both, because the pair is unusable as configured.
  const [loadedInput, loadedOutput] = await Promise.allSettled([
    loadHandle("input"),
    loadHandle("output"),
  ]);
  const inputFailed = loadedInput.status === "rejected";
  const outputFailed = loadedOutput.status === "rejected";
  const restoredInput =
    loadedInput.status === "fulfilled" ? loadedInput.value : null;
  const restoredOutput =
    loadedOutput.status === "fulfilled" ? loadedOutput.value : null;

  // A permission probe failure only means "ask again on Scan"; the handle
  // itself is fine, so it must not be dropped.
  const [inputPermission, outputPermission] = await Promise.all([
    restoredInput === null
      ? Promise.resolve(null)
      : getPermission(restoredInput).catch(() => null),
    restoredOutput === null
      ? Promise.resolve(null)
      : getPermission(restoredOutput).catch(() => null),
  ]);

  if (restoredInput !== null && restoredOutput !== null) {
    let same: boolean;
    try {
      same = await restoredInput.isSameEntry(restoredOutput);
    } catch {
      // A transient comparison failure is not evidence of a conflict: keep
      // the handles (they fail loudly on use if actually broken) and ask the
      // user to re-pick rather than discarding two valid folders.
      inputDir = restoredInput;
      outputDir = restoredOutput;
      scannedEntries = [];
      existingOutputNames = new Set<string>();
      state = {
        ...state,
        inputFolderName: restoredInput.name,
        outputFolderName: restoredOutput.name,
        inputPermissionNeeded: inputPermission !== "granted",
        outputPermissionNeeded: outputPermission !== "granted",
        rows: [],
        scanned: false,
        progress: null,
        notice:
          "Could not verify that the saved input and output folders are different; pick them again to be safe.",
      };
      return;
    }
    if (same) {
      inputDir = null;
      outputDir = null;
      scannedEntries = [];
      existingOutputNames = new Set<string>();
      state = {
        ...state,
        inputFolderName: null,
        outputFolderName: null,
        inputPermissionNeeded: false,
        outputPermissionNeeded: false,
        rows: [],
        scanned: false,
        progress: null,
        notice:
          "The stored input and output folders are the same directory; pick them again",
      };
      render();
      return;
    }
  }

  inputDir = inputFailed ? null : restoredInput;
  outputDir = outputFailed ? null : restoredOutput;
  scannedEntries = [];
  existingOutputNames = new Set<string>();
  state = {
    ...state,
    inputFolderName: inputDir?.name ?? null,
    outputFolderName: outputDir?.name ?? null,
    inputPermissionNeeded:
      inputDir !== null && inputPermission !== "granted",
    outputPermissionNeeded:
      outputDir !== null && outputPermission !== "granted",
    notice:
      inputFailed || outputFailed
        ? "A saved folder could not be restored; pick it again."
        : null,
  };
}

async function chooseFolder(kind: "input" | "output"): Promise<void> {
  if (state.busy) {
    return;
  }
  requestPersistentStorage();
  state = { ...state, busy: true, notice: null };
  render();

  try {
    const handle = await pickFolder();
    // Refuse the same directory for input and output: renaming into the
    // scanned folder risks clobbering originals (the write probe catches
    // direct name matches, but not the self-collision churn).
    const other = kind === "input" ? outputDir : inputDir;
    if (other !== null && (await other.isSameEntry(handle))) {
      // finally reports busy:false and re-renders.
      state = {
        ...state,
        notice: "The input and output folders must be different directories.",
      };
      return;
    }
    // Ask permission before persisting: if the permission step failed after a
    // save, IndexedDB would hold a handle the visible state never adopted
    // until reload.
    const permission = await getPermission(handle);
    await saveHandle(kind, handle);

    if (kind === "input") {
      inputDir = handle;
    } else {
      outputDir = handle;
    }
    scannedEntries = [];
    existingOutputNames = new Set<string>();
    state = {
      ...state,
      inputFolderName: kind === "input" ? handle.name : state.inputFolderName,
      outputFolderName:
        kind === "output" ? handle.name : state.outputFolderName,
      inputPermissionNeeded:
        kind === "input" ? permission !== "granted" : state.inputPermissionNeeded,
      outputPermissionNeeded:
        kind === "output"
          ? permission !== "granted"
          : state.outputPermissionNeeded,
      rows: [],
      scanned: false,
      progress: null,
      summary: null,
    };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      // The user cancelled the directory picker; that is not an error.
      return;
    }
    state = { ...state, notice: errorMessage(error) };
  } finally {
    state = { ...state, busy: false };
    render();
  }
}

/** Scan click is the only flow that calls requestPermission. */
async function scan(): Promise<void> {
  flushManualName();
  if (state.busy || inputDir === null || outputDir === null) {
    return;
  }
  requestPersistentStorage();
  const input = inputDir;
  const output = outputDir;
  state = {
    ...state,
    busy: true,
    rows: [],
    scanned: false,
    progress: null,
    summary: null,
    notice: null,
  };
  scannedEntries = [];
  render();

  try {
    // Start every needed request synchronously in this click handler, before
    // the first await, so none depends on a later non-gesture callback.
    const inputPermissionRequest = state.inputPermissionNeeded
      ? requestPermission(input)
      : null;
    const outputPermissionRequest = state.outputPermissionNeeded
      ? requestPermission(output)
      : null;
    const [inputGranted, outputGranted] = await Promise.all([
      inputPermissionRequest ?? Promise.resolve(true),
      outputPermissionRequest ?? Promise.resolve(true),
    ]);
    state = {
      ...state,
      inputPermissionNeeded: !inputGranted,
      outputPermissionNeeded: !outputGranted,
    };
    if (!inputGranted || !outputGranted) {
      state = {
        ...state,
        notice: "Read/write permission for both folders is required.",
      };
      return;
    }

    const entries = await scanInputFolder(input);
    scannedEntries = entries;
    if (entries.length === 0) {
      existingOutputNames = new Set<string>();
      state = { ...state, rows: [], scanned: true };
      return;
    }

    state = {
      ...state,
      progress: { done: 0, total: entries.length },
    };
    render();
    const parsed = await parseAll(
      entries,
      defaultParseFile,
      (done, total) => {
        state = { ...state, progress: { done, total } };
        render();
      }
    );

    const existingNames = await readExistingNames(output);
    existingOutputNames = existingNames;
    state = {
      ...state,
      rows: computePlan(parsed, existingNames),
      scanned: true,
      progress: null,
    };
  } catch (error) {
    // A mid-scan failure must not leave stale accumulators behind: rename()
    // plans against scannedEntries and the existing-name set, so a partial
    // scan result could otherwise be used by the next click.
    scannedEntries = [];
    existingOutputNames = new Set<string>();
    if (error instanceof DOMException && error.name === "NotAllowedError") {
      // Permission revoked between scans surfaces as NotAllowedError from
      // folder access, not as a missed prompt: mark both folders so the next
      // Scan click re-requests (a granted folder resolves without prompting).
      state = {
        ...state,
        inputPermissionNeeded: true,
        outputPermissionNeeded: true,
        notice: "Folder permission is needed; press Scan to grant it.",
        progress: null,
        scanned: true,
      };
    } else {
      state = {
        ...state,
        notice: errorMessage(error),
        progress: null,
        scanned: true,
      };
    }
  } finally {
    state = { ...state, busy: false, progress: null };
    render();
  }
}

async function rename(): Promise<void> {
  flushManualName();
  if (state.busy || inputDir === null || outputDir === null) {
    return;
  }
  const input = inputDir;
  const output = outputDir;
  const moveProcessed = state.moveProcessed;
  state = { ...state, busy: true, notice: null, summary: null };
  render();

  try {
    // Plan only now, inside the write gesture, against names read now. Plans
    // rendered during scanning and edits are never reused for the write.
    const freshNames = await readExistingNames(output);
    existingOutputNames = freshNames;
    const planned = computePlan(state.rows, freshNames);
    state = { ...state, rows: planned };
    const renameRows = toRenameRows(planned, scannedEntries);
    if (renameRows.length === 0) {
      // A click that does nothing still deserves its result, and the run
      // started by clearing the previous summary.
      state = { ...state, summary: summary(state.rows, []) };
      return;
    }

    let outcomes = await executeRenames(input, output, renameRows, {
      moveProcessed,
    });
    recordSuccessfulNames(planned, outcomes);

    // Terminalize rows that were successfully written or moved so a later
    // Rename click cannot re-plan them (which would bump to _2/_3 again).
    for (const outcome of outcomes) {
      if (outcome.status === "written" || outcome.status === "moved") {
        const row = state.rows.find((candidate) => candidate.original === outcome.original);
        if (row !== undefined && row.finalName !== null) {
          row.status = "done";
        }
      }
    }

    const writeCollisions = outcomes.filter(
      (outcome) => outcome.writeCollision === true
    );
    let cancelledCollisions = false;
    if (writeCollisions.length > 0) {
      const collisionOriginals = writeCollisions
        .map((outcome) => outcome.original)
        .join(", ");
      const retry = window.confirm(
        `${writeCollisions.length} file(s) collided with a name that appeared in the output folder: ${collisionOriginals}. ` +
          "Select OK to re-read the folder, bump those names, and retry only those files once. " +
          "Select Cancel to leave those originals untouched."
      );
      if (retry) {
        outcomes = await retryWriteCollisions(
          input,
          output,
          writeCollisions,
          outcomes,
          moveProcessed
        );
      } else {
        cancelledCollisions = true;
      }
    }

    // One composed notice: the Cancel path and the post-retry remainder must
    // never overwrite each other, and processed/ collisions are just as loud.
    const notices: string[] = [];
    const remainingCollisions = outcomes.filter(
      (outcome) => outcome.writeCollision === true
    ).length;
    if (remainingCollisions > 0) {
      notices.push(
        cancelledCollisions
          ? `${remainingCollisions} colliding file(s) were left untouched.`
          : `${remainingCollisions} colliding file(s) were left untouched after the run.`
      );
    }
    const processedCollisions = outcomes.filter(
      (outcome) => outcome.processedCollision === true
    ).length;
    if (processedCollisions > 0) {
      notices.push(
        `${processedCollisions} original(s) already exist in processed/; clear or rename the archived copies before moving them again.`
      );
    }
    if (notices.length > 0) {
      state = { ...state, notice: notices.join(" ") };
    }
    state = { ...state, summary: summary(state.rows, outcomes) };
  } catch (error) {
    state = { ...state, notice: errorMessage(error) };
  } finally {
    state = { ...state, busy: false };
    render();
  }
}

async function retryWriteCollisions(
  input: FileSystemDirectoryHandle,
  output: FileSystemDirectoryHandle,
  collisions: RowOutcome[],
  outcomes: RowOutcome[],
  moveProcessed: boolean
): Promise<RowOutcome[]> {
  const collisionNames = new Set(collisions.map((outcome) => outcome.original));
  const collisionRows = state.rows.filter((row) =>
    collisionNames.has(row.original)
  );
  const freshNames = await readExistingNames(output);
  // Union, not replace: the names recorded from the first run were just
  // written, and a stale directory read must never let a replanned collision
  // pick an already-occupied output name. Plan against the union too —
  // bumping must dodge every occupied name, not just the freshly-read ones.
  const mergedNames = new Set([...existingOutputNames, ...freshNames]);
  existingOutputNames = mergedNames;
  const replanned = computePlan(collisionRows, mergedNames);
  const replannedByOriginal = new Map(
    replanned.map((row) => [row.original, row])
  );
  state = {
    ...state,
    rows: state.rows.map(
      (row) => replannedByOriginal.get(row.original) ?? row
    ),
  };

  const retryOutcomes = await executeRenames(
    input,
    output,
    toRenameRows(replanned, scannedEntries),
    { moveProcessed }
  );
  recordSuccessfulNames(replanned, retryOutcomes);
  const retryByOriginal = new Map(
    retryOutcomes.map((outcome) => [outcome.original, outcome])
  );
  return outcomes.map(
    (outcome) => retryByOriginal.get(outcome.original) ?? outcome
  );
}

function toRenameRows(rows: Row[], entries: ScanEntry[]): RenameRow[] {
  const entriesByName = new Map(entries.map((entry) => [entry.name, entry]));
  const renameRows: RenameRow[] = [];

  for (const row of rows) {
    if (row.status === "excluded" || row.finalName === null) {
      continue;
    }
    const entry = entriesByName.get(row.original);
    if (!entry) {
      throw new Error(`Scanned file is missing: ${row.original}`);
    }
    // Use the file handle to fetch fresh bytes at write time instead of the
    // scan-time snapshot. This avoids writing stale bytes if the source file
    // was replaced on disk between scan and rename.
    renameRows.push({
      original: row.original,
      bytes: () => entry.handle.getFile().then((file) => file.arrayBuffer()),
      finalName: row.finalName,
      kind: row.manualName.trim() === "" ? "auto" : "manual",
      collision: row.collision,
    });
  }
  return renameRows;
}

function recordSuccessfulNames(rows: Row[], outcomes: RowOutcome[]): void {
  const rowsByOriginal = new Map(rows.map((row) => [row.original, row]));
  for (const outcome of outcomes) {
    // A failed row can still have written its output (the archive step failed
    // afterwards); that name is occupied in the output folder and must join
    // the collision set even though the row is not "written"/"moved".
    if (outcome.writtenName !== undefined) {
      existingOutputNames.add(outcome.writtenName);
    }
    if (outcome.status !== "written" && outcome.status !== "moved") {
      continue;
    }
    const row = rowsByOriginal.get(outcome.original);
    if (row !== undefined && row.finalName !== null) {
      existingOutputNames.add(row.finalName);
    }
  }
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "object" && error !== null) {
    try {
      // Truncate: a large serialized object is unreadable in a one-line notice.
      return JSON.stringify(error).slice(0, 200);
    } catch {
      return String(error);
    }
  }
  return String(error);
}

if (app) {
  if ("showDirectoryPicker" in window) {
    void restoreHandles();
  } else {
    render();
  }
}
