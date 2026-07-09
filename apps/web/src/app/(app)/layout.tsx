import { NavRail } from "@/components/nav-rail";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-svh">
      <NavRail />
      <div className="flex flex-1 flex-col">{children}</div>
    </div>
  );
}
