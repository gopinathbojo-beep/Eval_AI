import { useEffect, useState, type ReactNode } from "react";
import type { BBox, PageInfo } from "../types";
import { useBlobUrl } from "./AuthImage";
import { Button } from "./ui";
import {
  IconChevronLeft,
  IconChevronRight,
  IconZoomIn,
  IconZoomOut,
  IconRotateCcw,
  IconAlertCircle,
  IconInfo,
} from "./Icons";

/** Original uploaded page with synchronized page navigation, zoom controls, and highlight box. */
export function PageViewer({
  kind,
  docId,
  pages,
  page,
  onPage,
  highlight,
  actions,
}: {
  kind: string;
  docId: string;
  pages: PageInfo[];
  page: number;
  onPage: (n: number) => void;
  highlight?: BBox | null;
  actions?: ReactNode;
}) {
  const info = pages.find((p) => p.page_number === page) ?? pages[0];
  const { url, failed } = useBlobUrl(
    info ? `/documents/${kind}/${docId}/pages/${info.page_number}/image` : null
  );
  const [zoom, setZoom] = useState(1);

  // Reset zoom whenever page changes
  useEffect(() => {
    setZoom(1);
  }, [page]);

  if (!info) return null;

  return (
    <div className="flex h-full flex-col bg-surface select-none">
      {/* Viewer Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface px-3.5 py-2.5 text-sm shadow-xs">
        {/* Single Consolidated Previous/Next Page Navigation */}
        <div className="flex items-center gap-1.5">
          <Button
            small
            variant="secondary"
            disabled={page <= 1}
            onClick={() => onPage(page - 1)}
            aria-label="Previous page"
            icon={<IconChevronLeft size={15} />}
          >
            <span className="hidden sm:inline">Prev</span>
          </Button>
          <div className="flex items-center rounded-lg border border-line bg-sunken px-2.5 py-1 text-xs font-semibold text-ink">
            Page {info.page_number} of {pages.length}
          </div>
          <Button
            small
            variant="secondary"
            disabled={page >= pages.length}
            onClick={() => onPage(page + 1)}
            aria-label="Next page"
            icon={<IconChevronRight size={15} />}
          >
            <span className="hidden sm:inline">Next</span>
          </Button>
        </div>

        {/* Right side: Actions & Zoom */}
        <div className="flex items-center gap-2">
          {actions}
          <div className="flex items-center rounded-lg border border-line bg-sunken/60 p-0.5">
            <button
              type="button"
              onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}
              aria-label="Zoom out"
              className="rounded p-1 text-mute transition-colors hover:bg-surface hover:text-ink disabled:opacity-40"
              disabled={zoom <= 0.5}
            >
              <IconZoomOut size={15} />
            </button>
            <button
              type="button"
              onClick={() => setZoom(1)}
              title="Reset zoom to 100%"
              className="px-2 text-xs font-semibold font-mono text-ink hover:text-pen"
            >
              {Math.round(zoom * 100)}%
            </button>
            <button
              type="button"
              onClick={() => setZoom((z) => Math.min(3, z + 0.25))}
              aria-label="Zoom in"
              className="rounded p-1 text-mute transition-colors hover:bg-surface hover:text-ink disabled:opacity-40"
              disabled={zoom >= 3}
            >
              <IconZoomIn size={15} />
            </button>
            {zoom !== 1 && (
              <button
                type="button"
                onClick={() => setZoom(1)}
                title="Reset zoom"
                aria-label="Reset zoom"
                className="ml-0.5 rounded border-l border-line pl-1.5 pr-1 text-mute hover:text-ink"
              >
                <IconRotateCcw size={13} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Viewport Canvas with Independent Scroll */}
      <div className="relative min-h-0 flex-1 overflow-auto bg-slate-900/5 p-4 dark:bg-slate-950/40">
        {failed && (
          <div className="flex h-64 flex-col items-center justify-center gap-2 text-center text-mark">
            <IconAlertCircle size={28} />
            <p className="text-sm font-medium">Page image could not be loaded.</p>
          </div>
        )}
        {!url && !failed && (
          <div className="flex h-96 w-full animate-pulse items-center justify-center rounded-xl bg-sunken/80 text-mute">
            <p className="text-xs font-medium">Loading high-resolution document scan...</p>
          </div>
        )}
        {url && (
          <div
            className="relative mx-auto rounded-lg shadow-md transition-all duration-150 ease-out"
            style={{ width: `${zoom * 100}%`, maxWidth: zoom <= 1 ? "100%" : "none" }}
          >
            <img
              src={url}
              alt={`Document page ${info.page_number}`}
              className="block w-full rounded-lg bg-surface object-contain"
            />
            {highlight && highlight.width > 0 && info.width > 0 && info.height > 0 && (
              <div
                className="pointer-events-none absolute rounded border-2 border-mark bg-mark/15 ring-2 ring-mark/30 transition-all duration-200"
                style={{
                  left: `${(highlight.x / info.width) * 100}%`,
                  top: `${(highlight.y / info.height) * 100}%`,
                  width: `${(highlight.width / info.width) * 100}%`,
                  height: `${(highlight.height / info.height) * 100}%`,
                }}
              />
            )}
          </div>
        )}
      </div>

      {/* Contextual Annotation Footer */}
      {highlight && highlight.width > 0 && (
        <div className="flex items-center gap-2 border-t border-line bg-sunken/40 px-3.5 py-1.5 text-xs text-mute">
          <IconInfo size={14} className="shrink-0 text-pen" />
          <span>The red border highlights the approximate crop detected by OCR on this page.</span>
        </div>
      )}
    </div>
  );
}
