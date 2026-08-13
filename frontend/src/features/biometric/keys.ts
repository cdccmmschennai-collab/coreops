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
};
