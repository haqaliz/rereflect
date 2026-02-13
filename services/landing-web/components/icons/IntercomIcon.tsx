interface IntercomIconProps {
  className?: string;
  size?: number;
}

export function IntercomIcon({ className, size = 24 }: IntercomIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <rect width="24" height="24" rx="5" fill="#286EFA" />
      <path
        d="M19.5 16.5c0 0-2.5 2.5-7.5 2.5s-7.5-2.5-7.5-2.5"
        stroke="white"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <line x1="6" y1="7" x2="6" y2="13" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="9" y1="5.5" x2="9" y2="14" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="12" y1="5" x2="12" y2="14.5" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="15" y1="5.5" x2="15" y2="14" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
      <line x1="18" y1="7" x2="18" y2="13" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
