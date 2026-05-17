"use client";
import { useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowLeft, Download, RefreshCw, Wand2, RotateCcw } from "lucide-react";
import toast from "react-hot-toast";
import useSWR from "swr";

import AnalysisPanel from "@/components/editor/AnalysisPanel";
import TemplateSelector from "@/components/editor/TemplateSelector";
import AudioPicker from "@/components/editor/AudioPicker";
import ReelPreview from "@/components/editor/ReelPreview";
import StatusTracker from "@/components/editor/StatusTracker";
import HookTextPicker from "@/components/editor/HookTextPicker";
import TransitionPicker from "@/components/editor/TransitionPicker";
import api, { fetchJob, renderJob, updateJob } from "@/lib/api";
import type { Job, TransitionStyle } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000";

type EditorTab = "content" | "template" | "transitions" | "audio" | "captions" | "branding";

const TABS: { id: EditorTab; label: string }[] = [
  { id: "content",     label: "Content" },
  { id: "template",    label: "Template" },
  { id: "transitions", label: "Transitions" },
  { id: "audio",       label: "Audio" },
  { id: "captions",    label: "Captions" },
  { id: "branding",    label: "Branding" },
];

function EditorInner() {
  const searchParams = useSearchParams();
  const jobId = searchParams.get("id") ?? "";
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<EditorTab>("content");

  const { data: job, mutate } = useSWR<Job>(
    jobId ? `/jobs/${jobId}` : null,
    () => fetchJob(jobId),
    {
      refreshInterval: (j) => {
        if (!j) return 3000;
        if (j.outputFile || j.status === "failed") return 0;
        return 3000;
      },
    }
  );

  const isAnalyzing     = job?.status === "queued" || job?.status === "analyzing";
  const isRendering     = job?.status === "rendering";
  const isReadyToRender = job?.status === "done" && (job.progress ?? 0) >= 40 && !job.outputFile;
  const isRendered      = !!job?.outputFile;
  const isFailed        = job?.status === "failed";

  // ── Render ────────────────────────────────────────────────────────────
  async function handleRender() {
    if (!job || isRendering || isRendered) return;
    mutate(
      { ...job, status: "rendering", stage: "Rendering queued…", progress: 50 },
      { revalidate: false }
    );
    try {
      await renderJob(jobId);
    } catch (err: any) {
      toast.error(err?.response?.data?.error || "Render failed");
      mutate();
    }
  }

  async function handleRegenerate() {
    if (!job || isRendering) return;
    mutate(
      { ...job, status: "rendering", stage: "Generating new variation…", progress: 50,
        outputFile: undefined, outputUrl: undefined },
      { revalidate: false }
    );
    try {
      await api.patch(`/api/jobs/${jobId}`, { outputFile: null, outputUrl: null }).catch(() => {});
      await renderJob(jobId);
      toast.success("Generating new variation…");
    } catch (err: any) {
      toast.error(err?.response?.data?.error || "Re-generate failed");
      mutate();
    }
  }

  // ── Template ──────────────────────────────────────────────────────────
  async function handleTemplateChange(t: string) {
    await updateJob(jobId, { template: t });
    mutate();
  }

  // ── Transitions ───────────────────────────────────────────────────────
  async function handleTransitionStyle(t: TransitionStyle) {
    await updateJob(jobId, { transitionStyle: t });
    mutate();
  }
  async function handleTransitionDuration(d: number) {
    await updateJob(jobId, { transitionDuration: d });
    mutate();
  }
  async function handleSpeedRamp(v: boolean) {
    await updateJob(jobId, { speedRamp: v });
    mutate();
  }
  async function handleZoomPunch(v: boolean) {
    await updateJob(jobId, { zoomPunch: v });
    mutate();
  }

  // ── Hook / CTA ────────────────────────────────────────────────────────
  async function handleSelectHook(text: string) {
    await updateJob(jobId, { hookText: text });
    mutate();
    toast.success("Hook text updated");
  }
  async function handleChangeCta(text: string) {
    await updateJob(jobId, { ctaText: text });
    mutate();
  }
  async function handleToggleCta(enabled: boolean) {
    await updateJob(jobId, { ctaEnabled: enabled });
    mutate();
  }

  // ── Branding ──────────────────────────────────────────────────────────
  async function handleMuteToggle() {
    if (!job) return;
    await updateJob(jobId, { muteAudio: !job.muteAudio });
    mutate();
  }
  async function handleLogoUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !jobId) return;
    const fd = new FormData();
    fd.append("logo", file);
    try {
      await api.post(`/api/upload/logo/${jobId}`, fd);
      mutate();
      toast.success("Logo uploaded!");
    } catch {
      toast.error("Logo upload failed");
    }
  }
  async function handleLogoPosition(pos: string) {
    if (!job) return;
    await updateJob(jobId, { logoPosition: pos as Job["logoPosition"] });
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

  const showEditor = job && (job.progress ?? 0) >= 40;

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
              isFailed    ? "bg-red-500/15 text-red-400"       :
              isRendered  ? "bg-green-500/15 text-green-400"   :
              isRendering ? "bg-orange-500/15 text-orange-400" :
              isAnalyzing ? "bg-brand-500/15 text-brand-400"   :
              "bg-white/10 text-white/60"
            }`}>
              {isFailed ? "Failed" : isRendered ? "Ready ✓" : isRendering ? "Rendering…" : isAnalyzing ? "Analysing…" : "Analysed"}
            </span>
          )}

          {isRendered && !isRendering && (
            <button
              onClick={handleRegenerate}
              className="btn-ghost flex items-center gap-1.5 text-sm"
              title="Generate a different cut"
            >
              <RotateCcw className="w-4 h-4" /> Regenerate
            </button>
          )}

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
        {/* Left panel */}
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

        {/* Right panel */}
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

          {showEditor && (
            <div className="p-4 space-y-4">
              <AnalysisPanel job={job} />

              {/* Tab bar — scrollable on mobile */}
              <div className="glass rounded-xl p-1 flex gap-1 overflow-x-auto scrollbar-none">
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`shrink-0 py-2 px-3 rounded-lg text-xs font-medium transition-all duration-150 ${
                      activeTab === tab.id ? "bg-brand-500 text-white shadow" : "text-white/50 hover:text-white"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <AnimatePresence mode="wait">
                {/* Content = hook text + CTA (content type auto-detected by AI) */}
                {activeTab === "content" && (
                  <motion.div key="content" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    <HookTextPicker
                      options={job.hookTextOptions ?? []}
                      selected={job.hookText ?? ""}
                      ctaText={job.ctaText}
                      ctaEnabled={job.ctaEnabled !== false}
                      onSelectHook={handleSelectHook}
                      onChangeCta={handleChangeCta}
                      onToggleCta={handleToggleCta}
                    />
                  </motion.div>
                )}

                {activeTab === "template" && (
                  <motion.div key="template" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    <TemplateSelector contentType={job.contentType} selected={job.template} onSelect={handleTemplateChange} />
                  </motion.div>
                )}

                {activeTab === "transitions" && (
                  <motion.div key="transitions" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                    <TransitionPicker
                      selected={(job.transitionStyle as TransitionStyle) ?? "fade"}
                      duration={job.transitionDuration ?? 0.3}
                      speedRamp={job.speedRamp ?? false}
                      zoomPunch={job.zoomPunch ?? true}
                      onSelect={handleTransitionStyle}
                      onDuration={handleTransitionDuration}
                      onSpeedRamp={handleSpeedRamp}
                      onZoomPunch={handleZoomPunch}
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
                      {/* Caption source badge */}
                      {job.captionsAutoGenerated ? (
                        <div className="flex items-center gap-2 bg-brand-500/10 border border-brand-500/20 rounded-xl px-3 py-2.5">
                          <span className="text-brand-400 text-sm">✨</span>
                          <div>
                            <p className="text-xs font-semibold text-brand-400">AI-generated captions</p>
                            <p className="text-[11px] text-white/40 mt-0.5">No speech detected — contextual overlays added automatically</p>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2 bg-green-500/10 border border-green-500/20 rounded-xl px-3 py-2.5">
                          <span className="text-green-400 text-sm">🎙️</span>
                          <div>
                            <p className="text-xs font-semibold text-green-400">Speech captions</p>
                            <p className="text-[11px] text-white/40 mt-0.5">Transcribed from audio via Whisper AI</p>
                          </div>
                        </div>
                      )}

                      {/* Style picker */}
                      <div>
                        <p className="text-xs text-white/40 mb-2">Caption style</p>
                        <div className="flex gap-2 flex-wrap">
                          {["modern", "bold", "minimal", "hype", "neon", "clean", "luxury"].map((s) => (
                            <button
                              key={s}
                              onClick={() => { updateJob(jobId, { captionStyle: s }); mutate(); }}
                              className={`text-xs px-3 py-1.5 rounded-lg border transition-all capitalize ${
                                (job.captionStyle ?? "modern") === s
                                  ? "border-brand-500 bg-brand-500/15 text-brand-400"
                                  : "border-white/10 text-white/50 hover:text-white"
                              }`}
                            >
                              {s}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Caption list */}
                      <div className="pt-1 border-t border-white/5 space-y-2">
                        {(job.captions ?? []).length === 0 ? (
                          <p className="text-white/30 text-sm">No captions</p>
                        ) : (
                          (job.captions ?? []).slice(0, 10).map((c: any, i: number) => (
                            <div key={i} className="flex items-center gap-3 text-sm">
                              <span className="text-white/25 tabular-nums shrink-0 text-xs">{fmtTime(c.start)}</span>
                              <span className="flex-1 text-white/80">{c.text}</span>
                              {job.captionsAutoGenerated && (
                                <span className="text-[10px] text-brand-400/60 shrink-0">auto</span>
                              )}
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  </motion.div>
                )}

                {activeTab === "branding" && (
                  <motion.div key="branding" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-4">
                    {/* Mute */}
                    <div className="card flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium">Mute original audio</p>
                        <p className="text-xs text-white/40 mt-0.5">Remove video sound — keep background music only</p>
                      </div>
                      <button
                        onClick={handleMuteToggle}
                        className={`relative w-11 h-6 rounded-full transition-colors ${job.muteAudio ? "bg-brand-500" : "bg-white/10"}`}
                      >
                        <span className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-all ${job.muteAudio ? "left-6" : "left-1"}`} />
                      </button>
                    </div>

                    {/* Logo */}
                    <div className="card space-y-3">
                      <p className="text-sm font-medium">Logo / Watermark</p>
                      <label className="flex items-center gap-3 cursor-pointer bg-white/5 hover:bg-white/10 transition-colors rounded-xl px-4 py-3">
                        <span className="text-xs text-white/60">{job.logoFile ? "✓ Logo uploaded — upload again to replace" : "Upload PNG / JPG (transparent PNGs work best)"}</span>
                        <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={handleLogoUpload} />
                        <span className="ml-auto text-xs text-brand-400 font-medium shrink-0">Browse</span>
                      </label>
                      <div>
                        <p className="text-xs text-white/40 mb-2">Position</p>
                        <div className="grid grid-cols-2 gap-2">
                          {([
                            { key: "top_left",     label: "↖ Top left" },
                            { key: "top_right",    label: "↗ Top right" },
                            { key: "bottom_left",  label: "↙ Bottom left" },
                            { key: "bottom_right", label: "↘ Bottom right" },
                          ] as { key: Job["logoPosition"]; label: string }[]).map(({ key, label }) => (
                            <button
                              key={key}
                              onClick={() => handleLogoPosition(key!)}
                              className={`py-2 px-3 rounded-lg text-xs font-medium border transition-all ${
                                (job.logoPosition ?? "bottom_right") === key
                                  ? "border-brand-500 bg-brand-500/15 text-brand-400"
                                  : "border-white/10 text-white/50 hover:text-white"
                              }`}
                            >
                              {label}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Export format */}
                    <div className="card space-y-3">
                      <p className="text-sm font-medium">Export Format</p>
                      <div className="grid grid-cols-3 gap-2">
                        {([
                          { key: "reels",  label: "Instagram\nReels",  ar: "9:16" },
                          { key: "tiktok", label: "TikTok",            ar: "9:16" },
                          { key: "shorts", label: "YouTube\nShorts",   ar: "9:16" },
                        ] as { key: string; label: string; ar: string }[]).map(({ key, label, ar }) => (
                          <button
                            key={key}
                            onClick={() => { updateJob(jobId, { exportPreset: key as any, aspectRatio: ar }); mutate(); }}
                            className={`py-2.5 px-2 rounded-xl text-xs font-medium border transition-all text-center whitespace-pre-line ${
                              (job.exportPreset ?? "reels") === key
                                ? "border-brand-500 bg-brand-500/15 text-brand-400"
                                : "border-white/10 text-white/50 hover:text-white"
                            }`}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
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
