import { Button } from "@/components/ui/button";

interface PaginationProps {
  total: number;
  limit: number;
  offset: number;
  onPageChange: (offset: number) => void;
}

export function Pagination({ total, limit, offset, onPageChange }: PaginationProps) {
  const start = total === 0 ? 0 : offset + 1;
  const end = Math.min(offset + limit, total);
  const canPrev = offset > 0;
  const canNext = end < total;

  return (
    <div className="flex items-center justify-between border-t border-border bg-secondary/30 px-3 py-2 text-xs text-muted-foreground">
      <span className="tabular">
        Showing {start}–{end} of {total}
      </span>
      <div className="flex gap-2">
        <Button
          variant="secondary"
          size="sm"
          disabled={!canPrev}
          onClick={() => onPageChange(Math.max(0, offset - limit))}
        >
          ‹ Prev
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={!canNext}
          onClick={() => onPageChange(offset + limit)}
        >
          Next ›
        </Button>
      </div>
    </div>
  );
}
