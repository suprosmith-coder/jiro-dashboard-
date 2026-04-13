/**
 * Supabase Edge Function: bot-guilds
 *
 * Returns guild config data from Supabase for a specific guild.
 * Used by the dashboard to load settings, stats, and module configs.
 * Validates that the requesting user actually has access to that guild
 * by checking their Discord access token.
 *
 * Deploy:
 *   supabase functions deploy bot-guilds
 *
 * Required secrets:
 *   BOT_TOKEN
 *   SUPABASE_URL       (auto-injected by Supabase)
 *   SUPABASE_SERVICE_ROLE_KEY  (auto-injected by Supabase)
 */

import { serve } from "https://deno.land/std@0.177.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const DISCORD_API = "https://discord.com/api/v10";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
};

serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: CORS });

  try {
    const url      = new URL(req.url);
    const guildId  = url.searchParams.get("guild_id");
    const authHeader = req.headers.get("authorization") || "";
    const discordToken = authHeader.replace("Bearer ", "");

    if (!guildId)      return json({ error: "Missing guild_id" }, 400);
    if (!discordToken) return json({ error: "Missing authorization" }, 401);

    // ── Verify user actually has access to this guild ───────────
    const guildsRes = await fetch(`${DISCORD_API}/users/@me/guilds`, {
      headers: { Authorization: `Bearer ${discordToken}` },
    });

    if (!guildsRes.ok) return json({ error: "Invalid Discord token" }, 401);

    const userGuilds: any[] = await guildsRes.json();
    const hasAccess = userGuilds.some((g: any) => {
      if (g.id !== guildId) return false;
      const perms = BigInt(g.permissions);
      return (perms & 0x20n) === 0x20n || (perms & 0x8n) === 0x8n;
    });

    if (!hasAccess) return json({ error: "Access denied" }, 403);

    // ── Query Supabase for guild data ───────────────────────────
    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    );

    // Fetch config, recent stats in parallel
    const [configRes, msgStats, memberStats, modStats, amStats] = await Promise.all([
      supabase.from("guild_config").select("data").eq("guild_id", guildId).single(),
      supabase.from("message_logs").select("event_type", { count: "exact", head: true })
        .eq("guild_id", guildId)
        .gte("created_at", new Date(Date.now() - 7 * 86400000).toISOString()),
      supabase.from("member_events").select("event_type", { count: "exact", head: true })
        .eq("guild_id", guildId)
        .gte("created_at", new Date(Date.now() - 7 * 86400000).toISOString()),
      supabase.from("mod_logs").select("id", { count: "exact", head: true })
        .eq("guild_id", guildId)
        .gte("created_at", new Date(Date.now() - 7 * 86400000).toISOString()),
      supabase.from("automod_events").select("id", { count: "exact", head: true })
        .eq("guild_id", guildId)
        .gte("created_at", new Date(Date.now() - 7 * 86400000).toISOString()),
    ]);

    return json({
      config:  configRes.data?.data || {},
      stats: {
        messages_7d: msgStats.count    || 0,
        members_7d:  memberStats.count || 0,
        mod_7d:      modStats.count    || 0,
        automod_7d:  amStats.count     || 0,
      },
    });

  } catch (e) {
    console.error(e);
    return json({ error: "Internal server error", detail: String(e) }, 500);
  }
});

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...CORS, "Content-Type": "application/json" },
  });
}
