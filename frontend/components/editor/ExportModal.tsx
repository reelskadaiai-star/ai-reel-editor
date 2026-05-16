"use client";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Download, Lock, CheckCircle, Loader2, Sparkles } from "lucide-react";
import toast from "react-hot-toast";
import api from "@/lib/api";
import type { Job } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000";

declare global {
  interface Window { Razorpay: any }
}

interface Props {
  job: Job;
  onClose: () => void;
}

type Step = "preview" | "paying" | "paid";

export default function ExportModal({ job, onClose }: Props) {
  const [step, setStep] = useState<Step>(job.paid ? "paid" : "preview");
  const [loading, setLoading] = useState(false);

  async function handlePay() {
    setLoading(true);
    try {
      const { data: order } = await api.post("/api/payment/create-order", { jobId: job.jobId });

      if (order.alreadyPaid) {
        setStep("paid");
        return;
      }

      const options = {
        key: order.key,
        amount: order.amount,
        currency: order.currency,
        name: "ReelAI",
        description: "HD Reel Export — watermark-free",
        order_id: order.orderId,
        prefill: {},
        theme: { color: "#5c7cfa" },
        handler: async (response: any) => {
          setStep("paying");
          try {
            await api.post("/api/payment/verify", {
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
              jobId: job.jobId,
            });
            setStep("paid");
            toast.success("Payment successful! Your HD reel is ready 🎉");
          } catch {
            toast.error("Payment verification failed. Contact support.");
            setStep("preview");
          }
        },
        modal: { ondismiss: () => setLoading(false) },
      };

      if (!window.Razorpay) {
        // Load Razorpay script dynamically
        await new Promise<void>((resolve) => {
          const s = document.createElement("script");
          s.src = "https://checkout.razorpay.com/v1/checkout.js";
          s.onload = () => resolve();
          document.body.appendChild(s);
        });
      }

      new window.Razorpay(options).open();
    } catch (err: any) {
      toast.error(err?.response?.data?.error || "Payment error");
    } finally {
      setLoading(false);
    }
  }

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
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold">Export Reel</h2>
          <button onClick={onClose} className="btn-ghost p-2 rounded-full">
            <X className="w-5 h-5" />
          </button>
        </div>

        <AnimatePresence mode="wait">
          {step === "preview" && (
            <motion.div key="preview" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-5">
              {/* Watermarked preview note */}
              <div className="bg-white/5 rounded-2xl p-4 flex items-start gap-3">
                <Lock className="w-5 h-5 text-white/40 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium">Watermark-free HD export</p>
                  <p className="text-xs text-white/40 mt-1">
                    Your reel is ready with a watermark. Pay once to get a clean 1080×1920 HD copy.
                  </p>
                </div>
              </div>

              {/* Pricing */}
              <div className="flex items-center justify-between bg-brand-500/10 border border-brand-500/20 rounded-2xl px-5 py-4">
                <div>
                  <p className="text-2xl font-bold">₹20</p>
                  <p className="text-xs text-white/40">One-time per reel</p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-brand-400 font-semibold">What you get</p>
                  <p className="text-xs text-white/50 mt-1">1080×1920 · No watermark · Forever yours</p>
                </div>
              </div>

              <button
                onClick={handlePay}
                disabled={loading}
                className="btn-primary w-full flex items-center justify-center gap-2 text-base py-4"
              >
                {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Sparkles className="w-5 h-5" />}
                {loading ? "Opening payment…" : "Pay ₹20 & Download"}
              </button>

              <p className="text-xs text-center text-white/20">
                Secured by Razorpay · UPI, Cards, Net Banking accepted
              </p>
            </motion.div>
          )}

          {step === "paying" && (
            <motion.div key="paying" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center gap-4 py-6">
              <Loader2 className="w-10 h-10 text-brand-400 animate-spin" />
              <p className="text-white/70">Verifying payment…</p>
            </motion.div>
          )}

          {step === "paid" && (
            <motion.div key="paid" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="flex flex-col items-center gap-5 py-4">
              <div className="w-20 h-20 rounded-full bg-green-500/15 flex items-center justify-center">
                <CheckCircle className="w-10 h-10 text-green-400" />
              </div>
              <div className="text-center">
                <p className="font-bold text-lg">Payment successful!</p>
                <p className="text-sm text-white/40 mt-1">Your HD reel is ready to download</p>
              </div>
              <a
                href={`${API}/api/jobs/${job.jobId}/download`}
                download
                className="btn-primary w-full flex items-center justify-center gap-2"
              >
                <Download className="w-5 h-5" />
                Download HD Reel
              </a>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </motion.div>
  );
}
