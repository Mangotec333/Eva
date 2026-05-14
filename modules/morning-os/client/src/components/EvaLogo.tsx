import { cn } from '@/lib/utils';

export function EvaLogo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="EVA"
      fill="none"
      className={cn(className)}
    >
      {/* Two arcs meeting — a sunrise / awakening mark */}
      <circle cx="16" cy="16" r="13" stroke="currentColor" strokeWidth="1.5" opacity="0.35" />
      <path
        d="M5 19 C 10 11, 22 11, 27 19"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
      <circle cx="16" cy="19" r="1.6" fill="currentColor" />
    </svg>
  );
}
