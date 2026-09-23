import type { ButtonHTMLAttributes } from "react";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "solid" | "ghost" | "soft" };

export function Button({ className = "", variant = "solid", ...props }: ButtonProps) {
  const styles = {
    solid: "ui-button-solid",
    soft: "ui-button-soft",
    ghost: "ui-button-ghost",
  }[variant];
  return <button className={`ui-button ${styles} ${className}`} {...props} />;
}
