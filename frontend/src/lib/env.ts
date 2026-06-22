/** Typed access to public runtime configuration. */
export const env = {
  apiBaseUrl:
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8100/api/v1",
  productName: process.env.NEXT_PUBLIC_PRODUCT_NAME ?? "CoreOps",
} as const;

/**
 * Feature flags. Default OFF; opt in per environment.
 *
 * `attendanceCorrections` — the Attendance Corrections workflow. Deferred until
 * biometric integration or automated attendance capture exists; attendance is
 * entered manually by the PM today, so there is nothing meaningful to correct.
 * Do not enable until the workflow (tables/APIs/approvals) is actually built.
 */
export const features = {
  attendanceCorrections:
    process.env.NEXT_PUBLIC_FEATURE_ATTENDANCE_CORRECTIONS === "true",
} as const;
