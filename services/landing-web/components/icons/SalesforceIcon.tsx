interface SalesforceIconProps {
  className?: string;
  size?: number;
}

export function SalesforceIcon({ className, size = 24 }: SalesforceIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <rect width="24" height="24" rx="5" fill="#00A1E0" />
      {/* Salesforce cloud simplified */}
      <path
        d="M9.3 8.6c.55-.58 1.32-.94 2.18-.94 1.14 0 2.13.63 2.65 1.57.45-.2.95-.32 1.47-.32 1.99 0 3.6 1.62 3.6 3.61 0 1.99-1.61 3.6-3.6 3.6H8.4C7.07 16.12 6 15.05 6 13.72c0-1.13.78-2.08 1.83-2.34a2.87 2.87 0 0 1 1.47-2.78Z"
        fill="white"
      />
    </svg>
  );
}
