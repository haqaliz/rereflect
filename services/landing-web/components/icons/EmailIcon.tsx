interface EmailIconProps {
  className?: string;
  size?: number;
}

export function EmailIcon({ className, size = 24 }: EmailIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <rect width="24" height="24" rx="5" fill="url(#email-gradient)" />
      <path
        d="M6 8.5L12 13L18 8.5"
        stroke="white"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <rect
        x="5"
        y="7"
        width="14"
        height="10"
        rx="2"
        stroke="white"
        strokeWidth="1.5"
      />
      <defs>
        <linearGradient id="email-gradient" x1="0" y1="0" x2="24" y2="24">
          <stop stopColor="hsl(35, 80%, 55%)" />
          <stop offset="1" stopColor="hsl(25, 70%, 50%)" />
        </linearGradient>
      </defs>
    </svg>
  );
}
