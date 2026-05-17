"use client";
import { motion } from "framer-motion";
import { CheckCircle2, Zap, Timer } from "lucide-react";
import type { TransitionStyle } from "@/lib/types";

const TRANSITIONS: { id: TransitionStyle; label: string; emoji: string; desc: string }[] = [
  { id: "fade",       label: "Fade",       emoji: "🌅", desc: "Smooth opacity blend" },
  { id: "dissolve",   label: "Dissolve",   emoji: "✨", desc: "Pixel-level dissolve" },
  { id: "slideleft",  label: "Slide Left", emoji: "◀️", desc: "New clip slides in from right" },
  { id: "slideright", label: "Slide Right",emoji: "▶️", desc: "New clip slides in from left" },
  { id: "wipeleft",   label: "Wipe Left",  emoji: "⬅️", desc: "Classic wipe transition" },
  { id: "wiperight",  label: "Wipe Right", emoji: "➡️", desc: "Wipe from left to right" },
  { id: "circleopen", label: "Circle",     emoji: "⭕", desc: "Iris / circle open effect" },
  { id: "radial",     label: "Radial",     emoji: "🌀", desc: "Clockwise radial wipe" },
  { id: "zoomin",     label: "Zoom In",    emoji: "🔍", desc: "New clip zooms in" },
  { id: "none",       label: "Cut",        emoji: "✂️", desc: "Hard cut — fastest render" },
];

const DURATIONS = [
  { value: 0.2, label: "Fast" },
  { value: 0.3, label: "Normal" },
  { value: 0.5, label: "Slow" },
  { value: 0.7, label: "Dramatic" },
];

interface Props {
  selected: TransitionStyle;
  duration: number;
  speedRamp: boolean;
  zoomPunch: boolean;
  onSelect: (t: TransitionStyle) => void;
  onDuration: (d: number) => void;
  onSpeedRamp: (v: boolean) => void;
  onZoomPunch: (v: boolean) => void;
}

export default function TransitionPicker({
  selected, duration, speedRamp, zoomPunch,
  onSelect, onDuration, onSpeedRamp, onZoomPunch,
}: Props) {
  return (
    <div className="space-y-4">
      {/* Transition type */}
      <div className="card space-y-3">
        <h3 className="font-semibold text-sm">Transition Style</h3>
        <div className="grid grid-cols-2 gap-2">
          {TRANSITIONS.map((t) => (
            <motion.button
              key={t.id}
              whileTap={{ scale: 0.97 }}
              onClick={() => onSelect(t.id)}
              className={`relative flex items-start gap-2.5 p-3 rounded-xl border text-left transition-all duration-150 ${
                selected === t.id
                  ? "border-brand-500 bg-brand-500/10"
                  : "border-white/5 bg-white/[0.02] hover:border-white/10"
              }`}
            >
              {selected === t.id && (
                <CheckCircle2 className="absolute top-2 right-2 w-3.5 h-3.5 text-brand-400" />
              )}
              <span className="text-lg">{t.emoji}</span>
              <div>
                <p className="text-xs font-semibold">{t.label}</p>
                <p className="text-[10px] text-white/35 mt-0.5">{t.desc}</p>
              </div>
            </motion.button>
          ))}
        </div>
      </div>

      {/* Transition duration (only if not hard cut) */}
      {selected !== "none" && (
        <div className="card space-y-3">
          <div className="flex items-center gap-2">
            <Timer className="w-4 h-4 text-white/40" />
            <h3 className="font-semibold text-sm">Transition Duration</h3>
          </div>
          <div className="flex gap-2">
            {DURATIONS.map((d) => (
              <button
                key={d.value}
                onClick={() => onDuration(d.value)}
                className={`flex-1 py-2 rounded-lg text-xs font-medium border transition-all ${
                  duration === d.value
                    ? "border-brand-500 bg-brand-500/15 text-brand-400"
                    : "border-white/10 text-white/50 hover:text-white"
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Effects */}
      <div className="card space-y-3">
        <div className="flex items-center gap-2 mb-1">
          <Zap className="w-4 h-4 text-brand-400" />
          <h3 className="font-semibold text-sm">Clip Effects</h3>
        </div>

        {/* Speed ramp */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Speed Ramp</p>
            <p className="text-xs text-white/40 mt-0.5">Slow-mo on highlight moments (0.75× speed)</p>
          </div>
          <button
            onClick={() => onSpeedRamp(!speedRamp)}
            className={`relative w-11 h-6 rounded-full transition-colors ${speedRamp ? "bg-brand-500" : "bg-white/10"}`}
          >
            <span className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-all ${speedRamp ? "left-6" : "left-1"}`} />
          </button>
        </div>

        {/* Zoom punch */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Zoom Punch</p>
            <p className="text-xs text-white/40 mt-0.5">Subtle scale-in on each clip start</p>
          </div>
          <button
            onClick={() => onZoomPunch(!zoomPunch)}
            className={`relative w-11 h-6 rounded-full transition-colors ${zoomPunch ? "bg-brand-500" : "bg-white/10"}`}
          >
            <span className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-all ${zoomPunch ? "left-6" : "left-1"}`} />
          </button>
        </div>
      </div>
    </div>
  );
}
