import { useId, useState } from "react";

import { callTool } from "../api/rpc";
import type { JobStatus, VaultStatus } from "../types";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader } from "./ui/card";

const setupHint = "Set a vault first: chronicle vault set <path>";

export function VaultProjectToggle({ project, vault, onRefresh, running }: {
  project: string;
  vault: VaultStatus;
  onRefresh: () => Promise<unknown>;
  running: boolean;
}) {
  const hintId = useId();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mirrored = vault.projects.includes(project);

  async function toggle() {
    if (mirrored && !window.confirm(`Remove ${project}'s pages from the Obsidian vault? Your memories are not affected.`)) return;
    setSaving(true);
    setError(null);
    try {
      await callTool(mirrored ? "memory_vault_remove_project" : "memory_vault_add_project", { project });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update vault project");
    } finally {
      // Opt-in settings can change even when generating/deleting pages fails.
      await onRefresh();
      setSaving(false);
    }
  }

  return <div className="vault-controls">
    <Button variant={mirrored ? "soft" : "ghost"} aria-pressed={mirrored}
      aria-label={`Show in Obsidian: ${project}`} aria-describedby={!vault.path ? hintId : undefined}
      disabled={!vault.path || saving || running} onClick={() => void toggle()}>
      {saving ? "Saving..." : "Show in Obsidian"}<span aria-hidden="true">{mirrored ? " · on" : " · off"}</span>
    </Button>
    {!vault.path && <p className="control-note" id={hintId}>{setupHint}</p>}
    {error && <p className="control-note" role="alert">{error}</p>}
  </div>;
}

export function VaultControls({ vault, running, onStarted }: {
  vault: VaultStatus;
  running: boolean;
  onStarted: (job: JobStatus) => void;
}) {
  const hintId = useId();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function sync() {
    setStarting(true);
    setError(null);
    try {
      onStarted(await callTool<JobStatus>("memory_vault_sync"));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not sync vault");
    } finally {
      setStarting(false);
    }
  }

  return <Card className="control-plate process-plate"><CardHeader>
    <div className="project-title-row"><h2>Obsidian vault</h2><Badge>{vault.projects.length} projects</Badge></div>
  </CardHeader><CardContent>
    <p className="control-note mono vault-path">{vault.path || "No vault configured"}</p>
    <div className="vault-controls"><Button variant="soft" disabled={!vault.path || running || starting}
      aria-describedby={!vault.path ? hintId : undefined} onClick={() => void sync()}>
      {starting ? "Starting..." : "Sync vault"}
    </Button></div>
    {!vault.path && <p className="control-note" id={hintId}>{setupHint}</p>}
    {(error || vault.last_error) && <p className="control-note" role="alert">{error || vault.last_error}</p>}
  </CardContent></Card>;
}
