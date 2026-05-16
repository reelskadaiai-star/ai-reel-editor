"use client";
import { motion } from "framer-motion";
import { Home, UtensilsCrossed, ShoppingBag, TrendingUp, Clock, Film } from "lucide-react";
import type { Job } from "@/lib/types";

const TYPE_META: Record<string, { icon: any; label: string; color: string }> = {
  real_estate: { icon: Home, label: "Real Estate", color: "text-cyan-400" },
  food: { icon: UtensilsCrossed, label: "Food", color: "text-orange-400" },
  product: { icon: ShoppingBag, label: "Product", color: "text-purple-400" },
  unknown: { icon: Film, label: "Video", color: "text-white/50" },
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
      <div className="flex items-center gap-3">
        <div className={`w-9 h-9 rounded-xl bg-white/5 flex items-center justify-center ${meta.color}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <h3 className="font-semibold">Content Analysis</h3>
          <p className="text-xs text-white/40">AI detected your content type</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Stat label="Type" value={meta.label} accent={meta.color} />
        <Stat label="Confidence" value={`${conf}%`} />
        <Stat label="Duration" value={job.durationSeconds ? `${Math.round(job.durationSeconds)}s` : "—"} />
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Stat label="Scenes" value={job.sceneCount?.toString() ?? "—"} />
        <Stat label="Beats" value={job.beatTimestamps?.length.toString() ?? "—"} />
        <Stat label="Captions" value={job.captions?.length.toString() ?? "—"} />
      </div>

      {/* Dominant colors */}
      {(job.dominantColors?.length ?? 0) > 0 && (
        <div>
          <p className="text-xs text-white/40 mb-2">Dominant colours</p>
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

      {/* Hook text */}
      {job.hookText && (
        <div className="bg-brand-500/10 rounded-xl p-3 border border-brand-500/20">
          <p className="text-xs text-brand-400 font-semibold mb-1">AI Hook Text</p>
          <p className="text-sm text-white font-medium">{job.hookText}</p>
        </div>
      )}
    </motion.div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="bg-white/[0.03] rounded-xl p-3 text-center">
      <p className={`text-base font-bold ${accent || "text-white"}`}>{value}</p>
      <p className="text-xs text-white/30 mt-0.5">{label}</p>
    </div>
  );
}
