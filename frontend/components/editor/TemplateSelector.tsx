"use client";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { CheckCircle } from "lucide-react";
import axios from "axios";

interface Template {
  id: string;
  name: string;
  description: string;
  contentType: string;
  tags: string[];
  captionStyle: string;
  transitionStyle: string;
  targetDurationSec: number;
}

interface Props {
  contentType: string;
  selected: string;
  onSelect: (id: string) => void;
}

export default function TemplateSelector({ contentType, selected, onSelect }: Props) {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios
      .get(`/api/templates?contentType=${contentType}`)
      .then((r) => setTemplates(r.data))
      .finally(() => setLoading(false));
  }, [contentType]);

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2].map((i) => (
          <div key={i} className="h-24 rounded-2xl bg-white/5 animate-pulse" />
        ))}
      </div>
    );
  }

  if (!templates.length) {
    return <p className="text-white/30 text-sm text-center py-8">No templates for this content type yet.</p>;
  }

  return (
    <div className="space-y-3">
      {templates.map((t) => (
        <motion.button
          key={t.id}
          onClick={() => onSelect(t.id)}
          className={`w-full text-left rounded-2xl p-4 border transition-all duration-150 ${
            selected === t.id
              ? "border-brand-500 bg-brand-500/10"
              : "border-white/5 bg-white/[0.02] hover:border-white/10 hover:bg-white/[0.04]"
          }`}
          whileTap={{ scale: 0.99 }}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <h4 className="font-semibold text-sm">{t.name}</h4>
                {selected === t.id && <CheckCircle className="w-4 h-4 text-brand-400 shrink-0" />}
              </div>
              <p className="text-xs text-white/40">{t.description}</p>
            </div>
            <div className="text-right shrink-0">
              <p className="text-xs text-white/30">{t.targetDurationSec}s</p>
            </div>
          </div>
          <div className="flex gap-1.5 mt-3 flex-wrap">
            {t.tags.map((tag) => (
              <span key={tag} className="badge bg-white/5 text-white/40 text-[10px]">
                {tag}
              </span>
            ))}
          </div>
        </motion.button>
      ))}
    </div>
  );
}
