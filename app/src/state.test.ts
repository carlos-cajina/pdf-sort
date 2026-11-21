import { beforeEach, describe, expect, it, vi } from "vitest";
import { TransactionInfo } from "./engine/models";
import { extractInfo } from "./engine/orchestrator";
import { buildFilename } from "./engine/rename";
import type { ScanEntry } from "./fs/scan";
import type { RowOutcome } from "./fs/write";
import { extractPdfText } from "./pdf/text";
import {
  computePlan,
  defaultParseFile,
  parseAll,
  setManualName,
  summary,
  toggleRow,
  type Row,
} from "./state";

vi.mock("./pdf/text", () => ({ extractPdfText: vi.fn() }));

const BBVA_TEXT = `CAJINA MORALES CARLOS ERNESTO
A otros bancos - Cuenta CLABE
Comprobante 10/May/2026 08:19:07
Cuenta de retiro: 1572633671
Tipo de operación: Transferir - Otros bancos - Cuenta CLABE
Banco destino: BANAMEX
Importe: $128.00
Fecha de operación: 10/05/2026
BBVA México, S.A., Institución de Banca Múltiple, Grupo Financiero BBVA México.`;

function completeInfo(): TransactionInfo {
  return new TransactionInfo(
    new Date(Date.UTC(2026, 4, 10)),
    "BBVA",
    "Banamex",
    128
  );
}

function entry(name: string): ScanEntry {
  const handle: any = {
    kind: "file",
    name,
    async getFile(): Promise<File> {
      return new File([name], name, { type: "application/pdf" });
    },
  };
  return { name, file: new File([name], name, { type: "application/pdf" }), handle };
}

function makeRow(original: string, overrides: Partial<Row> = {}): Row {
  return {
    original,
    status: "ready",
    proposed: "auto.pdf",
    manualName: "",
    finalName: null,
    collision: false,
    ...overrides,
  };
}

const ignoreProgress = () => {};

beforeEach(() => {
  vi.mocked(extractPdfText).mockReset();
});

describe("parseAll", () => {
  it("returns a ready row with the proposed name after a successful parse", async () => {
    const rows = await parseAll(
      [entry("receipt.pdf")],
      async () => ({
        info: completeInfo(),
        proposed: "transfBBVA_to_Banamex_x128.00_May2026.pdf",
      }),
      ignoreProgress
    );

    expect(rows).toEqual([
      {
        original: "receipt.pdf",
        status: "ready",
        proposed: "transfBBVA_to_Banamex_x128.00_May2026.pdf",
        manualName: "",
        finalName: null,
        collision: false,
      },
    ]);
  });

  it("turns a rejected parse into an error row and continues the run", async () => {
    const rows = await parseAll(
      [entry("encrypted.pdf"), entry("good.pdf")],
      async (current) => {
        if (current.name === "encrypted.pdf") {
          throw new Error("encrypted PDF");
        }
        return { info: completeInfo(), proposed: "good.pdf" };
      },
      ignoreProgress
    );

    expect(rows).toEqual([
      {
        original: "encrypted.pdf",
        status: "error",
        proposed: null,
        manualName: "",
        finalName: null,
        collision: false,
        error: "encrypted PDF",
      },
      {
        original: "good.pdf",
        status: "ready",
        proposed: "good.pdf",
        manualName: "",
        finalName: null,
        collision: false,
      },
    ]);
  });

  it("marks empty extracted text as incomplete", async () => {
    const rows = await parseAll(
      [entry("scanned.pdf")],
      async () => {
        const info = extractInfo("");
        return { info, proposed: buildFilename(info) };
      },
      ignoreProgress
    );

    expect(rows[0].status).toBe("incomplete");
    expect(rows[0].proposed).toBeNull();
  });

  it("reports progress after every file through the total", async () => {
    const progress: [number, number][] = [];
    const entries = [entry("a.pdf"), entry("b.pdf"), entry("c.pdf")];

    await parseAll(
      entries,
      async () => ({ info: completeInfo(), proposed: "auto.pdf" }),
      (done, total) => progress.push([done, total])
    );

    expect(progress).toEqual([
      [1, 3],
      [2, 3],
      [3, 3],
    ]);
  });

  it("runs four parses concurrently and never exceeds that cap", async () => {
    const entries = Array.from({ length: 12 }, (_, index) =>
      entry(`receipt-${index}.pdf`)
    );
    let inFlight = 0;
    let maxInFlight = 0;

    const rows = await parseAll(
      entries,
      async () => {
        inFlight += 1;
        maxInFlight = Math.max(maxInFlight, inFlight);
        await new Promise<void>((resolve) => setTimeout(resolve, 5));
        inFlight -= 1;
        return { info: completeInfo(), proposed: "auto.pdf" };
      },
      ignoreProgress
    );

    expect(rows).toHaveLength(12);
    expect(maxInFlight).toBe(4);
  });
});

describe("defaultParseFile", () => {
  it("wires extracted PDF text through the engine", async () => {
    vi.mocked(extractPdfText).mockResolvedValue(BBVA_TEXT);

    const result = await defaultParseFile(entry("receipt.pdf"));

    expect(result.info.isComplete()).toBe(true);
    expect(result.proposed).toBe(
      "transfBBVA_to_Banamex_x128.00_May2026.pdf"
    );
  });
});

