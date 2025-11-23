# Overview

BD Padel League is a comprehensive web-based platform for managing competitive padel tournaments. Built with Flask and SQLAlchemy, it manages two parallel tournament systems:

1. **League System** - Swiss format league with playoffs, reschedule/substitute management
2. **Ladder Tournament** - Challenge-based ranking system with separate Men's and Women's divisions (November 2025)

The system handles team/player registration, automated pairings, match scheduling, score submission, leaderboards, and provides secure team-specific access via unique tokens.

# User Preferences

Preferred communication style: Simple, everyday language.

# Recent Changes

**November 23, 2025** - Ladder Challenge UI Improvement: Show Locked Teams with Disabled Buttons
- **Improved Challenge Team Availability Display**: Changed from hiding locked teams to showing them with disabled buttons
  - Previous behavior: Teams in active challenges were completely hidden from the challenge list
  - New behavior: All eligible teams are displayed, but teams currently in challenges show disabled buttons with status messages
  - Desktop UI: Locked/holiday teams show with grayed-out card, disabled button, and "Team currently under challenge" or "Team in holiday mode" message
  - Mobile UI: Locked/holiday teams show with grayed-out card, disabled button, and status badge
  - UX benefit: Users can see which teams exist but understand why they can't be challenged
  - Backend: Modified `ladder_my_team()` to return team data with `is_locked` and `is_holiday` flags
  - Template: Updated conditional rendering for challenge buttons based on team status

**November 22, 2025** - Free Agents Remove & Duplicate Contact Detection
- **Remove Button for Each Free Agent**: Added red "Remove" button (🗑️) in Free Agents section (desktop table + mobile cards)
  - Desktop: Action column with inline remove button
  - Mobile: Full-width remove button below agent details
  - Confirmation dialog prevents accidental deletion
  - Backend route: `/admin/remove-ladder-freeagent/<agent_id>` (POST)
- **Duplicate Contact Detection**: Auto-highlights free agents whose email or phone matches existing Ladder teams
  - Desktop: Yellow background row with yellow left border + "⚠️ Duplicate Contact" badge
  - Mobile: Yellow border card (4px) with yellow "⚠️ Duplicate Contact" badge
  - Backend checks both player1 and player2 contact info across all ladder teams
  - Helps admins identify potential duplicates before pairing

**November 18, 2025** - Free Agents Admin Panel Integration
- **Admin Panel Three-Tab Structure**: League, Ladder, and Free Agents tabs
  - Free Agents tab consolidates all free agent and Americano tournament management
  - Registered Free Agents section: Table/card view with name, gender, skill level, email, phone, registration date
  - Statistics dashboard: Total free agents count with Men/Women breakdown
  - Americano Tournaments section: Tournament cards showing date, gender, location, status, participants, matches
  - Tournament action buttons: View Details, Enter Scores, Leaderboard, Create New Tournament
  - Mobile responsive with collapsible sections matching admin panel design
- Fixed Americano tournaments page routing errors (admin_dashboard → admin_panel)
- All free agents now visible in unified admin interface

**November 17, 2025** - Major UI/UX Redesign: Ladder-First Experience
- **Homepage Redesign**: Dual-card hero layout emphasizing Ladder as primary tournament system
  - Ladder Challenge card: Large, prominent with "Open for Registration" green badge and yellow border
  - Swiss League card: Secondary placement with "Season in Progress" badge
  - Clear visual hierarchy: Ladder (purple gradient) vs League (neutral gray)
  - Live stats dashboard: Ladder Men's/Women's teams, Free Agents, League teams
  - Two registration paths clearly displayed: Team registration + Free agent option
- **Navigation Overhaul**: Dropdown menu system for both desktop and mobile
  - Register dropdown: Team-Ladder, Team-League, Free Agent (with descriptions)
  - Ladder dropdown: Men's Rankings, Women's Rankings
  - League dropdown: Leaderboard, Stats, Rounds
  - Mobile: Organized sections with category headers
- **Leaderboard Page**: Tabbed interface with [Ladder Men] [Ladder Women] [League] tabs
  - Embedded ladder rankings via iframes
  - League tab shows traditional leaderboard
  - Smooth tab switching without page reloads
- **Statistics Page**: Dual-tab layout with [Ladder Stats] [League Stats]
  - Ladder Stats: Dashboard cards showing total teams, active challenges, monthly matches, top performers
  - Top performers table with win rates and ladder rankings
  - League Stats: Existing league statistics (streaks, points leaders, differentials)
- **Rules Page**: Accordion-style expandable sections
  - Ladder Rules (expanded by default): Complete ladder system documentation
  - League Rules (collapsed): Swiss format league rules
  - Americano Tournaments (collapsed): Monthly pairing event details
  - Smooth expand/collapse animations
- All pages fully mobile-responsive with proper touch targets and card layouts

**November 17, 2025** - Ladder Tournament System Added & League Free Agents Deprecated
- Created 7 new database models for ladder tournament functionality (including Americano)
- Deprecated league free agent system - all free agents now managed through Ladder
- Separate Men's and Women's ladder divisions
- Challenge system: teams can challenge up to 3 ranks above
- Holiday mode with 2-week grace period
- Activity monitoring: minimum 2 matches per month
- Complete Americano tournament system:
  - Monthly tournaments for pairing ladder free agents
  - Smart round-robin pairing algorithm with partner rotation
  - Individual scoring and leaderboards
  - Top 50% pairing eligibility
  - Admin tournament creation, match generation, score entry, and team pairing
- Team names must be unique across both league and ladder (no duplicates allowed)
- Contact preferences: Email and/or WhatsApp for all registrations
- Fixed admin page loading issue: broken URL link in deprecated free agents section
- See `ladder_implementation_plan.md` for complete feature specifications

