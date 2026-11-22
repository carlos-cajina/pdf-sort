/** Thin orchestrator that wires the per-bank parsers together. */

import { TransactionInfo, cleanText } from "./models";
import { PARSERS, parseDate, extractAmount } from "./parsers";
import { SANTANDER_CLABE_RE, BANK_SIGNATURES, BANK_ALIASES } from "./patterns";

/** Return [sourceBank, destinationBank] for a receipt's text. */
export function identifyBanks(text: string): [string, string] {
  const textUpper = text.toUpperCase();
  for (const parser of PARSERS) {
    const result = parser(text, textUpper);
    if (result !== null) {
      return result;
    }
  }
  return ["UNKNOWN", "UNKNOWN"];
}

/** Extract date, banks, and amount from receipt text. */
export function extractInfo(text: string): TransactionInfo {
  text = cleanText(text);
  const dt = parseDate(text);
  const [source, dest] = identifyBanks(text);
  const amount = extractAmount(text);
  return new TransactionInfo(dt, source, dest, amount);
}

/** Extract the identifier that follows "Número de cuenta CLABE ...".
 *
 * Returns null when the text contains no CLABE marker at all.
 */
export function extractClabe(text: string): string | null {
  const match = SANTANDER_CLABE_RE.exec(text);
  if (match === null) {
    return null;
  }
  const identifier = match[1]?.trim() ?? null;
  return identifier ?? null;
}

/** Resolve a bank from a CLABE identifier using Banxico bank codes.
 *
 * The leading digits of a Mexican CLABE point at a registered institution
 * (e.g. "50" -> "Santander"). Names are normalized through the engine's
 * alias table so callers receive the canonical bank name.
 */
export function lookupBankByClabe(clabe: string): string {
  const raw = clabe.replace(/ /g, "").replace(/-/g, "").split("-")[0]!.trim();
  const key = raw.toUpperCase();
  const santanderPrefixes =
    BANK_SIGNATURES["Santander"]?.clabe_prefixes ?? {};
  if (key in santanderPrefixes) {
    return santanderPrefixes[key]!;
  }
  if (key in BANK_ALIASES) {
    return BANK_ALIASES[key]!;
  }
  return "UNKNOWN";
}
