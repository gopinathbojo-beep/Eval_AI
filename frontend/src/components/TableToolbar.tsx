import type { ReactNode } from "react";
import type { SortOrder } from "../hooks/useTableState";

export interface FilterOption {
  label: string;
  value: string;
}

export interface FilterConfig {
  key: string;
  label: string;
  options: FilterOption[];
  value: string;
  onChange: (value: string) => void;
}

export interface SortOption {
  label: string;
  value: string;
}

export interface TableToolbarProps {
  searchPlaceholder?: string;
  searchValue: string;
  onSearchChange: (value: string) => void;
  filters?: FilterConfig[];
  sortOptions: SortOption[];
  sortValue: string;
  onSortChange: (value: string) => void;
  sortOrder: SortOrder;
  onSortOrderToggle: () => void;
  isFiltered: boolean;
  onClearFilters: () => void;
  totalCount: number;
  filteredCount: number;
  itemLabel?: string;
  extraActions?: ReactNode;
}

export function TableToolbar({
  searchPlaceholder = "Search...",
  searchValue,
  onSearchChange,
  filters = [],
  sortOptions,
  sortValue,
  onSortChange,
  sortOrder,
  onSortOrderToggle,
  isFiltered,
  onClearFilters,
  totalCount,
  filteredCount,
  itemLabel = "items",
  extraActions,
}: TableToolbarProps) {
  return (
    <div className="mb-4 space-y-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        {/* Left: Search input */}
        <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
          <svg
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-mute"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            type="text"
            value={searchValue}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder}
            className="w-full rounded-md border border-line bg-surface py-1.5 pl-9 pr-8 text-sm text-ink placeholder:text-mute focus:border-pen focus:outline-none focus:ring-1 focus:ring-pen"
          />
          {searchValue && (
            <button
              type="button"
              onClick={() => onSearchChange("")}
              aria-label="Clear search"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-mute hover:text-ink"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        {/* Right / Middle: Filters, Sort, Clear */}
        <div className="flex flex-wrap items-center gap-2">
          {filters.map((f) => {
            const hasVal = Boolean(f.value);
            return (
              <div key={f.key} className="relative">
                <select
                  value={f.value}
                  onChange={(e) => f.onChange(e.target.value)}
                  aria-label={f.label}
                  className={`h-9 rounded-md border text-sm py-1.5 pl-2.5 pr-8 focus:border-pen focus:outline-none focus:ring-1 focus:ring-pen ${
                    hasVal
                      ? "border-pen bg-pen-soft/20 font-medium text-pen"
                      : "border-line bg-surface text-ink"
                  }`}
                >
                  <option value="">{f.label}</option>
                  {f.options.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            );
          })}

          {/* Sort By Dropdown */}
          <div className="flex items-center gap-1">
            <select
              value={sortValue}
              onChange={(e) => onSortChange(e.target.value)}
              aria-label="Sort by"
              className="h-9 rounded-md border border-line bg-surface py-1.5 pl-2.5 pr-8 text-sm text-ink focus:border-pen focus:outline-none focus:ring-1 focus:ring-pen"
            >
              {sortOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  Sort: {opt.label}
                </option>
              ))}
            </select>

            {/* Sort Order Toggle */}
            <button
              type="button"
              onClick={onSortOrderToggle}
              title={`Sorting ${sortOrder === "asc" ? "Ascending" : "Descending"}. Click to toggle.`}
              aria-label={`Sorting ${sortOrder === "asc" ? "Ascending" : "Descending"}. Click to toggle.`}
              className="inline-flex h-9 items-center gap-1 rounded-md border border-line bg-surface px-2.5 text-xs font-medium text-ink hover:bg-sunken focus:border-pen focus:outline-none"
            >
              <svg
                className={`h-4 w-4 transition-transform ${sortOrder === "desc" ? "rotate-180" : ""}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12" />
              </svg>
              <span>{sortOrder === "asc" ? "Asc" : "Desc"}</span>
            </button>
          </div>

          {/* Clear Filters Button */}
          {Boolean(isFiltered !== undefined ? isFiltered : (Boolean(searchValue?.trim()) || filters.some((f) => Boolean(f.value?.trim())))) && (
            <button
              type="button"
              onClick={onClearFilters}
              aria-label="Clear all active filters and search"
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-line bg-sunken px-2.5 text-xs font-medium text-mute hover:bg-line hover:text-ink focus:border-pen focus:outline-none transition-colors"
            >
              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
              <span>Clear Filters</span>
            </button>
          )}

          {extraActions}
        </div>
      </div>

      {/* Result Count and Active Filters Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-mute">
        <div>
          {Boolean(isFiltered !== undefined ? isFiltered : (Boolean(searchValue?.trim()) || filters.some((f) => Boolean(f.value?.trim())))) ? (
            <span>
              Showing <strong className="text-ink">{filteredCount}</strong> of{" "}
              <strong className="text-ink">{totalCount}</strong> {itemLabel}
            </span>
          ) : (
            <span>
              <strong className="text-ink">{totalCount}</strong> {itemLabel} total
            </span>
          )}
        </div>

        {/* Active Filter Tags */}
        {Boolean(isFiltered !== undefined ? isFiltered : (Boolean(searchValue?.trim()) || filters.some((f) => Boolean(f.value?.trim())))) && (
          <div className="flex flex-wrap items-center gap-1.5">
            {searchValue.trim() && (
              <span className="inline-flex items-center gap-1 rounded bg-sunken px-2 py-0.5 text-ink">
                Search: &ldquo;{searchValue}&rdquo;
                <button
                  type="button"
                  onClick={() => onSearchChange("")}
                  className="hover:text-mark ml-0.5"
                  aria-label="Remove search filter"
                >
                  ✕
                </button>
              </span>
            )}
            {filters
              .filter((f) => Boolean(f.value && f.value.trim() !== ""))
              .map((f) => {
                const optLabel = f.options.find((o) => o.value === f.value)?.label || f.value;
                return (
                  <span
                    key={f.key}
                    className="inline-flex items-center gap-1 rounded bg-pen-soft px-2 py-0.5 text-pen font-medium"
                  >
                    {f.label}: {optLabel}
                    <button
                      type="button"
                      onClick={() => f.onChange("")}
                      className="hover:text-mark ml-0.5"
                      aria-label={`Remove ${f.label} filter`}
                    >
                      ✕
                    </button>
                  </span>
                );
              })}
          </div>
        )}
      </div>
    </div>
  );
}

export interface TablePaginationProps {
  currentPage: number;
  totalPages: number;
  pageSize: number;
  pageSizeOptions?: number[];
  totalFilteredCount: number;
  itemLabel?: string;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

export function TablePagination({
  currentPage,
  totalPages,
  pageSize,
  pageSizeOptions = [10, 25, 50, 100],
  totalFilteredCount,
  itemLabel = "records",
  onPageChange,
  onPageSizeChange,
}: TablePaginationProps) {
  if (totalFilteredCount === 0) return null;

  const startRecord = (currentPage - 1) * pageSize + 1;
  const endRecord = Math.min(currentPage * pageSize, totalFilteredCount);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3 text-xs text-mute">
      <div>
        Showing <span className="font-medium text-ink">{startRecord}</span> to{" "}
        <span className="font-medium text-ink">{endRecord}</span> of{" "}
        <span className="font-medium text-ink">{totalFilteredCount}</span> {itemLabel}
      </div>

      <div className="flex flex-wrap items-center gap-4">
        {/* Page size dropdown */}
        <div className="flex items-center gap-1.5">
          <span>Rows per page:</span>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            aria-label="Rows per page"
            className="rounded border border-line bg-surface py-1 pl-2 pr-6 text-xs text-ink focus:border-pen focus:outline-none"
          >
            {pageSizeOptions.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
        </div>

        {/* Page Navigation */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            disabled={currentPage <= 1}
            onClick={() => onPageChange(currentPage - 1)}
            aria-label="Previous page"
            className="rounded border border-line bg-surface p-1 text-ink hover:bg-sunken disabled:opacity-40 disabled:hover:bg-surface"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>

          <span className="px-2 font-medium text-ink">
            Page {currentPage} of {totalPages}
          </span>

          <button
            type="button"
            disabled={currentPage >= totalPages}
            onClick={() => onPageChange(currentPage + 1)}
            aria-label="Next page"
            className="rounded border border-line bg-surface p-1 text-ink hover:bg-sunken disabled:opacity-40 disabled:hover:bg-surface"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

export function FilteredEmptyState({
  title = "No matching records found",
  message = "Try adjusting your search query or clearing active filters to see results.",
  onClearFilters,
}: {
  title?: string;
  message?: string;
  onClearFilters: () => void;
}) {
  return (
    <div className="rounded-lg border border-dashed border-line p-8 text-center bg-surface">
      <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-sunken text-mute">
        <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.75}
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
      </div>
      <p className="font-semibold text-ink">{title}</p>
      <p className="mt-1 text-xs text-mute max-w-sm mx-auto">{message}</p>
      <div className="mt-4">
        <button
          type="button"
          onClick={onClearFilters}
          className="rounded-md bg-pen px-3.5 py-1.5 text-xs font-medium text-surface hover:opacity-90 transition-opacity"
        >
          Clear Filters
        </button>
      </div>
    </div>
  );
}
