"use client";
import { motion } from "framer-motion";
import {
  Home, UtensilsCrossed, ShoppingBag, Music2, Plane, Film,
  Dumbbell, BookOpen, Sparkles, Video, Laugh, Mic, CheckCircle2,
} from "lucide-react";
import type { ContentType } from "@/lib/types";

const TYPES: {
  id: ContentType;
  label: string;
  icon: any;
  color: string;
  bg: string;
  desc: string;
}[] = [
  { id: "real_estate", label: "Real Estate",  icon: Home,          color: "text-cyan-400",   bg: "bg-cyan-500/15",   desc: "Property tours & listings" },
  { id: "food",        label: "Food",          icon: UtensilsCrossed, color: "text-orange-400", bg: "bg-orange-500/15", desc: "Recipes & food porn" },
  { id: "product",     label: "Product",       icon: ShoppingBag,   color: "text-purple-400", bg: "bg-purple-500/15", desc: "Showcase & unboxing" },
  { id: "dance",       label: "Dance",         icon: Music2,        color: "text-pink-400",   bg: "bg-pink-500/15",   desc: "Choreography & transitions" },
  { id: "travel",      label: "Travel",        icon: Plane,         color: "text-sky-400",    bg: "bg-sky-500/15",    desc: "Destinations & vlogs" },
  { id: "cinematic",   label: "Cinematic",     icon: Film,          color: "text-amber-400",  bg: "bg-amber-500/15",  desc: "Moody & film-grade" },
  { id: "fitness",     label: "Fitness",       icon: Dumbbell,      color: "text-green-400",  bg: "bg-green-500/15",  desc: "Workouts & transformation" },
  { id: "education",   label: "Education",     icon: BookOpen,      color: "text-yellow-400", bg: "bg-yellow-500/15", desc: "Tutorials & explainers" },
  { id: "lifestyle",   label: "Lifestyle",     icon: Sparkles,      color: "text-rose-400",   bg: "bg-rose-500/15",   desc: "Day-in-life & aesthetic" },
  { id: "vlog",        label: "Vlog",          icon: Video,         color: "text-indigo-400", bg: "bg-indigo-500/15", desc: "Daily life moments" },
  { id: "comedy",      label: "Comedy",        icon: Laugh,         color: "text-red-400",    bg: "bg-red-500/15",    desc: "Skits & funny clips" },
  { id: "interview",   label: "Interview",     icon: Mic,           color: "text-teal-400",   bg: "bg-teal-500/15",   desc: "Talks & testimonials" },
];

interface Props {
  detected: ContentType;
  selected: ContentType;
  confidence?: number;
  onSelect: (type: ContentType) => void;
}

export default function ContentTypeSelector({ detected, selected, confidence, onSelect }: Props) {
  const conf = Math.round((confidence ?? 0) * 100);

  return (
    <div className="card space-y-4">
      <div>
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-semibold text-sm">What kind of video is this?</h3>
          {confidence != null && (
            <span className="text-xs text-white/40">
              AI detected with {conf}% confidence
            </span>
          )}
        </div>
        <p className="text-xs text-white/40">
          Confirm or correct — this affects colour grade, transitions, captions &amp; hook text.
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        {TYPES.map((t) => {
          const isSelected = selected === t.id;
          const isDetected = detected === t.id && !isSelected;
          return (
            <motion.button
              key={t.id}
              whileTap={{ scale: 0.97 }}
              onClick={() => onSelect(t.id)}
              className={`relative flex flex-col gap-1.5 p-3 rounded-xl border text-left transition-all duration-150 ${
                isSelected
                  ? "border-brand-500 bg-brand-500/10"
                  : "border-white/5 bg-white/[0.02] hover:border-white/10 hover:bg-white/[0.04]"
              }`}
            >
              {/* AI detected badge */}
              {isDetected && (
                <span className="absolute top-1.5 right-1.5 text-[9px] bg-white/10 text-white/50 px-1.5 py-0.5 rounded-full">
                  AI
                </span>
              )}
              {isSelected && (
                <CheckCircle2 className="absolute top-1.5 right-1.5 w-3.5 h-3.5 text-brand-400" />
              )}
              <div className={`w-7 h-7 rounded-lg ${t.bg} flex items-center justify-center`}>
                <t.icon className={`w-4 h-4 ${t.color}`} />
              </div>
              <p className="text-xs font-semibold leading-tight">{t.label}</p>
              <p className="text-[10px] text-white/35 leading-tight">{t.desc}</p>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}

// Export lookup so AnalysisPanel can use it too
export const CONTENT_TYPE_META: Record<ContentType, { label: string; icon: any; color: string }> =
  Object.fromEntries(TYPES.map(t => [t.id, { label: t.label, icon: t.icon, color: t.color }])) as any;
