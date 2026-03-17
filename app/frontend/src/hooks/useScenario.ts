/**
 * @module useScenario
 *
 * Scenario metadata hook — fetches the active scenario’s identity and
 * configuration from `GET /api/scenario`.
 *
 * Returns a {@link ScenarioInfo} object containing:
 *   - `scenario_name`    — machine key (e.g. `'telecom-playground'`)
 *   - `display_name`     — human-readable title (e.g. `'Telecom Playground'`)
 *   - `description`      — brief scenario description
 *   - `domain`           — domain category (e.g. `'telecom'`)
 *   - `version`          — scenario version
 *   - `use_cases`        — list of supported use-case names
 *   - `example_questions` — pre-canned questions shown in the UI
 *
 * Fetches once on mount with cleanup via a `cancelled` flag to prevent
 * state updates after unmount.
 *
 * @returns `{ scenario, loading, error }`
 *
 * @dependents
 *   Used by {@link Header} (display_name),
 *   and potentially by ChatPanel for example questions.
 */
import { useState, useEffect, useCallback } from 'react';
import type { ScenarioDetail } from '../api/types';

/** @deprecated Use ScenarioDetail instead to avoid naming collision with api/types.ts ScenarioInfo */
export type ScenarioInfo = ScenarioDetail;

/**
 * Hook to load scenario metadata from the backend /api/scenario endpoint.
 * Fetches once on mount (single-scenario mode).
 */
export function useScenario() {
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchScenarioInfo = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { getScenarioDetail } = await import('../api/scenarioApi');
      const data = await getScenarioDetail();
      setScenario(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchScenarioInfo();
  }, [fetchScenarioInfo]);

  return { scenario, loading, error, refetch: fetchScenarioInfo };
}
