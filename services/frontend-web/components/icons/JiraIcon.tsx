export function JiraIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-label="Jira"
    >
      <path
        d="M23.5 11.386 12.732.61a.735.735 0 0 0-1.036 0l-1.9 1.899-2.532 2.531L2.234 10.07a.735.735 0 0 0 0 1.037L6.264 15.14l2.532 2.531 1.899 1.9a.735.735 0 0 0 1.037 0l4.03-4.031 2.53-2.532 4.031-4.031a.735.735 0 0 0 .177-1.591Z"
        fill="currentColor"
        opacity="0.4"
      />
      <path
        d="M12.732 5.968 6.264 12.437a.735.735 0 0 0 0 1.037l6.468 6.469 6.468-6.47a.735.735 0 0 0 0-1.036l-6.468-6.47Z"
        fill="currentColor"
        opacity="0.7"
      />
      <path
        d="M12.732 11.386a3.653 3.653 0 0 1-.005 5.156l-3.16-3.156 3.16-3.157a3.646 3.646 0 0 1 .005 3.157Z"
        fill="currentColor"
      />
    </svg>
  );
}
