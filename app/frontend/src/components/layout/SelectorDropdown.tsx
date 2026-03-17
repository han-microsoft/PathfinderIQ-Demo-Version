/**
 * SelectorDropdown — generic reusable dropdown for scenario/backend/model selection.
 *
 * Module role:
 *   Replaces three near-identical inline sub-components (HeaderModelSelector,
 *   HeaderBackendSelector, HeaderScenarioSelector) with a single generic
 *   component. Renders a labeled <select> element with switching/error states.
 *
 * Props are fully generic over the item type T — callers provide accessor
 * functions (getItemId, getItemLabel, etc.) rather than knowing the shape.
 *
 * Key collaborators:
 *   - components/layout/Header.tsx (NavSidebar) — renders instances
 *   - stores/*Store.ts — provides items/switching/error state
 *
 * Dependents:
 *   Rendered by Header.tsx for model, backend, and scenario selectors.
 */

/** Shared Tailwind classes for the dropdown select element. */
const SELECT_CLASSES = [
  "w-full rounded-md px-2 py-1.5 text-sm font-semibold",
  "bg-neutral-bg3 border border-border text-brand",
  "focus:outline-none focus:ring-1 focus:ring-brand/50",
  "disabled:opacity-50 disabled:cursor-wait",
  "cursor-pointer appearance-none",
  "bg-[length:1.25rem] bg-[right_0.25rem_center] bg-no-repeat",
  "bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2020%2020%22%20fill%3D%22%2375b5aa%22%3E%3Cpath%20d%3D%22M6%208l4%204%204-4%22%2F%3E%3C%2Fsvg%3E')]",
  "pr-7",
].join(" ");

/** Props for the generic selector dropdown. */
export interface SelectorDropdownProps<T> {
  /** Section label rendered above the dropdown (e.g. "Model"). */
  label: string;
  /** Array of items to render as options. */
  items: T[];
  /** ID of the currently active item. */
  activeId: string;
  /** Extract the unique ID from an item. */
  getItemId: (item: T) => string;
  /** Extract the display label from an item. */
  getItemLabel: (item: T) => string;
  /** Optional: determine whether an option should be disabled. */
  getItemDisabled?: (item: T) => boolean;
  /** Optional: suffix text for an option (e.g. " (not provisioned)"). */
  getItemSuffix?: (item: T) => string;
  /** Called when the user selects a different item. */
  onSwitch: (id: string) => void;
  /** True while a switch is in progress (disables the select). */
  switching: boolean;
  /** Error message from the last failed fetch or switch. */
  error: string | null;
}

/**
 * Generic selector dropdown with label, switching indicator, and error display.
 *
 * When items is empty, shows the activeId as a static text badge instead
 * of a <select> element.
 */
export function SelectorDropdown<T>({
  label,
  items,
  activeId,
  getItemId,
  getItemLabel,
  getItemDisabled,
  getItemSuffix,
  onSwitch,
  switching,
  error,
}: SelectorDropdownProps<T>) {
  /* Empty state — show static badge */
  if (items.length === 0) {
    return (
      <div className="text-xs text-text-muted">
        <span className="text-[10px] uppercase tracking-widest font-semibold block mb-1">
          {label}
        </span>
        <span className="text-brand font-semibold">{activeId || "—"}</span>
      </div>
    );
  }

  return (
    <div>
      <span className="text-[10px] uppercase tracking-widest font-semibold text-text-muted block mb-1">
        {label}
      </span>
      <select
        value={activeId}
        onChange={(e) => {
          if (e.target.value !== activeId) onSwitch(e.target.value);
        }}
        disabled={switching}
        className={SELECT_CLASSES}
        title={`Select ${label.toLowerCase()}`}
        role="combobox"
      >
        {items.map((item) => {
          const id = getItemId(item);
          const itemLabel = getItemLabel(item);
          const disabled = getItemDisabled?.(item) ?? false;
          const suffix = getItemSuffix?.(item) ?? "";
          return (
            <option key={id} value={id} disabled={disabled}>
              {itemLabel}{suffix}
            </option>
          );
        })}
      </select>
      {switching && (
        <span className="text-[10px] text-status-warning animate-pulse">
          Switching…
        </span>
      )}
      {error && (
        <span
          className="text-[10px] text-status-error truncate"
          title={error}
        >
          {error}
        </span>
      )}
    </div>
  );
}
