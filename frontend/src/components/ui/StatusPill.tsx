import { LucideIcon } from "lucide-react";
import { Tone } from "./Badge";

const DOT_CLASSES: Record<Tone, string> = {
  neutral: "bg-tertiary",
  accent: "bg-accent",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
};

const TEXT_CLASSES: Record<Tone, string> = {
  neutral: "text-secondary",
  accent: "text-accent-hover",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  info: "text-info",
};

/** Generic status indicator: a colored dot (or icon) + label. Pure
 * presentational -- callers map their own status vocabulary to a
 * {tone, label, icon, pulse} shape rather than this component knowing
 * about pipeline-step or run-level status strings. */
export default function StatusPill({
  tone,
  label,
  icon: Icon,
  pulse = false,
  size = "md",
}: {
  tone: Tone;
  label: string;
  icon?: LucideIcon;
  pulse?: boolean;
  size?: "sm" | "md";
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-medium ${TEXT_CLASSES[tone]} ${size === "sm" ? "text-xs" : "text-sm"}`}
    >
      {Icon ? (
        <Icon size={size === "sm" ? 13 : 15} className={pulse ? "animate-pulse" : ""} />
      ) : (
        <span className="relative flex h-2 w-2">
          {pulse && (
            <span
              className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${DOT_CLASSES[tone]}`}
            />
          )}
          <span className={`relative inline-flex h-2 w-2 rounded-full ${DOT_CLASSES[tone]}`} />
        </span>
      )}
      {label}
    </span>
  );
}
