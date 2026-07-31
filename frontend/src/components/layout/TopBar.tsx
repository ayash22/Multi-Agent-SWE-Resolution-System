import { ReactNode } from "react";

export default function TopBar({
  title,
  subtitle,
  action,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex h-14 shrink-0 items-center justify-between border-b border-border-subtle bg-surface/70 px-6 backdrop-blur">
      <div className="min-w-0">
        <div className="truncate text-sm font-semibold text-primary">{title}</div>
        {subtitle && <div className="truncate text-xs text-tertiary">{subtitle}</div>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-3">{action}</div>}
    </div>
  );
}
