# 🚀 Padel League Hub - Production Deployment Guide

Complete guide to deploy your padel league application to production using Render.com.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Deployment Steps](#deployment-steps)
3. [Post-Deployment Configuration](#post-deployment-configuration)
4. [Testing Your Deployment](#testing-your-deployment)
5. [Upgrading to Production](#upgrading-to-production)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### ✅ Before You Start

- [ ] GitHub account created
- [ ] Your code is in a GitHub repository
- [ ] Render.com account created (free, no credit card needed for testing)
- [ ] WhatsApp API credentials (if using WhatsApp notifications)
- [ ] Email credentials (if using email notifications)

### 📦 Files You Need (Already Created)

All these files are included in your repository:

- `render.yaml` - Deployment configuration
- `Procfile` - Process configuration
- `runtime.txt` - Python version
- `requirements.txt` - Dependencies
- `init_db.py` - Database initialization
- `migrate_to_postgres.py` - SQLite to PostgreSQL migration

---

## 🎯 Deployment Steps

### Step 1: Push Your Code to GitHub

```bash
# Initialize git (if not already done)
cd padel-league-hub
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit - ready for deployment"

# Create a new repository on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/padel-league-hub.git
git branch -M main
git push -u origin main
```

### Step 2: Create Render Account

1. Go to [render.com](https://render.com)
2. Click "Get Started" or "Sign Up"
3. Sign up with GitHub (recommended for easy integration)

### Step 3: Deploy from GitHub

#### Option A: Using render.yaml (Recommended - One Click Deploy)

1. **In Render Dashboard:**
   - Click "New +" → "Blueprint"
   - Connect your GitHub account if not already connected
   - Select your `padel-league-hub` repository
   - Render will automatically detect `render.yaml`
   - Click "Apply"

2. **Render will automatically create:**
   - Web Service (your Flask app)
   - Worker Service (scheduled tasks/reminders)
   - PostgreSQL Database
   - All environment variables

#### Option B: Manual Setup (Alternative)

If you prefer manual control:

1. **Create PostgreSQL Database:**
   - Click "New +" → "PostgreSQL"
   - Name: `padel-league-db`
   - Plan: Free
   - Click "Create Database"
   - **Save the connection string!**

2. **Create Web Service:**
   - Click "New +" → "Web Service"
   - Connect your repository
   - Name: `padel-league-hub`
   - Runtime: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
   - Plan: Free
   - Add environment variables (see Step 4)
   - Click "Create Web Service"

3. **Create Worker Service (for scheduled tasks):**
   - Click "New +" → "Background Worker"
   - Connect your repository
   - Name: `padel-league-worker`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python send_reminders.py`
   - Plan: Free
   - Add same environment variables
   - Click "Create Worker"

### Step 4: Configure Environment Variables

In your Render dashboard for the **Web Service**, go to "Environment" and add:

#### 🔴 Critical Variables (Generate Secure Values!)

```bash
# Generate SECRET_KEY with Python:
# python -c "import secrets; print(secrets.token_hex(32))"

SECRET_KEY=<your_generated_secret_key>
ADMIN_PASSWORD=<create_a_strong_password>
VERIFY_TOKEN=<create_a_verification_token>
```

#### 🔵 Application Settings

```bash
APP_BASE_URL=https://your-app-name.onrender.com
FLASK_ENV=production
TESTING_MODE=false
```

#### 🟡 Database (Auto-configured by Render)

```bash
DATABASE_URL=<automatically_set_by_render>
```

#### 🟢 WhatsApp (Optional - Add if Using)

```bash
WHATSAPP_API_KEY=<your_api_key>
WHATSAPP_PHONE_ID=<your_phone_id>
```

#### 🟣 Email (Optional - Add if Using)

```bash
EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=<your_app_specific_password>
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
```

**Important:** Click "Save Changes" after adding variables. This will trigger a redeploy.

### Step 5: Initialize Database

Once your app is deployed:

1. **Go to Render Dashboard** → Your Web Service → "Shell"
2. Run initialization:
   ```bash
   python init_db.py
   ```
3. You should see: "✅ Database initialized successfully!"

### Step 6: Migrate Existing Data (Optional)

If you have existing data in SQLite that you want to migrate:

1. **On your local machine:**
   ```bash
   # Set production database URL in .env
   DATABASE_URL=<your_render_postgres_url>
   
   # Run migration
   python migrate_to_postgres.py
   ```

2. Follow the prompts to confirm migration

---

## 🔧 Post-Deployment Configuration

### Set Up Custom Domain (Optional)

1. **In Render Dashboard:**
   - Go to your Web Service → "Settings"
   - Scroll to "Custom Domain"
   - Add your domain: `padelleague.com`
   - Follow DNS instructions to point your domain to Render

2. **SSL Certificate:**
   - Automatically provisioned by Render
   - No configuration needed!

### Enable Error Monitoring (Recommended)

1. **Sign up for Sentry (free tier):**
   - Go to [sentry.io](https://sentry.io)
   - Create account and project
   - Copy your DSN

2. **Add to requirements.txt:**
   ```
   sentry-sdk[flask]==1.38.0
   ```

3. **Add environment variable in Render:**
   ```bash
   SENTRY_DSN=<your_sentry_dsn>
   ENVIRONMENT=production
   ```

4. **Uncomment Sentry code in app.py** (lines 3006-3017)

### Set Up Monitoring

1. **Uptime Monitoring (Free):**
   - [UptimeRobot](https://uptimerobot.com)
   - [Pingdom](https://www.pingdom.com)
   - Add your Render URL for monitoring

2. **Render Built-in Monitoring:**
   - View logs: Dashboard → Service → "Logs"
   - View metrics: Dashboard → Service → "Metrics"

---

## ✅ Testing Your Deployment

### 1. Check App is Running

Visit your URL: `https://your-app-name.onrender.com`

You should see your padel league homepage!

### 2. Test Admin Access

1. Go to: `https://your-app-name.onrender.com/admin`
2. Login with your `ADMIN_PASSWORD`
3. Verify you can access the admin panel

### 3. Test Basic Functionality

- [ ] Homepage loads correctly
- [ ] Team registration works
- [ ] Free agent registration works
- [ ] Admin panel accessible
- [ ] Leaderboard displays

### 4. Test in TESTING_MODE First

**Important:** Before sending real notifications:

1. Set `TESTING_MODE=true` in environment variables
2. Test all notification features
3. Verify messages go to test contacts only
4. When confident, set `TESTING_MODE=false`

### 5. Check Logs

In Render Dashboard:
- Web Service → "Logs" - Check for errors
- Worker Service → "Logs" - Verify scheduler is running

---

## 🚀 Upgrading to Production

### When You're Ready for Real Usage

Currently on **Free Tier** limitations:
- ⏰ Web service sleeps after 15 min inactivity
- 🕐 Takes ~30 seconds to wake up
- ⚡ Limited resources
- 💾 Limited database storage

### Upgrade to Starter Plan ($7/month per service)

1. **In Render Dashboard:**
   - Go to your Web Service → "Settings"
   - Scroll to "Instance Type"
   - Change from "Free" to "Starter"
   - Click "Save Changes"

2. **Benefits:**
   - ✅ No sleeping - instant response
   - ✅ More CPU and RAM
   - ✅ Better performance
   - ✅ More concurrent connections

3. **Also Upgrade (Optional):**
   - Database to Starter ($7/mo) - More storage
   - Worker to Starter ($7/mo) - More reliable scheduling

### Production Checklist

Before going fully live:

- [ ] Upgraded web service to Starter plan
- [ ] Set `TESTING_MODE=false`
- [ ] Custom domain configured (optional)
- [ ] SSL certificate active (automatic with Render)
- [ ] Uptime monitoring enabled
- [ ] Error monitoring (Sentry) configured
- [ ] Database backups enabled (Render handles this)
- [ ] All team members can access the site
- [ ] WhatsApp/Email notifications tested
- [ ] Admin access verified

---

## 🔧 Troubleshooting

### App Won't Start

**Check logs:**
```
Render Dashboard → Your Service → Logs
```

**Common issues:**
- Missing environment variables
- Database connection issues
- Python dependency conflicts

**Solution:**
1. Verify all required environment variables are set
2. Check `DATABASE_URL` is set correctly
3. Manually redeploy: "Manual Deploy" → "Deploy latest commit"

### Database Connection Errors

**Error:** `connection to server failed`

**Solution:**
1. Check `DATABASE_URL` environment variable is set
2. Verify database service is running
3. Check database and web service are in the same region

### Web Service Sleeps (Free Tier)

**Expected behavior on free tier.**

**Solutions:**
- Upgrade to Starter plan ($7/mo)
- Use external ping service to keep alive (not recommended)
- Accept 30-second wake-up time for testing

### WhatsApp Messages Not Sending

**Check:**
1. `WHATSAPP_API_KEY` and `WHATSAPP_PHONE_ID` are set correctly
2. WhatsApp webhook is pointed to your Render URL
3. Check logs for error messages
4. Verify `TESTING_MODE` setting

### Migrations Fail

**If migrate_to_postgres.py fails:**

1. Check your local database exists: `instance/league.db`
2. Verify `DATABASE_URL` in .env is correct
3. Run init_db.py first: `python init_db.py`
4. Try migration again

### 500 Internal Server Error

**Check logs for specific error:**
```
Render Dashboard → Service → Logs
```

**Common causes:**
- Database not initialized - Run `python init_db.py`
- Missing SECRET_KEY - Add to environment variables
- Code error - Check stack trace in logs

---

## 📊 Cost Summary

### Testing Phase (Free - $0/month)
- ✅ Web Service: Free
- ✅ Worker Service: Free
- ✅ PostgreSQL Database: Free (1GB)
- ⚠️ Limitations: Services sleep after 15 min, 750 hrs/mo

### Production Phase (Recommended)
- 💰 Web Service: Starter - $7/month
- 💰 Worker Service: Starter - $7/month (optional)
- 💰 Database: Starter - $7/month (if you need >1GB)
- **Total: $7-21/month depending on needs**

### Enterprise Scale (If You Grow Big)
- 💰 Standard plans: $25+/month
- Only needed for 1000+ active users

---

## 🎯 Quick Reference Commands

### View Logs
```bash
# In Render Shell
tail -f /var/log/app.log
```

### Restart Service
```bash
# Render Dashboard → Service → Manual Deploy → "Clear build cache & deploy"
```

### Initialize/Reset Database
```bash
# In Render Shell
python init_db.py
```

### Check Database Status
```bash
# In Render Shell
python -c "from app import app, db; print(db.engine.table_names())"
```

---

## 🎉 Success!

Your Padel League Hub is now live! 🏆

**Your live URLs:**
- Main App: `https://your-app-name.onrender.com`
- Admin Panel: `https://your-app-name.onrender.com/admin`

**Next Steps:**
1. Share the URL with your padel buddies
2. Start testing with real users
3. Monitor logs for any issues
4. Upgrade to Starter plan when ready for production

**Need Help?**
- Check logs in Render Dashboard
- Review this guide
- Check Render documentation: [render.com/docs](https://render.com/docs)

---

**Happy Padeling! 🎾**

