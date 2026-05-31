/**
 * Typed fetch client. Attaches the JWT, parses the backend error envelope
 * ({error:{code,message,details,request_id}}) into a typed AppError.
 */
import type { ApiErrorBody } from "@/types/api";

import { getToken } from "./auth-storage";
import { env } from "./env";

export class AppError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: Record<string, unknown>;
  readonly requestId?: string | null;

  constructor(
    code: string,
    message: string,
    status: number,
    details?: Record<string, unknown>,
    requestId?: string | null,
  ) {
    super(message);
    this.name = "AppError";
    this.code = code;
    this.status = status;
    this.details = details;
    this.requestId = requestId;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${env.apiBaseUrl}${path}`, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
      cache: "no-store",
    });
  } catch {
    throw new AppError("network_error", "Could not reach the server.", 0);
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      if (!res.ok) {
        throw new AppError("http_error", res.statusText || "Request failed", res.status);
      }
      throw new AppError("parse_error", "Malformed server response.", res.status);
    }
  }

  if (!res.ok) {
    const body = data as ApiErrorBody | null;
    const err = body?.error;
    throw new AppError(
      err?.code ?? "http_error",
      err?.message ?? res.statusText ?? "Request failed",
      res.status,
      err?.details,
      err?.request_id ?? null,
    );
  }

  return data as T;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
