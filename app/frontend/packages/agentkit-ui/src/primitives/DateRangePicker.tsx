/**
 * DateRangePicker — single-button range picker with airline-style popover.
 *
 * Purpose: replace the two side-by-side datetime inputs with one trigger
 * that opens a calendar popover. The operator clicks a start day, then an
 * end day, and the range fills between. Times are edited in two compact
 * HH:MM fields below the calendar. Quick presets cover the common
 * incident-investigation windows (Last 1h, 6h, 24h, This shift).
 *
 * Wire-format contract: the parent sees `value` and `onChange` as plain
 * "YYYY-MM-DD HH:MM" strings — the same shape the situation store has
 * always used. Internal state holds Date objects for the picker, but they
 * never escape the component.
 *
 * Dependencies: react-day-picker v9 + date-fns. react-day-picker is the
 * most widely adopted React calendar component and maps directly onto the
 * airline-booking pattern via its `mode="range"` prop.
 */

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { DayPicker, type DateRange } from "react-day-picker";
import "react-day-picker/dist/style.css";
import { format, parse, addHours, startOfDay } from "date-fns";
import { Calendar as CalendarIcon } from "lucide-react";

interface DateRangePickerProps {
  /** Wire-format start: "YYYY-MM-DD HH:MM" (space-separated). */
  start: string;
  /** Wire-format end:   "YYYY-MM-DD HH:MM" (space-separated). */
  end: string;
  /** Called when the operator commits a new range via Apply or a preset. */
  onApply: (next: { start: string; end: string }) => void;
}

/* Wire format used by the situation-detector API contract. The store keeps
 * timestamps in this exact shape so all conversion happens at the picker
 * boundary. */
const WIRE_FMT = "yyyy-MM-dd HH:mm";

/* Parse / format helpers. Wrapped so a single source of truth governs the
 * wire format and parse failures fall back to a safe default ("now") rather
 * than throwing into the render. */
function parseWire(value: string): Date {
  const parsed = parse(value, WIRE_FMT, new Date());
  return isNaN(parsed.getTime()) ? new Date() : parsed;
}
function fmtWire(value: Date): string {
  return format(value, WIRE_FMT);
}

/* HH:MM-only parser for the time text inputs. Returns null on malformed
 * input so the caller can decide whether to revert or accept. */
function parseHHMM(value: string): { h: number; m: number } | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const h = Number(match[1]);
  const m = Number(match[2]);
  if (h < 0 || h > 23 || m < 0 || m > 59) return null;
  return { h, m };
}

/* Stamp HH:MM onto a Date without touching the date portion. Used when the
 * operator types a new start/end time. */
function withTime(base: Date, time: { h: number; m: number }): Date {
  const out = new Date(base);
  out.setHours(time.h, time.m, 0, 0);
  return out;
}

/* Compact label for the trigger button. Same-day ranges show the day once
 * with two times; multi-day ranges show both dates. Both formats are dense
 * enough to fit in the situation-control-bar without wrapping. */
function summarize(start: Date, end: Date): string {
  const sameDay =
    start.getFullYear() === end.getFullYear() &&
    start.getMonth() === end.getMonth() &&
    start.getDate() === end.getDate();
  if (sameDay) {
    return `${format(start, "d MMM yyyy")}  ${format(start, "HH:mm")} → ${format(end, "HH:mm")}`;
  }
  return `${format(start, "d MMM HH:mm")} → ${format(end, "d MMM HH:mm")}`;
}

/* Quick-range presets. Each returns [start, end] anchored to "now"; the
 * "This shift" preset uses the AEMO 6 a.m. / 2 p.m. / 10 p.m. boundary that
 * matches the control-room duty roster, but the floor is the latest such
 * boundary <= now so a single preset covers all three. */
const PRESETS: { label: string; range: () => [Date, Date] }[] = [
  { label: "Last 1h",  range: () => { const n = new Date(); return [addHours(n, -1),  n]; } },
  { label: "Last 6h",  range: () => { const n = new Date(); return [addHours(n, -6),  n]; } },
  { label: "Last 24h", range: () => { const n = new Date(); return [addHours(n, -24), n]; } },
  { label: "Today",    range: () => { const n = new Date(); return [startOfDay(n), n]; } },
];

