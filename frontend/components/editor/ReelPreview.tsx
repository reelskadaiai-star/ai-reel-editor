"use client";
import { useState } from "react";
import { motion } from "framer-motion";
import { Play, Pause, Film } from "lucide-react";
import type { Job } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000";
function outputUrl(file: string) { return `${API}/outputs/${file}`; }

interface Props { job: Job | undefined }

export default function ReelPreview({ job }: Props) {
  const [playing, setPlaying] = useState(false);

  const hasPreview = !!(job?.outputFile || job?.watermarkedFile);
  const videoSrc = hasPreview
    ? outputUrl(job!.outputFile ?? job!.watermarkedFile!)
    : null;

  return (
    <div className="relative w-full max-w-[220px] mx-auto">
      {/* Phone frame */}
      <div className="relative rounded-[2rem] overflow-hidden bg-surface-800 border border-white/10 shadow-2xl aspect-[9/16]">
        {videoSrc ? (
          <>
            <video
              src={videoSrc}
              className="w-full h-full object-cover"
              loop
              playsInline
              muted
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              id="reel-preview-video"
            />
            {/* Play/pause overlay */}
            <button
              className="absolute inset-0 flex items-center justify-center bg-black/0 hover:bg-black/20 transition-colors"
              onClick={() => {
                const v = document.getElementById("reel-preview-video") as HTMLVideoElement;
                v?.paused ? v.play() : v.pause();
              }}
            >
              <motion.div
                initial={false}
                animate={{ opacity: playing ? 0 : 1, scale: playing ? 0.8 : 1 }}
                className="w-12 h-12 rounded-full bg-black/50 backdrop-blur flex items-center justify-center"
              >
                {playing ? <Pause className="w-5 h-5 text-white" /> : <Play className="w-5 h-5 text-white ml-0.5" />}
              </motion.div>
            </button>

          </>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-white/20">
            <Film className="w-10 h-10" />
            <p className="text-xs text-center px-4">
              {job?.status === "queued" || job?.status === "analyzing"
                ? "Analysing your video…"
                : job?.status === "rendering"
                ? "Rendering reel…"
                : "Preview will appear here"}
            </p>
          </div>
        )}

        {/* Notch */}
        <div className="absolute top-3 left-1/2 -translate-x-1/2 w-16 h-4 bg-surface-900 rounded-full" />
      </div>

      {/* Thumbnail strip */}
      {job?.thumbnailFile && (
        <img
          src={outputUrl(job.thumbnailFile)}
          alt="Thumbnail"
          className="mt-3 w-full rounded-xl object-cover aspect-video opacity-60"
        />
      )}
    </div>
  );
}
