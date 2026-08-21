import { z } from "zod";

// Relative .ts value import - the node --test harness resolves it directly.
import { PRODUCTION_STATUS_VALUES } from "./production-status.ts";
import type { ProductionStatusCreateBody } from "./types";

export const REVISION_REQUIRED_ERROR = "Revision is required";
export const ACTIVITY_REQUIRED_ERROR = "Select an activity";

/**
 * The Save Status form.
 *
 * Counts are held as strings because that is what an `<input>` gives us, and
 * because `valueAsNumber` turns "" into NaN - indistinguishable from a real
 * zero. `CountInput` already refuses anything but digits keystroke by
 * keystroke, so the only states this schema has to accept are "" and digits;
 * `toCount` below is the single place a string becomes the number the API
 * receives.
 *
 * Deliberately NO rule tying `completed_on` to `status`. The backend accepts a
 * closed update with no completion date and an in-progress update with one, and
 * inventing a stricter client rule would make the UI refuse a record the API
 * would have stored - a second, conflicting definition of valid.
 */
export const productionStatusFormSchema = z.object({
  revision: z.string().trim().min(1, REVISION_REQUIRED_ERROR).max(50),
  activity_id: z.string().min(1, ACTIVITY_REQUIRED_ERROR),
  // OPTIONAL - deliberately no `.min(1)`. A project whose Planning Plant has no
  // Maintenance Plants has none to offer, and the form must not be blocked by
  // that. "" means "none selected" and is sent as null.
  maintenance_plant_id: z.string(),
  status: z.enum(PRODUCTION_STATUS_VALUES),
  tag_count: z.string(),
  doc_count: z.string(),
  spares_count: z.string(),
  crs_count: z.string(),
  completed_on: z.string(),
  remarks: z.string(),
});

export type ProductionStatusFormValues = z.infer<typeof productionStatusFormSchema>;

/**
 * A fresh form. Counts start empty rather than "0" so the boxes read as "not
 * entered", and `completed_on` starts empty - nothing here pre-fills today's
 * date, because no CoreOps form does and a defaulted completion date is a
 * business claim the user did not make.
 */
export const EMPTY_PRODUCTION_STATUS_FORM: ProductionStatusFormValues = {
  revision: "",
  activity_id: "",
  maintenance_plant_id: "",
  status: "in_progress",
  tag_count: "",
  doc_count: "",
  spares_count: "",
  crs_count: "",
  completed_on: "",
  remarks: "",
};

/**
 * Blank count -> 0, which is exactly the backend's contract for an unused unit
 * (NOT NULL DEFAULT 0, `Field(default=0, ge=0)`). Same converter shape as the
 * work-report form's `toCount`, so the two screens agree on what an empty count
 * box means.
 */
const toCount = (v: string): number =>
  Number.isFinite(Number(v)) ? Math.max(0, Math.trunc(Number(v))) : 0;

const orNull = (v: string): string | null => (v.trim() === "" ? null : v.trim());

/**
 * Form values -> POST body.
 *
 * The project is not in the body: it is the path, which is what the caller is
 * authorized against. Neither is the author - the server takes that from the
 * token, which is what keeps "By" a real person instead of whatever a client
 * chose to send.
 */
export function toProductionStatusBody(
  v: ProductionStatusFormValues,
): ProductionStatusCreateBody {
  return {
    revision: v.revision.trim(),
    activity_id: v.activity_id,
    // "" -> null. The API takes a plant id or nothing; it never receives an
    // empty string, and it never infers a plant when none was chosen.
    maintenance_plant_id: orNull(v.maintenance_plant_id),
    status: v.status,
    tag_count: toCount(v.tag_count),
    doc_count: toCount(v.doc_count),
    spares_count: toCount(v.spares_count),
    crs_count: toCount(v.crs_count),
    completed_on: orNull(v.completed_on),
    remarks: orNull(v.remarks),
  };
}

/**
 * What the form keeps after a successful save.
 *
 * Revision, activity and Maintenance Plant stay: recording several updates
 * against the same revision/activity/plant in one sitting is the normal case,
 * and clearing them would make the common path the most tedious one. Everything
 * the user asserted about THIS update - counts, completion date, remarks - is
 * cleared, so the next save can never inherit numbers from the last one. Status
 * is left as chosen because it is the thing most likely to be repeated or
 * deliberately advanced.
 */
export function resetAfterSave(
  v: ProductionStatusFormValues,
): ProductionStatusFormValues {
  return {
    ...EMPTY_PRODUCTION_STATUS_FORM,
    revision: v.revision.trim(),
    activity_id: v.activity_id,
    maintenance_plant_id: v.maintenance_plant_id,
    status: v.status,
  };
}
