# iPhone-Only Setup (No Mac Required)

Use the Market Rocket Scanner **entirely from your iPhone** — no computer needed after a one-time cloud deploy.

## How it works

| Piece | Where it runs |
|-------|----------------|
| Scanner + alerts | Cloud server (free Render.com) |
| You | iPhone Safari or Home Screen app |
| Push alerts | Telegram app on your phone |

`localhost` will **never** work on iPhone. You need a **real URL** like `https://your-app.onrender.com`.

---

## Step 1: Deploy to the cloud (one time, ~10 min)

### Option A — Render.com (recommended, free)

1. Push this repo to your GitHub account (or fork it)
2. Go to [render.com](https://render.com) → sign up free
3. **New → Blueprint** → connect your GitHub repo
4. Render reads `render.yaml` and deploys automatically
5. Copy your URL: `https://market-rocket-scanner-xxxx.onrender.com`

### Option B — From iPhone browser only

If you only have your phone:

1. Open [github.com](https://github.com) in Safari → fork `Simrantrading/ai-trading-dashboard`
2. Open [render.com](https://render.com) in Safari → sign up
3. New Web Service → connect GitHub → select repo
4. Set **Runtime**: Docker
5. Deploy → copy the URL

---

## Step 2: Telegram alerts on your phone (required)

Safari can't run scans in the background. **Telegram delivers alerts** even when the app is closed.

You'll receive two types of alerts:
- **Rocket alerts** — stocks making sharp price moves
- **News alerts** — major headlines from CNBC, Bloomberg, Yahoo Finance, WSJ, MarketWatch, and more that can move the market or specific sectors

1. Open Telegram → search **@BotFather**
2. Send `/newbot` → follow steps → copy your **bot token**
3. Start a chat with your new bot → send any message
4. Open this URL in Safari (replace `TOKEN`):

   ```
   https://api.telegram.org/botTOKEN/getUpdates
   ```

5. Find `"chat":{"id":123456789}` → that's your **chat ID**

6. In Render dashboard → your service → **Environment**:
   - `TELEGRAM_BOT_TOKEN` = your bot token
   - `TELEGRAM_CHAT_ID` = your chat ID

7. Redeploy. You'll get rocket **and news** alerts in Telegram all day.

### News alert sources

| Source | Coverage |
|--------|----------|
| CNBC | Top news, markets, economy, earnings |
| Bloomberg | Markets |
| Yahoo Finance | Breaking finance headlines |
| WSJ | Markets |
| MarketWatch | Top stories |
| Seeking Alpha | Market currents |

News is polled every **3 minutes** during market hours and filtered for major impact (Fed, earnings, mergers, sector moves, market-wide events). Set `NEWS_ALERTS_ENABLED=false` in Render env to disable.

---

## Step 3: Keep free server awake (cron)

Free Render sleeps after 15 min idle. Use a free cron to wake it:

1. Go to [cron-job.org](https://cron-job.org) → sign up free
2. Create cron job:
   - **URL**: `https://YOUR-APP.onrender.com/api/wake`
   - **Schedule**: every 5 minutes
   - **Active hours**: 4:00–20:00 ET (market hours)
3. Save

Each ping runs a scan, checks news feeds, and sends Telegram alerts.

---

## Step 4: Add to iPhone Home Screen

1. Open your cloud URL in **Safari** (not Chrome)
2. Tap **Share** (square with arrow)
3. Tap **Add to Home Screen**
4. Name it **Rockets** → Add

Opens like a native app. Tap **Enable Push** inside for Safari notifications too.

---

## Daily use on iPhone

| When | What to do |
|------|------------|
| Pre-market (4–9:30 ET) | Check Telegram for rocket + news alerts |
| Intraday | Open home screen app or Telegram |
| Post-market (4–8 ET) | Telegram alerts continue |
| Anytime | Open app → **Scan Now** for live results |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Safari can't connect to localhost | Use your **cloud URL**, not localhost |
| No alerts | Set Telegram env vars + cron job on `/api/wake` |
| App slow first load | Free tier waking up — wait 30 sec, retry |
| No pre-market data | Normal for some tickers — Telegram still fires on movers |

---

## Your URLs (fill in after deploy)

```
App:    https://________________.onrender.com
Wake:   https://________________.onrender.com/api/wake
Health: https://________________.onrender.com/api/health
```

Test health in Safari — should show `{"status":"ok"}`.
