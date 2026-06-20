/**
 * @module ScenarioSwitcher
 *
 * Runtime use-case swap selector.
 *
 * Renders the available scenario packs (GET /api/scenarios) through the shared
 * `SelectorDropdown` so the "Use case" selector matches the model/theme chrome
 * exactly (branded arrow, focus ring, switching indicator). Selection persists
 * and is sent as the `X-Scenario-Name` header on every API call; the backend
 * rebinds the agents/prompts/tools/datasource/topology for the chosen pack while
 * the core stays constant. Switching reloads the app so all scenario-scoped
 * state refetches cleanly.
 */
import { useEffect, useState } from 'react';
import { useScenarioStore, type ScenarioSummary } from '@/stores/scenarioStore';
import { fetchScenarios } from '@/api/scenarioApi';
import { SelectorDropdown } from './SelectorDropdown';

export function ScenarioSwitcher() {
  const scenarios = useScenarioStore((s) => s.scenarios);
  const selected = useScenarioStore((s) => s.selectedScenario);
  const loaded = useScenarioStore((s) => s.loaded);
  const setScenarios = useScenarioStore((s) => s.setScenarios);
  const selectScenario = useScenarioStore((s) => s.selectScenario);
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchScenarios()
      .then((cat) => {
        if (!cancelled) setScenarios(cat.scenarios, cat.active);
      })
      .catch(() => { /* leave catalog empty — operator default stays active */ });
    return () => { cancelled = true; };
  }, [setScenarios]);

  // Hide entirely until we know there is more than one pack to swap between.
  if (!loaded || scenarios.length < 2) return null;

  return (
    <SelectorDropdown<ScenarioSummary>
      label="Use case"
      items={scenarios}
      activeId={selected}
      getItemId={(s) => s.name}
      getItemLabel={(s) => s.display_name}
      onSwitch={(id) => { setSwitching(true); selectScenario(id); }}
      switching={switching}
      error={null}
    />
  );
}
