export function SalesforceIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-label="Salesforce"
    >
      {/* Simplified cloud mark — three overlapping rounded lobes, mirrors the
          Salesforce "cloud" silhouette without reproducing the exact brand
          mark. */}
      <path
        d="M9.6 6.4c.9-.95 2.16-1.55 3.56-1.55 1.86 0 3.47 1.05 4.29 2.6.62-.28 1.3-.43 2.02-.43 2.75 0 4.98 2.24 4.98 5s-2.23 5-4.98 5c-.33 0-.66-.03-.97-.1-.62 1.12-1.81 1.88-3.18 1.88-.57 0-1.11-.13-1.6-.36-.65 1.53-2.16 2.6-3.92 2.6-1.83 0-3.4-1.16-4-2.78-.28.06-.57.09-.87.09-2.3 0-4.16-1.87-4.16-4.18 0-1.54.83-2.88 2.06-3.6-.05-.26-.08-.53-.08-.81 0-2.42 1.95-4.38 4.36-4.38.87 0 1.68.25 2.37.7Z"
        fill="currentColor"
      />
    </svg>
  );
}