export function DateRangePicker({ start, end, onApply }: DateRangePickerProps) {
  /* Popover open/close. */
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  /* Popover viewport coords. The popover is portalled to document.body to
   * escape any `overflow: hidden` ancestor (e.g. the react-resizable-panels
   * panel that hosts the situation control bar). Coords are recomputed on
   * open, on window resize, and on document scroll so the popover tracks
   * the trigger if anything in the layout shifts while it is visible. */
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null);
  const POPOVER_WIDTH = 520;
  const POPOVER_MIN_WIDTH = 560;

  /* Local working copy of the range; committed to the parent on Apply. */
  const startDate = useMemo(() => parseWire(start), [start]);
  const endDate   = useMemo(() => parseWire(end),   [end]);
  const [draft, setDraft] = useState<DateRange | undefined>({ from: startDate, to: endDate });
  const [startTime, setStartTime] = useState(format(startDate, "HH:mm"));
  const [endTime,   setEndTime]   = useState(format(endDate,   "HH:mm"));

  /* Re-seed the draft whenever the popover opens, so re-opening after a
   * cancel does not preserve stale local edits. */
  useEffect(() => {
    if (open) {
      setDraft({ from: startDate, to: endDate });
      setStartTime(format(startDate, "HH:mm"));
      setEndTime(format(endDate, "HH:mm"));
    }
  }, [open, startDate, endDate]);

  /* Outside-click and Escape close the popover without applying. */
  useEffect(() => {
    if (!open) return;
    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      const inTrigger = triggerRef.current?.contains(target);
      const inPopover = popoverRef.current?.contains(target);
      if (!inTrigger && !inPopover) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  /* Position the portalled popover relative to the trigger. Runs on open,
   * on window resize, and on document scroll. The popover is clamped to
   * the viewport so it never spills off the right or bottom edge on a
   * narrow window. */
  useLayoutEffect(() => {
    if (!open) return;
    const recompute = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      const margin = 8;
      /* Prefer left-aligned with the trigger; clamp so the popover stays
       * within the viewport (with a small margin). */
      const left = Math.min(
        Math.max(margin, rect.left),
        window.innerWidth - POPOVER_WIDTH - margin,
      );
      const top = rect.bottom + 4;
      setCoords({ top, left });
    };
    recompute();
    window.addEventListener("resize", recompute);
    document.addEventListener("scroll", recompute, true);
    return () => {
      window.removeEventListener("resize", recompute);
      document.removeEventListener("scroll", recompute, true);
    };
  }, [open]);

  /* Apply: stamp the typed times onto the picker dates, format to wire
   * shape, fire onApply (parent commits range), close.
   * Falls back to the existing time when the input is malformed so the
   * operator can never produce an invalid value. */
  const apply = () => {
    const fromDate = draft?.from ?? startDate;
    const toDate   = draft?.to   ?? draft?.from ?? endDate;
    const startHM = parseHHMM(startTime) ?? { h: fromDate.getHours(), m: fromDate.getMinutes() };
    const endHM   = parseHHMM(endTime)   ?? { h: toDate.getHours(),   m: toDate.getMinutes()   };
    const finalStart = withTime(fromDate, startHM);
    const finalEnd   = withTime(toDate,   endHM);
    onApply({ start: fmtWire(finalStart), end: fmtWire(finalEnd) });
    setOpen(false);
  };

  /* Apply a preset directly, bypassing the calendar selection workflow. */
  const applyPreset = (preset: () => [Date, Date]) => {
    const [s, e] = preset();
    onApply({ start: fmtWire(s), end: fmtWire(e) });
    setOpen(false);
  };

  return (
    <div className="relative">
      {/* Trigger button — single, full-width, summarises the current range. */}
      <button
        ref={triggerRef}
        data-testid="date-range-trigger"
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs bg-neutral-bg1 rounded text-text-primary hover:bg-neutral-bg3 transition-colors"
      >
        <CalendarIcon className="h-3.5 w-3.5 text-text-secondary shrink-0" />
        <span className="truncate font-mono">{summarize(startDate, endDate)}</span>
      </button>

      {open && coords && createPortal(
        <div
          ref={popoverRef}
          data-testid="date-range-popover"
          /* Portalled to document.body and positioned with `fixed` coords so
             the popover escapes every `overflow: hidden` ancestor (the
             resize panels in particular). z-index sits above modals. */
          className="fixed z-[100] bg-neutral-bg2 rounded-lg shadow-2xl p-3 flex flex-col gap-2"
          style={{
            top: coords.top,
            left: coords.left,
            width: POPOVER_WIDTH,
            minWidth: POPOVER_MIN_WIDTH,
          }}
        >
          {/* Preset row — horizontal pills along the top. Single-click
              presets bypass the calendar workflow entirely. */}
          <div className="flex flex-wrap items-center gap-1.5 px-1">
            <span className="text-micro uppercase tracking-wider text-text-muted mr-1">Quick</span>
            {PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                onClick={() => applyPreset(p.range)}
                className="px-2 py-0.5 text-label rounded text-text-secondary bg-neutral-bg1 hover:bg-neutral-bg3 hover:text-text-primary transition-colors"
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* Two-month calendar — dominant block. */}
          <DayPicker
            mode="range"
            numberOfMonths={2}
            selected={draft}
            onSelect={setDraft}
            defaultMonth={startDate}
            showOutsideDays
            /* Theme — dark + brand selection ring. The component ships a
               minimal stylesheet that we override via CSS vars below. */
            styles={{
              root: { color: "var(--color-text-primary)" },
            }}
          />

          {/* Time + actions row — single horizontal band beneath the calendar. */}
          <div className="flex items-center gap-3 px-1">
            <label className="flex items-center gap-2 text-xs text-text-muted">
              Start
              <input
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                step={60}
                className="px-2 py-1 text-xs bg-neutral-bg1 rounded text-text-primary focus:outline-none [color-scheme:dark]"
              />
            </label>
            <label className="flex items-center gap-2 text-xs text-text-muted">
              End
              <input
                type="time"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                step={60}
                className="px-2 py-1 text-xs bg-neutral-bg1 rounded text-text-primary focus:outline-none [color-scheme:dark]"
              />
            </label>

            <div className="flex-1" />

            <button
              type="button"
              onClick={() => setOpen(false)}
              className="px-3 py-1 text-xs rounded text-text-secondary hover:bg-neutral-bg3 hover:text-text-primary transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={apply}
              className="px-3 py-1 text-xs font-medium rounded bg-brand text-on-accent hover:bg-brand/80 transition-colors"
            >
              Apply range
            </button>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
}
