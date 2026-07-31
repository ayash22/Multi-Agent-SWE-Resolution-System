import { LucideIcon } from "lucide-react";
import { ReactNode } from "react";

export default function EmptyState({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      <div className="mb-1 flex h-10 w-10 items-center justify-center rounded-full bg-elevated text-tertiary">
        <Icon size={18} />
      </div>
      <div className="text-sm font-medium text-primary">{title}</div>
      {description && (
        <p className="max-w-sm text-xs leading-relaxed text-secondary">{description}</p>
      )}
      {children}
    </div>
  );
}
