// Server component wrapper.
// generateStaticParams must live here (server component) while the actual UI
// is in EditorPageClient.tsx ("use client"). Next.js static analysis requires
// an explicit function export — re-export syntax is not detected.
import EditorPageClient from "./EditorPageClient";

export function generateStaticParams() {
  return [];
}

export default function EditorPage() {
  return <EditorPageClient />;
}
