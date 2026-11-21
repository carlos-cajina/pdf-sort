import type { TransactionInfo } from "./engine/models";
import { extractInfo } from "./engine/orchestrator";
import { buildFilename, sanitizeFilename } from "./engine/rename";
import type { ScanEntry } from "./fs/scan";
import { planRenames, type RowOutcome } from "./fs/write";

export type RowStatus = "parsing" | "ready" | "incomplete" | "error" | "excluded" | "done";

export type Row = {
  original: string;
  status: RowStatus;
  proposed: string | null;
  manualName: string;
  finalName: string | null;
  collision: boolean;
  error?: string;
};

type ParseResult = { info: TransactionInfo; proposed: string | null };
type ParseFile = (entry: ScanEntry) => Promise<ParseResult>;

const MAX_CONCURRENT_PARSES = 4;

/** Parse every entry with four workers, keeping results in scan order. */
export async function parseAll(
  entries: ScanEntry[],
  parseFile: ParseFile,
  onProgress: (done: number, total: number) => void
): Promise<Row[]> {
  const rows: Row[] = entries.map((entry) => ({
    original: entry.name,
    status: "parsing",
    proposed: null,
    manualName: "",
    finalName: null,
    collision: false,
  }));
  let nextIndex = 0;
  let done = 0;

  async function worker(): Promise<void> {
    while (nextIndex < entries.length) {
      const index = nextIndex;
      nextIndex += 1;
      const current = entries[index];

      try {
        const { proposed } = await parseFile(current);
        rows[index] = {
          original: current.name,
          status: proposed === null ? "incomplete" : "ready",
          proposed,
          manualName: "",
          finalName: null,
          collision: false,
        };
      } catch (error) {
        rows[index] = {
          original: current.name,
          status: "error",
          proposed: null,
          manualName: "",
          finalName: null,
          collision: false,
          error: error instanceof Error ? error.message : String(error),
        };
      }

      done += 1;
      onProgress(done, entries.length);
    }
  }

  await Promise.all(
    Array.from({ length: Math.min(MAX_CONCURRENT_PARSES, entries.length) }, () =>
      worker()
    )
  );
  // The progress contract runs up to (total, total); an empty scan still
  // reports its terminal (0, 0).
  if (entries.length === 0) {
    onProgress(0, 0);
  }
  return rows;
}

/** Real parser, dynamically imported so injecting a fake never loads pdf.js. */
export async function defaultParseFile(entry: ScanEntry): Promise<ParseResult> {
  const data = await entry.file.arrayBuffer();
  const { extractPdfText } = await import("./pdf/text");
  const text = await extractPdfText(data);
  // Empty text is incomplete by definition; make that explicit instead of
  // relying on extractInfo happening to yield nulls for empty input.
  if (text.trim() === "") {
    return { info: extractInfo(text), proposed: null };
  }
  const info = extractInfo(text);
  return { info, proposed: buildFilename(info) };
}

/** Set a manual filename, returning a new row array. */
export function setManualName(rows: Row[], original: string, name: string): Row[] {
  return rows.map((row) =>
    row.original === original ? { ...row, manualName: name } : row
  );
}

/** Exclude a row, or restore the status implied by its parse result. */
export function toggleRow(rows: Row[], original: string): Row[] {
  return rows.map((row) => {
    if (row.original !== original) {
      return row;
    }
    if (row.status === "done") {
      // Already renamed in a prior run; toggling must not reactivate it.
      return row;
    }
    if (row.status !== "excluded") {
      return { ...row, status: "excluded" };
    }

    let status: RowStatus = "ready";
    if (row.error !== undefined) {
      status = "error";
    } else if (row.proposed === null) {
      status = "incomplete";
    }
    return { ...row, status };
  });
}

/** Plan sanitized manual names and auto names together, preserving each row's proposal. */
export function computePlan(rows: Row[], existingNames: Set<string>): Row[] {
  // Done rows (already renamed in a prior run) are terminal: keep their
  // finalName, do not re-plan them, so a second run cannot bump them to _2.
  const active = rows.filter((row) => row.status !== "done");
  const planned = planRenames(
    active.map((row) => ({ ...row, proposed: resolveProposed(row) })),
    existingNames
  );

  // Merge back keyed by the row's original name, not by index, so the plan
  // can never attach a finalName to the wrong row.
  const plannedByOriginal = new Map(
    planned.map((plannedRow) => [plannedRow.original, plannedRow])
  );
  return rows.map((row) => {
    if (row.status === "done") {
      return row;
    }
    const plannedRow = plannedByOriginal.get(row.original);
    return {
      ...row,
      finalName: plannedRow?.finalName ?? null,
      collision: plannedRow?.collision ?? false,
    };
  });
}

/** A row's proposal going into the plan: manual name wins, excluded rows propose nothing. */
function resolveProposed(row: Row): string | null {
  if (row.status === "excluded") {
    return null;
  }
  if (row.manualName.trim() !== "") {
    const sanitized = sanitizeFilename(row.manualName.trim());
    // A name made only of unsafe characters or dots would collapse into a
    // degenerate target ("" → ".pdf", "." → ".pdf", ".." → "..pdf"); treat
    // it as no proposal so the row stays incomplete instead of writing one.
    if (sanitized === "" || sanitized === "." || sanitized === "..") {
      return null;
    }
    return ensurePdfExtension(sanitized);
  }
  return row.proposed;
}

/** Manual names are filenames: add the extension the plan/renamer expects. */
function ensurePdfExtension(name: string): string {
  return /\.pdf$/i.test(name) ? name : `${name}.pdf`;
}

/** Summarize successful writes/moves, unattempted rows, and failures. */
export function summary(rows: Row[], outcomes: RowOutcome[]): string {
  const renamed = outcomes.filter(
    (outcome) => outcome.status === "written" || outcome.status === "moved"
  ).length;
  const failed = outcomes.filter((outcome) => outcome.status === "failed").length;
  // Skipped means never attempted: excluded, blank, or already-done rows have
  // no finalName and executeRenames records no outcome for them. Parse-error
  // rows also have no finalName, but they failed rather than being skipped —
  // they are visible in the table and excluded from the skipped count.
  const skipped = rows.filter(
    (row) => row.finalName === null && row.status !== "error" && row.status !== "done"
  ).length;
  return `${renamed} renamed, ${skipped} skipped, ${failed} failed`;
}
