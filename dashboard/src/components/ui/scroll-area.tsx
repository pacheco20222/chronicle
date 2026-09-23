import type { HTMLAttributes } from "react";

export function ScrollArea({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`overflow-auto ${className}`} {...props} />;
}
