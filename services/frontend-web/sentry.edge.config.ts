/**
 * Sentry configuration for edge features (middleware, edge routes).
 * Initializes only when SENTRY_DSN is set, so a self-hosted install sends
 * nothing anywhere unless the operator opts in.
 *
 * Reference: https://docs.sentry.io/platforms/javascript/guides/nextjs/
 */
import * as Sentry from "@sentry/nextjs";

const dsn = process.env.SENTRY_DSN;

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.SENTRY_ENVIRONMENT ?? "development",
    tracesSampleRate: parseFloat(
      process.env.SENTRY_TRACES_SAMPLE_RATE ?? "0.1",
    ),

    // Do not send PII (emails, usernames) to Sentry.
    sendDefaultPii: false,
  });
}
