# BD Padel League - Review Context Document

**Last Updated:** 2026-01-31
**Status:** Initial Review Complete

---

## Project Overview

**Name:** BD Padel League Hub
**Tech Stack:** Python 3.11 + Flask 3.0 + SQLAlchemy + TailwindCSS
**Database:** PostgreSQL (production) / SQLite (development)
**Deployment:** Render.com / Heroku compatible

---

## Codebase Structure

```
/home/runner/workspace/
├── app.py                    # Main Flask app (9,464 lines, 92 routes)
├── models.py                 # SQLAlchemy models (421 lines)
├── utils.py                  # Utility functions (1,403 lines)
├── whatsapp_integration.py   # WhatsApp API client
├── scheduled_tasks.py        # Background jobs
├── requirements.txt          # Dependencies
├── templates/                # 41 HTML templates
│   ├── base.html            # Base layout with navigation
│   ├── admin.html           # Main admin dashboard
│   ├── ladder/              # 7 ladder-specific templates
│   └── ...                  # 30+ other templates
├── static/                   # CSS, images, logos
└── migrate_*.py              # 11 database migration scripts
```

---

## Core Features Reviewed

### 1. Tournament Formats

| Format | Status | Registration |
|--------|--------|--------------|
| **Swiss League** | Active | Closed |
| **Ladder Challenge** | Active | Open (Men/Women/Mixed) |
| **Americano Tournament** | Active | Monthly events |

### 2. Ladder Challenge System
- **Divisions:** Men's, Women's, Mixed
- **Ranking:** Challenge-based with rank swapping
- **Penalties:**
  - No-show: -1 rank
  - Inactivity (<2 matches/month): -3 ranks
  - Declined challenge: -1 rank
- **Holiday Mode:** Grace period + weekly penalty system
- **Payment:** Required for team registration (auto-assigns rank on payment)

### 3. Swiss League System
- Swiss pairing algorithm (avoids rematches)
- Round-based with deadlines
- Playoff progression: QF → SF → 3rd Place → Finals
- 8 teams qualify for playoffs

### 4. Match Management
- Score submission workflow: Winner submits → Opponent confirms/disputes
- Booking confirmation system
- Reschedule requests (limited per team)
- Substitute player requests

### 5. User Types & Access
| User Type | Auth Method | Access |
|-----------|-------------|--------|
| Admin | Password (session) | Full dashboard |
| Team | 64-char token (URL) | Team dashboard |
| Free Agent | Token (URL) | Registration/pairing |

---

## Database Models

### Main Models:
1. **Team** - Swiss league teams with player info + stats
2. **Player** - Individual player statistics
3. **Match** - Swiss league matches
4. **FreeAgent** - Unpaired players for Swiss
5. **Reschedule** - Reschedule requests
6. **Substitute** - Substitute player requests
7. **LeagueSettings** - Swiss configuration

### Ladder Models:
1. **LadderTeam** - Ladder teams with ranks + holiday mode
2. **LadderFreeAgent** - Ladder free agents
3. **LadderChallenge** - Challenge requests
4. **LadderMatch** - Ladder match results with rank tracking
5. **LadderSettings** - Ladder configuration (penalties, timeframes)

### Americano Models:
1. **AmericanoTournament** - Tournament configuration
2. **AmericanoMatch** - Individual matches with points

---

## Key Routes (92 total)

### Public Routes:
- `/` - Homepage
- `/leaderboard` - Swiss standings
- `/ladder/men/`, `/ladder/women/`, `/ladder/mixed/` - Ladder rankings
- `/players`, `/player/<id>` - Player profiles
- `/rules` - League rules

### Team Routes (Token-protected):
- `/my-matches/<token>` - Team match dashboard
- `/submit-booking/<token>`, `/confirm-booking/<token>`
- `/submit-score/<token>`, `/confirm-score/<token>`
- `/ladder/my-team/<token>` - Ladder team dashboard

### Admin Routes (~52):
- `/admin/` - Main dashboard
- `/admin/settings`, `/admin/ladder/settings`
- `/admin/ladder/rankings/<type>`
- `/admin/ladder/challenges/<type>`
- `/admin/ladder/matches/<type>`
- `/admin/ladder/dispute/resolve/<id>`
- `/admin/ladder/americano/*` - Americano management

---

## Notification System

| Channel | Provider | Status |
|---------|----------|--------|
| Email | SMTP (Gmail) | Active |
| WhatsApp | Meta Graph API v17.0 | Active |

**Testing Mode:** Redirects all notifications to test number when enabled

**Notification Types:**
- Match reminders (24-48h before)
- Deadline warnings
- Walkover threats
- Score submission requests
- Challenge notifications
- Registration confirmations

---

## Background Tasks

**Scheduled Jobs:**
- `send_walkover_warnings()` - Daily deadline warnings
- `send_match_reminders()` - Match reminders
- Automatic walkover enforcement (6-0, 6-0 for missed deadlines)

**Execution:** APScheduler / Render worker process

---

## Recent Development (Last 10 Commits)

1. `ed94cfb` - Saved progress
2. `def086d` - Auto-assign ranks upon payment confirmation
3. `76addb7` - Saved progress
4. `b5d3451` - Pair free agents into new ladder teams
5. `21aba48` - Published app
6. `54e611c` - Align ladder rankings across pages
7. `cfed878` - Improve match display accuracy
8. `cd874d1` - Fix team ranking consistency
9. `83ba6ff` - Align team page rankings
10. `5145233` - Consistent ranking display

---

## Configuration

### Environment Variables:
- `ADMIN_PASSWORD` - Admin authentication
- `TESTING_MODE` - Enable test notifications
- `WHATSAPP_API_KEY`, `WHATSAPP_PHONE_ID` - WhatsApp config
- `EMAIL_SENDER`, `EMAIL_PASSWORD`, `SMTP_SERVER`, `SMTP_PORT`
- `DATABASE_URL` - PostgreSQL connection
- `SECRET_KEY` - Flask sessions
- `APP_BASE_URL` - Production URL

---

## Areas for Future Review

- [ ] Security audit (input validation, XSS, SQL injection)
- [ ] Performance optimization (database queries, caching)
- [ ] Error handling consistency
- [ ] Test coverage
- [ ] Mobile responsiveness
- [ ] Accessibility (WCAG compliance)
- [ ] Code documentation
- [ ] API documentation

---

## Notes & Observations

### Strengths:
- Comprehensive feature set for tournament management
- Well-structured database schema
- Multiple notification channels
- Flexible ladder system with penalties
- Admin dashboard covers all operations

### Areas to Watch:
- Large monolithic app.py (9,464 lines) - could benefit from blueprints
- Admin password stored as env var (consider hashing)
- Migration scripts indicate active schema evolution

---

## Session Log

| Date | Action | Notes |
|------|--------|-------|
| 2026-01-31 | Initial full review | Explored all major components |

