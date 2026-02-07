export function SlackIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-label="Slack"
    >
      {/* Top-right: green */}
      <path
        d="M14.5 2a2 2 0 0 0-2 2v5.5a2 2 0 0 0 4 0v-3.5h1.5a2 2 0 0 0 0-4H14.5z"
        fill="#2EB67D"
      />
      {/* Top-left: blue */}
      <path
        d="M2 9.5a2 2 0 0 0 2 2h5.5a2 2 0 0 0 0-4H6V6a2 2 0 0 0-4 0v3.5z"
        fill="#36C5F0"
      />
      {/* Bottom-left: yellow */}
      <path
        d="M9.5 22a2 2 0 0 0 2-2v-5.5a2 2 0 0 0-4 0V18H6a2 2 0 0 0 0 4h3.5z"
        fill="#ECB22E"
      />
      {/* Bottom-right: red/pink */}
      <path
        d="M22 14.5a2 2 0 0 0-2-2h-5.5a2 2 0 0 0 0 4H18v1.5a2 2 0 0 0 4 0V14.5z"
        fill="#E01E5A"
      />
    </svg>
  );
}
