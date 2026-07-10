"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import * as React from "react";
import { UserButton } from "@clerk/nextjs";

import { Button } from "@/components/ui/button";
import { NavDrawer } from "@/components/nav-drawer";

export function TopBar({ title }: { title: string }) {
  const { setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);

  return (
    <header className="sticky top-0 z-10 flex h-14 md:h-16 items-center justify-between gap-2 border-b bg-background/80 px-3 md:px-6 backdrop-blur">
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <NavDrawer />
        <h1 className="truncate text-sm font-medium text-muted-foreground">
          {title}
        </h1>
      </div>
      <div className="flex shrink-0 items-center gap-1 md:gap-2">
        <Button
          variant="ghost"
          size="icon"
          className="size-11 md:size-9"
          onClick={() =>
            setTheme(resolvedTheme === "dark" ? "light" : "dark")
          }
          aria-label="Toggle theme"
        >
          {mounted && resolvedTheme === "dark" ? (
            <Sun className="size-4" />
          ) : (
            <Moon className="size-4" />
          )}
        </Button>
        <UserButton afterSignOutUrl="/" />
      </div>
    </header>
  );
}
