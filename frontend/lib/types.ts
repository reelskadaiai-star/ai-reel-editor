export interface Caption {
  start: number;
  end: number;
  text: string;
  style: string;
}

export interface Segment {
  start: number;
  end: number;
  score: number;
  type: "highlight" | "dead" | "normal" | "transition" | "beat";
  label: string;
}

export interface Job {
  _id: string;
  jobId: string;
  userId: string;
  status: "queued" | "analyzing" | "rendering" | "done" | "failed";
  progress: number;
  stage: string;

  // Input
  inputFile: string;
  durationSeconds?: number;
  fileSizeBytes?: number;

  // Analysis
  contentType: string;
  confidence?: number;
  segments?: Segment[];
  captions?: Caption[];
  beatTimestamps?: number[];
  dominantColors?: string[];
  sceneCount?: number;

  // Edit config
  template: string;
  musicFile?: string;
  aspectRatio: string;
  captionStyle: string;
  transitionStyle: string;
  targetDurationSec: number;
  hookText?: string;
  includeHookText: boolean;

  // Output
  outputFile?: string;
  watermarkedFile?: string;
  thumbnailFile?: string;

  // Payment
  paid: boolean;
  paymentOrderId?: string;
  paymentId?: string;

  error?: string;
  createdAt: string;
  updatedAt: string;
}
