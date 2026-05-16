"use client";
import { motion } from "framer-motion";
import { X, Download, Film } from "lucide-react";
import type { Job } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000";

interface Props {
  job: Job;
  onClose: () => void;
}

export default function ExportModal({ job, onClose }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ y: "100%", opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: "100%", opacity: 0 }}
        transition={{ type: "spring", damping: 30, stiffness: 300 }}
        className="w-full max-w-sm glass rounded-3xl p-6 space-y-6"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold">Export Reel</h2>
          <button onClick={onClose} className="btn-ghost p-2 rounded-full">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex flex-col items-center gap-5 py-2">
          <div className="w-20 h-20 rounded-full bg-brand-500/15 flex items-center justify-center">
            <Film className="w-10 h-10 text-brand-400" />
          </div>
          <div className="text-center">
            <p className="font-bold text-lg">Your reel is ready!</p>
            <p className="text-sm text-white/40 mt-1">1080×1920 HD · Free download</p>
          </div>
          <a
            href={`${API}/api/jobs/${job.jobId}/download`}
            download
            className="btn-primary w-full flex items-center justify-center gap-2"
          >
            <Download className="w-5 h-5" />
            Download Reel
          </a>
        </div>
      </motion.div>
    </motion.div>
  );
}
