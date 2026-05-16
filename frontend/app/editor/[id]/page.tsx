// Server component wrapper.
// Static export requires at least one known param — we use a placeholder.
// Real /editor/[uuid] traffic is caught by the CF Pages _redirects fallback
// (/* → index.html), then the client router runs LegacyRedirect which
// does router.replace('/editor?id=<uuid>').
import LegacyRedirect from "./LegacyRedirect";

export function generateStaticParams() {
  return [{ id: "__placeholder__" }];
}

export default function LegacyEditorPage() {
  return <LegacyRedirect />;
}
