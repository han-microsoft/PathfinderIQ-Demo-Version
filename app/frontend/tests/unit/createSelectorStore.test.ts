/**
 * Pre-refactor regression tests for createSelectorStore factory.
 *
 * Purpose:
 *   Tests for the generic selector store factory that will replace the
 *   three structurally-identical stores (scenarioStore, backendStore,
 *   modelStore) during Phase 2 of the refactor.
 *
 *   Written BEFORE the factory exists to define the expected contract.
 *   Once createSelectorStore.ts is implemented, update the import and
 *   these tests become the acceptance criteria.
 *
 * Contract:
 *   createSelectorStore<T>(config) returns a Zustand store with:
 *     - items: T[]
 *     - loading: boolean
 *     - error: string | null
 *     - switching: boolean
 *     - _activeOverride: string
 *     - fetchItems(): Promise<void>
 *     - switchItem(id: string): Promise<void>
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { createSelectorStore } from "@/stores/createSelectorStore";
import type { SelectorItem } from "@/stores/createSelectorStore";

/* ── Test fixtures ── */

interface TestItem extends SelectorItem {
  id: string;
  name: string;
  is_active: boolean;
}

const ITEMS: TestItem[] = [
  { id: "a", name: "Alpha", is_active: true },
  { id: "b", name: "Beta", is_active: false },
  { id: "c", name: "Charlie", is_active: false },
];

describe("createSelectorStore", () => {
  let mockFetch: ReturnType<typeof vi.fn>;
  let mockSelect: ReturnType<typeof vi.fn>;
  let mockOnSuccess: ReturnType<typeof vi.fn>;
  let useStore: ReturnType<typeof createSelectorStore<TestItem>>;

  beforeEach(() => {
    mockFetch = vi.fn().mockResolvedValue([...ITEMS]);
    mockSelect = vi.fn().mockResolvedValue({ status: "ok" });
    mockOnSuccess = vi.fn();
    useStore = createSelectorStore<TestItem>({
      name: "test",
      fetchFn: mockFetch,
      selectFn: mockSelect,
      getId: (item) => item.id,
      onSwitchSuccess: mockOnSuccess,
    });
  });

  it("initializes with empty state", () => {
    const state = useStore.getState();
    expect(state.items).toEqual([]);
    expect(state.loading).toBe(false);
    expect(state.error).toBeNull();
    expect(state.switching).toBe(false);
    expect(state._activeOverride).toBe("");
  });

  it("fetchItems populates items array", async () => {
    await useStore.getState().fetchItems();
    const state = useStore.getState();
    expect(state.items).toHaveLength(3);
    expect(state.loading).toBe(false);
    expect(mockFetch).toHaveBeenCalledOnce();
  });

  it("fetchItems sets error on failure", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Network error"));
    await useStore.getState().fetchItems();
    const state = useStore.getState();
    expect(state.error).toBe("Network error");
    expect(state.loading).toBe(false);
  });

  it("fetchItems skips if switching is in progress", async () => {
    useStore.setState({ switching: true });
    await useStore.getState().fetchItems();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("switchItem performs optimistic update", async () => {
    /* Pre-populate */
    useStore.setState({ items: [...ITEMS] });

    /* Start the switch but don't await yet */
    const switchPromise = useStore.getState().switchItem("b");

    /* During switch, the optimistic update should mark 'b' active */
    const mid = useStore.getState();
    expect(mid.switching).toBe(true);
    const activeItem = mid.items.find((i) => i.is_active);
    expect(activeItem?.id).toBe("b");

    await switchPromise;
  });

  it("switchItem calls selectFn then fetchFn to confirm", async () => {
    useStore.setState({ items: [...ITEMS] });
    await useStore.getState().switchItem("c");

    expect(mockSelect).toHaveBeenCalledWith("c");
    /* fetchFn called twice: once for initial populate isn't counted here,
       but switchItem calls it once to confirm. */
    expect(mockFetch).toHaveBeenCalledOnce();
    expect(useStore.getState().switching).toBe(false);
  });

  it("switchItem fires onSwitchSuccess callback", async () => {
    useStore.setState({ items: [...ITEMS] });
    await useStore.getState().switchItem("b");
    expect(mockOnSuccess).toHaveBeenCalledOnce();
  });

  it("switchItem rolls back on selectFn failure", async () => {
    const originalItems = [...ITEMS];
    useStore.setState({ items: originalItems });
    mockSelect.mockRejectedValueOnce(new Error("403 Forbidden"));

    await useStore.getState().switchItem("c");

    const state = useStore.getState();
    /* Items should be rolled back to original */
    expect(state.items).toEqual(originalItems);
    expect(state.error).toBe("403 Forbidden");
    expect(state.switching).toBe(false);
    expect(mockOnSuccess).not.toHaveBeenCalled();
  });

  it("switchItem is a no-op if already switching", async () => {
    useStore.setState({ items: [...ITEMS], switching: true });
    await useStore.getState().switchItem("b");
    expect(mockSelect).not.toHaveBeenCalled();
  });
});
