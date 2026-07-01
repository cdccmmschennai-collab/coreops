"use client";

/**
 * Searchable Combobox — Popover + Command (shadcn/ui pattern).
 *
 * Behavior:
 *   • Click trigger → list opens IMMEDIATELY with all options visible
 *   • Type to filter — search is optional, not mandatory
 *   • Arrow keys navigate, Enter selects, Escape closes
 *   • Clear button removes selection
 *   • allowCreate prop shows "Create 'X'" when no options match
 *
 * Filtering is done client-side before render (shouldFilter={false} on
 * Command so cmdk never hides items prematurely).
 */

import * as React from "react";
import { Check, ChevronsUpDown, Plus, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export interface ComboboxOption {
  value: string;
  /** Primary label — bold, used in search */
  label: string;
  /** Short secondary label shown at the right (e.g. project code) */
  sublabel?: string;
  /** Third line shown below the label (e.g. client name) */
  description?: string;
  /** Extra search terms not displayed (e.g. job_code_code) */
  keywords?: string[];
}

interface ComboboxProps {
  value: string;
  onValueChange: (value: string) => void;
  options: ComboboxOption[];
  placeholder?: string;
  searchPlaceholder?: string;
  emptyMessage?: string;
  disabled?: boolean;
  allowClear?: boolean;
  className?: string;
  /** Max items shown before user types. Defaults to all. */
  maxVisible?: number;
  /** If true, shows "Create 'X'" when no options match the search term. */
  allowCreate?: boolean;
  /** Called with the raw search string when the user picks "Create". */
  onCreateNew?: (inputValue: string) => void | Promise<void>;
}

function matchesSearch(opt: ComboboxOption, query: string): boolean {
  if (!query.trim()) return true;
  const q = query.toLowerCase();
  const haystack = [
    opt.label,
    opt.sublabel ?? "",
    opt.description ?? "",
    ...(opt.keywords ?? []),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(q);
}

/** cmdk matches on `value`; use human-readable text, not opaque IDs. */
function commandItemValue(opt: ComboboxOption): string {
  return [opt.label, opt.sublabel, opt.description, ...(opt.keywords ?? [])]
    .filter(Boolean)
    .join(" ");
}


export function Combobox({
  value,
  onValueChange,
  options,
  placeholder = "Select…",
  searchPlaceholder = "Search…",
  emptyMessage = "No results found.",
  disabled = false,
  allowClear = true,
  className,
  maxVisible,
  allowCreate = false,
  onCreateNew,
}: ComboboxProps) {
  const [open, setOpen] = React.useState(false);
  const [search, setSearch] = React.useState("");

  React.useEffect(() => {
    if (!open) setSearch("");
  }, [open]);

  const selected = options.find((o) => o.value === value);

  const filtered = React.useMemo(() => {
    const matches = options.filter((o) => matchesSearch(o, search));
    if (maxVisible && !search.trim()) return matches.slice(0, maxVisible);
    return matches;
  }, [options, search, maxVisible]);

  const hasExactMatch =
    !allowCreate ||
    options.some((o) => o.label.toLowerCase() === search.trim().toLowerCase());

  function handleSelect(next: string) {
    onValueChange(next === value ? "" : next);
    setOpen(false);
  }

  function handleClear(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    onValueChange("");
  }

  async function handleCreateNew() {
    if (onCreateNew && search.trim()) {
      await onCreateNew(search.trim());
      setOpen(false);
    }
  }

  const showCreate =
    allowCreate && search.trim() && !hasExactMatch;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="secondary"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className={cn(
            "w-full justify-between font-normal",
            !selected && "text-muted-foreground",
            className,
          )}
        >
          {/* Selected value stays a single line; when it's longer than the
              trigger it scrolls horizontally (thin scrollbar, shift-wheel /
              trackpad) instead of being clipped — the layout/width is unchanged. */}
          <span
            className={cn(
              "min-w-0 flex-1 whitespace-nowrap text-left",
              selected ? "overflow-x-auto scrollbar-thin-x" : "truncate",
            )}
          >
            {selected ? (
              <>
                <span className="text-foreground">{selected.label}</span>
                {selected.sublabel && (
                  <span className="ml-1.5 text-xs text-muted-foreground">
                    {selected.sublabel}
                  </span>
                )}
              </>
            ) : (
              <span>{placeholder}</span>
            )}
          </span>
          <span className="ml-2 flex shrink-0 items-center gap-0.5">
            {allowClear && selected && (
              <span
                role="button"
                aria-label="Clear selection"
                onMouseDown={handleClear}
                className="rounded p-0.5 hover:bg-secondary"
              >
                <X className="h-3.5 w-3.5 opacity-50 hover:opacity-100" />
              </span>
            )}
            <ChevronsUpDown className="h-4 w-4 opacity-50" />
          </span>
        </Button>
      </PopoverTrigger>

      <PopoverContent
        className="w-[var(--radix-popover-trigger-width)] min-w-[16rem] p-0"
        align="start"
        sideOffset={4}
      >
        <Command shouldFilter={false}>
          <CommandInput
            placeholder={searchPlaceholder}
            value={search}
            onValueChange={setSearch}
            autoFocus
          />
          <CommandList className="max-h-[min(300px,50vh)]">
            {showCreate && filtered.length === 0 && (
              <CommandGroup>
                <CommandItem
                  value={`__create__ ${search.trim()}`}
                  onSelect={() => void handleCreateNew()}
                  className="gap-2 text-primary"
                >
                  <Plus className="h-4 w-4 shrink-0" />
                  <span>
                    Create{" "}
                    <span className="font-medium">&ldquo;{search.trim()}&rdquo;</span>
                  </span>
                </CommandItem>
              </CommandGroup>
            )}

            {filtered.length === 0 && !showCreate && (
              <CommandEmpty>{emptyMessage}</CommandEmpty>
            )}

            {filtered.length > 0 && (
              <CommandGroup>
                {filtered.map((opt) => (
                  <CommandItem
                    key={opt.value}
                    value={commandItemValue(opt)}
                    keywords={opt.keywords}
                    onSelect={() => handleSelect(opt.value)}
                  >
                    <Check
                      className={cn(
                        "mr-2 h-4 w-4 shrink-0",
                        value === opt.value ? "opacity-100" : "opacity-0",
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        {/* Long option names stay truncated with an ellipsis; the
                            native title tooltip reveals the full text on hover. */}
                        <span className="truncate font-medium" title={opt.label}>
                          {opt.label}
                        </span>
                        {opt.sublabel && (
                          <span className="shrink-0 font-mono text-xs text-muted-foreground">
                            {opt.sublabel}
                          </span>
                        )}
                      </div>
                      {opt.description && (
                        <div
                          className="truncate text-xs text-muted-foreground"
                          title={opt.description}
                        >
                          {opt.description}
                        </div>
                      )}
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}

            {showCreate && filtered.length > 0 && (
              <CommandGroup>
                <CommandItem
                  value={`__create__ ${search.trim()}`}
                  onSelect={() => void handleCreateNew()}
                  className="gap-2 text-primary"
                >
                  <Plus className="h-4 w-4 shrink-0" />
                  <span>
                    Create{" "}
                    <span className="font-medium">&ldquo;{search.trim()}&rdquo;</span>
                  </span>
                </CommandItem>
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
