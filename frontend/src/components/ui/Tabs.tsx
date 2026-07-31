export interface TabItem {
  id: string;
  label: string;
  badge?: React.ReactNode;
}

export default function Tabs({
  items,
  activeId,
  onChange,
  className = "",
}: {
  items: TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <div className={`inline-flex items-center gap-1 rounded-lg bg-app p-1 ${className}`}>
      {items.map((item) => (
        <button
          key={item.id}
          onClick={() => onChange(item.id)}
          className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            item.id === activeId
              ? "bg-elevated text-primary shadow-sm"
              : "text-secondary hover:text-primary"
          }`}
        >
          {item.label}
          {item.badge}
        </button>
      ))}
    </div>
  );
}
