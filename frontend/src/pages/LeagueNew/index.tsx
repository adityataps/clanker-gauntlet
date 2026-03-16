import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { api } from "@/api/client";

export function LeagueNewPage() {
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [sessionCreation, setSessionCreation] = useState("manager_only");
  const [allowSharedKey, setAllowSharedKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const { data, error: apiError } = await api.POST("/leagues", {
        body: {
          name: name.trim(),
          description: description.trim() || null,
          sport: "nfl",
          session_creation: sessionCreation,
          allow_shared_key: allowSharedKey,
        },
      });
      if (apiError || !data) throw new Error("Failed to create league");
      navigate(`/leagues/${data.id}`);
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-8">
      <Button
        variant="ghost"
        size="sm"
        className="mb-6 -ml-1 text-muted-foreground"
        onClick={() => navigate("/dashboard")}
      >
        <ArrowLeft className="mr-1.5 h-4 w-4" />
        Back to dashboard
      </Button>

      <Card>
        <CardHeader>
          <CardTitle>Create a league</CardTitle>
          <CardDescription>
            A league is a group of managers that share sessions. You&apos;ll be the league manager.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-1.5">
              <Label htmlFor="name">League name</Label>
              <Input
                id="name"
                placeholder="The Gauntlet"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                autoFocus
                maxLength={80}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="description">
                Description <span className="font-normal text-muted-foreground">(optional)</span>
              </Label>
              <Input
                id="description"
                placeholder="A brief description of the league"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={240}
              />
            </div>

            <div className="space-y-1.5">
              <Label>Who can create sessions?</Label>
              <Select value={sessionCreation} onValueChange={setSessionCreation}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manager_only">Manager only</SelectItem>
                  <SelectItem value="any_member">Any member</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Controls who can spin up new simulation sessions inside this league.
              </p>
            </div>

            <Separator />

            {/* Shared key toggle */}
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-medium">League shared API key</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Allow members without their own LLM key to use a league-level key set by you.
                  Members with their own key always use it instead.
                </p>
              </div>
              <Switch
                checked={allowSharedKey}
                onCheckedChange={setAllowSharedKey}
                aria-label="Enable league shared key"
              />
            </div>

            {allowSharedKey && (
              <p className="rounded-md border border-border bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
                After creating the league, go to the <strong>Settings</strong> tab to add your API
                key. The key is encrypted at rest and only used for agent decisions.
              </p>
            )}

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate("/dashboard")}
                disabled={saving}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={!name.trim() || saving}>
                {saving ? "Creating…" : "Create league"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
