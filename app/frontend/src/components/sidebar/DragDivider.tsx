/** Shared drag divider for resizable panels. */
export function DragDivider({
  onMouseDown,
}: {
  onMouseDown: (e: React.MouseEvent) => void;
}) {
  return (
    <div
      className="h-2.5 shrink-0 cursor-row-resize bg-neutral-bg3 hover:bg-neutral-bg4 active:bg-brand/20 transition-colors flex items-center justify-center group/handle"
      onMouseDown={onMouseDown}
    >
      <div className="w-10 h-1 rounded-full bg-neutral-bg5 group-hover/handle:bg-brand/70 transition-colors" />
    </div>
  );
}
