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
 *
 * `taskContinuation` — lets a TASK_BASED activity continue across several daily
 * reports as one work item with a fixed deadline (open-task suggestions +
 * Continue/Start-new choice). Mirror of the backend TASK_CONTINUATION_ENABLED;
 * keep the two in step per environment. Default OFF.
 *
 * `reportDayParts` — the Full-Day / Split-Day work report selector (First-Half
 * + Second-Half period cards). Mirror of the backend REPORT_DAY_PARTS_ENABLED;
 * keep the two in step per environment. With the flag off the form stays the
 * classic full-day experience and only legacy payloads are sent. Default OFF.
 */
export const features = {
  attendanceCorrections:
    process.env.NEXT_PUBLIC_FEATURE_ATTENDANCE_CORRECTIONS === "true",
  taskContinuation:
    process.env.NEXT_PUBLIC_FEATURE_TASK_CONTINUATION === "true",
  reportDayParts:
    process.env.NEXT_PUBLIC_REPORT_DAY_PARTS_ENABLED === "true",
} as const;
