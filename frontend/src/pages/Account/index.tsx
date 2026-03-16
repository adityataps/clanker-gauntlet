import { useEffect, useState } from "react";
import { Eye, EyeOff, Save, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { api } from "@/api/client";
import { useAuthStore } from "@/store/authStore";

const PROVIDERS = [
  { key: "anthropic", label: "Anthropic (Claude)" },
  { key: "openai", label: "OpenAI (GPT)" },
  { key: "gemini", label: "Google (Gemini)" },
] as const;

type ProviderKey = (typeof PROVIDERS)[number]["key"];

function ApiKeyRow({
  providerKey,
  label,
  hasKey,
  onSaved,
}: {
  providerKey: ProviderKey;
  label: string;
  hasKey: boolean;
  onSaved: () => void;
}) {
  const [value, setValue] = useState("");
  const [visible, setVisible] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function handleSave() {
    if (!value.trim()) return;
    setSaving(true);
    try {
      await api.PUT("/auth/me/api-key", {
        body: { provider: providerKey, api_key: value.trim() },
      });
      setValue("");
      onSaved();
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      await api.DELETE("/auth/me/api-key", {
        body: { provider: providerKey },
      });
      onSaved();
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label>{label}</Label>
        {hasKey ? (
          <Badge variant="secondary" className="text-xs">
            Key saved
          </Badge>
        ) : (
          <Badge variant="outline" className="text-xs text-muted-foreground">
            Not set
          </Badge>
        )}
      </div>

      <div className="flex gap-2">
        <div className="relative flex-1">
          <Input
            type={visible ? "text" : "password"}
            placeholder={hasKey ? "Enter new key to replace…" : "sk-…"}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="pr-9"
          />
          <button
            type="button"
            onClick={() => setVisible((v) => !v)}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>

        <Button size="sm" onClick={handleSave} disabled={!value.trim() || saving}>
          <Save className="mr-1.5 h-3.5 w-3.5" />
          {saving ? "Saving…" : "Save"}
        </Button>

        {hasKey && (
          <Button size="sm" variant="destructive" onClick={handleDelete} disabled={deleting}>
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    </div>
  );
}

export function AccountPage() {
  const { user, refreshUser } = useAuthStore();
  const [hasKeys, setHasKeys] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (user) setHasKeys(user.has_keys);
  }, [user]);

  async function reload() {
    await refreshUser();
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-8">
      <h1 className="mb-1 text-2xl font-bold">Account settings</h1>
      <p className="mb-8 text-sm text-muted-foreground">Manage your profile and API keys</p>

      {/* Profile */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Profile
        </h2>
        <div className="space-y-1.5">
          <Label>Display name</Label>
          <Input value={user?.display_name ?? ""} disabled />
        </div>
        <div className="space-y-1.5">
          <Label>Email</Label>
          <Input value={user?.email ?? ""} disabled />
        </div>
      </section>

      <Separator className="my-8" />

      {/* API Keys */}
      <section className="space-y-5">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            LLM API keys
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Keys are encrypted at rest and used to power your agent teams. Stored per-provider — you
            only need to set keys for providers you plan to use.
          </p>
        </div>

        {PROVIDERS.map(({ key, label }) => (
          <ApiKeyRow
            key={key}
            providerKey={key}
            label={label}
            hasKey={hasKeys[key] ?? false}
            onSaved={reload}
          />
        ))}
      </section>
    </div>
  );
}
