"use client";
import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, Film, Loader2, X, Layers } from "lucide-react";
import clsx from "clsx";

interface Props {
  onUpload: (files: File[]) => Promise<void>;
  loading?: boolean;
}

const ACCEPTED = { "video/*": [".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"] };
const MAX_SIZE = 500 * 1024 * 1024;
const MAX_FILES = 5;

export default function UploadZone({ onUpload, loading }: Props) {
  const [queued, setQueued] = useState<File[]>([]);
  const [localError, setLocalError] = useState<string | null>(null);

  const onDrop = useCallback(
    (accepted: File[], rejected: any[]) => {
      setLocalError(null);
      if (rejected.length) {
        const err = rejected[0].errors[0];
        setLocalError(err.code === "file-too-large" ? "File too large (max 500 MB each)" : err.message);
        return;
      }
      if (!accepted.length) return;
      setQueued((prev) => [...prev, ...accepted].slice(0, MAX_FILES));
    },
    []
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    maxFiles: MAX_FILES,
    maxSize: MAX_SIZE,
    disabled: loading,
    noClick: loading || queued.length >= MAX_FILES,
  });

  async function handleGo() {
    if (!queued.length || loading) return;
    await onUpload(queued);
  }

  function removeFile(i: number) {
    setQueued((prev) => prev.filter((_, idx) => idx !== i));
  }

  return (
    <div className="w-full space-y-3">
      <div
        {...getRootProps()}
        className={clsx(
          "relative flex flex-col items-center justify-center gap-4",
          "border-2 border-dashed rounded-2xl p-8 cursor-pointer transition-all duration-200",
          isDragActive
            ? "drop-active border-brand-500 bg-brand-500/5"
            : queued.length > 0
            ? "border-white/20 bg-white/[0.02]"
            : "border-white/10 hover:border-white/20 hover:bg-white/[0.02]",
          (loading || queued.length >= MAX_FILES) && "cursor-not-allowed opacity-70"
        )}
      >
        <input {...getInputProps()} />

        <AnimatePresence mode="wait">
          {loading ? (
            <motion.div key="loading" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center gap-3">
              <div className="w-16 h-16 rounded-2xl bg-brand-500/15 flex items-center justify-center">
                <Loader2 className="w-8 h-8 text-brand-400 animate-spin" />
              </div>
              <p className="font-semibold text-white">
                {queued.length > 1 ? `Uploading ${queued.length} clips…` : "Uploading…"}
              </p>
            </motion.div>
          ) : isDragActive ? (
            <motion.div key="drop" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col items-center gap-3">
              <div className="w-16 h-16 rounded-2xl bg-brand-500/20 flex items-center justify-center">
                <Film className="w-8 h-8 text-brand-400" />
              </div>
              <p className="font-semibold text-brand-400">Drop to add clip</p>
            </motion.div>
          ) : queued.length === 0 ? (
            <motion.div key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center gap-4 text-center">
              <div className="w-16 h-16 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center">
                <Upload className="w-7 h-7 text-white/40" />
              </div>
              <div>
                <p className="font-semibold text-white">Drop your video here</p>
                <p className="text-sm text-white/40 mt-1">or tap to browse — up to {MAX_FILES} clips</p>
              </div>
              <div className="flex gap-2 flex-wrap justify-center">
                {["MP4", "MOV", "AVI", "MKV", "WEBM"].map((f) => (
                  <span key={f} className="badge bg-white/5 text-white/40">{f}</span>
                ))}
              </div>
              <p className="text-xs text-white/20">Max 500 MB per clip</p>
            </motion.div>
          ) : (
            <motion.div key="queued" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center gap-2 text-center w-full">
              <div className="w-10 h-10 rounded-xl bg-brand-500/15 flex items-center justify-center mb-1">
                <Layers className="w-5 h-5 text-brand-400" />
              </div>
              <p className="text-sm font-semibold text-white">{queued.length} clip{queued.length > 1 ? "s" : ""} ready</p>
              {queued.length < MAX_FILES && (
                <p className="text-xs text-white/40">Drop more or tap to add (max {MAX_FILES})</p>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* File list + Go button */}
      <AnimatePresence>
        {queued.length > 0 && !loading && (
          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-2">
            {queued.map((f, i) => (
              <motion.div
                key={f.name + i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 10 }}
                className="flex items-center gap-3 glass rounded-xl px-4 py-3"
              >
                <Film className="w-4 h-4 text-brand-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{f.name}</p>
                  <p className="text-xs text-white/40">{fmtBytes(f.size)}</p>
                </div>
                {queued.length > 1 && <span className="text-xs text-white/30 shrink-0">Clip {i + 1}</span>}
                <button
                  onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                  className="p-1 rounded-lg hover:bg-white/10 transition-colors ml-1"
                >
                  <X className="w-3.5 h-3.5 text-white/40" />
                </button>
              </motion.div>
            ))}

            <button onClick={handleGo} className="btn-primary w-full py-3 flex items-center justify-center gap-2">
              {queued.length === 1 ? "Analyse Video →" : `Merge & Analyse ${queued.length} Clips →`}
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {localError && (
          <motion.p initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="text-red-400 text-sm text-center">
            {localError}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}

function fmtBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
