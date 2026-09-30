import posthog from "posthog-js";

const key = import.meta.env.VITE_POSTHOG_KEY;
const host = import.meta.env.VITE_POSTHOG_HOST;

export const posthogConfigured = Boolean(key && host);

if (!posthogConfigured) {
  if (import.meta.env.DEV) {
    const missingVariable = !key ? "VITE_POSTHOG_KEY" : "VITE_POSTHOG_HOST";
    throw new Error(
      `${missingVariable} variable required by PostHog is missing or un-configured, this causes events to be silently missed. This error stops appearing once ${missingVariable} is configured`,
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
