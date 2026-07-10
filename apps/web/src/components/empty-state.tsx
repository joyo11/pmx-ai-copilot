import { Button } from "@/components/ui/button";

export function EmptyState({
  Icon,
  title,
  description,
  actionLabel,
  onAction,
}: {
  Icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="flex max-w-md flex-col items-center gap-4 text-center">
        <div className="flex size-12 items-center justify-center rounded-full bg-muted">
          <Icon className="size-6 text-muted-foreground" />
        </div>
        <div className="space-y-1.5">
          <h2 className="text-lg font-semibold">{title}</h2>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
        {actionLabel ? (
          <Button onClick={onAction} disabled={!onAction}>
            {actionLabel}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
