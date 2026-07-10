"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FolderKanban,
  MessageSquare,
  FileText,
  Bell,
  Settings,
  ShieldAlert,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const items = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/notifications", label: "Notifications", icon: Bell },
];

const bottomItems = [
  { href: "/settings", label: "Settings", icon: Settings },
];

/** Desktop fixed rail (hidden below md). Mobile uses NavDrawer via TopBar. */
export function NavRail() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex h-svh w-16 flex-col border-r bg-sidebar text-sidebar-foreground">
      <div className="flex h-16 items-center justify-center border-b">
        <Link
          href="/"
          className="flex size-9 items-center justify-center rounded-md bg-primary text-primary-foreground"
          aria-label="PMX AI home"
        >
          <ShieldAlert className="size-5" />
        </Link>
      </div>
      <nav className="flex flex-1 flex-col items-center gap-1 py-3">
        {items.map((it) => (
          <NavLink
            key={it.href}
            href={it.href}
            label={it.label}
            Icon={it.icon}
            active={pathname?.startsWith(it.href) ?? false}
          />
        ))}
      </nav>
      <nav className="flex flex-col items-center gap-1 py-3 border-t">
        {bottomItems.map((it) => (
          <NavLink
            key={it.href}
            href={it.href}
            label={it.label}
            Icon={it.icon}
            active={pathname?.startsWith(it.href) ?? false}
          />
        ))}
      </nav>
    </aside>
  );
}

function NavLink({
  href,
  label,
  Icon,
  active,
}: {
  href: string;
  label: string;
  Icon: React.ComponentType<{ className?: string }>;
  active: boolean;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href={href}
          className={cn(
            "flex size-10 items-center justify-center rounded-md text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
            active && "bg-sidebar-accent text-sidebar-accent-foreground"
          )}
          aria-label={label}
        >
          <Icon className="size-5" />
        </Link>
      </TooltipTrigger>
      <TooltipContent side="right" sideOffset={8}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}

/** Full list of nav destinations for consumers (drawer, etc.). */
export const NAV_ITEMS = items;
export const NAV_BOTTOM_ITEMS = bottomItems;
