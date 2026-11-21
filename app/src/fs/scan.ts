export type ScanEntry = {
  name: string;
  file: File;
  handle: FileSystemFileHandle;
};

export async function scanInputFolder(
  dir: FileSystemDirectoryHandle
): Promise<ScanEntry[]> {
  const fileHandles: FileSystemFileHandle[] = [];

  for await (const handle of dir.values()) {
    if (handle.kind !== "file") {
      continue;
    }

    if (!isPdfName(handle.name)) {
      continue;
    }

    fileHandles.push(handle as FileSystemFileHandle);
  }

  // Match the Python CLI, which iterates sorted(input_dir.iterdir()): the
  // in-run dedup suffix assignment depends on row order, so the scan order
  // must be deterministic and identical to the reference implementation.
  // Python compares code points; UTF-16 string comparison diverges from that
  // for astral characters (e.g. emoji) against U+E000–U+FFFF.
  fileHandles.sort(compareNamesByCodePoint);

  // Resolve the Files concurrently — each getFile is independent — while
  // keeping the sorted scan order. A failing getFile still aborts the scan
  // loudly rather than silently dropping an entry.
  const files = await Promise.all(fileHandles.map((fileHandle) => fileHandle.getFile()));
  return fileHandles.map((fileHandle, index) => {
    const file = files[index];
    if (file === undefined) {
      throw new Error(`getFile resolved out of order for ${fileHandle.name}`);
    }
    return { name: fileHandle.name, file, handle: fileHandle };
  });
}

/**
 * Match the Python CLI's `p.suffix.lower() == ".pdf"`: a name ending in
 * ".pdf" case-insensitively, with a non-empty stem. A bare dotfile like
 * ".pdf" has no suffix in pathlib and is skipped, unlike a case-insensitive
 * regex which would include it.
 */
function isPdfName(name: string): boolean {
  return name.length > 4 && name.toLowerCase().endsWith(".pdf");
}

/** Code-point ordering, byte-identical to Python's default str comparison. */
function compareNamesByCodePoint(
  a: FileSystemFileHandle,
  b: FileSystemFileHandle
): number {
  const aCp = Array.from(a.name);
  const bCp = Array.from(b.name);
  const shared = Math.min(aCp.length, bCp.length);
  for (let i = 0; i < shared; i++) {
    const diff = aCp[i]!.codePointAt(0)! - bCp[i]!.codePointAt(0)!;
    if (diff !== 0) {
      return diff;
    }
  }
  return aCp.length - bCp.length;
}
