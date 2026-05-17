"use client";
import { motion } from "framer-motion";
import {
  Home, UtensilsCrossed, ShoppingBag, Music2, Plane, Film,
  Dumbbell, BookOpen, Sparkles, Video, Laugh, Mic, Cpu,
} from "lucide-react";
import type { Job, ContentType } from "@/lib/types";

const TYPE_META: Record<string, { icon: any; label: string; color: string; bg: string }> = {
  real_estate: { icon: Home,           label: "Real Estate", color: "text-cyan-400",   bg: "bg-cyan-500/15" },
  food:        { icon: UtensilsCrossed,label: "Food",        color: "text-orange-400", bg: "bg-orange-500/15" },
  product:     { icon: ShoppingBag,    label: "Product",     color: "text-purple-400", bg: "bg-purple-500/15" },
  dance:       { icon: Music2,         label: "Dance",       color: "text-pink-400",   bg: "bg-pink-500/15" },
  travel:      { icon: Plane,          label: "Travel",      color: "text-sky-400",    bg: "bg-sky-500/15" },
  cinematic:   { icon: Film,           label: "Cinematic",   color: "text-amber-400",  bg: "bg-amber-500/15" },
  fitness:     { icon: Dumbbell,       label: "Fitness",     color: "text-green-400",  bg: "bg-green-500/15" },
  education:   { icon: BookOpen,       label: "Education",   color: "text-yellow-400", bg: "bg-yellow-500/15" },
  lifestyle:   { icon: Sparkles,       label: "Lifestyle",   color: "text-rose-400",   bg: "bg-rose-500/15" },
  vlog:        { icon: Video,          label: "Vlog",        color: "text-indigo-400", bg: "bg-indigo-500/15" },
  comedy:      { icon: Laugh,          label: "Comedy",      color: "text-red-400",    bg: "bg-red-500/15" },
  interview:   { icon: Mic,            label: "Interview",   color: "text-teal-400",   bg: "bg-teal-500/15" },
  unknown:     { icon: Film,           label: "Video",       color: "text-white/50",   bg: "bg-white/5" },
};

interface Props { job: Job }

export default function AnalysisPanel({ job }: Props) {
  const meta = TYPE_META[job.contentType] ?? TYPE_META.unknown;
  const Icon = meta.icon;
  const conf = Math.round((job.confidence ?? 0) * 100);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="card space-y-4"
    >
      {/* Header with auto-detected badge */}
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-xl ${meta.bg} flex items-center justify-center`}>
          <Icon className={`w-5 h-5 ${meta.color}`} />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className={`font-bold text-base ${meta.color}`}>{meta.label}</h3>
            <span className="flex items-center gap-1 text-[10px] bg-brand-500/15 text-brand-400 px-2 py-0.5 rounded-full">
              <Cpu className="w-2.5 h-2.5" />
              AI detected · {conf}%
            </span>
          </div>
          <p className="text-xs text-white/40 mt-0.5">
            Auto-applied: colour grade, template &amp; transitions
          </p>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Duration"  value={job.durationSeconds ? `${Math.round(job.durationSeconds)}s` : "—"} />
        <Stat label="Scenes"    value={job.sceneCount?.toString() ?? "—"} />
        <Stat label="Beats"     value={job.beatTimestamps?.length.toString() ?? "—"} />
      </div>

      {/* Dominant colours */}
      {(job.dominantColors?.length ?? 0) > 0 && (
        <div>
          <p className="text-xs text-white/40 mb-2">Colour palette</p>
          <div className="flex gap-2">
            {job.dominantColors!.map((c, i) => (
              <div
                key={i}
                className="w-7 h-7 rounded-lg ring-1 ring-white/10"
                style={{ background: c }}
                title={c}
              />
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white/[0.03] rounded-xl p-3 text-center">
      <p className="text-base font-bold text-white">{value}</p>
      <p className="text-xs text-white/30 mt-0.5">{label}</p>
    </div>
  );
}
