/**
 * agentkit-ui / layout / ResizableThreeColumnLayout — a persistent,
 * resizable 3-column shell.
 *
 * Domain-blind wrapper over react-resizable-panels: three columns with
 * drag-to-resize separators and optional localStorage persistence. The
 * consumer supplies the column content (including any headers/labels) and
 * the default/min sizes. `react-resizable-panels` is a peer dependency.
 */
import { type ReactNode } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";

export interface ResizableThreeColumnLayoutProps {
  left: ReactNode;
  center: ReactNode;
  right: ReactNode;
  /** Default column percentages [left, center, right]. Default [25, 45, 30]. */
  sizes?: [number, number, number];
  /** Min column percentages [left, center, right]. Default [15, 20, 20]. */
  minSizes?: [number, number, number];
  /** Extra classes on each column Panel (left, center, right). */
  panelClassNames?: [string, string, string];
  /** Separator class. Defaults to a divider line that highlights on hover. */
  separatorClassName?: string;
}

const DEFAULT_SEPARATOR =
  "w-1 bg-divider hover:bg-brand transition-colors cursor-col-resize";

export function ResizableThreeColumnLayout({
  left,
  center,
  right,
  sizes = [25, 45, 30],
  minSizes = [15, 20, 20],
  panelClassNames = ["", "", ""],
  separatorClassName = DEFAULT_SEPARATOR,
}: ResizableThreeColumnLayoutProps) {
  return (
    <div className="flex-1 flex overflow-hidden">
      <Group orientation="horizontal">
        <Panel defaultSize={sizes[0]} minSize={minSizes[0]} className={panelClassNames[0]}>
          {left}
        </Panel>
        <Separator className={separatorClassName} />
        <Panel defaultSize={sizes[1]} minSize={minSizes[1]} className={panelClassNames[1]}>
          {center}
        </Panel>
        <Separator className={separatorClassName} />
        <Panel defaultSize={sizes[2]} minSize={minSizes[2]} className={panelClassNames[2]}>
          {right}
        </Panel>
      </Group>
    </div>
  );
}
