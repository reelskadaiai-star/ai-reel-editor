"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, Zap, Home, UtensilsCrossed, ShoppingBag } from "lucide-react";
import toast from "react-hot-toast";
import UploadZone from "@/components/upload/UploadZone";
import { uploadVideo } from "@/lib/api";

const SPECIALIZATIONS = [
  { icon: Home, label: "Real Estate", color: "from-blue-500 to-cyan-400", desc: "Luxury property reels" },
  { icon: UtensilsCrossed, label: "Food", color: "from-orange-500 to-red-400", desc: "Viral food content" },
  { icon: ShoppingBag, label: "Products", color: "from-purple-500 to-pink-400", desc: "Showcase anything" },
];

const STATS = [
  { value: "< 60s", label: "Avg render time" },
  { value: "AI", label: "Auto-editing" },
  { value: "₹20", label: "HD export" },
  { value: "9:16", label: "Reel-ready" },
];

export default function HomePage() {
  const router = useRouter();
  const [uploading, setUploading] = useState(false);

  async function handleUpload(file: File) {
    setUploading(true);
    try {
      const { jobId } = await uploadVideo(file);
      toast.success("Video uploaded! Analyzing…");
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
      </div>

      {/* Header */}
      <motion.header
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="flex items-center gap-2 mb-14"
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
        className="text-center max-w-lg mb-10"
      >
        <h1 className="text-4xl sm:text-5xl font-bold leading-tight mb-4">
          Upload video.<br />
          <span className="text-gradient">AI creates the reel.</span>
        </h1>
        <p className="text-white/50 text-lg">
          Real estate, food & product reels generated automatically in under a minute.
          No editing skills needed.
        </p>
      </motion.div>

      {/* Specializations */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.2 }}
        className="flex gap-3 mb-10 flex-wrap justify-center"
      >
        {SPECIALIZATIONS.map((s) => (
          <div key={s.label} className="flex items-center gap-2.5 glass rounded-full px-4 py-2">
            <div className={`w-6 h-6 rounded-full bg-gradient-to-br ${s.color} flex items-center justify-center`}>
              <s.icon className="w-3.5 h-3.5 text-white" />
            </div>
            <div>
              <p className="text-sm font-medium leading-none">{s.label}</p>
              <p className="text-xs text-white/40 mt-0.5">{s.desc}</p>
            </div>
          </div>
        ))}
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
        className="flex gap-6 mt-12 flex-wrap justify-center"
      >
        {STATS.map((s) => (
          <div key={s.label} className="text-center">
            <p className="text-2xl font-bold text-brand-400">{s.value}</p>
            <p className="text-xs text-white/40 mt-1">{s.label}</p>
          </div>
        ))}
      </motion.div>

      {/* Footer */}
      <p className="mt-12 text-xs text-white/20">
        Powered by open-source AI · FFmpeg · Whisper · CLIP
      </p>
    </main>
  );
}