# System Architecture

## Core Framework
- **Backend**: Flask 3.0 with Jinja2 templating
- **Database**: SQLAlchemy ORM with dual support:
  - PostgreSQL for production (primary)
  - SQLite fallback for local development
- **Session Management**: Flask sessions with secure secret key handling
- **WSGI Server**: Gunicorn for production deployment

## Database Schema
All models tracked in `models.py` within a single PostgreSQL database:

### League Models:
- **Team**: Team registration, player details, match statistics (wins/losses/draws), points, sets/games differentials, reschedule/substitute usage tracking, secure access tokens
- **Player**: Individual player statistics across all matches participated in (handles substitutions separately from team stats)
- **Match**: Round-based match records, scheduling, booking times, score storage, status tracking (scheduled/completed/bye/walkover/disputed)
- **FreeAgent**: Solo player registration with skill level for pairing
- **Reschedule**: Reschedule request tracking with deadlines and approval workflow
- **Substitute**: Substitute player management with admin approval
- **LeagueSettings**: Configuration for Swiss rounds, playoff teams, registration status

### Ladder Models (Added November 2025):
- **LadderTeam**: Ladder teams with rankings, gender, contact preferences, stats, holiday mode tracking
- **LadderFreeAgent**: Individual players awaiting pairing via Americano tournaments
- **LadderChallenge**: Challenge requests with acceptance/completion deadlines, status tracking
- **LadderMatch**: Match results with dual score verification, rank swapping
- **AmericanoTournament**: Monthly tournaments for free agent pairing
- **AmericanoMatch**: Individual Americano match results and player points
- **LadderSettings**: Ladder configuration (challenge rules, penalties, activity requirements)

## Authentication & Security
- **Admin Access**: Password-protected admin panel with session-based authentication
- **Team Access**: Unique token-based URLs for secure team-specific match viewing
- **Player Confirmation**: Two-factor confirmation system for team registration (player 2 must confirm via unique token)
- **Environment Variables**: All secrets stored in environment variables (SECRET_KEY, ADMIN_PASSWORD, VERIFY_TOKEN)

## Key Features Architecture

### Swiss Format Pairing System
- Automated opponent matching based on current standings (wins, then sets differential)
- Avoids repeat matchups when possible
- Handles odd team counts with bye rounds
- Implemented in `utils.py::generate_round_pairings()`

### Match Scheduling & Deadlines
- Weekly rounds: Monday-Sunday for regular matches
- Reschedule deadline: Wednesday 23:59
- Makeup match window: Monday-Wednesday
- Automatic walkover enforcement for missed deadlines

### Score Management
- Winning team submits scores
- Both teams must verify scores
- Dispute resolution system for disagreements
- Automatic statistics calculation (team and individual player stats)

### Notification System
- Email notifications for match reminders, reschedules, substitutes
- WhatsApp integration support (optional)
- Scheduled tasks via background worker (`scheduled_tasks.py`)

## Frontend Architecture
- **CSS Framework**: Tailwind CSS (CDN-based)
- **Mobile Responsive**: Mobile-first design with dual-view system:
  - Desktop: Full data tables
  - Mobile: Card-based layouts with large touch targets
- **Gradients & Theming**: Purple/indigo gradient theme throughout
- **Interactive Elements**: Hover effects, transitions, status badges

## Deployment Configuration
- **Production Platform**: Deployed on Replit with custom domain
- **Custom Domain**: goeclectic.xyz (configured October 2025)
- **Database Pooling**: Connection pre-ping, 5-minute recycling, 10-second timeout
- **Health Checks**: Dedicated `/health` endpoint (no database queries)
- **Build/Run Separation**: Dependencies installed during build phase, not runtime
- **Error Handling**: Custom 404/500 handlers, graceful session rollback

## Data Flow Patterns
1. **Registration Flow**: Team/FreeAgent → Player confirmation → Admin approval
2. **Round Generation**: Admin triggers → Swiss pairing algorithm → Match creation
3. **Match Lifecycle**: Scheduled → Booking proposed → Both teams confirm → Score submission → Both teams verify → Completed
4. **Statistics Updates**: Match completion → Team stats updated → Individual player stats updated → Leaderboard recalculated

# External Dependencies

## Required Services
- **PostgreSQL Database**: Primary production database (Neon-hosted on Replit, or Render PostgreSQL)
- **SMTP Email Server**: For notifications (Gmail SMTP or similar)
  - Requires: EMAIL_SENDER, EMAIL_PASSWORD, SMTP_SERVER, SMTP_PORT

## Optional Integrations
- **WhatsApp Business API**: For WhatsApp notifications
  - Requires: WHATSAPP_API_KEY, WHATSAPP_PHONE_ID, ACCESS_TOKEN
- **Sentry**: Error monitoring (commented in code, ready to enable)

## Python Package Dependencies
Core packages from `requirements.txt`:
- flask (3.0.0) - Web framework
- flask-sqlalchemy (3.1.1) - ORM
- gunicorn (21.2.0) - Production WSGI server
- psycopg2-binary (2.9.9) - PostgreSQL adapter
- apscheduler (3.10.4) - Background task scheduling
- requests (2.31.0) - HTTP client for API calls
- python-dotenv (1.0.0) - Environment variable management

## Environment Variables Required
- `SECRET_KEY` - Flask session encryption (generate with secrets.token_hex(32))
- `ADMIN_PASSWORD` - Admin panel access
- `VERIFY_TOKEN` - Webhook security
- `DATABASE_URL` - PostgreSQL connection string (auto-injected on Replit/Render)
- `APP_BASE_URL` - Application base URL for email links (set to https://goeclectic.xyz)

## CDN Dependencies
- Tailwind CSS - Styling framework (loaded via CDN)
- Google Fonts (Inter) - Typography