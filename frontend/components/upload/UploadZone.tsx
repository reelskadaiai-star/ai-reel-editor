"use client";
import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, Film, Loader2, CheckCircle } from "lucide-react";
import clsx from "clsx";

interface Props {
  onUpload: (file: File) => Promise<void>;
  loading?: boolean;
}

const ACCEPTED = { "video/*": [".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"] };
const MAX_SIZE = 500 * 1024 * 1024; // 500 MB

export default function UploadZone({ onUpload, loading }: Props) {
  const [preview, setPreview] = useState<{ name: string; size: string } | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const onDrop = useCallback(
    (accepted: File[], rejected: any[]) => {
      setLocalError(null);
      if (rejected.length) {
        const err = rejected[0].errors[0];
        setLocalError(err.code === "file-too-large" ? "File too large (max 500 MB)" : err.message);
        return;
      }
      if (!accepted[0]) return;
      const f = accepted[0];
      setPreview({ name: f.name, size: fmtBytes(f.size) });
      onUpload(f);
    },
    [onUpload]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED,
    maxFiles: 1,
    maxSize: MAX_SIZE,
    disabled: loading,
    noClick: loading,
  });

  return (
    <div className="w-full">
      <div
        {...getRootProps()}
        className={clsx(
          "relative flex flex-col items-center justify-center gap-4",
          "border-2 border-dashed rounded-2xl p-10 cursor-pointer",
          "transition-all duration-200",
          isDragActive
            ? "drop-active border-brand-500"
            : "border-white/10 hover:border-white/20 hover:bg-white/[0.02]",
          loading && "cursor-not-allowed opacity-70"
        )}
      >
        <input {...getInputProps()} />

        <AnimatePresence mode="wait">
          {loading ? (
            <motion.div
              key="loading"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              className="flex flex-col items-center gap-3"
            >
              <div className="w-16 h-16 rounded-2xl bg-brand-500/15 flex items-center justify-center">
                <Loader2 className="w-8 h-8 text-brand-400 animate-spin" />
              </div>
              <div className="text-center">
                <p className="font-semibold text-white">Uploading{preview ? ` ${preview.name}` : "…"}</p>
                {preview && <p className="text-sm text-white/40 mt-1">{preview.size}</p>}
              </div>
            </motion.div>
          ) : isDragActive ? (
            <motion.div
              key="drop"
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex flex-col items-center gap-3"
            >
              <div className="w-16 h-16 rounded-2xl bg-brand-500/20 flex items-center justify-center">
                <Film className="w-8 h-8 text-brand-400" />
              </div>
              <p className="font-semibold text-brand-400">Drop to upload</p>
            </motion.div>
          ) : (
            <motion.div
              key="idle"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex flex-col items-center gap-4 text-center"
            >
              <div className="w-16 h-16 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center">
                <Upload className="w-7 h-7 text-white/40" />
              </div>
              <div>
                <p className="font-semibold text-white">Drop your video here</p>
                <p className="text-sm text-white/40 mt-1">or tap to browse</p>
              </div>
              <div className="flex gap-2 flex-wrap justify-center">
                {["MP4", "MOV", "AVI", "MKV"].map((f) => (
                  <span key={f} className="badge bg-white/5 text-white/40">{f}</span>
                ))}
              </div>
              <p className="text-xs text-white/20">Max 500 MB</p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {localError && (
          <motion.p
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="text-red-400 text-sm mt-3 text-center"
          >
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
