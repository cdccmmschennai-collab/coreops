import { Info } from "lucide-react";

/** Marks a section that mirrors the design but has no backend yet. */
export function PreviewBanner({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700">
      <Info className="h-3.5 w-3.5 shrink-0" />
      <span>
        <span className="font-semibold">Preview</span> - {children}
      </span>
    </div>
  );
}
