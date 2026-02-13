interface HubSpotIconProps {
  className?: string;
  size?: number;
}

export function HubSpotIcon({ className, size = 24 }: HubSpotIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <rect width="24" height="24" rx="5" fill="#FF7A59" />
      {/* HubSpot sprocket simplified */}
      <circle cx="12" cy="12" r="3" stroke="white" strokeWidth="1.5" />
      <circle cx="12" cy="5.5" r="1.5" fill="white" />
      <circle cx="12" cy="18.5" r="1.5" fill="white" />
      <circle cx="5.5" cy="12" r="1.5" fill="white" />
      <circle cx="18.5" cy="12" r="1.5" fill="white" />
      <line x1="12" y1="7" x2="12" y2="9" stroke="white" strokeWidth="1.5" />
      <line x1="12" y1="15" x2="12" y2="17" stroke="white" strokeWidth="1.5" />
      <line x1="7" y1="12" x2="9" y2="12" stroke="white" strokeWidth="1.5" />
      <line x1="15" y1="12" x2="17" y2="12" stroke="white" strokeWidth="1.5" />
    </svg>
  );
}
