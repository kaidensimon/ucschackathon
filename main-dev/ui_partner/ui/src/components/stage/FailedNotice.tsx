// A model did not load. Says what happened and offers what to do next.
// The three buttons do nothing in the mock.
import { CircleAlert } from "lucide-react";
import { Button } from "../shared/Button";

export function FailedNotice({
  name,
  reason,
  others,
  onDead,
}: {
  /** the seat's short name */
  name: string;
  /** what went wrong, in the engine's words */
  reason: string;
  /** how many seats are left if the debate goes on without this one */
  others: number;
  onDead: () => void;
}) {
  return (
    <div
      data-part="failed-notice"
      role="alert"
      className="flex items-center gap-4 rounded-card border border-line bg-surface py-3 pr-3 pl-4"
    >
      <CircleAlert size={18} aria-hidden="true" className="shrink-0 text-error" />
      <p className="min-w-0 flex-1 text-ink text-label">
        <strong className="font-semibold">{name} did not load.</strong> {reason}
      </p>
      <div className="flex shrink-0 gap-2">
        <Button variant="ink" onClick={onDead}>
          Try again
        </Button>
        <Button onClick={onDead}>Continue with {others}</Button>
        <Button onClick={onDead}>Stop</Button>
      </div>
    </div>
  );
}
