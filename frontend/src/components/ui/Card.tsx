import { ReactNode } from "react";

export default function Card({
  title,
  action,
  padded = true,
  className = "",
  children,
}: {
  title?: ReactNode;
  action?: ReactNode;
  padded?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={`rounded-xl border border-border bg-surface shadow-panel ${className}`}
    >
      {(title || action) && (
        <div className="flex items-center justify-between border-b border-border-subtle px-5 py-3.5">
          {typeof title === "string" ? (
            <h2 className="text-sm font-semibold text-primary">{title}</h2>
          ) : (
            title
          )}
          {action}
        </div>
      )}
      <div className={padded ? "p-5" : ""}>{children}</div>
    </div>
  );
}
