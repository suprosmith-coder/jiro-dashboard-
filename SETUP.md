# Jiro Dashboard — Full Setup Guide

## Architecture

```
User
 │
 ▼
GitHub Pages (static)
  index.html      ← Landing / Login page
  callback.html   ← OAuth redirect handler
  servers.html    ← Guild picker
  app.html        ← Main dashboard
 │
 │  POST /discord-oauth  (code exchange)
 ▼
Supabase Edge Functions
  discord-oauth   ← Exchanges code → token, fetches user + guilds
  bot-guilds      ← Validates access, serves guild config
 │
 ▼
Supabase (PostgreSQL)
  All bot logs read directly via REST API (anon key + RLS)
```

---

## Step 1 — Discord Developer Portal

1. Go to https://discord.com/developers/applications
2. Create a new application (or use your bot's existing one)
3. Go to **OAuth2 → General**
4. Add redirect URI: `https://yourusername.github.io/jiro-dashboard/callback.html`
5. Copy your **Client ID** and **Client Secret**

---

## Step 2 — Supabase Project

1. Create a project at https://supabase.com
2. Run `supabase_schema.sql` in the SQL Editor
3. Copy your **Project URL** and **anon key** from Settings → API

### Set Edge Function Secrets

```bash
supabase secrets set DISCORD_CLIENT_ID=your_client_id
supabase secrets set DISCORD_CLIENT_SECRET=your_client_secret
supabase secrets set DISCORD_REDIRECT_URI=https://yourusername.github.io/jiro-dashboard/callback.html
supabase secrets set BOT_TOKEN=your_bot_token
```

### Deploy Edge Functions

```bash
supabase functions deploy discord-oauth
supabase functions deploy bot-guilds
```

---

## Step 3 — Configure Frontend Files

In **index.html**, find the CONFIG block and fill in:
```js
const CONFIG = {
  DISCORD_CLIENT_ID: "YOUR_CLIENT_ID_HERE",
  REDIRECT_URI:      "https://yourusername.github.io/jiro-dashboard/callback.html",
};
```

In **callback.html**:
```js
const CONFIG = {
  SUPABASE_FUNCTION_URL: "https://YOUR_PROJECT.supabase.co/functions/v1/discord-oauth",
};
```

In **app.html**:
```js
const CFG = {
  SUPABASE_URL:  "https://YOUR_PROJECT.supabase.co",
  SUPABASE_ANON: "YOUR_ANON_KEY",
  BOT_GUILDS_FN: "https://YOUR_PROJECT.supabase.co/functions/v1/bot-guilds",
};
```

Also update the **INVITE_URL** in `servers.html` with your bot's client ID.

---

## Step 4 — GitHub Pages

1. Push all dashboard files to a GitHub repo
2. Go to **Settings → Pages → Source → main → / (root)**
3. Your site is live at `https://yourusername.github.io/repo-name/`

---

## Step 5 — Bot `logs.py`

Replace your `cogs/logs.py` with the provided one.
It writes to Supabase using the **service role key** (set as an env var in your bot).

```python
# In your bot's .env or config:
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_SERVICE_KEY = "your_service_role_key"  # NOT the anon key
```

---

## User Flow (exactly like Carl-bot / Sapphire)

1. User visits `index.html` → clicks **Login with Discord**
2. Discord OAuth screen appears → user approves
3. Discord redirects to `callback.html?code=XXX`
4. `callback.html` POSTs code to Supabase Edge Function `discord-oauth`
5. Edge Function returns `{ user, guilds, access_token }`
6. User is redirected to `servers.html` — grid of servers where **Jiro is present**
7. User clicks a server → redirected to `app.html?guild=GUILD_ID`
8. Dashboard loads — all data is their server's logs from Supabase

No passwords. No API keys shown to users. Completely seamless.
