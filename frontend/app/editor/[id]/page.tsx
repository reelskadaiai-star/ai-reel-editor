// Required for static export — dynamic job IDs resolved client-side via useParams
export function generateStaticParams() {
  return [];
}

"use client";
import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowLeft, Download, RefreshCw, Music, Wand2, Share2 } from "lucide-react";
import toast from "react-hot-toast";
import useSWR from "swr";

import AnalysisPanel from "@/components/editor/AnalysisPanel";
import TemplateSelector from "@/components/editor/TemplateSelector";
import AudioPicker from "@/components/editor/AudioPicker";
import ReelPreview from "@/components/editor/ReelPreview";
import ExportModal from "@/components/editor/ExportModal";
import StatusTracker from "@/components/editor/StatusTracker";
import { fetchJob, renderJob, updateJob } from "@/lib/api";
import type { Job } from "@/lib/types";

type EditorTab = "template" | "audio" | "captions";

export default function EditorPage() {
  const { id: jobId } = useParams<{ id: string }>();
  const router = useRouter();

  const [activeTab, setActiveTab] = useState<EditorTab>("template");
  const [showExport, setShowExport] = useState(false);
  const [rendering, setRendering] = useState(false);

  // Poll job status every 3s while processing
  const { data: job, mutate } = useSWR<Job>(
    jobId ? `/jobs/${jobId}` : null,
    () => fetchJob(jobId),
    {
      refreshInterval: (job) => {
        if (!job) return 3000;
        if (["done", "failed"].includes(job.status) && job.progress >= 100) return 0;
        return 3000;
      },
    }
  );

  const isAnalyzing = job?.status === "analyzing" || job?.status === "queued";
  const isRendering = job?.status === "rendering";
  const isReadyToRender = job?.status === "done" && job.progress >= 40 && !job.outputFile;
  const isRendered = !!job?.outputFile;
  const isFailed = job?.status === "failed";

  async function handleRender() {
    if (!job) return;
    setRendering(true);
    try {
      await renderJob(jobId);
      toast.success("Rendering started!");
      mutate();
    } catch (err: any) {
      toast.error(err?.response?.data?.error || "Render failed");
    } finally {
      setRendering(false);
    }
  }

  async function handleTemplateChange(templateId: string) {
    await updateJob(jobId, { template: templateId });
    mutate();
  }

  return (
    <div className="min-h-dvh flex flex-col bg-surface-900">
      {/* Top bar */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-white/5 glass sticky top-0 z-40">
        <button onClick={() => router.push("/")} className="btn-ghost flex items-center gap-1.5 text-sm">
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <div className="flex items-center gap-2">
          {job && (
            <span className={`badge text-xs ${
              isFailed ? "bg-red-500/15 text-red-400" :
              isRendered ? "bg-green-500/15 text-green-400" :
              isRendering ? "bg-orange-500/15 text-orange-400" :
              isAnalyzing ? "bg-brand-500/15 text-brand-400" :
              "bg-white/10 text-white/60"
            }`}>
              {isFailed ? "Failed" : isRendered ? "Ready" : isRendering ? "Rendering…" : isAnalyzing ? "Analysing…" : "Analysed"}
            </span>
          )}
          {isRendered && (
            <button onClick={() => setShowExport(true)} className="btn-primary flex items-center gap-2 text-sm py-2 px-4">
              <Download className="w-4 h-4" /> Export ₹20
            </button>
          )}
        </div>
      </header>

      {/* Main layout */}
      <div className="flex-1 flex flex-col lg:flex-row gap-0 overflow-hidden">

        {/* Left: Preview */}
        <div className="lg:w-[400px] lg:sticky lg:top-[57px] lg:h-[calc(100dvh-57px)] flex flex-col items-center justify-center p-4 border-r border-white/5">
          <ReelPreview job={job} />

          {/* Render / retry CTA */}
          {isReadyToRender && (
            <motion.button
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              onClick={handleRender}
              disabled={rendering}
              className="btn-primary mt-5 w-full flex items-center justify-center gap-2"
            >
              {rendering ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
              {rendering ? "Starting render…" : "Generate Reel"}
            </motion.button>
          )}

          {isFailed && (
            <div className="mt-4 text-center">
              <p className="text-red-400 text-sm mb-2">Something went wrong: {job?.error}</p>
              <button onClick={handleRender} className="btn-ghost text-sm">Try again</button>
            </div>
          )}
        </div>

        {/* Right: Controls */}
        <div className="flex-1 overflow-y-auto">
          {/* Status tracker while processing */}
          <AnimatePresence>
            {(isAnalyzing || isRendering) && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="p-4"
              >
                <StatusTracker job={job} />
              </motion.div>
            )}
          </AnimatePresence>

          {/* Analysis results */}
          {job && job.progress >= 40 && (
            <div className="p-4 space-y-4">
              <AnalysisPanel job={job} />

              {/* Tabs */}
              <div className="flex gap-1 glass rounded-xl p-1">
                {(["template", "audio", "captions"] as EditorTab[]).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all duration-150 capitalize ${
                      activeTab === tab
                        ? "bg-brand-500 text-white shadow"
                        : "text-white/50 hover:text-white"
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              <AnimatePresence mode="wait">
                {activeTab === "template" && (
                  <motion.div key="template" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    <TemplateSelector
                      contentType={job.contentType}
                      selected={job.template}
                      onSelect={handleTemplateChange}
                    />
                  </motion.div>
                )}
                {activeTab === "audio" && (
                  <motion.div key="audio" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    <AudioPicker jobId={jobId} onSelect={mutate} />
                  </motion.div>
                )}
                {activeTab === "captions" && (
                  <motion.div key="captions" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    <div className="card space-y-3">
                      <h3 className="font-semibold text-sm text-white/70">AI Captions</h3>
                      {(job.captions || []).length === 0 ? (
                        <p className="text-white/30 text-sm">No speech detected</p>
                      ) : (
                        job.captions.slice(0, 8).map((c: any, i: number) => (
                          <div key={i} className="flex gap-3 text-sm">
                            <span className="text-white/30 tabular-nums shrink-0">
                              {fmtTime(c.start)}
                            </span>
                            <span className="text-white/80">{c.text}</span>
                          </div>
                        ))
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
        </div>
      </div>

      {/* Export modal */}
      <AnimatePresence>
        {showExport && job && (
          <ExportModal job={job} onClose={() => setShowExport(false)} />
        )}
      </AnimatePresence>
    </div>
  );
}

function fmtTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
