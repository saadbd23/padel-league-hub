# 📖 BD Padel League - Complete System Guide

Welcome to the BD Padel League management system! This guide covers everything you need to know to run your padel league successfully.

---

## 📑 Table of Contents
1. [System Overview](#system-overview)
2. [Getting Started](#getting-started)
3. [Registration System](#registration-system)
4. [Admin Panel](#admin-panel)
5. [Match Management](#match-management)
6. [Reschedule System](#reschedule-system)
7. [Substitute System](#substitute-system)
8. [Scoring & Statistics](#scoring--statistics)
9. [Weekly Admin Workflow](#weekly-admin-workflow)
10. [Troubleshooting](#troubleshooting)

---

## 🎯 System Overview

### What is BD Padel League?
A complete web-based platform for managing padel tournaments using the Swiss format. The system handles:
- Team and free agent registration
- Automatic round pairing
- Match scheduling and booking
- Score submission and verification
- Leaderboards and statistics
- Reschedules and substitutes
- Email notifications

### Key Features
- **Swiss Format**: Teams paired based on similar records
- **Monday-Sunday Rounds**: Full 7-day weeks for each round
- **Secure Access**: Teams access matches via unique tokens
- **Automatic Stats**: Real-time leaderboard and statistics updates
- **Smart Scheduling**: Reschedule system with automatic walkovers
- **Email Notifications**: Automatic emails for key events
- **Admin Dashboard**: Complete control over league operations

---

## 🚀 Getting Started

### 1. Initial Setup

#### Create `.env` File
Create a `.env` file in the project root:

```bash
# Admin Password (REQUIRED)
ADMIN_PASSWORD=YourSecurePasswordHere

# Testing Mode (set to false for production)
TESTING_MODE=false

# WhatsApp Configuration (optional)
WHATSAPP_API_KEY=your_whatsapp_api_key
WHATSAPP_PHONE_ID=your_phone_id

# Email Configuration (optional)
EMAIL_SENDER=your_email@example.com
EMAIL_PASSWORD=your_email_password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
```

**Critical Settings:**
- `ADMIN_PASSWORD`: Choose a strong password for admin access
- `TESTING_MODE=false`: Sends notifications to real contacts (set to `true` for testing)

#### Install Dependencies
```bash
pip install -r requirements.txt
```

#### Run the Application
```bash
python app.py
```

Access at: `http://localhost:5000`

---

### 2. Admin Login

1. Navigate to the site
2. Click **"Admin"** in the navigation menu
3. Enter your admin password (from `.env` file)
4. Click **"Login to Admin Panel"**

**Default Password** (if not set): `admin123`  
**Security**: Change this immediately in your `.env` file!

---

## 👥 Registration System

### Team Registration

**Process:**
1. Players go to **"Register Your Team"**
2. Fill in team details:
   - Team name
   - Player 1: Name, phone, email
   - Player 2: Name, phone, email
3. Click **"Register Team"**
4. **Player 2 receives SMS/WhatsApp confirmation link**
5. Player 2 clicks link to confirm participation
6. **Admin reviews and confirms team** in admin panel
7. Team is now active in the league

**Admin Tasks:**
- Monitor new team registrations
- Verify team details
- Confirm teams to activate them
- Delete spam/invalid registrations

---

### Free Agent Registration

**For Solo Players Without Partners:**

**Process:**
1. Players go to **"Free Agent Registration"**
2. Fill in details:
   - Name
   - Phone
   - Email
   - **Skill Level** (Beginner, Intermediate, Advanced)
3. Click **"Register as Free Agent"**
4. Wait for admin to pair them with another free agent

**Admin Pairing Process:**
1. Go to admin panel → Free Agents section
2. Select 2 free agents with similar skill levels
3. Enter team name
4. Click **"Pair Agents"**
5. System creates team automatically
6. Both players notified
7. Confirm the new team

**Skill Levels:**
- **Beginner**: New to padel, <6 months experience
- **Intermediate**: 6 months - 2 years, comfortable with basics
- **Advanced**: 2+ years, competitive play, strong skills

**Important**: Encourage players to be honest about skill levels for fair pairing!

---

## 🎮 Admin Panel

### Dashboard Overview

**Sections:**
1. **Generate Round Pairings** - Create new rounds
2. **Reschedule Management** - View/approve reschedules
3. **Registered Teams** - Team list with stats and actions
4. **Scheduled Matches** - All matches with scores and status
5. **Free Agents** - Solo players awaiting pairing
6. **Pending Requests** - Reschedules and substitutes
7. **Request History** - Approved/denied requests

### Key Admin Actions

**Team Management:**
- ✅ Confirm team registration
- ❌ Delete team (if no matches played)
- 📊 View team statistics
- 🔗 Access team match page

**Match Management:**
- ✏️ Update match scores manually
- 🎯 Override match results
- 📅 Generate new rounds
- ⏰ Check deadline violations

**Request Management:**
- ✅ Approve reschedule requests
- ❌ Reject reschedule requests
- ✅ Approve substitute requests
- ❌ Deny substitute requests

---

## 🎾 Match Management

### Team Match Page

Each team has a secure unique URL: `/my-matches/<token>`

**Features:**
- View upcoming and past matches
- Propose match booking (date/time)
- Confirm opponent's booking proposal
- Submit match scores
- Confirm opponent's scores
- Request reschedules
- Request substitutes

### Booking Process

**Team A (Proposer):**
1. Selects date and time
2. Clicks "Propose This Schedule"
3. Opponent notified

**Team B (Confirmer):**
1. Sees proposed date/time
2. Options:
   - Click **"Confirm This Schedule"** (one-click)
   - Click **"Suggest Different Time"** (propose alternative)

**Result**: Once both agree, match is scheduled

---

### Score Submission

**Winner Submits First:**
1. After match, winning team goes to their match page
2. Enters score from their perspective
   - Set 1: e.g., `6-4`
   - Set 2: e.g., `6-3`
   - Set 3: (if played) e.g., `10-8`
3. Clicks **"Submit Score"**

**Opponent Confirms:**
1. Opponent sees: "Winner: Team Name, Score: 6-4, 6-3"
2. Options:
   - Click **"Confirm This Score"** (one-click)
   - Click **"Dispute This Score"** (escalates to admin)

**Result**:
- Once confirmed: Match verified
- Stats automatically updated
- Leaderboards refresh
- Match marked complete

---

## 📅 Reschedule System

### Monday Morning Workflow (Your Vision)

**Weekly Schedule:**
```
Monday 9:00 AM → Generate round (Round N starts)
Monday-Sunday → Teams play matches
Sunday 23:59 → Round N deadline
Monday 9:00 AM → Generate next round (Round N+1)
```

### Reschedule Policy

**Allowance**: 2 reschedules per team for entire league stage

**Request Deadline**: **Wednesday 23:59** of current round
- Can only request Mon-Wed
- After Wednesday: Too late for that round

**Reschedule Window**: **Monday-Wednesday** of following week only
- Cannot reschedule to Thursday-Sunday
- Date picker blocks invalid dates

**Makeup Match Deadline**: **Wednesday 23:59** of following week
- Must complete by this deadline
- If missed: **Automatic walkover** to opponent

### Reschedule Flow Example

```
Round 1 (Oct 20-26):
├─ Monday Oct 20: Round 1 starts
├─ Tuesday Oct 21: Team A requests reschedule
├─ Wednesday Oct 22: Last day to request reschedules
├─ Admin approves reschedule
└─ Sunday Oct 26: Round 1 regular deadline

Round 2 (Oct 27-Nov 2):
├─ Monday Oct 27: Round 2 generated
├─ Monday-Wednesday: Team A plays MAKEUP match (from Round 1)
├─ Wednesday Oct 29 23:59: MAKEUP DEADLINE (if missed → walkover)
├─ Round 2: Team A also plays regular Round 2 match
└─ Sunday Nov 2: Round 2 regular deadline
```

### Admin Reschedule Management

**Dashboard**: `/admin/reschedules`

**Features:**
- View all pending reschedules
- See deadlines for each
- **"Check Deadlines"** button (applies automatic walkovers)
- Approve/reject with one click
- Track reschedule usage per team

---

## 👥 Substitute System

### Policy
- **Allowance**: 2 substitutes per team (league stage only)
- **No substitutes in playoffs**
- **Requires**: Name, phone, and **email**
- **Admin approval required**

### Request Process

**Team Requests:**
1. Go to match page
2. Fill in substitute details:
   - Name
   - Phone
   - **Email** (required)
3. Click **"Submit Substitute Request"**

**Emails Sent Immediately:**
- ✉️ Player 1: "Your request submitted"
- ✉️ Player 2: "Teammate submitted request"
- ✉️ Substitute: "You've been requested"

**Admin Approves:**
- ✅ Click "Approve" in admin panel
- ✉️ All 3 parties receive approval emails

**Admin Denies:**
- ❌ Click "Deny" in admin panel
- ✉️ All 3 parties receive denial emails

---

## 📊 Scoring & Statistics

### Ranking System

**Order of Ranking Criteria:**
1. **Points** (Win=3, Draw=1, Loss=0)
2. **Head-to-Head** result
3. **Set Difference** (sets won - sets lost)
4. **Game Difference** (games won - games lost)
5. **Sets Won** (total)
6. **Games Won** (total)

### Leaderboards

**Team Leaderboard:**
- Overall team rankings
- Record (W-L-D)
- Points
- Sets and games
- Current streak

**Player Leaderboard:**
- Individual player statistics
- Matches played
- Wins/losses
- Win percentage
- Participation tracking

**Auto-Update**: Stats update immediately after score confirmation

---

## 🗓️ Weekly Admin Workflow

### Every Monday at 9:00 AM

**Your Routine (5-10 minutes):**

1. **Login to Admin Panel**
   - Navigate to `/admin/login`
   - Enter password

2. **Check Deadline Violations**
   - Go to "Reschedule Dashboard"
   - Click **"Check Deadlines"**
   - System applies automatic walkovers for:
     - Regular matches past Sunday 23:59
     - Makeup matches past Wednesday 23:59
   - Review any walkovers applied

3. **Review Pending Requests**
   - Approve/reject reschedule requests
   - Approve/reject substitute requests
   - Check team confirmations

4. **Generate Next Round**
   - Return to main admin panel
   - Enter round number (1, 2, 3, etc.)
   - Click **"Generate Round"**
   - System shows warnings if teams have pending makeup matches
   - Proceed anyway - those teams play 2 matches this week

5. **Done!**
   - Teams receive notifications (if configured)
   - New round is live
   - Teams have until next Sunday 23:59

**Mid-Week Tasks (Optional):**
- Monitor reschedule requests
- Approve/deny as they come in
- Answer team questions
- Resolve any disputes

---

## 🔧 Troubleshooting

### Common Issues

#### "Can't access admin panel"
- **Solution**: Login at `/admin/login` with your password
- Check `.env` file has `ADMIN_PASSWORD` set

#### "Teams not receiving emails"
- **Solution**: 
  - Check `.env` has email credentials
  - Verify `TESTING_MODE=false` for production
  - Test email configuration

#### "Date picker showing wrong dates for reschedules"
- **Should show**: Monday-Wednesday of next week only
- **Refresh page** or clear browser cache

#### "Leaderboard not updating after match"
- **Solution**: Both teams must confirm score
- Once both confirm, stats update automatically
- Check match status is "verified"

#### "Forgot admin password"
- **Solution**: Check your `.env` file
- Change password in `.env`
- Restart Flask app
- Login with new password

### Database Issues

If you need to reset everything:
```bash
python reset_for_production.py
```

**Warning**: This deletes ALL data!

---

## 📋 Quick Reference

### Important URLs
- **Home**: `/`
- **Team Registration**: `/register-team`
- **Free Agent Registration**: `/register-freeagent`
- **Leaderboard**: `/leaderboard`
- **Rules**: `/rules`
- **Admin Login**: `/admin/login`
- **Admin Panel**: `/admin` (requires login)
- **Team Match Page**: `/my-matches/<token>` (unique per team)

### Key Deadlines
- **Regular Matches**: Sunday 23:59 of the round week
- **Makeup Matches**: Wednesday 23:59 of the following week
- **Reschedule Requests**: Wednesday 23:59 of current round
- **Round Generation**: Every Monday 9:00 AM

### Team Limits
- **Reschedules**: 2 per team (league stage)
- **Substitutes**: 2 per team (league stage)
- **No reschedules/subs in playoffs**

### Automatic Walkovers
- Regular match not completed by Sunday → Walkover
- Makeup match not completed by Wednesday → Walkover
- Default score: 6-0, 6-0

---

## 🎯 Best Practices

### For Admins

**Do's:**
✅ Generate rounds every Monday morning  
✅ Check deadlines regularly  
✅ Respond to requests within 24 hours  
✅ Pair free agents by similar skill levels  
✅ Keep TESTING_MODE=false for production  
✅ Monitor the reschedule dashboard  

**Don'ts:**
❌ Don't generate rounds mid-week  
❌ Don't approve reschedules without checking limits  
❌ Don't override walkovers without genuine emergency  
❌ Don't forget to check deadlines on Monday  

---

### For Teams

**Do's:**
✅ Respond to booking requests within 24 hours  
✅ Submit scores immediately after matches  
✅ Request reschedules early (Mon-Wed only)  
✅ Complete makeup matches by Wednesday  
✅ Be honest when reporting scores  
✅ Communicate with opponents via WhatsApp  

**Don'ts:**
❌ Don't wait until Thursday to request reschedules  
❌ Don't skip matches without notification  
❌ Don't submit incorrect scores  
❌ Don't abuse the reschedule system  

---

## 📧 Email Notifications

### Automatic Emails Sent For:

**Team Registration:**
- Player 2 confirmation request
- Admin team confirmation

**Substitute Requests:**
- Request submitted → 3 parties (Player 1, Player 2, Substitute)
- Request approved → 3 parties
- Request denied → 3 parties

**Future Enhancements:**
- Reschedule confirmations
- Match reminders
- Round notifications
- Score dispute alerts

---

## 🔐 Security Features

### Admin Protection
- Password-protected admin panel
- Session-based authentication
- All admin routes require login
- Logout functionality

### Team Privacy
- Unique secure tokens per team
- Only team members can access their match page
- No cross-team access
- Tokens are unguessable (48+ characters)

### Data Integrity
- Score verification (both teams confirm)
- Automatic stats calculation
- Walkover enforcement
- Admin override for emergencies

---

## 📚 Additional Resources

### In-App Resources
- **Rules Page**: Complete rulebook available at `/rules`
- **Player Profiles**: Individual stats and match history
- **Team Pages**: Team stats and match history
- **Stats Tab**: Detailed statistical breakdowns

### Admin Resources
- **Reschedule Dashboard**: `/admin/reschedules`
- **Team List**: View all teams with stats
- **Match List**: All matches with management options
- **Free Agents**: Solo players awaiting pairing

---

## 🎾 Launch Checklist

### Pre-Launch
- [ ] `.env` file created with production settings
- [ ] `TESTING_MODE=false`
- [ ] Strong `ADMIN_PASSWORD` set
- [ ] Admin login tested
- [ ] Email credentials configured (optional)
- [ ] WhatsApp credentials configured (optional)

### Week 0 (Registration)
- [ ] Accept team registrations
- [ ] Accept free agent registrations
- [ ] Pair free agents by skill level
- [ ] Confirm all teams
- [ ] Prepare for Round 1

### Week 1 (League Starts)
- [ ] Monday 9 AM: Generate Round 1
- [ ] Monitor match scheduling
- [ ] Process reschedule/substitute requests
- [ ] Sunday: Check all matches completed

### Ongoing (Every Week)
- [ ] Monday 9 AM: Check deadlines → Generate next round
- [ ] Process requests as they come in
- [ ] Monitor for disputes
- [ ] Maintain leaderboard accuracy

---

## 🚀 System Status

**Current Version**: 2.0 (Production Ready)  
**Database Status**: Clean and ready for real players  
**Last Reset**: October 21, 2025  

### Production Ready Features
✅ Team and free agent registration  
✅ Swiss format pairing  
✅ Match booking and scheduling  
✅ Score submission and verification  
✅ Reschedule system (Monday workflow)  
✅ Substitute system (with emails)  
✅ Admin password protection  
✅ Leaderboards and statistics  
✅ Automatic walkovers  
✅ Email notifications  

**Your league is ready to launch!** 🏆

---

## 📞 Support & Contact

**For Issues:**
1. Check this guide
2. Review the Rules page (`/rules`)
3. Check `.env` configuration
4. Verify admin password

**For Development Issues:**
- Contact the development team
- Provide error messages and screenshots
- Include steps to reproduce the issue

---

*Last Updated: October 21, 2025*  
*BD Padel League System v2.0*  
*Developed for competitive padel tournament management*

**Good luck with your padel league!** 🎾🏆✨
