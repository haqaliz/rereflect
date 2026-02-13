interface ZendeskIconProps {
  className?: string;
  size?: number;
}

export function ZendeskIcon({ className, size = 24 }: ZendeskIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <rect width="24" height="24" rx="5" fill="#03363D" />
      {/* Zendesk "Z" shape */}
      <path
        d="M7 8H17L7 16H17"
        stroke="white"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
