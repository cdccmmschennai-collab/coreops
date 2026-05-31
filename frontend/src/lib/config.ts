// Frontend runtime configuration (from NEXT_PUBLIC_* env).
// Product name is read from one place only (Naming Decision Record, D-001).
export const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8100/api/v1";

export const productName = process.env.NEXT_PUBLIC_PRODUCT_NAME ?? "CoreOps";
