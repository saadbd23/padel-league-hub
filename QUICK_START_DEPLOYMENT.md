# ⚡ Quick Start: Deploy to Production in 15 Minutes

The fastest path from local development to live production site.

---

## 🚀 5-Step Deployment

### Step 1: Push to GitHub (2 min)

```bash
cd padel-league-hub

# If not already initialized
git init
git add .
git commit -m "Ready for deployment"

# Create repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/padel-league-hub.git
git branch -M main
git push -u origin main
```

### Step 2: Sign Up for Render (2 min)

1. Go to [render.com](https://render.com)
2. Click "Get Started" → Sign up with GitHub
3. Authorize Render to access your repositories

### Step 3: Deploy with One Click (5 min)

1. **In Render Dashboard:**
   - Click "New +" → "Blueprint"
   - Select `padel-league-hub` repository
   - Click "Apply"

2. **Render automatically creates:**
   - ✅ Web service
   - ✅ Worker service  
   - ✅ PostgreSQL database
   - ✅ Environment variables

3. **Wait for deployment** (Render will build and deploy everything)

### Step 4: Set Required Environment Variables (3 min)

In Render Dashboard → Web Service → Environment:

**Generate SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Add these variables:**
```bash
SECRET_KEY=<paste_your_generated_key>
ADMIN_PASSWORD=<create_strong_password>
VERIFY_TOKEN=padel_league_2025
APP_BASE_URL=https://your-app-name.onrender.com
```

Click "Save Changes" (this triggers a redeploy).

### Step 5: Initialize Database (3 min)

Once deployed:

1. **Go to:** Render Dashboard → Web Service → "Shell"
2. **Run:**
   ```bash
   python init_db.py
   ```
3. **See:** "✅ Database initialized successfully!"

---

## 🎉 You're Live!

**Your site is now live at:** `https://your-app-name.onrender.com`

### Test It:

1. Visit your URL
2. Go to `/admin` and login with your `ADMIN_PASSWORD`
3. Create a test team
4. Verify everything works!

---

## 📊 What You Have Now

### Free Tier (Testing) - $0/month

✅ Fully functional website  
✅ PostgreSQL database  
✅ Scheduled reminders working  
✅ SSL certificate (HTTPS)  
⚠️ App sleeps after 15 min (wakes in 30 sec)  

### Perfect for:
- Testing with friends
- Small leagues (up to ~50 users)
- Validating functionality
- Getting user feedback

---

## 🔄 Optional: Add WhatsApp/Email

If you want notifications, add these environment variables:

**WhatsApp:**
```bash
WHATSAPP_API_KEY=your_api_key
WHATSAPP_PHONE_ID=your_phone_id
```

**Email:**
```bash
EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
```

**Test first:**
```bash
TESTING_MODE=true  # Routes all notifications to test contacts
```

---

## 💰 When Ready for Production

### Upgrade to Starter ($7/month)

**Benefits:**
- No sleeping - instant response ⚡
- Better performance 🚀  
- More reliable 💪

**How to upgrade:**
1. Render Dashboard → Web Service → Settings
2. Change "Instance Type" from "Free" to "Starter"
3. Click "Save"

---

## 🆘 Quick Troubleshooting

### App won't start?
**→ Check logs:** Render Dashboard → Service → "Logs"

### Can't login to admin?
**→ Verify ADMIN_PASSWORD** is set in Environment Variables

### Database errors?
**→ Run init_db.py** in Render Shell

### App is slow/doesn't respond?
**→ Expected on free tier** - app sleeps after 15 min. Upgrade to Starter plan.

---

## 📚 Full Documentation

For detailed guides, see:
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Complete deployment instructions
- **[PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md)** - Pre-launch checklist
- **[env.production.example](env.production.example)** - All environment variables

---

## 🎯 Next Steps

1. **Test thoroughly** with your padel buddies
2. **Monitor logs** for any issues
3. **Gather feedback** from users
4. **Upgrade to Starter** when you're ready for production
5. **Enable monitoring** (Sentry, UptimeRobot)

---

## ✨ Pro Tips

💡 **Start with TESTING_MODE=true** to test notifications safely  
💡 **Backup your data** before major changes  
💡 **Monitor logs** regularly in the first week  
💡 **Only upgrade when needed** - free tier is fine for testing  
💡 **Use custom domain** for professional appearance  

---

**That's it! You're deployed! 🏆🎾**

Questions? Check the full [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

