/**
 * Sentry client-side configuration.
 * Runs in the browser. Initializes only when NEXT_PUBLIC_SENTRY_DSN is set, so a
 * self-hosted install sends nothing anywhere unless the operator opts in.
 *
 * Reference: https://docs.sentry.io/platforms/javascript/guides/nextjs/
 */
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? "development",
    tracesSampleRate: parseFloat(
      process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? "0.1",
    ),

    // Replay captures user sessions for reproductions — 10 % normal / 100 % on error.
    replaysSessionSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,
    integrations: [Sentry.replayIntegration()],

    // Do not send PII (emails, usernames) to Sentry.
    sendDefaultPii: false,
  });
}

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
