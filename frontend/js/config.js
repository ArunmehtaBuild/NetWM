/**
 * NetWM Frontend Configuration
 * The only file that knows about API hosts & runtime flags.
 * See frontend/PLAN.md
 */

const search = typeof window !== "undefined" && window.location ? window.location.search : "";
const params = new URLSearchParams(search);

export const API_BASE =
  params.get("api") ??
  (typeof window !== "undefined" ? window.NETWM_API_BASE : null) ??
  "http://127.0.0.1:5000";

// Force mock mode if ?mock is in the URL query string
export const USE_MOCK = params.has("mock");

// Active demo scenario if specified in URL (?demo=thursday)
export const DEFAULT_DEMO = params.get("demo") ?? "thursday";
