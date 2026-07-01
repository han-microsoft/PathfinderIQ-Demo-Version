/**
 * TeamsCallModal — spoofed Microsoft Teams call overlay.
 *
 * Opens as a full-viewport modal simulating a Teams voice call.
 * Shows contact name, role, pulsing "Calling..." animation, and
 * call controls (mute, video, end). Visual demo only — no real call.
 *
 * Used by: SituationCard contact rows, PriorityActionCard contact rows.
 */

import { useState, useEffect } from "react";
import { Phone, PhoneOff, Mic, MicOff, Video, VideoOff } from "lucide-react";

interface TeamsCallModalProps {
  contact: { name: string; role: string; phone: string; teams: string };
  onClose: () => void;
}

/** Extract initials from a full name for the avatar circle. */
function getInitials(name: string): string {
  return name
    .split(" ")
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export function TeamsCallModal({ contact, onClose }: TeamsCallModalProps) {
  const [muted, setMuted] = useState(false);
  const [videoOn, setVideoOn] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  /* Close on Escape key. */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  /* Elapsed timer — ticks every second. */
  useEffect(() => {
    const interval = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const minutes = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const seconds = String(elapsed % 60).padStart(2, "0");

  return (
    <div
      data-testid="teams-call-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-teams-backdrop backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex flex-col items-center gap-8 p-12 max-w-md w-full"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Avatar circle with initials */}
        <div className="relative">
          <div className="h-28 w-28 rounded-full bg-teams-avatar flex items-center justify-center text-4xl font-bold text-on-accent">
            {getInitials(contact.name)}
          </div>
          {/* Pulsing ring animation */}
          <div className="absolute inset-0 rounded-full border-2 border-teams-avatar animate-ping opacity-30" />
        </div>

        {/* Contact info */}
        <div className="text-center space-y-2">
          <h2 className="text-2xl font-semibold text-on-accent">{contact.name}</h2>
          <p className="text-sm text-teams-text">{contact.role}</p>
          <p className="text-xs font-mono text-teams-text-muted">{contact.phone}</p>
        </div>

        {/* Status */}
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-teams-status animate-pulse" />
          <span className="text-sm text-teams-text">
            Calling... {minutes}:{seconds}
          </span>
        </div>

        {/* Call controls */}
        <div className="flex items-center gap-6">
          {/* Mute toggle */}
          <button
            onClick={() => setMuted(!muted)}
            className={`h-12 w-12 rounded-full flex items-center justify-center transition-colors ${
              muted
                ? "bg-teams-mute text-on-accent"
                : "bg-teams-control-bg text-teams-text hover:bg-teams-control-hover"
            }`}
            title={muted ? "Unmute" : "Mute"}
          >
            {muted ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
          </button>

          {/* Video toggle */}
          <button
            onClick={() => setVideoOn(!videoOn)}
            className={`h-12 w-12 rounded-full flex items-center justify-center transition-colors ${
              videoOn
                ? "bg-teams-status text-on-accent"
                : "bg-teams-control-bg text-teams-text hover:bg-teams-control-hover"
            }`}
            title={videoOn ? "Turn off camera" : "Turn on camera"}
          >
            {videoOn ? <Video className="h-5 w-5" /> : <VideoOff className="h-5 w-5" />}
          </button>

          {/* End call */}
          <button
            data-testid="teams-call-end"
            onClick={onClose}
            className="h-14 w-14 rounded-full bg-teams-mute text-on-accent flex items-center justify-center hover:bg-teams-mute-hover transition-colors"
            title="End call"
          >
            <PhoneOff className="h-6 w-6" />
          </button>
        </div>

        {/* Teams branding */}
        <div className="flex items-center gap-2 text-teams-text-muted text-xs mt-4">
          <Phone className="h-3 w-3" />
          <span>Microsoft Teams (Demo)</span>
        </div>
      </div>
    </div>
  );
}
