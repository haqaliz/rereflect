interface JiraIconProps {
  className?: string;
  size?: number;
}

export function JiraIcon({ className, size = 24 }: JiraIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <rect width="24" height="24" rx="5" fill="#0052CC" />
      {/* Jira mark simplified: three stacked/overlapping chevrons */}
      <path
        d="M12 4.5L16.5 9C16.5 10.6569 15.1569 12 13.5 12H12V10.5C12 9.67157 11.3284 9 10.5 9H9V7.5C9 5.84315 10.3431 4.5 12 4.5Z"
        fill="white"
      />
      <path
        d="M8.75 8.25L13.25 12.75C13.25 14.4069 11.9069 15.75 10.25 15.75H8.75V14.25C8.75 13.4216 8.07843 12.75 7.25 12.75H5.75V11.25C5.75 9.59315 7.09315 8.25 8.75 8.25Z"
        fill="white"
        opacity="0.75"
      />
      <path
        d="M12 12L16.5 16.5C16.5 18.1569 15.1569 19.5 13.5 19.5H12V18C12 17.1716 11.3284 16.5 10.5 16.5H9V15C9 13.3431 10.3431 12 12 12Z"
        fill="white"
        opacity="0.5"
      />
    </svg>
  );
}
