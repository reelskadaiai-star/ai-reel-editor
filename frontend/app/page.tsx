"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  Sparkles, Home, UtensilsCrossed, ShoppingBag,
  Dumbbell, Plane, Film, BookOpen, Laugh, Layers,
} from "lucide-react";
import toast from "react-hot-toast";
import UploadZone from "@/components/upload/UploadZone";
import { uploadVideo, uploadMultipleVideos } from "@/lib/api";

const SPECIALIZATIONS = [
  { icon: Home,           label: "Real Estate", color: "from-cyan-500 to-blue-400",    desc: "Luxury property reels" },
  { icon: UtensilsCrossed,label: "Food",         color: "from-orange-500 to-red-400",   desc: "Viral food content" },
  { icon: ShoppingBag,    label: "Products",     color: "from-purple-500 to-pink-400",  desc: "Showcase anything" },
  { icon: Dumbbell,       label: "Fitness",      color: "from-green-500 to-emerald-400",desc: "Workout reels" },
  { icon: Plane,          label: "Travel",       color: "from-sky-500 to-indigo-400",   desc: "Destination clips" },
  { icon: Film,           label: "Cinematic",    color: "from-amber-500 to-yellow-400", desc: "Film-grade edits" },
  { icon: BookOpen,       label: "Education",    color: "from-yellow-500 to-lime-400",  desc: "Tutorial clips" },
  { icon: Laugh,          label: "Comedy",       color: "from-red-500 to-rose-400",     desc: "Viral skits" },
];

const STATS = [
  { value: "< 60s",  label: "Avg render time" },
  { value: "12",     label: "Content types" },
  { value: "9",      label: "Transitions" },
  { value: "5 clips",label: "Multi-upload" },
];

export default function HomePage() {
  const router = useRouter();
  const [uploading, setUploading] = useState(false);

  async function handleUpload(files: File[]) {
    setUploading(true);
    try {
      let jobId: string;
      if (files.length === 1) {
        const res = await uploadVideo(files[0]);
        jobId = res.jobId;
        toast.success("Video uploaded! Analysing…");
      } else {
        const res = await uploadMultipleVideos(files);
        jobId = res.jobId;
        toast.success(`${res.clipCount} clips uploaded! Merging & analysing…`);
      }
      router.push(`/editor?id=${jobId}`);
    } catch (err: any) {
      toast.error(err?.response?.data?.error || "Upload failed. Try again.");
      setUploading(false);
    }
  }

  return (
    <main className="min-h-dvh flex flex-col items-center px-4 py-10 relative overflow-hidden">
      {/* Background blobs */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -left-40 w-96 h-96 bg-brand-500/10 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -right-40 w-96 h-96 bg-accent-purple/10 rounded-full blur-3xl" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-brand-500/5 rounded-full blur-3xl" />
      </div>

      {/* Header */}
      <motion.header
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="flex items-center gap-2 mb-12"
      >
        <div className="w-9 h-9 rounded-xl bg-gradient-brand flex items-center justify-center shadow-lg shadow-brand-500/30">
          <Sparkles className="w-5 h-5 text-white" />
        </div>
        <span className="text-xl font-bold tracking-tight">ReelAI</span>
        <span className="badge bg-brand-500/15 text-brand-400 ml-1">Beta</span>
      </motion.header>

      {/* Hero text */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1 }}
        className="text-center max-w-lg mb-8"
      >
        <h1 className="text-4xl sm:text-5xl font-bold leading-tight mb-4">
          Upload video.<br />
          <span className="text-gradient">AI creates the reel.</span>
        </h1>
        <p className="text-white/50 text-lg">
          Auto-edit, colour grade, add captions, music &amp; transitions.
          Upload up to 5 clips and get a viral-ready reel.
        </p>
      </motion.div>

      {/* Content types — scrolling chips */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2 }}
        className="flex gap-2 mb-8 flex-wrap justify-center max-w-lg"
      >
        {SPECIALIZATIONS.map((s) => (
          <div key={s.label} className="flex items-center gap-2 glass rounded-full px-3 py-1.5">
            <div className={`w-5 h-5 rounded-full bg-gradient-to-br ${s.color} flex items-center justify-center`}>
              <s.icon className="w-3 h-3 text-white" />
            </div>
            <span className="text-xs font-medium">{s.label}</span>
          </div>
        ))}
        <div className="flex items-center gap-2 glass rounded-full px-3 py-1.5">
          <Layers className="w-4 h-4 text-white/40" />
          <span className="text-xs font-medium text-white/60">+ more</span>
        </div>
      </motion.div>

      {/* Upload zone */}
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.3 }}
        className="w-full max-w-md"
      >
        <UploadZone onUpload={handleUpload} loading={uploading} />
      </motion.div>

      {/* Stats */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
        className="flex gap-6 mt-10 flex-wrap justify-center"
      >
        {STATS.map((s) => (
          <div key={s.label} className="text-center">
            <p className="text-xl font-bold text-brand-400">{s.value}</p>
            <p className="text-xs text-white/40 mt-1">{s.label}</p>
          </div>
        ))}
      </motion.div>

      <p className="mt-10 text-xs text-white/20">
        Powered by open-source AI · FFmpeg · Whisper · CLIP · xfade
      </p>
    </main>
  );
}
