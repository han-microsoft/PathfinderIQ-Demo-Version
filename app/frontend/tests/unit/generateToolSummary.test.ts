/**
 * Pre-refactor regression tests for generateToolSummary().
 *
 * Purpose:
 *   Pins the current behavior of generateToolSummary() before it is
 *   extracted from chatStore.ts into features/chat/partUtils.ts.
 *   After extraction, these tests import from the new location and
 *   must still pass unchanged.
 *
 * The function is currently private inside chatStore.ts, so we
 * duplicate it here identically for testing. During refactor Step 2.3,
 *   1. Move the function to features/chat/partUtils.ts (export it).
 *   2. Update this test to import from the new module.
 *   3. Delete the inline copy below.
 *   4. All tests must still pass.
 */
import { describe, it, expect } from "vitest";
import { generateToolSummary } from "@/features/chat/partUtils";

describe("generateToolSummary", () => {
  it("returns row count for columns+data tabular response", () => {
    const result = JSON.stringify({ columns: ["a", "b"], data: [1, 2, 3] });
    expect(generateToolSummary("query_graph", result)).toBe("✓ 3 rows");
  });

  it("returns row count for columns+rows tabular response", () => {
    const result = JSON.stringify({ columns: ["a"], rows: [{ a: 1 }, { a: 2 }] });
    expect(generateToolSummary("query_telemetry", result)).toBe("✓ 2 rows");
  });

  it("returns result count for results array", () => {
    const result = JSON.stringify({ results: ["a", "b"], count: 5 });
    expect(generateToolSummary("search_runbooks", result)).toBe("✓ 5 results");
  });

  it("returns results.length when count absent", () => {
    const result = JSON.stringify({ results: ["a", "b"] });
    expect(generateToolSummary("search_tickets", result)).toBe("✓ 2 results");
  });

  it("returns dispatch_id for dispatch responses", () => {
    const result = JSON.stringify({ dispatch_id: "D-12345" });
    expect(generateToolSummary("dispatch_field_engineer", result)).toBe("✓ D-12345");
  });

  it("returns error detail for error responses", () => {
    const result = JSON.stringify({ error: true, detail: "Permission denied" });
    expect(generateToolSummary("query_graph", result)).toBe("✗ Permission denied");
  });

  it("truncates long error details to 80 chars", () => {
    const longDetail = "A".repeat(100);
    const result = JSON.stringify({ error: true, detail: longDetail });
    expect(generateToolSummary("query_graph", result)).toBe(`✗ ${"A".repeat(80)}`);
  });

  it("handles non-string error detail", () => {
    const result = JSON.stringify({ error: true, detail: { nested: true } });
    expect(generateToolSummary("query_graph", result)).toBe("✗ Error");
  });

  it("returns ✓ Complete for unrecognized JSON structures", () => {
    const result = JSON.stringify({ status: "ok", value: 42 });
    expect(generateToolSummary("unknown_tool", result)).toBe("✓ Complete");
  });

  it("returns truncated string for non-JSON result over 60 chars", () => {
    const result = "A".repeat(80);
    const summary = generateToolSummary("unknown_tool", result);
    expect(summary).toBe("A".repeat(60) + "…");
  });

  it("returns raw string for non-JSON result under 60 chars", () => {
    const result = "Short plain text";
    expect(generateToolSummary("unknown_tool", result)).toBe("Short plain text");
  });

  it("handles error:true with null detail (falls back to 'Error')", () => {
    const result = JSON.stringify({ error: true });
    expect(generateToolSummary("query_graph", result)).toBe("✗ Error");
  });
});
