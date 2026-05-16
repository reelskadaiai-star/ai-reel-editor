// Server component wrapper.
// generateStaticParams must live in a server component; the actual UI is in
// EditorPageClient.tsx (which has "use client" at the top).
// Dynamic job IDs (UUIDs) are not known at build time — the Cloudflare Pages
// _redirects fallback serves index.html for unknown /editor/* paths so the
// Next.js client-side router hydrates and renders EditorPageClient.
export function generateStaticParams() {
  return [];
}

export { default } from "./EditorPageClient";
