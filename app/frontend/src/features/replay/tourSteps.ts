export interface ReplayTourStep {
  title: string;
  body: string;
  cta: string;
  /** Optional full-body agent image shown below the text on introduction cards. */
  agentImage?: string;
  poweredBy?: {
    logoSrc: string;
    label: string;
    description: string;
  };
}

/**
 * Tour steps for the session replay.
 *
 * Index mapping (dynamic, driven by agent order in the replay script):
 *   0: Before start (scenario overview)
 *   1: After user prompt injected (orchestrator introduction)
 *   2: First delegation_start on orchestrator
 *   3: First delegation_start on networkInvestigator
 *   4: First delegation_start on knowledgeAnalyst
 *   5: First delegation_start on fieldCoordinator
 *   6: Orchestrator resumes (remediation actions)
 *   7: First delegation_start on communicationsSpecialist
 *   8: Final orchestrator summary complete
 *
 * The engine increments through these in order, one per first-seen agent.
 * If the conversation has fewer agents, later indices are skipped.
 */
export const REPLAY_TOUR_STEPS: ReplayTourStep[] = [
  // 0: Before start
  {
    title: "Scenario Overview",
    body: "A fibre cut on the Sydney-Melbourne corridor has triggered a cascading alert storm across enterprise VPNs, broadband, and mobile services. In this demo, a multi-agent system built entirely on the Microsoft stack investigates root cause, blast radius, and remediation in minutes \u2014 work that previously took hours of manual coordination.",
    cta: "Start Demo",
  },
  // 1: User prompt injected
  {
    title: "NOC Orchestrator",
    body: "The orchestrator receives the raw alert burst and acts as the central coordinator. Built on Azure AI Foundry, it decomposes the incident into specialist tasks and delegates them in parallel \u2014 combining graph reasoning, document retrieval, and field logistics into a single agentic workflow.",
    cta: "Continue",
    agentImage: "/images/agents/nocorchestrator_fullbody.png",
    poweredBy: {
      logoSrc: "/images/foundryiq-logo.png",
      label: "Azure AI Foundry",
      description: "Multi-agent orchestration \u2014 task decomposition, parallel delegation, and synthesis across specialist agents.",
    },
  },
  // 2: Orchestrator delegation_start (first time)
  {
    title: "Orchestrator \u2014 Planning",
    body: "The orchestrator is now reading the correlated alerts, forming a diagnosis plan, and dispatching tasks to three specialist agents simultaneously. Each agent has its own tools and data sources, but they all share the same graph ontology as their common understanding of the network.\n\n\ud83d\udca1 Watch for the highlights on key tool results \u2014 they explain why each finding matters.",
    cta: "Continue",
  },
  // 3: NetworkInvestigator delegation_start (first time)
  {
    title: "Network Investigator",
    body: "This agent queries the network ontology in Microsoft Fabric using GQL to trace topology dependencies, then cross-references real-time telemetry from Fabric Eventhouse (KQL) to confirm optical power loss. It also performs per-sensor fault localization \u2014 reading individual optical sensors along the corridor to triangulate the exact fault segment \u2014 and checks whether the backup fibre shares the same physical conduit.",
    cta: "Continue",
    agentImage: "/images/agents/networkinvestigator_fullbody.png",
    poweredBy: {
      logoSrc: "/images/fabric-logo.png",
      label: "Fabric IQ",
      description: "Fabric Graph (GQL) for topology traversal and sensor lookup, Fabric Eventhouse (KQL) for real-time telemetry and per-sensor readings \u2014 structured data reasoning at scale.",
    },
  },
  // 4: KnowledgeAnalyst delegation_start (first time)
  {
    title: "Knowledge Analyst",
    body: "This agent searches operational runbooks and historical incident tickets using Azure AI Search with vector + semantic ranking. It finds the exact SOP for this fault type, surfaces past incidents on the same corridor including a critical shared-risk conduit warning, and quantifies the SLA penalty exposure: $75,000/hour across the affected enterprise VPNs.",
    cta: "Continue",
    agentImage: "/images/agents/knowledgeanalyst_fullbody.png",
    poweredBy: {
      logoSrc: "/images/foundryiq-logo.png",
      label: "Foundry IQ",
      description: "Azure AI Search for vector retrieval across runbooks, SOPs, historical tickets, and SLA policies \u2014 unstructured knowledge made actionable.",
    },
  },
  // 5: FieldCoordinator delegation_start (first time)
  {
    title: "Field Coordinator",
    body: "This agent traverses the graph to find amplifier sites, optical sensors with GPS coordinates, servicing depots, and on-duty engineers along the corridor. It then checks equipment manifests via search to confirm OTDR and splicer availability \u2014 producing a ranked dispatch plan ready for operator approval.",
    cta: "Continue",
    agentImage: "/images/agents/fieldcoordinator_fullbody.png",
    poweredBy: {
      logoSrc: "/images/copilot-logo.png",
      label: "Work IQ",
      description: "Graph traversal for depot/roster lookup, AI Search for equipment manifests \u2014 bridging digital topology to physical field operations.",
    },
  },
  // 6: Orchestrator resumes with remediation actions
  {
    title: "Orchestrator \u2014 Remediation",
    body: "The orchestrator synthesises all specialist findings and executes immediate remediation: rerouting VPN traffic to the backup MPLS path, placing the failed link in admin-down to prevent flapping, dispatching the nearest field engineer to the Goulburn splice site, and calling them to confirm ETA.",
    cta: "Continue",
    poweredBy: {
      logoSrc: "/images/foundryiq-logo.png",
      label: "Foundry Agents",
      description: "Tool calling for network remediation \u2014 reroute, admin-down, field dispatch, and engineer coordination.",
    },
  },
  // 7: CommunicationsSpecialist delegation_start (first time)
  {
    title: "Communications Specialist",
    body: "The final specialist handles all incident communications \u2014 creating a formal SEV-1 incident ticket, publishing customer advisories to the affected enterprise VPN customers, and emailing a structured incident report to NOC leadership. All three reference the same root cause, blast radius, and remediation status.",
    cta: "Continue",
    agentImage: "/images/agents/communicationsspecialist_fullbody.png",
    poweredBy: {
      logoSrc: "/images/foundryiq-logo.png",
      label: "Foundry Agents",
      description: "Structured document generation \u2014 incident tickets, customer advisories, and stakeholder reports from a single synthesis.",
    },
  },
  // 8: Final orchestrator summary
  {
    title: "Investigation Complete",
    body: "From chaos to resolution \u2014 the agents recognised the pattern across 20 alerts, traced the root cause through the graph, localised the fault to a 150km corridor segment, discovered the backup fibre shares the same duct, quantified $75k/hour in SLA exposure, dispatched a field engineer with GPS and equipment, and communicated to all stakeholders. All evidence-based, all in minutes.",
    cta: "Continue",
  },
  // 9: Demo complete — closing card
  {
    title: "Demo Complete",
    body: "We hope you\u2019re as excited about graph-enabled agents as we are \u2014 all powered by the Microsoft IQ stack. We can\u2019t wait to see what you build!",
    cta: "Close",
    agentImage: "/images/agents/group_photo.png",
  },
];
