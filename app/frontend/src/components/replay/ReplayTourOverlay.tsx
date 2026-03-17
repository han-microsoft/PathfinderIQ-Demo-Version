import { useReplayStore } from "@/stores/replayStore";
import { useScenario } from "@/hooks/useScenario";
import { REPLAY_TOUR_STEPS } from "@/features/replay/tourSteps";
import { useTranslation } from "@/hooks/useTranslation";

export function ReplayTourOverlay() {
  const isPaused = useReplayStore((s) => s.isPaused);
  const stepIndex = useReplayStore((s) => s.tourStepIndex);
  const replayVariant = useReplayStore((s) => s.replayVariant);
  const { scenario } = useScenario();
  const { t } = useTranslation();
  const scenarioSteps = replayVariant === "detailed"
    ? (scenario?.replay_tour_detailed?.length ? scenario.replay_tour_detailed : scenario?.replay_tour)
    : scenario?.replay_tour;
  const steps = scenarioSteps?.length ? scenarioSteps : REPLAY_TOUR_STEPS;

  if (!isPaused || stepIndex < 0 || stepIndex >= steps.length) {
    return null;
  }

  const step = steps[stepIndex];

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/45 backdrop-blur-sm px-4">
      <div className="w-full max-w-xl rounded-xl border border-border bg-neutral-bg2 shadow-2xl p-6">
        <div className="mb-2 text-xs font-mono text-text-muted">
          {t("replay.stepOf", { current: stepIndex + 1, total: steps.length })}
        </div>
        <h2 className="text-2xl font-bold text-text-primary mb-3">
          {t(`replay.tour.${stepIndex}.title`) !== `replay.tour.${stepIndex}.title`
            ? t(`replay.tour.${stepIndex}.title`)
            : step.title}
        </h2>
        <p className="text-sm leading-relaxed text-text-secondary">
          {t(`replay.tour.${stepIndex}.body`) !== `replay.tour.${stepIndex}.body`
            ? t(`replay.tour.${stepIndex}.body`)
            : step.body}
        </p>
        {step.poweredBy && (
          <div className="mt-4 rounded-lg border border-border bg-neutral-bg3 p-3">
            <div className="flex items-center gap-3">
              <img src={step.poweredBy.logoSrc} alt="" className="h-8 w-8 shrink-0" />
              <p className="text-sm text-text-primary">
                <span className="font-semibold">{t("replay.poweredBy")} {step.poweredBy.label}</span>
              </p>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-text-secondary">
              {step.poweredBy.description}
            </p>
          </div>
        )}
        <div className="mt-6 flex justify-center">
          <button
            onClick={() => useReplayStore.getState().resumeTour()}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-hover"
          >
            {t(`replay.tour.${stepIndex}.cta`) !== `replay.tour.${stepIndex}.cta`
              ? t(`replay.tour.${stepIndex}.cta`)
              : step.cta}
          </button>
        </div>
        {step.agentImage && (
          <div className="mt-5 flex justify-center">
            <img
              src={step.agentImage}
              alt={step.title}
              className="max-h-72 w-auto object-contain drop-shadow-lg"
            />
          </div>
        )}
      </div>
    </div>
  );
}
