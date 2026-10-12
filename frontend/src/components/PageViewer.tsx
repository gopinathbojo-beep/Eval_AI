import { useEffect, useState, type ReactNode } from "react";
import type { BBox, PageInfo } from "../types";
import { useBlobUrl } from "./AuthImage";
import { Button } from "./ui";

/** Original page with an optional highlight box (bbox is in full-resolution page pixels). */
export function PageViewer({ kind, docId, pages, page, onPage, highlight, actions }: {
  kind: string; docId: string; pages: PageInfo[]; page: number; onPage: (n: number) => void; highlight?: BBox | null; actions?: ReactNode;
}) {
  const info = pages.find((p) => p.page_number === page) ?? pages[0];
  const { url, failed } = useBlobUrl(info ? `/documents/${kind}/${docId}/pages/${info.page_number}/image` : null);
  const [zoom, setZoom] = useState(1);
  useEffect(() => setZoom(1), [page]);
  if (!info) return null;
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-line px-3 py-2 text-sm">
        <div className="flex items-center gap-1">
          <Button small disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page">‹</Button>
          <span className="px-2">Page {info.page_number} of {pages.length}</span>
          <Button small disabled={page >= pages.length} onClick={() => onPage(page + 1)} aria-label="Next page">›</Button>
        </div>
        <div className="flex items-center gap-2">
          {actions}
          <div className="flex items-center gap-1">
            <Button small onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))} aria-label="Zoom out">−</Button>
            <span className="w-12 text-center">{Math.round(zoom * 100)}%</span>
            <Button small onClick={() => setZoom((z) => Math.min(3, z + 0.25))} aria-label="Zoom in">+</Button>
          </div>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto bg-sunken p-3">
        {failed && <p className="text-sm text-mark">Page image could not be loaded.</p>}
        {!url && !failed && <div className="h-64 animate-pulse rounded bg-line" />}
        {url && (
          <div className="relative mx-auto" style={{ width: `${zoom * 100}%` }}>
            <img src={url} alt={`Page ${info.page_number}`} className="block w-full" />
            {highlight && highlight.width > 0 && (
              <div className="pointer-events-none absolute border-2 border-mark bg-mark/10"
                style={{ left: `${(highlight.x / info.width) * 100}%`, top: `${(highlight.y / info.height) * 100}%`,
                  width: `${(highlight.width / info.width) * 100}%`, height: `${(highlight.height / info.height) * 100}%` }} />
            )}
          </div>
        )}
      </div>
      {highlight && <p className="border-t border-line px-3 py-1.5 text-xs text-mute">Red box is where the model says this text is. It can be approximate, so check the page itself.</p>}
    </div>
  );
}
