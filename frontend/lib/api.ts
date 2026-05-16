import axios from "axios";
import type { Job } from "./types";

// In static export (Cloudflare Pages), all calls go directly to the Render backend.
// NEXT_PUBLIC_API_URL is baked in at build time via CF Pages env vars.
const BASE_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000")
    : (process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000");

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  withCredentials: false,
});

// Attach auth token if present
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("reel_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Global error normaliser
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      if (typeof window !== "undefined") localStorage.removeItem("reel_token");
    }
    return Promise.reject(err);
  }
);

export async function uploadVideo(file: File): Promise<{ jobId: string }> {
  const fd = new FormData();
  fd.append("video", file);
  const { data } = await api.post<{ jobId: string; status: string }>("/api/upload", fd, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120_000,
  });
  return data;
}

export async function fetchJob(jobId: string): Promise<Job> {
  const { data } = await api.get<Job>(`/api/jobs/${jobId}`);
  return data;
}

export async function renderJob(jobId: string, overrides?: Partial<Job>): Promise<void> {
  await api.post(`/api/jobs/${jobId}/render`, overrides || {});
}

export async function updateJob(jobId: string, updates: Partial<Job>): Promise<Job> {
  const { data } = await api.patch<Job>(`/api/jobs/${jobId}`, updates);
  return data;
}

export async function fetchTemplates(contentType?: string): Promise<any[]> {
  const params = contentType ? { contentType } : {};
  const { data } = await api.get("/api/templates", { params });
  return data;
}

export async function loginAnonymous(): Promise<string> {
  const { data } = await api.post<{ token: string }>("/api/auth/anonymous");
  if (typeof window !== "undefined") localStorage.setItem("reel_token", data.token);
  return data.token;
}

export default api;
