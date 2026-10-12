import { useEffect, useState } from "react";
import { fetchBlobUrl } from "../api/client";

export function useBlobUrl(path: string | null) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true, created: string | null = null;
    setUrl(null); setFailed(false);
    if (path) fetchBlobUrl(path).then((u) => { created = u; alive ? setUrl(u) : URL.revokeObjectURL(u); }).catch(() => alive && setFailed(true));
    return () => { alive = false; if (created) URL.revokeObjectURL(created); };
  }, [path]);
  return { url, failed };
}

export function AuthImage({ path, alt, className }: { path: string; alt: string; className?: string }) {
  const { url, failed } = useBlobUrl(path);
  if (failed) return <div className="p-4 text-sm text-mark">Image could not be loaded.</div>;
  if (!url) return <div className="h-24 animate-pulse rounded bg-sunken" />;
  return <img src={url} alt={alt} className={className} />;
}
