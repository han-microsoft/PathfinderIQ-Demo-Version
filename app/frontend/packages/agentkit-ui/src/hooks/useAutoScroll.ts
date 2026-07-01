/**
 * @module useAutoScroll
 *
 * Smart auto-scroll hook — manages scroll-to-bottom behaviour for the
 * chat message list during SSE streaming.
 *
 * Behaviour:
 *   - Scrolls to bottom when new content arrives (streaming tokens)
 *     and the user is already near the bottom (within `threshold` px).
 *   - Pauses auto-scrolling when the user manually scrolls up,
 *     preventing disruptive jumps during reading.
 *   - Resumes auto-scrolling when the user scrolls back to bottom.
 *   - Exposes a floating “scroll to bottom” button trigger.
 *
 * @param options.threshold — pixel distance from bottom to consider
 *   “at bottom” (default: 100)
 * @param options.deps — dependency array that triggers scroll checks
 *   (typically `[streamingContent]`)
 *
 * @returns `{ containerRef, handleScroll, scrollToBottom, showScrollButton }`
 *
 * @dependents
 *   Used by {@link MessageList} for its scrollable container.
 */

import { useCallback, useEffect, useRef, useState } from "react";

interface UseAutoScrollOptions {
  /** Distance from bottom (px) to consider "at bottom". Default: 100 */
  threshold?: number;
  /** Dependencies that trigger a scroll check. Typically [streamingContent]. */
  deps?: unknown[];
}

export function useAutoScroll({
  threshold = 100,
  deps = [],
}: UseAutoScrollOptions = {}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [showScrollButton, setShowScrollButton] = useState(false);

  // Check if the user is near the bottom
  const checkIsAtBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return true;
    const distanceFromBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight;
    return distanceFromBottom <= threshold;
  }, [threshold]);

  // Handle user scroll events
  const handleScroll = useCallback(() => {
    const atBottom = checkIsAtBottom();
    setIsAtBottom(atBottom);
    setShowScrollButton(!atBottom);
  }, [checkIsAtBottom]);

  // Auto-scroll when deps change (new tokens)
  useEffect(() => {
    if (isAtBottom && containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: "instant",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  // Scroll to bottom on demand
  const scrollToBottom = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: "smooth",
      });
      setIsAtBottom(true);
      setShowScrollButton(false);
    }
  }, []);

  return {
    containerRef,
    handleScroll,
    scrollToBottom,
    isAtBottom,
    showScrollButton,
  };
}
