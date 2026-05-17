"use client";
import { useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowLeft, Download, RefreshCw, Wand2 } from "lucide-react";
import toast from "react-hot-toast";
import useSWR from "swr";

import AnalysisPanel from "@/components/editor/AnalysisPanel";
import TemplateSelector from "@/components/editor/TemplateSelector";
import AudioPicker from "@/components/editor/AudioPicker";
import ReelPreview from "@/components/editor/ReelPreview";
import StatusTracker from "@/components/editor/StatusTracker";
import { fetchJob, renderJob, updateJob } from "@/lib/api";
import type { Job } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000";

type EditorTab = "template" | "audio" | "captions";

function EditorInner() {
  const searchParams = useSearchParams();
  const jobId = searchParams.get("id") ?? "";
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<EditorTab>("template");

  const { data: job, mutate } = useSWR<Job>(
    jobId ? `/jobs/${jobId}` : null,
    () => fetchJob(jobId),
    {
      refreshInterval: (j) => {
        if (!j) return 3000;
        // Stop polling once fully done or failed
        if (j.outputFile || j.status === "failed") return 0;
        return 3000;
      },
    }
  );

  const isAnalyzing = job?.status === "queued" || job?.status === "analyzing";
  const isRendering = job?.status === "rendering";
  const isReadyToRender = job?.status === "done" && (job.progress ?? 0) >= 40 && !job.outputFile;
  const isRendered = !!job?.outputFile;
  const isFailed = job?.status === "failed";

  async function handleRender() {
    if (!job || isRendering || isRendered) return;

    // ── Optimistic update: flip to "rendering" in the SWR cache immediately ──
    // This makes the StatusTracker appear on the FIRST click, before the server
    // responds. SWR polling will then sync real progress from the server.
    mutate(
      { ...job, status: "rendering", stage: "Rendering queued", progress: 50 },
      { revalidate: false }
    );

    try {
      await renderJob(jobId);
      mutate(); // kick off a real re-fetch to sync server state
    } catch (err: any) {
      toast.error(err?.response?.data?.error || "Render failed");
      mutate(); // revert to real server state on error
    }
  }

  async function handleTemplateChange(t: string) {
    await updateJob(jobId, { template: t });
    mutate();
  }

  if (!jobId) {
    return (
      <div className="min-h-dvh flex items-center justify-center text-white/40">
        No job ID.{" "}
        <button onClick={() => router.push("/")} className="underline ml-1">Go home</button>
      </div>
    );
  }

  return (
    <div className="min-h-dvh flex flex-col bg-surface-900">
      {/* ── Header ── */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-white/5 glass sticky top-0 z-40">
        <button onClick={() => router.push("/")} className="btn-ghost flex items-center gap-1.5 text-sm">
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <div className="flex items-center gap-2">
          {job && (
            <span className={`badge text-xs ${
              isFailed    ? "bg-red-500/15 text-red-400"    :
              isRendered  ? "bg-green-500/15 text-green-400" :
              isRendering ? "bg-orange-500/15 text-orange-400" :
              isAnalyzing ? "bg-brand-500/15 text-brand-400" :
              "bg-white/10 text-white/60"
            }`}>
              {isFailed ? "Failed" : isRendered ? "Ready" : isRendering ? "Rendering…" : isAnalyzing ? "Analysing…" : "Analysed"}
            </span>
          )}
          {/* Direct download — use HF Space URL if available, else gateway redirect */}
          {isRendered && (
            <a
              href={job?.outputUrl ?? `${API}/api/jobs/${jobId}/download`}
              download
              target="_blank"
              rel="noreferrer"
              className="btn-primary flex items-center gap-2 text-sm py-2 px-4"
            >
              <Download className="w-4 h-4" /> Download
            </a>
          )}
        </div>
      </header>

      {/* ── Body ── */}
      <div className="flex-1 flex flex-col lg:flex-row gap-0 overflow-hidden">
        {/* Left panel — preview + generate button */}
        <div className="lg:w-[400px] lg:sticky lg:top-[57px] lg:h-[calc(100dvh-57px)] flex flex-col items-center justify-center p-4 border-r border-white/5">
          <ReelPreview job={job} />

          {isReadyToRender && (
            <motion.button
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              onClick={handleRender}
              className="btn-primary mt-5 w-full flex items-center justify-center gap-2"
            >
              <Wand2 className="w-4 h-4" />
              Generate Reel
            </motion.button>
          )}

          {isRendering && (
            <div className="mt-5 flex items-center gap-2 text-orange-400 text-sm">
              <RefreshCw className="w-4 h-4 animate-spin" />
              Rendering your reel…
            </div>
          )}

          {isFailed && (
            <div className="mt-4 text-center">
              <p className="text-red-400 text-sm mb-2">{job?.error || "Something went wrong"}</p>
              <button onClick={() => mutate()} className="btn-ghost text-sm">Retry</button>
            </div>
          )}
        </div>

        {/* Right panel — status + editor tabs */}
        <div className="flex-1 overflow-y-auto">
          <AnimatePresence>
            {(isAnalyzing || isRendering) && (
              <motion.div
                key="status"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="p-4"
              >
                <StatusTracker job={job} />
              </motion.div>
            )}
          </AnimatePresence>

          {job && (job.progress ?? 0) >= 40 && (
            <div className="p-4 space-y-4">
              <AnalysisPanel job={job} />
              <div className="flex gap-1 glass rounded-xl p-1">
                {(["template", "audio", "captions"] as EditorTab[]).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`flex-1 py-2 rounded-lg text-sm font-medium transition-all duration-150 capitalize ${
                      activeTab === tab ? "bg-brand-500 text-white shadow" : "text-white/50 hover:text-white"
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>
              <AnimatePresence mode="wait">
                {activeTab === "template" && (
                  <motion.div key="template" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    <TemplateSelector contentType={job.contentType} selected={job.template} onSelect={handleTemplateChange} />
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
                      {(job.captions ?? []).length === 0 ? (
                        <p className="text-white/30 text-sm">No speech detected</p>
                      ) : (
                        (job.captions ?? []).slice(0, 8).map((c: any, i: number) => (
                          <div key={i} className="flex gap-3 text-sm">
                            <span className="text-white/30 tabular-nums shrink-0">{fmtTime(c.start)}</span>
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
    </div>
  );
}

export default function EditorPage() {
  return (
    <Suspense fallback={<div className="min-h-dvh flex items-center justify-center text-white/40">Loading…</div>}>
      <EditorInner />
    </Suspense>
  );
}

function fmtTime(s: number) {
  const m = Math.floor(s / 60);
  return `${m}:${Math.floor(s % 60).toString().padStart(2, "0")}`;
}