describe("row updates and planning", () => {
  it("deduplicates a manual name against an auto name without mutating rows", () => {
    const rows = [
      makeRow("auto.pdf", { proposed: "same.pdf" }),
      makeRow("manual.pdf", { status: "incomplete", proposed: null }),
    ];
    const snapshot = rows.map((row) => ({ ...row }));

    const updated = setManualName(rows, "manual.pdf", "same.pdf");
    const planned = computePlan(updated, new Set());

    expect(updated).not.toBe(rows);
    expect(rows).toEqual(snapshot);
    expect(updated[1].manualName).toBe("same.pdf");
    expect(planned.map((row) => row.finalName)).toEqual([
      "same.pdf",
      "same_2.pdf",
    ]);
    expect(planned[1].proposed).toBeNull();
    expect(updated[1].finalName).toBeNull();
  });

  it("sanitizes manual names before deduplication", () => {
    let rows = [
      makeRow("a.pdf", { status: "incomplete", proposed: null }),
      makeRow("b.pdf", { status: "incomplete", proposed: null }),
    ];
    rows = setManualName(rows, "a.pdf", "my/receipt.pdf");
    rows = setManualName(rows, "b.pdf", "my:receipt.pdf");

    const planned = computePlan(rows, new Set());

    expect(planned.map((row) => row.finalName)).toEqual([
      "my_receipt.pdf",
      "my_receipt_2.pdf",
    ]);
  });

  it("appends .pdf to a manual name at plan time and still dedups it", () => {
    let rows = [
      makeRow("auto.pdf", { proposed: "receipt.pdf" }),
      makeRow("manual.pdf", { status: "incomplete", proposed: null }),
    ];
    rows = setManualName(rows, "manual.pdf", "receipt");

    const planned = computePlan(rows, new Set());

    expect(planned[1].finalName).toBe("receipt_2.pdf");
    expect(planned[1].proposed).toBeNull();

    // A lone manual name without an extension keeps the extension in the plan.
    const standalone = computePlan(
      setManualName(
        [makeRow("solo.pdf", { status: "incomplete", proposed: null })],
        "solo.pdf",
        "receipt"
      ),
      new Set()
    );
    expect(standalone[0].finalName).toBe("receipt.pdf");

    // An already-suffixed name (any case) is left alone.
    const suffixed = computePlan(
      setManualName(
        [makeRow("solo.pdf", { status: "incomplete", proposed: null })],
        "solo.pdf",
        "RECEIPT.PDF"
      ),
      new Set()
    );
    expect(suffixed[0].finalName).toBe("RECEIPT.PDF");
  });

  it("treats a manual name that sanitizes to a dot component as no proposal", () => {
    const rows = [
      makeRow("dot.pdf", { status: "incomplete", proposed: null }),
      makeRow("dots.pdf", { status: "incomplete", proposed: null }),
    ];
    const planned = computePlan(
      setManualName(setManualName(rows, "dot.pdf", "."), "dots.pdf", ".."),
      new Set()
    );

    // "." → ".pdf" and ".." → "..pdf" would be degenerate/hidden targets.
    expect(planned[0].finalName).toBeNull();
    expect(planned[1].finalName).toBeNull();
  });

  it("excludes an auto row from the plan without mutating the input", () => {
    const rows = [makeRow("auto.pdf", { proposed: "auto.pdf" })];

    const excluded = toggleRow(rows, "auto.pdf");
    const planned = computePlan(excluded, new Set());

    expect(rows[0].status).toBe("ready");
    expect(excluded[0].status).toBe("excluded");
    expect(planned[0].finalName).toBeNull();
    expect(planned[0].collision).toBe(false);
  });

  it.each([
    { status: "ready", proposed: "auto.pdf", error: undefined },
    { status: "incomplete", proposed: null, error: undefined },
    { status: "error", proposed: null, error: "unreadable" },
  ] as const)("restores $status when an excluded row is included again", (fixture) => {
    const rows = [
      makeRow("row.pdf", {
        status: fixture.status,
        proposed: fixture.proposed,
        error: fixture.error,
      }),
    ];

    const excluded = toggleRow(rows, "row.pdf");
    const restored = toggleRow(excluded, "row.pdf");

    expect(excluded[0].status).toBe("excluded");
    expect(restored[0].status).toBe(fixture.status);
  });
});

describe("summary", () => {
  it("counts written and moved outcomes as renamed, and unattempted rows as skipped", () => {
    const rows = [
      makeRow("written.pdf", { finalName: "written-new.pdf" }),
      makeRow("moved.pdf", { finalName: "moved-new.pdf" }),
      makeRow("failed.pdf", { finalName: "failed-new.pdf" }),
      makeRow("excluded.pdf", { status: "excluded", finalName: null }),
      makeRow("blank.pdf", {
        status: "incomplete",
        proposed: null,
        finalName: null,
      }),
    ];
    const outcomes: RowOutcome[] = [
      { original: "written.pdf", status: "written" },
      { original: "moved.pdf", status: "moved" },
      { original: "failed.pdf", status: "failed", error: "quota exceeded" },
    ];

    expect(summary(rows, outcomes)).toBe("2 renamed, 2 skipped, 1 failed");
  });
});
