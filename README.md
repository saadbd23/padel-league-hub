# 🎾 BD Padel League

A comprehensive web-based platform for managing competitive padel tournaments using the Swiss format. Built with Flask, this system provides everything needed to run a professional padel league from registration to playoffs.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Flask](https://img.shields.io/badge/flask-3.0+-green.svg)

---

## ✨ Features

### 🏆 Tournament Management
- **Swiss Format Pairing**: Automatic opponent matching based on current standings
- **Round-by-Round Play**: Weekly rounds with Monday-Sunday scheduling
- **Flexible Scheduling**: Teams coordinate their own match times
- **Real-Time Leaderboards**: Team and individual player rankings
- **Comprehensive Statistics**: Wins, losses, sets, games, streaks, and more

### 👥 Registration System
- **Team Registration**: Register as a complete team (2 players)
- **Free Agent System**: Solo players matched with similar skill levels
- **Player Confirmation**: Two-factor confirmation for team members
- **Skill-Based Pairing**: Fair matching based on self-reported skill levels

### 📊 Match Features
- **One-Click Booking**: Propose and confirm match schedules easily
- **Score Submission**: Simple score entry from winning team's perspective
- **Score Verification**: Both teams must confirm scores
- **Dispute Resolution**: Built-in system for score disagreements
- **Match History**: Complete record of all matches

### 📅 Advanced Scheduling
- **Smart Reschedule System**: 
  - 2 reschedules per team
  - Wednesday request cutoff
  - Monday-Wednesday makeup match window
  - Automatic walkover enforcement
- **Substitute Players**: 
  - 2 substitutes per team (league stage)
  - Email notifications to all parties
  - Admin approval workflow

### 🔐 Security & Access
- **Password-Protected Admin Panel**: Secure administrative access
- **Unique Team Tokens**: Private access to team match pages
- **Session Management**: Persistent admin login
- **No Cross-Team Access**: Teams can only view their own matches

### 📧 Communication
- **Email Notifications**: Automatic emails for key events
- **WhatsApp Integration**: Optional SMS/WhatsApp notifications
- **Testing Mode**: Redirect notifications for testing

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Installation

1. **Clone the repository**
```bash
git clone <your-repo-url>
cd padel-league-hub
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Create environment file**
```bash
# Copy the template
cp env.template .env

# Edit .env and set your values
ADMIN_PASSWORD=YourSecurePassword
TESTING_MODE=false
```

4. **Initialize the database**
```bash
python
>>> from app import app, db
>>> with app.app_context():
>>>     db.create_all()
>>> exit()
```

5. **Run the application**
```bash
python app.py
```

6. **Access the site**
```
http://localhost:5000
```

---

## 🚀 Production Deployment

### Deploy to Production (Render.com)

Ready to deploy your league live? We've made it easy!

**📘 Quick Start (15 minutes):**
- Follow **[QUICK_START_DEPLOYMENT.md](QUICK_START_DEPLOYMENT.md)** for fastest deployment
- Free tier available for testing
- One-click deployment with `render.yaml`

**📚 Complete Guide:**
- See **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** for detailed instructions
- Includes troubleshooting and production upgrade path
- PostgreSQL setup and migration tools included

**✅ Before Going Live:**
- Complete **[PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md)**
- Review **[DEPLOYMENT_SUMMARY.md](DEPLOYMENT_SUMMARY.md)** for overview

**💰 Cost:**
- **Testing:** Free (with limitations)
- **Production:** $7-21/month (recommended)

**Deployment includes:**
- ✅ Web application
- ✅ Background worker for scheduled tasks
- ✅ PostgreSQL database
- ✅ SSL certificate (HTTPS)
- ✅ Automatic deployments from GitHub

---

## 📖 Usage

### For League Administrators

**Initial Setup:**
1. Navigate to `/admin/login`
2. Login with your admin password
3. Accept team and free agent registrations
4. Pair free agents based on skill levels
5. Confirm all teams

**Weekly Routine (Every Monday 9:00 AM):**
1. Login to admin panel
2. Click "Manage Reschedules" → "Check Deadlines"
3. Review and approve/deny pending requests
4. Return to admin panel
5. Enter round number and click "Generate Round"
6. Monitor matches throughout the week

**Mid-Week Tasks:**
- Approve/deny reschedule requests
- Approve/deny substitute requests
- Resolve score disputes
- Answer team questions

### For Players

**Team Registration:**
1. Go to "Register Your Team"
2. Fill in team name and both players' details
3. Player 2 confirms via SMS/WhatsApp link
4. Wait for admin confirmation
5. Receive unique team access link

**Free Agent Registration:**
1. Go to "Free Agent Registration"
2. Fill in your details and skill level
3. Wait for admin to pair you with another player
4. Confirm new team formation

**Match Management:**
1. Access your team page via unique link
2. Propose match booking or confirm opponent's proposal
3. Play your match
4. Submit score after match
5. Confirm opponent's score

---

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Required
ADMIN_PASSWORD=your_secure_admin_password

# Optional - Testing Mode
TESTING_MODE=false  # Set to 'true' to redirect all notifications to test contacts

# Optional - WhatsApp Integration
WHATSAPP_API_KEY=your_whatsapp_api_key
WHATSAPP_PHONE_ID=your_whatsapp_phone_id

# Optional - Email Integration
EMAIL_SENDER=your_email@example.com
EMAIL_PASSWORD=your_email_password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
VERIFY_TOKEN=your_verify_token_here
ADMIN_EMAIL=admin@yourleague.com  # Email to receive registration notifications
```

### Database

The system uses SQLite by default. The database file is created at `instance/league.db`.

**Database Models:**
- `Team`: Team information and statistics
- `Player`: Individual player records
- `Match`: Match details and scores
- `FreeAgent`: Solo players awaiting pairing
- `Reschedule`: Reschedule requests and status
- `Substitute`: Substitute player requests

---

## 📋 System Architecture

### Swiss Format Tournament
- Teams paired based on similar records each round
- No team plays the same opponent twice (league stage)
- Byes awarded if odd number of teams
- Top teams advance to playoffs

### Reschedule System
```
Round Week (Mon-Sun):
├─ Monday 9AM: Round generated
├─ Mon-Wed: Can request reschedules
├─ Sunday 23:59: Regular match deadline
└─ If rescheduled → Next week Mon-Wed with Wed 23:59 deadline
```

### Deadline Enforcement
- **Regular Matches**: Sunday 23:59 (full week)
- **Makeup Matches**: Wednesday 23:59 (following week)
- **Automatic Walkovers**: 6-0, 6-0 for deadline violations
- **Admin Override**: Available for genuine emergencies

---

## 🎯 Key Workflows

### Score Submission & Verification
```
1. Winner submits score from their perspective
   ↓
2. Opponent sees: "Winner: Team X, Score: 6-4, 6-3"
   ↓
3. Opponent clicks "Confirm" or "Dispute"
   ↓
4. If confirmed: Stats auto-update
   If disputed: Admin resolves
```

### Reschedule Request
```
1. Team requests (Mon-Wed only)
   ↓
2. Admin reviews and approves/rejects
   ↓
3. If approved: Match rescheduled to next week Mon-Wed
   ↓
4. Team plays 2 matches that week (makeup + regular)
   ↓
5. Wednesday 23:59: Must complete or walkover awarded
```

### Substitute Request
```
1. Team submits (name, phone, email)
   ↓
2. Emails sent to Player 1, Player 2, Substitute
   ↓
3. Admin approves or denies
   ↓
4. Approval/denial emails sent to all 3 parties
```

---

## 📱 Screenshots

<!-- Add screenshots here when available -->

### Home Page
*Coming soon*

### Admin Dashboard
*Coming soon*

### Team Match Page
*Coming soon*

### Leaderboard
*Coming soon*

---

## 🛠️ Tech Stack

- **Backend**: Python 3.8+, Flask 3.0+
- **Database**: SQLite (SQLAlchemy ORM)
- **Frontend**: HTML5, TailwindCSS (CDN), Vanilla JavaScript
- **Authentication**: Flask Sessions
- **Notifications**: Email (SMTP), WhatsApp (optional API integration)

---

## 📚 Documentation

### System Documentation
Complete system documentation is available in [`SYSTEM_GUIDE.md`](SYSTEM_GUIDE.md), including:
- Detailed setup instructions
- Admin workflows
- Feature explanations
- Troubleshooting guide
- Best practices

### Deployment Documentation
Production deployment guides:
- **[QUICK_START_DEPLOYMENT.md](QUICK_START_DEPLOYMENT.md)** - Deploy in 15 minutes
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Complete deployment instructions
- **[PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md)** - Pre-launch verification
- **[DEPLOYMENT_SUMMARY.md](DEPLOYMENT_SUMMARY.md)** - Overview and decision guide
- **[env.production.example](env.production.example)** - Environment variables template

---

## 🔐 Security

- **Admin Protection**: Password-protected admin panel with session management
- **Team Privacy**: Unique secure tokens (48+ characters) for team access
- **No Cross-Access**: Teams cannot access other teams' data
- **Environment Security**: Credentials stored in `.env` (not committed to repo)
- **Score Verification**: Both teams must confirm scores

---

## 🌟 Highlights

### What Makes This System Special

✅ **Automatic Walkovers**: No manual tracking of missed deadlines  
✅ **No Round Delays**: Tournament always moves forward on schedule  
✅ **Smart Reschedules**: Limited to maintain tournament integrity  
✅ **One-Click Actions**: Booking and score confirmation simplified  
✅ **Real-Time Updates**: Leaderboards and stats update automatically  
✅ **Fair Pairing**: Swiss format ensures balanced competition  
✅ **Email Notifications**: Keep all parties informed  
✅ **Mobile Friendly**: Responsive design works on all devices  

---

## 🎯 Roadmap

### Future Enhancements
- [ ] Mobile app (iOS/Android)
- [ ] Live match scoring
- [ ] Photo upload for match results
- [ ] Advanced analytics dashboard
- [ ] Payment integration for league fees
- [ ] Playoff bracket visualization
- [ ] Player messaging system
- [ ] Court booking integration
- [ ] Tournament photo gallery
- [ ] Season archives

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

### Development Setup
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Test thoroughly
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 👏 Acknowledgments

- Built for the padel community in Bangladesh
- Inspired by the need for fair, automated tournament management
- Thanks to all beta testers and early adopters

---

## 📞 Contact & Support

**For League Administrators:**
- Check the `SYSTEM_GUIDE.md` for detailed instructions
- Review the in-app Rules page at `/rules`

**For Development Issues:**
- Open an issue on GitHub
- Provide error messages and reproduction steps

---

## 🏆 About the League

BD Padel League is designed to bring competitive padel to Bangladesh with:
- Fair Swiss format pairing
- Professional match management
- Transparent scoring and rankings
- Community building through competition

**Join us and experience the future of padel tournament management!** 🎾

---

*Developed with ❤️ for the padel community*  
*Version 2.0 - Production Ready*  
*Last Updated: October 2025*