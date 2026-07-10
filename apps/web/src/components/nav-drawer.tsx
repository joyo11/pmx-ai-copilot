"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, ShieldAlert } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { NAV_ITEMS, NAV_BOTTOM_ITEMS } from "@/components/nav-rail";

/** Mobile hamburger + slide-out drawer with the same nav items as the rail. */
export function NavDrawer() {
  const [open, setOpen] = React.useState(false);
  const pathname = usePathname();

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="md:hidden size-11"
          aria-label="Open navigation"
        >
          <Menu className="size-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-72 p-0 flex flex-col">
        <SheetHeader className="border-b p-4">
          <SheetTitle asChild>
            <Link
              href="/"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 text-base font-semibold"
            >
              <span className="flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <ShieldAlert className="size-4" />
              </span>
              PMX AI
            </Link>
          </SheetTitle>
        </SheetHeader>
        <nav className="flex-1 overflow-y-auto p-2">
          {NAV_ITEMS.map((it) => (
            <DrawerLink
              key={it.href}
              href={it.href}
              label={it.label}
              Icon={it.icon}
              active={pathname?.startsWith(it.href) ?? false}
              onClick={() => setOpen(false)}
            />
          ))}
        </nav>
        <nav className="border-t p-2">
          {NAV_BOTTOM_ITEMS.map((it) => (
            <DrawerLink
              key={it.href}
              href={it.href}
              label={it.label}
              Icon={it.icon}
              active={pathname?.startsWith(it.href) ?? false}
              onClick={() => setOpen(false)}
            />
          ))}
        </nav>
      </SheetContent>
    </Sheet>
  );
}

function DrawerLink({
  href,
  label,
  Icon,
  active,
  onClick,
}: {
  href: string;
  label: string;
  Icon: React.ComponentType<{ className?: string }>;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className={cn(
        "flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-medium text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
        active && "bg-sidebar-accent text-sidebar-accent-foreground"
      )}
    >
      <Icon className="size-5" />
      {label}
    </Link>
  );
}
