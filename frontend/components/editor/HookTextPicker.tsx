"use client";
import { motion } from "framer-motion";
import { Sparkles, CheckCircle2, Edit3 } from "lucide-react";
import { useState } from "react";

interface Props {
  options: string[];
  selected: string;
  ctaText?: string;
  ctaEnabled?: boolean;
  onSelectHook: (text: string) => void;
  onChangeCta: (text: string) => void;
  onToggleCta: (enabled: boolean) => void;
}

export default function HookTextPicker({
  options,
  selected,
  ctaText,
  ctaEnabled = true,
  onSelectHook,
  onChangeCta,
  onToggleCta,
}: Props) {
  const [customHook, setCustomHook] = useState("");
  const [editingCta, setEditingCta] = useState(false);
  const [ctaDraft, setCtaDraft] = useState(ctaText || "");

  const allOptions = options.length > 0
    ? options
    : ["Watch till the end 👇", "You won't believe this 😱", "This changed everything 🔥"];

  return (
    <div className="space-y-4">
      {/* Hook text */}
      <div className="card space-y-3">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-brand-400" />
          <h3 className="font-semibold text-sm">Opening Hook</h3>
          <span className="text-[10px] text-white/30 ml-auto">Shown first 2 seconds</span>
        </div>

        <div className="space-y-2">
          {allOptions.map((opt, i) => (
            <motion.button
              key={i}
              whileTap={{ scale: 0.99 }}
              onClick={() => onSelectHook(opt)}
              className={`w-full text-left px-4 py-3 rounded-xl border transition-all duration-150 flex items-center gap-3 ${
                selected === opt
                  ? "border-brand-500 bg-brand-500/10"
                  : "border-white/5 bg-white/[0.02] hover:border-white/10"
              }`}
            >
              <span className="text-sm flex-1">{opt}</span>
              {selected === opt && <CheckCircle2 className="w-4 h-4 text-brand-400 shrink-0" />}
            </motion.button>
          ))}
        </div>

        {/* Custom hook input */}
        <div className="flex gap-2">
          <input
            value={customHook}
            onChange={(e) => setCustomHook(e.target.value)}
            placeholder="Write your own hook…"
            maxLength={80}
            className="flex-1 bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-brand-500/50"
          />
          <button
            onClick={() => {
              if (customHook.trim()) {
                onSelectHook(customHook.trim());
                setCustomHook("");
              }
            }}
            className="btn-primary text-sm px-4 py-2"
          >
            Use
          </button>
        </div>
      </div>

      {/* CTA overlay */}
      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">End-screen CTA</p>
            <p className="text-xs text-white/40 mt-0.5">Shown in the last 3.5 seconds</p>
          </div>
          <button
            onClick={() => onToggleCta(!ctaEnabled)}
            className={`relative w-11 h-6 rounded-full transition-colors ${ctaEnabled ? "bg-brand-500" : "bg-white/10"}`}
          >
            <span className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-all ${ctaEnabled ? "left-6" : "left-1"}`} />
          </button>
        </div>

        {ctaEnabled && (
          <div className="flex gap-2 items-center">
            {editingCta ? (
              <>
                <input
                  autoFocus
                  value={ctaDraft}
                  onChange={(e) => setCtaDraft(e.target.value)}
                  maxLength={60}
                  className="flex-1 bg-white/5 border border-brand-500/50 rounded-xl px-3 py-2 text-sm text-white focus:outline-none"
                />
                <button
                  onClick={() => {
                    onChangeCta(ctaDraft);
                    setEditingCta(false);
                  }}
                  className="btn-primary text-xs px-3 py-2"
                >
                  Save
                </button>
              </>
            ) : (
              <>
                <div className="flex-1 bg-white/5 rounded-xl px-4 py-2.5">
                  <p className="text-sm text-white/80">{ctaText || "Follow for more 🔥"}</p>
                </div>
                <button
                  onClick={() => { setCtaDraft(ctaText || ""); setEditingCta(true); }}
                  className="p-2 rounded-xl bg-white/5 hover:bg-white/10 transition-colors"
                >
                  <Edit3 className="w-4 h-4 text-white/50" />
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
