/**
 * ChatSettings — popover for context depth control.
 *
 * Renders a small settings panel that lets the user adjust how many
 * past conversation turns are included in the LLM context window.
 * Value is stored in chatSettingsStore and passed in every ChatRequest.
 *
 * Key collaborators:
 *   - stores/chatSettingsStore.ts — contextDepth state
 *   - ChatInput.tsx — renders the cogwheel button that opens this popover
 */

import { useState } from "react";
import { useChatSettingsStore } from "@/stores/chatSettingsStore";
import { useTranslation } from "@/hooks/useTranslation";

interface ChatSettingsProps {
  onClose: () => void;
}

export function ChatSettings({ onClose }: ChatSettingsProps) {
  const contextDepth = useChatSettingsStore((s) => s.contextDepth);
  const setContextDepth = useChatSettingsStore((s) => s.setContextDepth);
  const [inputValue, setInputValue] = useState(
    contextDepth === null ? "" : String(contextDepth)
  );
  const { t } = useTranslation();

  const handleApply = () => {
    const parsed = parseInt(inputValue, 10);
    if (inputValue === "" || inputValue === "0") {
      setContextDepth(null); // unlimited
    } else if (!isNaN(parsed) && parsed > 0) {
      setContextDepth(parsed);
    }
    onClose();
  };

  return (
    <div className="absolute bottom-full left-0 mb-2 z-50 bg-neutral-bg2 border border-border rounded-lg shadow-xl p-3 w-56">
      <h4 className="text-xs font-semibold text-text-primary mb-2">{t("chat.settings.title")}</h4>
      <div className="space-y-2">
        <div>
          <label className="text-[10px] text-text-muted block mb-1">
            {t("chat.settings.contextTurns")}
          </label>
          <input
            type="number"
            min={0}
            max={50}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleApply()}
            className="w-full bg-neutral-bg1 border border-border rounded px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-brand"
            placeholder={t("chat.settings.unlimited")}
          />
        </div>
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="text-[10px] text-text-muted hover:text-text-secondary px-2 py-1"
          >
            {t("chat.settings.cancel")}
          </button>
          <button
            onClick={handleApply}
            className="text-[10px] text-brand hover:text-brand-hover px-2 py-1 font-medium"
          >
            {t("chat.settings.apply")}
          </button>
        </div>
      </div>
    </div>
  );
}
