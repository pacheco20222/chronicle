import * as SeparatorPrimitive from "@radix-ui/react-separator";

export function Separator({ className = "", ...props }: SeparatorPrimitive.SeparatorProps) {
  return <SeparatorPrimitive.Root decorative orientation="horizontal" className={`h-px w-full bg-[#302b3c] ${className}`} {...props} />;
}
