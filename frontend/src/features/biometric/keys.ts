export const biometricKeys = {
  all: ["biometric"] as const,
  externalCodes: (
    provider: string,
    status: string,
    q: string,
    limit: number,
    offset: number,
  ) =>
    [...biometricKeys.all, "external-codes", provider, status, q, limit, offset] as const,
  // Employee picker search. Not scoped to a code - the same result set serves
  // whichever row the PM opens next.
  employeeSearch: (q: string) => [...biometricKeys.all, "employee-search", q] as const,
  dailySummary: (employeeId: string, from: string, to: string) =>
    [...biometricKeys.all, "daily-summary", employeeId, from, to] as const,
  // PM daily review: one date, the whole roster. Keyed by the classification
  // filter, search text and page too, since all three are applied server-side.
  dailyReview: (
    date: string,
    classification: string,
    q: string,
    limit: number,
    offset: number,
  ) => [...biometricKeys.all, "daily-review", date, classification, q, limit, offset] as const,
  // Phase 9B detail screen: one employee, one day.
  dailyReviewDetail: (employeeId: string, date: string) =>
    [...biometricKeys.all, "daily-review-detail", employeeId, date] as const,
};
