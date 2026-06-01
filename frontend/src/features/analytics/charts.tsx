"use client";

// Pure-SVG chart primitives for the analytics screen.
// All colours reference Tailwind/CSS vars so they work with the design system.

import * as React from "react";

// ── shared ────────────────────────────────────────────────────────────────────

const CHART_COLORS = [
  "hsl(var(--primary))",
  "#8b5cf6",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#6366f1",
];

export function ChartLegend({ items }: { items: { color: string; label: string }[] }) {
  return (
    <div className="flex flex-wrap gap-3">
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="h-2 w-2 rounded-sm" style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
    </div>
  );
}

// ── DonutChart ─────────────────────────────────────────────────────────────────

export interface DonutSlice { label: string; value: number }

export function DonutChart({ slices, total }: { slices: DonutSlice[]; total?: string }) {
  const sum  = slices.reduce((s, x) => s + x.value, 0);
  const R = 60; const C = 75;
  let acc = 0;

  return (
    <div className="flex items-center gap-4">
      <svg width="150" height="150" viewBox="0 0 150 150" style={{ flexShrink: 0 }}>
        {slices.map((s, i) => {
          const start = (acc / sum) * 2 * Math.PI - Math.PI / 2;
          acc += s.value;
          const end   = (acc / sum) * 2 * Math.PI - Math.PI / 2;
          const large = end - start > Math.PI ? 1 : 0;
          const x1 = C + R * Math.cos(start); const y1 = C + R * Math.sin(start);
          const x2 = C + R * Math.cos(end);   const y2 = C + R * Math.sin(end);
          return (
            <path
              key={i}
              d={`M ${C} ${C} L ${x1} ${y1} A ${R} ${R} 0 ${large} 1 ${x2} ${y2} Z`}
              fill={CHART_COLORS[i % CHART_COLORS.length]}
              opacity="0.9"
            />
          );
        })}
        <circle cx={C} cy={C} r="36" fill="hsl(var(--card))" />
        {total && (
          <>
            <text x={C} y={C - 4}  textAnchor="middle" fontSize="16" fontWeight="600"
              fill="hsl(var(--foreground))" fontFamily="var(--font-mono)">{total}</text>
            <text x={C} y={C + 14} textAnchor="middle" fontSize="9"
              fill="hsl(var(--muted-foreground))">hours</text>
          </>
        )}
      </svg>
      <div className="flex flex-col gap-1.5 text-xs flex-1">
        {slices.map((s, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
            <span className="flex-1 text-muted-foreground">{s.label}</span>
            <span className="tabular font-medium">{Math.round((s.value / sum) * 100)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── BurnBar ────────────────────────────────────────────────────────────────────

export interface BurnEntry { name: string; allocated: number; logged: number; color?: string }

export function BurnBars({ entries }: { entries: BurnEntry[] }) {
  if (entries.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No project data this period.</p>;
  }
  return (
    <div className="flex flex-col gap-4">
      {entries.map((e, i) => {
        const pct   = e.allocated > 0 ? Math.min(100, Math.round((e.logged / e.allocated) * 100)) : 0;
        const over  = e.logged > e.allocated;
        const color = e.color ?? CHART_COLORS[i % CHART_COLORS.length];
        return (
          <div key={e.name}>
            <div className="mb-1.5 flex items-baseline justify-between text-sm">
              <span className="font-medium truncate mr-2">{e.name}</span>
              <span className={`tabular text-xs shrink-0 ${over ? "text-destructive" : "text-muted-foreground"}`}>
                {Math.round(e.logged / 60)}h / {Math.round(e.allocated / 60)}h
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${pct}%`,
                  background: over ? "hsl(var(--destructive))" : color,
                  opacity: 0.9,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── LineChart ──────────────────────────────────────────────────────────────────

export function LineChart({ data, labels }: { data: number[]; labels?: string[] }) {
  const w = 320; const h = 130; const pad = 12;
  const max = 100; const min = Math.max(0, Math.min(...data) - 10);
  const pts = data.map((v, i) => {
    const x = pad + (i / Math.max(data.length - 1, 1)) * (w - pad * 2);
    const y = pad + (1 - (v - min) / Math.max(max - min, 1)) * (h - pad * 2);
    return [x, y] as [number, number];
  });
  const d   = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const area = `${d} L ${pts[pts.length - 1][0]},${h - pad} L ${pts[0][0]},${h - pad} Z`;

  return (
    <svg viewBox={`0 0 ${w} ${h + 16}`} width="100%" style={{ display: "block" }}>
      <g stroke="hsl(var(--border))" strokeDasharray="2 3" fill="none">
        {[pad, h / 2, h - pad].map((y) => (
          <line key={y} x1={pad} y1={y} x2={w - pad} y2={y} />
        ))}
      </g>
      <path d={area} fill="hsl(var(--primary))" opacity="0.08" />
      <path d={d} stroke="hsl(var(--primary))" strokeWidth="2" fill="none" />
      {pts.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r={i === pts.length - 1 ? 3 : 0}
          fill="hsl(var(--primary))" />
      ))}
      {pts.length > 0 && (
        <text
          x={pts[pts.length - 1][0] + 8} y={pts[pts.length - 1][1] + 4}
          fontSize="11" fill="hsl(var(--foreground))"
          fontFamily="var(--font-mono)"
        >
          {data[data.length - 1]}%
        </text>
      )}
      {labels && (
        <g fontSize="9" fill="hsl(var(--muted-foreground))" fontFamily="var(--font-mono)">
          <text x={pad}             y={h + 12}>{labels[0]}</text>
          <text x={w / 2}           y={h + 12} textAnchor="middle">{labels[Math.floor(labels.length / 2)]}</text>
          <text x={w - pad}         y={h + 12} textAnchor="end">{labels[labels.length - 1]}</text>
        </g>
      )}
    </svg>
  );
}

// ── Heatmap ────────────────────────────────────────────────────────────────────

export interface HeatmapRow { name: string; weeks: number[] }

export function Heatmap({ rows, weekLabels }: { rows: HeatmapRow[]; weekLabels: string[] }) {
  if (rows.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No data to display.</p>;
  }
  const maxVal = Math.max(...rows.flatMap((r) => r.weeks), 1);

  return (
    <div className="overflow-x-auto">
      <div
        className="grid gap-1"
        style={{
          gridTemplateColumns: `120px repeat(${weekLabels.length}, minmax(32px, 1fr))`,
          minWidth: 400 + weekLabels.length * 40,
        }}
      >
        {/* header */}
        <div />
        {weekLabels.map((w) => (
          <div key={w} className="text-center tabular text-[11px] text-muted-foreground">{w}</div>
        ))}
        {/* rows */}
        {rows.map((row) => (
          <React.Fragment key={row.name}>
            <div className="flex items-center truncate pr-2 text-xs text-muted-foreground">
              {row.name}
            </div>
            {row.weeks.map((v, ci) => {
              const opacity = v === 0 ? 0 : 0.1 + (v / maxVal) * 0.85;
              return (
                <div
                  key={ci}
                  title={`${row.name} · ${weekLabels[ci]} · ${Math.round(v / 60)}h`}
                  className="flex h-8 items-center justify-center rounded text-[10px] font-medium"
                  style={{
                    background: v === 0 ? "hsl(var(--secondary))" : `hsl(var(--primary))`,
                    opacity: v === 0 ? 1 : opacity,
                    color: opacity > 0.5 ? "#fff" : "hsl(var(--muted-foreground))",
                  }}
                >
                  {v > 0 ? `${Math.round(v / 60)}h` : ""}
                </div>
              );
            })}
          </React.Fragment>
        ))}
      </div>
      <div className="mt-3 flex gap-4 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded" style={{ background: "hsl(var(--secondary))" }} />
          No data
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded" style={{ background: "hsl(var(--primary))", opacity: 0.25 }} />
          Low
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded" style={{ background: "hsl(var(--primary))" }} />
          High
        </span>
      </div>
    </div>
  );
}

// ── StackedBars (preview — no category field yet) ─────────────────────────────

const STACK_COLORS = [
  "hsl(var(--primary))",
  "#8b5cf6",
  "#10b981",
  "#f59e0b",
];

export function StackedBarsPreview() {
  const bars = Array.from({ length: 30 }, (_, i) => {
    const seed = (i * 7) % 11;
    return {
      a: 70 + ((seed * 5) % 40),
      b: 25 + ((seed * 3) % 20),
      c: 12 + ((seed * 2) % 18),
      d: i % 5 === 0 ? 18 : 5 + (seed % 8),
    };
  });
  const maxVal = 200;
  const W = 660; const bw = (W - 40) / bars.length - 1;

  return (
    <svg viewBox={`0 0 ${W} 200`} width="100%" style={{ display: "block" }}>
      <g stroke="hsl(var(--border))" strokeDasharray="2 3" fill="none">
        {[20, 60, 100, 140, 180].map((y) => (
          <line key={y} x1="36" y1={y} x2={W - 4} y2={y} />
        ))}
      </g>
      <g fontSize="9" fill="hsl(var(--muted-foreground))" textAnchor="end" fontFamily="var(--font-mono)">
        <text x="32" y="24">200h</text>
        <text x="32" y="64">150</text>
        <text x="32" y="104">100</text>
        <text x="32" y="144">50</text>
        <text x="32" y="184">0</text>
      </g>
      {bars.map((d, i) => {
        const x     = 40 + i * (bw + 1);
        const scale = 160 / maxVal;
        const ha = d.a * scale; const hb = d.b * scale;
        const hc = d.c * scale; const hd = d.d * scale;
        const y1 = 180 - ha; const y2 = y1 - hb;
        const y3 = y2 - hc; const y4 = y3 - hd;
        return (
          <g key={i}>
            <rect x={x} y={y1} width={bw} height={ha} fill={STACK_COLORS[0]} opacity="0.85" />
            <rect x={x} y={y2} width={bw} height={hb} fill={STACK_COLORS[1]} opacity="0.85" />
            <rect x={x} y={y3} width={bw} height={hc} fill={STACK_COLORS[2]} opacity="0.85" />
            <rect x={x} y={y4} width={bw} height={hd} fill={STACK_COLORS[3]} opacity="0.85" />
          </g>
        );
      })}
    </svg>
  );
}
