/**
 * Tests for SelectorDropdown — generic dropdown used by model/backend/scenario selectors.
 *
 * Purpose:
 *   Verifies the generic dropdown renders items, highlights the active one,
 *   calls onSwitch when selection changes, and shows switching/error states.
 *   Replaces three inline selector sub-components in Header.tsx.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SelectorDropdown } from "@/components/layout/SelectorDropdown";

interface TestItem {
  id: string;
  label: string;
  is_active: boolean;
  disabled?: boolean;
}

const ITEMS: TestItem[] = [
  { id: "alpha", label: "Alpha", is_active: true },
  { id: "beta", label: "Beta", is_active: false },
  { id: "charlie", label: "Charlie", is_active: false, disabled: true },
];

describe("SelectorDropdown", () => {
  it("renders a label header", () => {
    render(
      <SelectorDropdown
        label="Model"
        items={ITEMS}
        activeId="alpha"
        getItemId={(i) => i.id}
        getItemLabel={(i) => i.label}
        onSwitch={vi.fn()}
        switching={false}
        error={null}
      />,
    );
    expect(screen.getByText("Model")).toBeTruthy();
  });

  it("renders a select element with all items as options", () => {
    render(
      <SelectorDropdown
        label="Backend"
        items={ITEMS}
        activeId="alpha"
        getItemId={(i) => i.id}
        getItemLabel={(i) => i.label}
        onSwitch={vi.fn()}
        switching={false}
        error={null}
      />,
    );
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    expect(select).toBeTruthy();
    expect(select.options).toHaveLength(3);
    expect(select.value).toBe("alpha");
  });

  it("calls onSwitch when selection changes", () => {
    const onSwitch = vi.fn();
    render(
      <SelectorDropdown
        label="Model"
        items={ITEMS}
        activeId="alpha"
        getItemId={(i) => i.id}
        getItemLabel={(i) => i.label}
        onSwitch={onSwitch}
        switching={false}
        error={null}
      />,
    );
    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "beta" } });
    expect(onSwitch).toHaveBeenCalledWith("beta");
  });

  it("does NOT call onSwitch when selecting the already-active item", () => {
    const onSwitch = vi.fn();
    render(
      <SelectorDropdown
        label="Model"
        items={ITEMS}
        activeId="alpha"
        getItemId={(i) => i.id}
        getItemLabel={(i) => i.label}
        onSwitch={onSwitch}
        switching={false}
        error={null}
      />,
    );
    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "alpha" } });
    expect(onSwitch).not.toHaveBeenCalled();
  });

  it("disables the select when switching is true", () => {
    render(
      <SelectorDropdown
        label="Model"
        items={ITEMS}
        activeId="alpha"
        getItemId={(i) => i.id}
        getItemLabel={(i) => i.label}
        onSwitch={vi.fn()}
        switching={true}
        error={null}
      />,
    );
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    expect(select.disabled).toBe(true);
  });

  it("shows switching indicator when switching", () => {
    render(
      <SelectorDropdown
        label="Model"
        items={ITEMS}
        activeId="alpha"
        getItemId={(i) => i.id}
        getItemLabel={(i) => i.label}
        onSwitch={vi.fn()}
        switching={true}
        error={null}
      />,
    );
    expect(screen.getByText(/switching|checking/i)).toBeTruthy();
  });

  it("shows error message when error is set", () => {
    render(
      <SelectorDropdown
        label="Model"
        items={ITEMS}
        activeId="alpha"
        getItemId={(i) => i.id}
        getItemLabel={(i) => i.label}
        onSwitch={vi.fn()}
        switching={false}
        error="Connection failed"
      />,
    );
    expect(screen.getByText("Connection failed")).toBeTruthy();
  });

  it("shows placeholder when items array is empty", () => {
    render(
      <SelectorDropdown
        label="Model"
        items={[]}
        activeId=""
        getItemId={(i: TestItem) => i.id}
        getItemLabel={(i: TestItem) => i.label}
        onSwitch={vi.fn()}
        switching={false}
        error={null}
      />,
    );
    /* When empty, should show active ID as a static badge */
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("applies getItemDisabled to mark options disabled", () => {
    render(
      <SelectorDropdown
        label="Backend"
        items={ITEMS}
        activeId="alpha"
        getItemId={(i) => i.id}
        getItemLabel={(i) => i.label}
        getItemDisabled={(i) => !!i.disabled}
        onSwitch={vi.fn()}
        switching={false}
        error={null}
      />,
    );
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    const charlieOpt = Array.from(select.options).find(
      (o) => o.value === "charlie",
    );
    expect(charlieOpt?.disabled).toBe(true);
  });
});
