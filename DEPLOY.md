# Deploying this to a live, public URL (free, ~10 minutes)

This gets you a real `https://yourname.onrender.com` URL that anyone --
a provider, an investor, a friend -- can hit directly. No credit card
needed. This has to be done from your own accounts, not by me, since it
needs your credentials.

## Step 1: Push the code to GitHub

If you don't already have a GitHub account, make one at github.com (free).

```bash
cd paywall-gateway
git init
git add .
git commit -m "Initial paywall gateway MVP"
```

Then on github.com: click the "+" in the top right -> "New repository" ->
name it (e.g. `paywall-gateway`) -> Create repository (leave it empty,
don't add a README). GitHub will show you commands like:

```bash
git remote add origin https://github.com/YOUR_USERNAME/paywall-gateway.git
git branch -M main
git push -u origin main
```

Run those. Your code is now on GitHub.

## Step 2: Deploy on Render

1. Go to render.com and sign up (free, no card required).
2. Click **New** -> **Web Service**.
3. Connect your GitHub account, then select the `paywall-gateway` repo.
4. Render should auto-detect the `Dockerfile` and the `render.yaml` in
   this project. If it asks you to confirm settings, the important ones
   are already set: runtime = Docker, plan = Free.
5. Click **Create Web Service**.

Render will build and deploy it -- takes a few minutes the first time.
When it's done, you'll get a URL like:

```
https://paywall-gateway-xxxx.onrender.com
```

That's live. Anyone can hit `https://paywall-gateway-xxxx.onrender.com/`
right now and get a real response.

## Step 3: Register a real provider + endpoint on the live instance

Same calls as `test_flow.py`, just pointed at your live URL instead of
`127.0.0.1`:

```bash
curl -X POST https://paywall-gateway-xxxx.onrender.com/providers \
  -H "Content-Type: application/json" \
  -d '{"slug":"acme-data","name":"Acme Financial Data"}'

curl -X POST https://paywall-gateway-xxxx.onrender.com/providers/acme-data/endpoints \
  -H "Content-Type: application/json" \
  -d '{"path":"market-summary","price_usd":0.002,"upstream_url":"https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&apikey=demo"}'
```

Then visit `https://paywall-gateway-xxxx.onrender.com/directory` in a
browser -- you'll see your live, public directory listing. That URL is
the single most useful thing to have in hand when you talk to anyone
about this: it's not a screenshot or a claim, it's a real, working thing
they can click.

## One real limitation to know about (free tier, not your code)

Render's free web services **spin down after 15 minutes of no traffic**
and take 30-60 seconds to wake back up on the next request. That's fine
for you testing it, but if you're about to show it to someone live (a
call, a demo), hit the URL yourself a minute or two beforehand so it's
already warm when they see it. This is a free-tier constraint, not
something wrong with the build -- when you eventually want an always-on
version, Render's paid tier starts at $7/month.

## What you'll be able to point to after this

- A real, public URL running your actual code, not a local demo.
- A real `/directory` endpoint showing a live paywalled listing.
- The GitHub repo itself, showing real commit history and working code
  -- this matters more than people expect; anyone technical will look.
