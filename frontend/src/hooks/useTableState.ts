import { useEffect, useMemo, useState } from "react";

export type SortOrder = "asc" | "desc";

export interface UseTableStateOptions<T> {
  data: T[] | null | undefined;
  searchFilter: (item: T, query: string) => boolean;
  filters?: Record<string, (item: T, value: string) => boolean>;
  sortFns: Record<string, (a: T, b: T) => number>;
  defaultSort: string;
  defaultOrder?: SortOrder;
  initialPageSize?: number;
}

export function useTableState<T>({
  data,
  searchFilter,
  filters = {},
  sortFns,
  defaultSort,
  defaultOrder = "asc",
  initialPageSize = 10,
}: UseTableStateOptions<T>) {
  const [search, setSearch] = useState("");
  const [activeFilters, setActiveFilters] = useState<Record<string, string>>({});
  const [sortBy, setSortBy] = useState(defaultSort);
  const [sortOrder, setSortOrder] = useState<SortOrder>(defaultOrder);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(initialPageSize);

  // Set filter value
  const setFilter = (key: string, value: string) => {
    setActiveFilters((prev) => {
      const next = { ...prev };
      if (!value) delete next[key];
      else next[key] = value;
      return next;
    });
    setPage(1);
  };

  const handleSearchChange = (val: string) => {
    setSearch(val);
    setPage(1);
  };

  const handleSortChange = (key: string) => {
    setSortBy(key);
    setPage(1);
  };

  const handleSortOrderToggle = () => {
    setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    setPage(1);
  };

  const isFiltered = useMemo(() => {
    const hasSearch = search.trim().length > 0;
    const hasFilters = Object.values(activeFilters).some((v) => v !== "");
    const isNonDefaultSort = sortBy !== defaultSort || sortOrder !== defaultOrder;
    return hasSearch || hasFilters || isNonDefaultSort;
  }, [search, activeFilters, sortBy, defaultSort, sortOrder, defaultOrder]);

  const clearFilters = () => {
    setSearch("");
    setActiveFilters({});
    setSortBy(defaultSort);
    setSortOrder(defaultOrder);
    setPage(1);
  };

  // Filtered & sorted data
  const filteredData = useMemo(() => {
    if (!data) return [];
    let items = [...data];

    // Search query
    const q = search.trim().toLowerCase();
    if (q) {
      items = items.filter((item) => searchFilter(item, q));
    }

    // Active filters (AND logic)
    for (const [key, val] of Object.entries(activeFilters)) {
      if (val && filters[key]) {
        items = items.filter((item) => filters[key](item, val));
      }
    }

    // Sorting (with stable fallback using index)
    const compareFn = sortFns[sortBy];
    if (compareFn) {
      const indexed = items.map((el, index) => ({ el, index }));
      indexed.sort((a, b) => {
        const res = compareFn(a.el, b.el);
        if (res !== 0) {
          return sortOrder === "asc" ? res : -res;
        }
        return a.index - b.index;
      });
      items = indexed.map((item) => item.el);
    }

    return items;
  }, [data, search, activeFilters, sortBy, sortOrder, searchFilter, filters, sortFns]);

  // Total pages
  const totalItems = filteredData.length;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

  // Auto-clamp page if items shrink
  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  // Paginated slice
  const paginatedData = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredData.slice(start, start + pageSize);
  }, [filteredData, page, pageSize]);

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize);
    setPage(1);
  };

  return {
    search,
    setSearch: handleSearchChange,
    activeFilters,
    setFilter,
    sortBy,
    setSortBy: handleSortChange,
    sortOrder,
    toggleSortOrder: handleSortOrderToggle,
    isFiltered,
    clearFilters,
    page,
    setPage,
    pageSize,
    setPageSize: handlePageSizeChange,
    totalCount: data ? data.length : 0,
    filteredCount: totalItems,
    totalPages,
    paginatedData,
    filteredData,
  };
}
