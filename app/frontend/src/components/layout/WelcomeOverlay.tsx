/**
 * WelcomeOverlay — initialization splash screen shown on first visit.
 *
 * Displays staggered fade-in text and real-time initialization status.
 * Shows only when localStorage flag "welcome-dismissed" is absent.
 * The "Proceed" button appears when all init steps are complete.
 * An orange "Close Welcome Screen" button is always visible top-right.
 */

import { useState, useEffect } from "react";
import { useReadinessStore, type InitStatus } from "@/stores/readinessStore";
import { useReplayStore } from "@/stores/replayStore";
import { runReplay } from "@/features/replay/replayEngine";

const STORAGE_KEY = "welcome-dismissed";

/** Status indicator icon + color for each init state. */
function StatusBadge({ status }: { status: InitStatus }) {
  switch (status) {
    case "pending":
      return <span className="text-text-muted">—</span>;
    case "loading":
      return <span className="text-status-warning animate-pulse">⏳ In Progress</span>;
    case "complete":
      return <span className="text-status-success">✓ Complete</span>;
    case "failed":
      return <span className="text-status-error">✗ Failed</span>;
  }
}

export function WelcomeOverlay() {
  const [phase, setPhase] = useState<"intro" | "init">("intro");
  const [visible, setVisible] = useState(true);
  const [fadeOut, setFadeOut] = useState(false);

  const sessions = useReadinessStore((s) => s.sessions);
  const serviceHealth = useReadinessStore((s) => s.serviceHealth);
  const graphTopology = useReadinessStore((s) => s.graphTopology);
  const agents = useReadinessStore((s) => s.agents);
  const iface = useReadinessStore((s) => s.interface);
  const allReady = useReadinessStore((s) => s.allReady);

  // Staggered fade-in animation triggers
  const [showTitle, setShowTitle] = useState(false);
  const [showSubtitle, setShowSubtitle] = useState(false);
  const [showStatus, setShowStatus] = useState(false);

  useEffect(() => {
    if (!visible || phase !== "init") return;
    setShowTitle(false);
    setShowSubtitle(false);
    setShowStatus(false);
    const t1 = setTimeout(() => setShowTitle(true), 200);
    const t2 = setTimeout(() => setShowSubtitle(true), 600);
    const t3 = setTimeout(() => setShowStatus(true), 1000);
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3); };
  }, [phase, visible]);

  const handleShowInit = () => {
    setPhase("init");
  };

  const handleDismiss = () => {
    setFadeOut(true);
    try { localStorage.setItem(STORAGE_KEY, "1"); } catch {}
    setTimeout(() => {
      setVisible(false);
      /* Show the "Play Demo Flow" button hint after the overlay closes. */
      useReplayStore.setState({ showDemoHint: true });
    }, 400);
  };

  const handleWatchDemo = () => {
    // Dismiss overlay, then start replay
    handleDismiss();
    setTimeout(() => {
      useReplayStore.getState().startReplay("detailed");
      runReplay();
    }, 500);
  };

  if (!visible) return null;

  const statusItems: { label: string; status: InitStatus }[] = [
    { label: "Sessions Retrieved", status: sessions },
    { label: "Service Health", status: serviceHealth },
    { label: "Graph Topology", status: graphTopology },
    { label: "Agents Initialized", status: agents },
    { label: "Interface Ready", status: iface },
  ];

  return (
    <div
      className={`fixed inset-0 z-[60] flex flex-col items-center justify-center bg-neutral-bg1/95 backdrop-blur-md transition-opacity duration-400 ${
        fadeOut ? "opacity-0" : "opacity-100"
      }`}
    >
      {phase === "intro" ? (
        <>
          <button
            onClick={handleShowInit}
            className="absolute top-6 right-8 px-5 py-2.5 rounded-lg bg-status-warning hover:bg-status-warning text-black font-bold text-sm transition-colors shadow-lg"
          >
            ✕
          </button>

          <div className="h-full w-full overflow-y-auto">
            <div className="mx-auto flex max-w-5xl flex-col gap-6 px-8 py-10">
              <div className="flex flex-col gap-4">
                <h1 className="text-5xl font-bold text-text-primary flex items-center gap-4">
                  <img src="/images/pathfinderIQ_logo_notext.png" alt="" className="h-14 w-auto" />
                  Pathfinder IQ
                </h1>

                <section className="rounded-xl border border-border-default bg-neutral-bg2 p-5">
                  <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">Billboard Statement</h2>
                  <p className="text-lg font-medium leading-relaxed text-text-primary">
                    PathfinderIQ brings the 3IQ narrative to life&mdash;early and evolving&mdash;turning Foundry IQ, Fabric IQ*, and WorkIQ into an end&#8209;to&#8209;end customer intelligence system landing with customers and showing measurable impact.
                  </p>
                  <p className="mt-3 text-xs leading-relaxed text-text-muted">
                    * Fabric IQ represents the default intelligence layer, providing graph traversal and telemetry correlation across operational scenarios.
                  </p>
                  <p className="mt-2 text-xs font-semibold leading-relaxed text-text-muted">
                    Built by Asia AI Apps GBB to fulfil pressing needs from the Telecom, Energy, and Airline industries, among others.
                  </p>

                </section>
              </div>

              <section className="rounded-xl border border-border-default bg-neutral-bg2 p-6">
                <h2 className="mb-3 text-2xl font-semibold text-text-primary">Problem Statement</h2>
                <div className="space-y-3 text-base leading-relaxed text-text-secondary">
                  <p>
                    Organizations have now realized the potential of multiagent systems. Digital workers represent the opportunity to automate business processes at a scale that was not previously possible.
                  </p>
                  <p>
                    Advances in reasoning models have given agents incredible problem solving capabilities. Vector search (thanks to Fabric IQ) has matured significantly, allowing agents to retrieve <em>unstructured</em> data from manuals, procedures or product documents.
                  </p>
                  <p>
                    MCPs and function calling have allowed agents to use structured data, and run basic SQL queries on tables to retrieve logs, product inventories or customer purchasing history.
                  </p>
                  <p>
                    However one key piece has been missing- in a large organization, with data tables spanning across products databases, customers databases, assets and inventories, agents have no way of understanding the <em>relationship</em> between this data.
                  </p>
                </div>
                <img src="/images/problem_slide.png" alt="Problem statement diagram" className="mt-4 w-full rounded-lg border border-border" />
              </section>

              <section className="rounded-xl border border-border-default bg-neutral-bg2 p-6">
                <h2 className="mb-3 text-2xl font-semibold text-text-primary">Making It Real</h2>
                <p className="text-base leading-relaxed text-text-secondary">
                  Telecom, airlines, and energy companies all manage complex systems as critical infrastructure &mdash; vulnerable to cascading failures where consequences are extreme and rapid recovery is non-negotiable.
                </p>

                <div className="mt-4 space-y-4">
                  <div className="rounded-lg border border-border bg-neutral-bg3 p-4">
                    <p className="text-sm font-semibold text-text-primary">&#x1F4E1; Telecom</p>
                    <p className="mt-1 text-sm leading-relaxed text-text-secondary">
                      A single fibre cut cascades into thousands of service failures across VPN, broadband, and mobile &mdash; each requiring coordinated diagnosis across topology, telemetry, runbooks, and field dispatch. Nortel&apos;s network operations struggled with exactly this kind of cross-system complexity at scale. SLA penalties alone can exceed <strong>$75,000/hour</strong> per enterprise customer.
                    </p>
                  </div>

                  <div className="rounded-lg border border-border bg-neutral-bg3 p-4">
                    <p className="text-sm font-semibold text-text-primary">&#x2708;&#xfe0f; Airlines</p>
                    <p className="mt-1 text-sm leading-relaxed text-text-secondary">
                      Severe weather triggers cascading rebooking across crew rosters, gate assignments, connecting flights, and passenger entitlements &mdash; a combinatorial problem that grows exponentially with each cancellation. Pan Am and Ansett Australia both faced operational meltdowns where inability to reason about crew-aircraft-route dependencies in real time contributed to their collapse. Southwest Airlines&apos; 2022 crisis cancelled <strong>16,900 flights in 10 days</strong>, costing <strong>$800M</strong>.
                    </p>
                  </div>

                  <div className="rounded-lg border border-border bg-neutral-bg3 p-4">
                    <p className="text-sm font-semibold text-text-primary">&#x26A1; Energy</p>
                    <p className="mt-1 text-sm leading-relaxed text-text-secondary">
                      A transmission line fault requires tracing through substations, transformer ratings, protection relay zones, and generation dispatch &mdash; while load must be rebalanced in real time to prevent wider blackout. Enron&apos;s trading floor exposed how poor systems understanding led to catastrophic grid manipulation. The 2021 Texas grid crisis left <strong>4.5M homes without power for days</strong> &mdash; faster cross-system reasoning could have prevented cascading transformer failures.
                    </p>
                  </div>
                </div>

                <p className="mt-4 text-base font-medium leading-relaxed text-text-primary">
                  These are not standard agent problems. RAG retrieves documents. Tool-calling queries tables. But diagnosing a fibre cut requires traversing a topology graph, checking telemetry, searching runbooks, and dispatching a field engineer with GPS coordinates &mdash; all within minutes, all interdependent. <strong>Agentic graphs provide the systems-level reasoning that critical infrastructure demands.</strong>
                </p>
                <img src="/images/solution_slide.png" alt="Solution overview" className="mt-4 w-full rounded-lg border border-border" />
              </section>

              <section className="rounded-xl border border-border-default bg-neutral-bg2 p-6">
                <h2 className="mb-3 text-2xl font-semibold text-text-primary">Opportunity</h2>
                <div className="space-y-3 text-base leading-relaxed text-text-secondary">
                  <p>
                    By building a Knowledge Layer, organizations will be able to empower their agents to truly understand how data relates to other data. Fabric Ontology provides a graph which captures these relationships.
                  </p>
                  <p>
                    The nodes on the graph represent different entities, whether it&apos;s a customer, an asset like a power transformer or telecom tower, or a product. Within each of these nodes, there might be multiple data tables, each with their own schema, columns and headings.
                  </p>
                  <p>
                    The edges of the graph show how these different data sources relate to each other. Now rather than blindly trying to retrieve data through RAG, your digital workers can intelligently coordinate, traverse your organization efficiently, find the right data with confidence, and use RAG where it shines- over unstructured data such as manuals and PDFs.
                  </p>
                </div>
              </section>

              <section className="rounded-xl border border-border-default bg-neutral-bg2 p-6">
                <h2 className="mb-3 text-2xl font-semibold text-text-primary">Demo overview</h2>
                <p className="text-base leading-relaxed text-text-secondary">
                  In this demo, we showcase how Fabric IQ and Foundry IQ come together to empower multi-agent systems.
                </p>
                <p className="mt-3 text-base leading-relaxed text-text-secondary">
                  Across a range of scenarios, you will see how agents (built with Microsoft Foundry) can take a complex problem, decompose it into steps, traverse the graph (the ontology provided by Fabric), retrieve unstructured information using Foundry IQ, and effectively solve a problem.
                </p>
                <img src="/images/investigation_slide.png" alt="Investigation flow" className="mt-4 w-full rounded-lg border border-border" />
              </section>

              <section className="rounded-xl border border-border-default bg-neutral-bg2 p-6">
                <h2 className="mb-3 text-2xl font-semibold text-text-primary">Video to share with customers</h2>
                <p className="mb-4 break-all font-mono text-sm text-text-secondary">Send this URL to your customers: https://vimeo.com/manage/videos/1170548213</p>
                <div className="space-y-4">
                  <div className="relative w-full overflow-hidden rounded-lg border border-border-default bg-neutral-bg3" style={{ paddingTop: "56.25%" }}>
                    <iframe
                      src="https://player.vimeo.com/video/1170548213"
                      title="Pathfinder IQ Overview"
                      className="absolute inset-0 h-full w-full"
                      allow="autoplay; fullscreen; picture-in-picture"
                      allowFullScreen
                    />
                  </div>
                  <p className="break-all font-mono text-sm text-text-secondary">https://vimeo.com/manage/videos/1170548213</p>
                </div>
              </section>

              <section className="rounded-xl border border-border-default bg-neutral-bg2 p-6">
                <h2 className="mb-3 text-2xl font-semibold text-text-primary">How to run this demo</h2>
                <div className="space-y-4">
                  <div className="relative w-full overflow-hidden rounded-lg border border-border-default bg-neutral-bg3" style={{ paddingTop: "56.25%" }}>
                    <iframe
                      src="https://player.vimeo.com/video/1170548252"
                      title="How to run this demo"
                      className="absolute inset-0 h-full w-full"
                      allow="autoplay; fullscreen; picture-in-picture"
                      allowFullScreen
                    />
                  </div>
                </div>
              </section>

              <section className="rounded-xl border border-border-default bg-neutral-bg2 p-6">
                <h2 className="mb-3 text-2xl font-semibold text-text-primary">Components</h2>
                <div className="space-y-4">
                  <div className="flex items-start gap-3">
                    <img src="/images/fabric-logo.png" alt="" className="h-9 w-9 shrink-0" />
                    <p className="text-base leading-relaxed text-text-secondary">
                      <span className="font-semibold text-text-primary">Fabric IQ:</span> Powers the ontology, allowing agents to query structured data, understand relationships between data sources, and reason over table schemas.
                    </p>
                  </div>
                  <div className="flex items-start gap-3">
                    <img src="/images/foundryiq-logo.png" alt="" className="h-9 w-9 shrink-0" />
                    <p className="text-base leading-relaxed text-text-secondary">
                      <span className="font-semibold text-text-primary">Foundry IQ:</span> Enables querying unstructured data sources across vector search (PDFs), SharePoint, MCPs, web search, and more.
                    </p>
                  </div>
                  <div className="flex items-start gap-3">
                    <img src="/images/copilot-logo.png" alt="" className="h-9 w-9 shrink-0" />
                    <p className="text-base leading-relaxed text-text-secondary">
                      <span className="font-semibold text-text-primary">Work IQ:</span> Connects to Microsoft 365 data so agents can work with emails, Teams, and other collaboration context.
                    </p>
                  </div>
                </div>
                <img src="/images/architecture_slide.png" alt="Architecture overview" className="mt-4 w-full rounded-lg border border-border" />
              </section>

              <section className="rounded-xl border border-border-default bg-neutral-bg2 p-6">
                <h2 className="mb-3 text-2xl font-semibold text-text-primary">Code &amp; Accelerator</h2>
                <p className="text-base leading-relaxed text-text-secondary">
                  This project is open source. See the repository README for setup instructions.
                </p>
              </section>

              <div className="pb-6">
                <button
                  onClick={handleShowInit}
                  className="rounded-lg bg-brand px-6 py-3 text-sm font-bold text-white transition-colors hover:bg-brand-hover"
                >
                  GET STARTED
                </button>
              </div>
            </div>
          </div>
        </>
      ) : (
        <>
          {/* Close button — always visible, top-right */}
          <button
            onClick={handleDismiss}
            className="absolute top-6 right-8 px-5 py-2.5 rounded-lg bg-status-warning hover:bg-status-warning text-black font-bold text-sm transition-colors shadow-lg"
          >
            ✕ Close Welcome Screen
          </button>

          {/* Welcome text — staggered fade-in */}
          <div className="flex flex-col items-center gap-4 mb-12">
            <h1
              className={`text-5xl font-bold text-text-primary transition-all duration-700 ${
                showTitle ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
              }`}
            >
              Welcome, Operator
            </h1>
            <p
              className={`text-2xl text-text-secondary transition-all duration-700 ${
                showSubtitle ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
              }`}
            >
              System Initializing
            </p>
          </div>

          {/* Status rows — fade in together */}
          <div
            className={`flex flex-col gap-3 w-80 transition-all duration-700 ${
              showStatus ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
            }`}
          >
            {statusItems.map((item) => (
              <div key={item.label} className="flex items-center justify-between text-sm font-mono">
                <span className="text-text-secondary">{item.label}</span>
                <StatusBadge status={item.status} />
              </div>
            ))}
          </div>

          {/* Ready + Action buttons */}
          <div className="mt-12 flex flex-col items-center gap-4">
            <p
              className={`text-xl font-semibold text-brand transition-all duration-500 ${
                allReady ? "opacity-100" : "opacity-0"
              }`}
            >
              Ready.
            </p>
            <div className="flex items-center gap-4">
              <button
                onClick={handleWatchDemo}
                disabled={!allReady}
                className={`px-8 py-3 rounded-lg font-bold text-lg transition-all duration-500 ${
                  allReady
                    ? "bg-brand hover:bg-brand-hover text-white shadow-lg shadow-blue-500/20 scale-100"
                    : "bg-neutral-bg3 text-text-muted cursor-not-allowed scale-95 opacity-50"
                }`}
              >
                ▶ See PathfinderIQ in Action!
              </button>
              <button
                onClick={handleDismiss}
                disabled={!allReady}
                className={`px-8 py-3 rounded-lg font-bold text-lg transition-all duration-500 border ${
                  allReady
                    ? "border-text-secondary text-text-secondary hover:border-text-primary hover:text-text-primary scale-100"
                    : "border-neutral-bg3 text-text-muted cursor-not-allowed scale-95 opacity-50"
                }`}
              >
                Run My Own Scenario
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}