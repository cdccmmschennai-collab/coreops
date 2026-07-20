/**
 * Guard for count-input keystrokes: a valid in-progress count value is the
 * empty string (mid-edit) or ASCII digits only. Everything else — minus signs,
 * decimal points, "e"/"E" scientific notation, "+", spaces, letters — is
 * rejected wholesale, so a controlled input simply reverts the change.
 *
 * Deliberately NOT a converter: no Number(), no clamping, no trimming. The
 * string stays exactly what the user typed; conversion to a number happens
 * only at the API boundary (work-reports schemas.ts `toCount`).
 */
export function isCountString(value: string): boolean {
  return /^\d*$/.test(value);
}
