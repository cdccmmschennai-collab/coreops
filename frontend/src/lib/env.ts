/** Typed access to public runtime configuration. */
export const env = {
  apiBaseUrl:
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8100/api/v1",
  productName: process.env.NEXT_PUBLIC_PRODUCT_NAME ?? "CoreOps",
} as const;
