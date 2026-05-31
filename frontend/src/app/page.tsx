"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { productName } from "@/lib/config";

export default function Home() {
  const [status, setStatus] = useState<string>("checking…");

  useEffect(() => {
    apiGet<{ status: string }>("/health")
      .then((d) => setStatus(d.status))
      .catch(() => setStatus("unreachable"));
  }, []);

  const ok = status === "ok";

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 16,
      }}
    >
      <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700 }}>{productName}</h1>
      <p style={{ margin: 0, color: "var(--muted)" }}>
        Workforce Management System — v1 (foundations)
      </p>
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 14px",
          borderRadius: 8,
          background: "#fff",
          border: "1px solid #e6e8ec",
          fontSize: 14,
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: ok ? "var(--ok)" : "var(--err)",
          }}
        />
        backend: {status}
      </div>
    </main>
  );
}
