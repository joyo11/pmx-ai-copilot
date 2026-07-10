"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { createProject, type ProjectSector } from "@/lib/api";

const SECTORS: { value: ProjectSector; label: string }[] = [
  { value: "healthcare", label: "Healthcare" },
  { value: "infrastructure", label: "Infrastructure" },
  { value: "transportation", label: "Transportation" },
  { value: "education", label: "Education" },
  { value: "commercial", label: "Commercial" },
  { value: "other", label: "Other" },
];

export function NewProjectDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const { getToken } = useAuth();
  const [name, setName] = React.useState("");
  const [client, setClient] = React.useState("");
  const [sector, setSector] = React.useState<ProjectSector>("healthcare");
  const [submitting, setSubmitting] = React.useState(false);

  const reset = React.useCallback(() => {
    setName("");
    setClient("");
    setSector("healthcare");
    setSubmitting(false);
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    try {
      const token = await getToken();
      const project = await createProject(
        { name: name.trim(), client: client.trim(), sector },
        { token }
      );
      toast.success(`Created "${project.name}"`);
      onOpenChange(false);
      reset();
      router.push(`/projects/${project.id}`);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to create project"
      );
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) reset();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
          <DialogDescription>
            Give the project a name and pick its sector. You can upload
            schedules, budgets, and RFIs on the next screen.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="project-name">Project name</Label>
            <Input
              id="project-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Hospital South Wing Expansion"
              required
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="project-client">Client / owner</Label>
            <Input
              id="project-client"
              value={client}
              onChange={(e) => setClient(e.target.value)}
              placeholder="Group PMX"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="project-sector">Sector</Label>
            <Select
              id="project-sector"
              value={sector}
              onChange={(e) => setSector(e.target.value as ProjectSector)}
            >
              {SECTORS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </Select>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || !name.trim()}>
              {submitting ? "Creating…" : "Create project"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
