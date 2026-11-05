import posthog from "posthog-js";

const key = import.meta.env.VITE_POSTHOG_KEY;
const host = import.meta.env.VITE_POSTHOG_HOST;

export const posthogConfigured = Boolean(key && host);

if (!posthogConfigured) {
  if (import.meta.env.DEV) {
    // A warning, not a throw: every caller already checks `posthogConfigured`, so the app works without
    // analytics - but throwing here took the whole page down for anyone running `npm run dev` without a
    // PostHog project, which is the normal state of a fresh checkout.
    const missingVariable = !key ? "VITE_POSTHOG_KEY" : "VITE_POSTHOG_HOST";
    console.warn(
      `${missingVariable} variable required by PostHog is missing or un-configured, this causes events to be silently missed. This warning stops appearing once ${missingVariable} is configured`,
    );
  }
} else {
  posthog.init(key, {
    api_host: host,
    capture_pageview: "history_change",
    logs: {
      serviceName: "mercado-em-dia-web",
      environment: import.meta.env.MODE,
    },
    capture_exceptions: {
      capture_unhandled_errors: true,
      capture_unhandled_rejections: true,
      capture_console_errors: false,
    },
  });
}

export function capture(...args: Parameters<typeof posthog.capture>) {
  if (posthogConfigured) posthog.capture(...args);
}

export default posthog;
