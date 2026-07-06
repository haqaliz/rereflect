interface AsanaIconProps {
  className?: string;
  size?: number;
}

export function AsanaIcon({ className, size = 24 }: AsanaIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <rect width="24" height="24" rx="5" fill="#F06A6A" />
      {/* Asana mark: three overlapping circles */}
      <circle cx="12" cy="7.25" r="2.25" fill="white" />
      <circle cx="7.25" cy="14.75" r="2.25" fill="white" />
      <circle cx="16.75" cy="14.75" r="2.25" fill="white" />
    </svg>
  );
}
