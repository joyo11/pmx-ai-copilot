import Link from "next/link";
import { ArrowRight, ShieldAlert, Activity, MessageSquare } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <div className="flex min-h-svh flex-col">
      <header className="flex h-16 items-center justify-between border-b px-6">
        <div className="flex items-center gap-2">
          <div className="flex size-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <ShieldAlert className="size-4" />
          </div>
          <span className="font-semibold tracking-tight">PMX AI</span>
        </div>
        <nav className="flex items-center gap-2">
          <Button variant="ghost" asChild>
            <Link href="/dashboard">Sign in</Link>
          </Button>
          <Button asChild>
            <Link href="/dashboard">
              Get started <ArrowRight className="size-4" />
            </Link>
          </Button>
        </nav>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col items-center justify-center gap-16 px-6 py-24 text-center">
        <div className="space-y-6">
          <div className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs text-muted-foreground">
            <span className="size-1.5 rounded-full bg-emerald-500" />
            Built for construction project managers
          </div>
          <h1 className="text-balance text-5xl font-semibold tracking-tight sm:text-6xl">
            Project Risk Copilot
            <br />
            <span className="text-muted-foreground">
              for the people who ship buildings.
            </span>
          </h1>
          <p className="mx-auto max-w-2xl text-balance text-lg text-muted-foreground">
            PMX AI reads your schedules, budgets, RFIs, and meeting notes, then
            tells you which projects are slipping, why, and what to do next.
            Grounded in your documents. Cited every time.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Button size="lg" asChild>
              <Link href="/dashboard">
                Open dashboard <ArrowRight className="size-4" />
              </Link>
            </Button>
            <Button size="lg" variant="ghost" asChild>
              <Link href="/chat">Ask a question</Link>
            </Button>
          </div>
        </div>

        <div className="grid w-full gap-6 text-left sm:grid-cols-3">
          <Feature
            Icon={Activity}
            title="Health scores that explain themselves"
            body="Every project gets a 0–100 score with the factors, weights, and reasoning. No black box."
          />
          <Feature
            Icon={ShieldAlert}
            title="Risk engine, not a keyword search"
            body="Schedule, budget, operational, communication, and compliance risks with severity, likelihood, and recommended action."
          />
          <Feature
            Icon={MessageSquare}
            title="Chat with your project"
            body="Ask 'what is delaying Bravo?' and get an answer with citations back to the specific PDF page."
          />
        </div>
      </main>

      <footer className="border-t px-6 py-6 text-center text-xs text-muted-foreground">
        Portfolio project built for firms like{" "}
        <a
          href="https://www.grouppmx.com/"
          target="_blank"
          rel="noreferrer"
          className="underline underline-offset-4"
        >
          Group PMX
        </a>
        . Not affiliated.
      </footer>
    </div>
  );
}

function Feature({
  Icon,
  title,
  body,
}: {
  Icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-xl border bg-card p-5">
      <Icon className="size-5 text-muted-foreground" />
      <h3 className="mt-3 text-sm font-semibold">{title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{body}</p>
    </div>
  );
}
