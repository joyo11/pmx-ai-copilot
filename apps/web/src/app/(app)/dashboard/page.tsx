import { TopBar } from "@/components/top-bar";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { AlertCircle, DollarSign, Activity, FolderKanban } from "lucide-react";

export default function DashboardPage() {
  return (
    <>
      <TopBar title="Dashboard" />
      <main className="flex-1 space-y-6 p-6">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Active projects"
            value="—"
            Icon={FolderKanban}
            hint="No projects yet"
          />
          <StatCard
            label="At risk"
            value="—"
            Icon={AlertCircle}
            hint="Data pending"
          />
          <StatCard
            label="Total budget"
            value="—"
            Icon={DollarSign}
            hint="Upload budgets"
          />
          <StatCard
            label="Avg health"
            value="—"
            Icon={Activity}
            hint="Score coming soon"
          />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Welcome to PMX AI</CardTitle>
            <CardDescription>
              This is the executive dashboard. Once you create a project and
              upload your first document, health scores, risks, and AI alerts
              will populate here.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            M0 — foundation shipping. Upload → risk engine → chat streams
            arrive in M1.
          </CardContent>
        </Card>
      </main>
    </>
  );
}

function StatCard({
  label,
  value,
  Icon,
  hint,
}: {
  label: string;
  value: string;
  Icon: React.ComponentType<{ className?: string }>;
  hint: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardDescription className="flex items-center justify-between">
          <span>{label}</span>
          <Icon className="size-4 text-muted-foreground" />
        </CardDescription>
        <CardTitle className="text-3xl font-semibold tabular-nums">
          {value}
        </CardTitle>
      </CardHeader>
      <CardContent className="text-xs text-muted-foreground">
        {hint}
      </CardContent>
    </Card>
  );
}
