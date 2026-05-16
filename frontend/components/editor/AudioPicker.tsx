"use client";
import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { motion } from "framer-motion";
import { Music, Upload, CheckCircle, Loader2 } from "lucide-react";
import toast from "react-hot-toast";
import axios from "axios";
import clsx from "clsx";

interface Props {
  jobId: string;
  onSelect: () => void;
}

const SUGGESTED_MUSIC = [
  { id: "cinematic_ambient", label: "Cinematic Ambient", genre: "Ambient", bpm: 90 },
  { id: "upbeat_corporate", label: "Upbeat Corporate", genre: "Corporate", bpm: 120 },
  { id: "trending_pop", label: "Trending Pop Beat", genre: "Pop", bpm: 128 },
  { id: "trap_beat", label: "Trap Hype", genre: "Trap", bpm: 140 },
  { id: "calm_ambient", label: "Calm Ambient", genre: "Ambient", bpm: 70 },
  { id: "energetic_electronic", label: "Energetic Electronic", genre: "EDM", bpm: 132 },
];

export default function AudioPicker({ jobId, onSelect }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const onDrop = useCallback(
    async (accepted: File[]) => {
      if (!accepted[0]) return;
      setUploading(true);
      try {
        const fd = new FormData();
        fd.append("audio", accepted[0]);
        await axios.post(`/api/upload/audio/${jobId}`, fd);
        toast.success("Audio uploaded!");
        setSelected("custom");
        onSelect();
      } catch {
        toast.error("Audio upload failed");
      } finally {
        setUploading(false);
      }
    },
    [jobId, onSelect]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "audio/*": [".mp3", ".wav", ".m4a", ".aac"] },
    maxFiles: 1,
    disabled: uploading,
  });

  async function selectPreset(id: string) {
    setSelected(id);
    await axios.patch(`/api/jobs/${jobId}`, { musicFile: `presets/${id}.mp3` });
    toast.success("Music updated");
    onSelect();
  }

  return (
    <div className="space-y-4">
      {/* Upload custom */}
      <div
        {...getRootProps()}
        className={clsx(
          "flex items-center gap-3 border-2 border-dashed rounded-2xl p-4 cursor-pointer transition-all duration-150",
          isDragActive ? "border-brand-500 bg-brand-500/5" : "border-white/10 hover:border-white/20"
        )}
      >
        <input {...getInputProps()} />
        <div className="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center shrink-0">
          {uploading ? <Loader2 className="w-5 h-5 text-brand-400 animate-spin" /> : <Upload className="w-5 h-5 text-white/40" />}
        </div>
        <div>
          <p className="text-sm font-medium">Upload your audio</p>
          <p className="text-xs text-white/40">MP3, WAV, M4A · drag or tap</p>
        </div>
        {selected === "custom" && <CheckCircle className="w-5 h-5 text-brand-400 ml-auto" />}
      </div>

      {/* Preset suggestions */}
      <div>
        <p className="text-xs text-white/30 font-medium mb-3 uppercase tracking-wider">AI Suggestions</p>
        <div className="space-y-2">
          {SUGGESTED_MUSIC.map((m) => (
            <motion.button
              key={m.id}
              onClick={() => selectPreset(m.id)}
              className={`w-full flex items-center gap-3 p-3 rounded-xl border transition-all ${
                selected === m.id
                  ? "border-brand-500 bg-brand-500/10"
                  : "border-white/5 bg-white/[0.02] hover:border-white/10"
              }`}
              whileTap={{ scale: 0.98 }}
            >
              <div className="w-9 h-9 rounded-lg bg-white/5 flex items-center justify-center shrink-0">
                <Music className="w-4 h-4 text-white/50" />
              </div>
              <div className="flex-1 text-left">
                <p className="text-sm font-medium">{m.label}</p>
                <p className="text-xs text-white/30">{m.genre} · {m.bpm} BPM</p>
              </div>
              {selected === m.id && <CheckCircle className="w-4 h-4 text-brand-400" />}
            </motion.button>
          ))}
        </div>
      </div>
    </div>
  );
}
