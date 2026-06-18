/** Two-letter initials from a person's full name (e.g. "Santhosh Kumar" → "SK"). */
export function nameInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const letters =
    parts.length >= 2
      ? `${parts[0][0]}${parts[parts.length - 1][0]}`
      : name.slice(0, 2);
  return letters.toUpperCase();
}

/** Two-letter initials derived from the local part of an email address. */
export function emailInitials(email: string): string {
  const local = email.split("@")[0] ?? email;
  const parts = local.split(/[.\-_]/).filter(Boolean);
  const letters =
    parts.length >= 2 ? `${parts[0][0]}${parts[1][0]}` : local.slice(0, 2);
  return letters.toUpperCase();
}
