"use client";
import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

// Redirects old /editor/[id] URLs to the new /editor?id=xxx format.
// Triggered by the _redirects fallback serving index.html, which lets
// the Next.js client router handle the path and run this component.
export default function LegacyRedirect() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  useEffect(() => {
    if (id && id !== "__placeholder__") {
      router.replace(`/editor?id=${id}`);
    } else {
      router.replace("/");
    }
  }, [id, router]);

  return null;
}
