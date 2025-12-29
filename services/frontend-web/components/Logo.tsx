import { cn } from "@/lib/utils";

interface LogoProps {
  className?: string;
  size?: "sm" | "md" | "lg" | "xl";
}

const sizeMap = {
  sm: "w-6 h-6",
  md: "w-8 h-8",
  lg: "w-10 h-10",
  xl: "w-12 h-12",
};

export function Logo({ className, size = "md" }: LogoProps) {
  return (
    <svg
      viewBox="0 0 413 409"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn(sizeMap[size], className)}
    >
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M28.0273 0.368978C61.1953 -0.41002 97.4107 0.285874 130.808 0.289877C138.878 14.8668 147.93 34.4607 155.644 49.7557L256.057 49.7782C264.245 34.7272 273.125 15.8888 280.798 0.292806L383.744 0.328939C358.728 51.1179 332.444 101.739 307.744 152.603L412.295 152.619C404.886 168.229 396.387 184.556 388.625 200.079L333.935 309.584C344.883 332.758 357.644 356.126 368.735 379.281C371.545 385.148 380.861 402.349 382.644 407.548L382.098 408.257L280.227 408.293C273.698 393.41 262.637 372.952 255.128 357.954C223.382 358.836 187.554 358.075 155.55 358.011L130.367 408.274L26.5264 408.254C50.7564 357.742 77.6609 306.172 102.671 255.798L0 255.768L77.8564 100.097C61.3195 67.7266 43.7923 33.0558 28.0273 0.368978ZM154.312 153.16C154.312 153.16 107.047 246.931 103.059 255.651C154.487 255.618 257.589 254.937 257.589 254.937C257.589 254.937 291.409 187.185 307.271 152.767L237.852 152.781C216.486 152.791 154.312 153.16 154.312 153.16Z"
        className="fill-foreground"
      />
    </svg>
  );
}

export function LogoWithText({ className, size = "md" }: LogoProps) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <Logo size={size} />
      <span className="font-semibold text-foreground">
        <span className="text-muted-foreground">Re</span>reflect
      </span>
    </div>
  );
}
