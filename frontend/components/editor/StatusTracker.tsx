"use client";
import { motion } from "framer-motion";
import { Brain, Scissors, Music, Type, Sparkles } from "lucide-react";
import type { Job } from "@/lib/types";

const STAGES = [
  { key: "detect", icon: Brain, label: "Detecting scenes", threshold: 5 },
  { key: "classify", icon: Sparkles, label: "Classifying content", threshold: 20 },
  { key: "audio", icon: Music, label: "Analysing beats", threshold: 35 },
  { key: "captions", icon: Type, label: "Generating captions", threshold: 50 },
  { key: "highlights", icon: Scissors, label: "Scoring highlights", threshold: 70 },
];

interface Props { job: Job | undefined }

export default function StatusTracker({ job }: Props) {
  const progress = job?.progress ?? 0;
  const stage = job?.stage ?? "";

  return (
    <div className="card space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">
          {job?.status === "rendering" ? "Rendering reel…" : "Analysing video…"}
        </h3>
        <span className="text-brand-400 font-bold tabular-nums">{progress}%</span>
      </div>

      {/* Progress bar */}
      <div className="progress-bar">
        <motion.div
          className="progress-fill"
          style={{ width: `${progress}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        />
      </div>

      {/* Stage chips */}
      <div className="space-y-2">
        {STAGES.map((s) => {
          const done = progress >= s.threshold;
          const active = progress >= s.threshold - 15 && progress < s.threshold;
          return (
            <div
              key={s.key}
              className={`flex items-center gap-3 text-sm transition-all duration-300 ${
                done ? "text-white/70" : active ? "text-brand-400" : "text-white/20"
              }`}
            >
              <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 transition-all ${
                done ? "bg-brand-500/20" : active ? "bg-brand-500/10 ring-1 ring-brand-500" : "bg-white/5"
              }`}>
                <s.icon className="w-3.5 h-3.5" />
              </div>
              <span>{s.label}</span>
              {done && <span className="ml-auto text-brand-500 text-xs">✓</span>}
              {active && (
                <motion.span
                  animate={{ opacity: [0.5, 1, 0.5] }}
                  transition={{ repeat: Infinity, duration: 1.5 }}
                  className="ml-auto text-brand-400 text-xs"
                >
                  •••
                </motion.span>
              )}
            </div>
          );
        })}
      </div>

      {stage && (
        <p className="text-xs text-white/30 text-center">{stage}</p>
      )}
    </div>
  );
}
