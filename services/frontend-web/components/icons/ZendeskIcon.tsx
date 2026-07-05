export function ZendeskIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-label="Zendesk"
    >
      <path
        d="M2 13.5A8.5 8.5 0 0 1 10.5 5v8.5H2Z"
        fill="currentColor"
        opacity="0.4"
      />
      <path
        d="M22 10.5A8.5 8.5 0 0 1 13.5 19v-8.5H22Z"
        fill="currentColor"
        opacity="0.7"
      />
      <path
        d="M2 5h8.5v3.4a5.1 5.1 0 0 1-5.1 5.1H2V5Z"
        fill="currentColor"
      />
      <path
        d="M22 19h-8.5v-3.4a5.1 5.1 0 0 1 5.1-5.1H22V19Z"
        fill="currentColor"
      />
    </svg>
  );
}
