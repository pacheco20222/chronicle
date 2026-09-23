import * as CheckboxPrimitive from "@radix-ui/react-checkbox";

export function Checkbox({ className = "", ...props }: CheckboxPrimitive.CheckboxProps) {
  return (
    <CheckboxPrimitive.Root className={`h-4 w-4 rounded border border-[#655876] data-[state=checked]:border-[#efb366] data-[state=checked]:bg-[#efb366] ${className}`} {...props}>
      <CheckboxPrimitive.Indicator className="flex items-center justify-center text-xs font-black text-[#16151d]">✓</CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
