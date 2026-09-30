import posthog, { posthogConfigured } from "@/app/posthog";

type LogAttributes = Record<string, boolean | number | string>;

export const posthogLog = {
  info(message: string, attributes: LogAttributes) {
    if (posthogConfigured) posthog.logger.info(message, attributes);
  },
};
