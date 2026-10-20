import {
  forwardRef,
  useEffect,
  useId,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import {
  IconCheck,
  IconChevronDown,
  IconPlus,
  IconSearch,
  IconX,
} from "./Icons";
import { Spinner } from "./ui";

export interface ComboboxOption {
  value: string;
  label: string;
  sublabel?: string;
  [key: string]: unknown;
}

export interface SearchableComboboxProps {
  id?: string;
  name?: string;
  value: string;
  onChange: (value: string, selectedOption?: ComboboxOption) => void;
  options: ComboboxOption[];
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  className?: string;
  allowCustom?: boolean;
  customActionLabel?: (query: string) => string;
  onAddCustom?: (query: string) => Promise<string | void> | string | void;
  emptyMessage?: string;
  itemNoun?: string;
  icon?: ReactNode;
  error?: string;
  autoFocus?: boolean;
  onBlur?: () => void;
}

export interface SearchableComboboxHandle {
  focus: () => void;
  clear: () => void;
}

function highlightMatch(text: string, query: string) {
  const trimmed = query.trim();
  if (!trimmed) return text;
  const escaped = trimmed.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const parts = text.split(new RegExp(`(${escaped})`, "gi"));
  return (
    <>
      {parts.map((part, i) =>
        part.toLowerCase() === trimmed.toLowerCase() ? (
          <span
            key={i}
            className="font-semibold text-pen bg-pen-soft/80 px-0.5 rounded"
          >
            {part}
          </span>
        ) : (
          part
        )
      )}
    </>
  );
}

export const SearchableCombobox = forwardRef<
  SearchableComboboxHandle,
  SearchableComboboxProps
>(function SearchableCombobox(
  {
    id,
    name,
    value,
    onChange,
    options,
    placeholder = "Type to search or select...",
    required,
    disabled,
    className = "",
    allowCustom = false,
    customActionLabel,
    onAddCustom,
    emptyMessage,
    itemNoun = "option",
    icon,
    error,
    autoFocus,
    onBlur,
  },
  ref
) {
  const autoId = useId();
  const inputId = id || autoId;
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  // Find label of currently selected option by value
  const selectedOption = useMemo(
    () => options.find((o) => o.value === value || o.label === value),
    [options, value]
  );

  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState(selectedOption ? selectedOption.label : value || "");
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [isAdding, setIsAdding] = useState(false);
  const [customError, setCustomError] = useState<string | null>(null);

  // Sync internal query when incoming value or options change and dropdown is closed
  useEffect(() => {
    if (!isOpen) {
      if (selectedOption) {
        setQuery(selectedOption.label);
      } else {
        setQuery(value || "");
      }
    }
  }, [value, selectedOption, isOpen]);

  useImperativeHandle(ref, () => ({
    focus: () => inputRef.current?.focus(),
    clear: () => {
      setQuery("");
      onChange("");
    },
  }));

  // Dynamic filtering: support both numbers, letters, spaces and symbols
  const filteredOptions = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((opt) => {
      const matchLabel = opt.label.toLowerCase().includes(q);
      const matchSub = opt.sublabel?.toLowerCase().includes(q);
      return matchLabel || matchSub;
    });
  }, [options, query]);

  // Determine if typed text has an exact match
  const hasExactMatch = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return false;
    return options.some(
      (opt) =>
        opt.label.toLowerCase() === q || opt.value.toLowerCase() === q
    );
  }, [options, query]);

  // Show "Add Custom" option if allowCustom is true, user typed non-empty text, and no exact match
  const showAddOption = Boolean(
    allowCustom && query.trim() && !hasExactMatch
  );

  const totalInteractiveItems =
    filteredOptions.length + (showAddOption ? 1 : 0);

  // Handle outside click to close dropdown
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
        setHighlightedIndex(-1);

        // If the query exactly matches an existing option, select it
        const trimmed = query.trim().toLowerCase();
        const exact = options.find(
          (o) => o.label.toLowerCase() === trimmed || o.value.toLowerCase() === trimmed
        );
        if (exact) {
          onChange(exact.value, exact);
          setQuery(exact.label);
        } else if (!allowCustom) {
          // Revert to selected option's label if custom is not allowed
          setQuery(selectedOption ? selectedOption.label : "");
        } else if (!onAddCustom) {
          // If custom is allowed without onAddCustom (e.g. Exam Type free text)
          onChange(query.trim());
        }
        onBlur?.();
      }
    };

    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [query, options, selectedOption, allowCustom, onAddCustom, onChange, onBlur]);

  // Scroll active item into view
  useEffect(() => {
    if (highlightedIndex >= 0 && listRef.current) {
      const el = listRef.current.children[highlightedIndex] as HTMLElement;
      if (el) {
        el.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    }
  }, [highlightedIndex]);

  const handleSelectOption = (option: ComboboxOption) => {
    onChange(option.value, option);
    setQuery(option.label);
    setIsOpen(false);
    setHighlightedIndex(-1);
    setCustomError(null);
  };

  const handleTriggerAddCustom = async () => {
    const trimmed = query.trim();
    if (!trimmed || isAdding) return;

    if (onAddCustom) {
      try {
        setIsAdding(true);
        setCustomError(null);
        const newId = await onAddCustom(trimmed);
        setIsOpen(false);
        setHighlightedIndex(-1);
        if (typeof newId === "string") {
          onChange(newId, { value: newId, label: trimmed });
          setQuery(trimmed);
        }
      } catch (err) {
        setCustomError(
          err instanceof Error ? err.message : "Failed to add custom item"
        );
      } finally {
        setIsAdding(false);
      }
    } else {
      // Just plain string value without DB entity creation
      onChange(trimmed, { value: trimmed, label: trimmed });
      setQuery(trimmed);
      setIsOpen(false);
      setHighlightedIndex(-1);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (disabled) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
        setHighlightedIndex(0);
      } else {
        setHighlightedIndex((prev) =>
          totalInteractiveItems === 0
            ? -1
            : (prev + 1) % totalInteractiveItems
        );
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!isOpen) {
        setIsOpen(true);
        setHighlightedIndex(totalInteractiveItems - 1);
      } else {
        setHighlightedIndex((prev) =>
          totalInteractiveItems === 0
            ? -1
            : (prev - 1 + totalInteractiveItems) % totalInteractiveItems
        );
      }
    } else if (e.key === "Enter") {
      if (isOpen && totalInteractiveItems > 0 && highlightedIndex >= 0) {
        e.preventDefault();
        e.stopPropagation();
        if (highlightedIndex < filteredOptions.length) {
          handleSelectOption(filteredOptions[highlightedIndex]);
        } else if (showAddOption) {
          handleTriggerAddCustom();
        }
      } else if (isOpen && showAddOption && highlightedIndex === -1) {
        // If user presses enter on custom text with no option highlighted
        e.preventDefault();
        e.stopPropagation();
        handleTriggerAddCustom();
      }
    } else if (e.key === "Escape") {
      if (isOpen) {
        e.preventDefault();
        e.stopPropagation();
        setIsOpen(false);
        setHighlightedIndex(-1);
      }
    } else if (e.key === "Tab") {
      if (isOpen) {
        setIsOpen(false);
        setHighlightedIndex(-1);
      }
    }
  };

  const handleClear = () => {
    setQuery("");
    onChange("");
    setCustomError(null);
    inputRef.current?.focus();
    setIsOpen(true);
  };

  const resolvedEmptyMessage =
    emptyMessage || `No matching ${itemNoun}s found`;

  return (
    <div ref={containerRef} className={`relative w-full ${className}`}>
      <div className="relative flex items-center">
        {icon ? (
          <span className="pointer-events-none absolute left-3 text-mute">
            {icon}
          </span>
        ) : (
          <span className="pointer-events-none absolute left-3 text-mute">
            <IconSearch size={16} />
          </span>
        )}

        <input
          ref={inputRef}
          id={inputId}
          name={name}
          type="text"
          role="combobox"
          aria-expanded={isOpen}
          aria-autocomplete="list"
          aria-controls={`${inputId}-listbox`}
          autoComplete="off"
          disabled={disabled}
          required={required && !value && !query}
          autoFocus={autoFocus}
          placeholder={placeholder}
          value={query}
          onFocus={() => {
            setIsOpen(true);
            setHighlightedIndex(-1);
          }}
          onChange={(e) => {
            const val = e.target.value;
            setQuery(val);
            setIsOpen(true);
            setHighlightedIndex(0);
            setCustomError(null);
            // If custom is allowed and no async creation needed, propagate change
            if (allowCustom && !onAddCustom) {
              onChange(val);
            }
          }}
          onKeyDown={handleKeyDown}
          className={`w-full rounded-lg border bg-surface py-2 text-sm text-ink placeholder:text-mute shadow-sm transition-ui focus:border-pen focus:ring-2 focus:ring-pen/20 focus:outline-none disabled:bg-sunken disabled:cursor-not-allowed ${icon ? "pl-9" : "pl-9"
            } ${query ? "pr-16" : "pr-9"} ${error || customError ? "border-mark focus:border-mark focus:ring-mark/20" : "border-line"
            }`}
        />

        <div className="absolute right-2.5 flex items-center gap-1 text-mute">
          {query && !disabled && (
            <button
              type="button"
              onClick={handleClear}
              title="Clear selection"
              tabIndex={-1}
              className="p-1 rounded hover:bg-sunken hover:text-ink transition-colors"
            >
              <IconX size={14} />
            </button>
          )}

          <button
            type="button"
            disabled={disabled}
            onClick={() => {
              if (!disabled) {
                if (isOpen) {
                  setIsOpen(false);
                } else {
                  inputRef.current?.focus();
                  setIsOpen(true);
                }
              }
            }}
            tabIndex={-1}
            title={isOpen ? "Close suggestions" : "Show suggestions"}
            className="p-1 rounded hover:bg-sunken hover:text-ink transition-colors"
          >
            <IconChevronDown
              size={15}
              className={`transition-transform duration-200 ${isOpen ? "rotate-180" : ""
                }`}
            />
          </button>
        </div>
      </div>

      {/* Floating Suggestions Dropdown */}
      {isOpen && !disabled && (
        <div
          id={`${inputId}-listbox`}
          role="listbox"
          className="absolute z-50 mt-1.5 w-full rounded-xl border border-line bg-surface p-1 shadow-lg max-h-64 overflow-y-auto animate-in fade-in-50 duration-150 backdrop-blur-sm"
        >
          {filteredOptions.length > 0 ? (
            <ul ref={listRef} className="space-y-0.5">
              {filteredOptions.map((opt, idx) => {
                const isSelected =
                  opt.value === value || opt.label === value || opt.label === query;
                const isHighlighted = idx === highlightedIndex;

                return (
                  <li
                    key={opt.value}
                    role="option"
                    aria-selected={isSelected}
                    onMouseEnter={() => setHighlightedIndex(idx)}
                    onClick={() => handleSelectOption(opt)}
                    className={`flex items-center justify-between rounded-lg px-2.5 py-2 text-sm cursor-pointer select-none transition-colors ${
                      isHighlighted
                        ? "bg-pen-soft text-pen font-medium"
                        : isSelected
                        ? "bg-pen-soft/40 text-ink font-medium"
                        : "text-ink hover:bg-sunken/60"
                    }`}
                  >
                    <div className="flex flex-col min-w-0">
                      <span className="truncate">
                        {highlightMatch(opt.label, query)}
                      </span>
                      {opt.sublabel && (
                        <span className="text-[11px] text-mute truncate mt-0.5">
                          {opt.sublabel}
                        </span>
                      )}
                    </div>

                    {isSelected && (
                      <span className="text-pen shrink-0 ml-2">
                        <IconCheck size={16} />
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : !showAddOption ? (
            <div className="px-3 py-4 text-center">
              <p className="text-xs font-medium text-mute">
                {resolvedEmptyMessage}
              </p>
            </div>
          ) : null}

          {/* Interactive "Create custom" Option */}
          {showAddOption && (
            <>
              {filteredOptions.length > 0 && (
                <div className="my-1 h-px bg-line/60" />
              )}
              <div
                role="option"
                aria-selected={highlightedIndex === filteredOptions.length}
                onMouseEnter={() => setHighlightedIndex(filteredOptions.length)}
                onClick={handleTriggerAddCustom}
                className={`flex items-center justify-between rounded-lg px-2.5 py-2 text-sm cursor-pointer select-none transition-colors ${
                  highlightedIndex === filteredOptions.length
                    ? "bg-pen-soft text-pen font-medium"
                    : "text-ink hover:bg-sunken/60"
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-pen/10 text-pen">
                    {isAdding ? <Spinner size={12} /> : <IconPlus size={13} />}
                  </span>
                  <span className="truncate">
                    {isAdding ? (
                      `Adding "${query.trim()}"...`
                    ) : customActionLabel ? (
                      customActionLabel(query.trim())
                    ) : (
                      <>
                        Create <span className="font-semibold text-pen">"{query.trim()}"</span>
                      </>
                    )}
                  </span>
                  <span className="shrink-0 text-[10px] font-medium text-mute px-1.5 py-0.5 rounded bg-sunken">
                    New {itemNoun}
                  </span>
                </div>
                <kbd className="shrink-0 ml-2 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-mute shadow-2xs">
                  ↵ Enter
                </kbd>
              </div>
            </>
          )}
        </div>
      )}

      {/* Error Displays */}
      {(customError || error) && (
        <p className="mt-1 text-xs font-medium text-mark">
          {customError || error}
        </p>
      )}
    </div>
  );
});

