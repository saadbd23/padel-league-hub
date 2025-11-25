# Overview

BD Padel League is a web-based platform designed for managing competitive padel tournaments, built using Flask and SQLAlchemy. It supports two main tournament systems: a Swiss-format League with playoff management and a challenge-based Ladder Tournament for both men's and women's divisions. The platform streamlines team/player registration, automates pairings, facilitates match scheduling, enables score submission, maintains leaderboards, and provides secure team access. The business vision is to provide a robust, user-friendly solution for padel clubs and communities to organize and run their leagues efficiently, enhancing player engagement and competition.

# Recent Changes

## November 25, 2025 (Current)
- **Fixed Admin Walkover Display**: Updated admin override code to correctly set `match.status = "walkover"` instead of "completed". Walkovers now display with orange "W - Team Name" badge in admin panel and "Admin Override - Walkover" badge on public rounds page. Updated filters to exclude walkover status from automatic deadline checks (preventing duplicate walkovers). Round completion percentages now correctly count walkovers as completed matches. Updated both admin and public round data calculations to include walkovers in completion counts. Verified with Team Jithbo vs Padel Bros test match showing 10/11 complete in Round 1.

## November 24, 2025
- **Added Round Summary Section with Accordion View and Confirmation Status**: Reorganized "Round Summary" section in league admin panel to show accordion-style sections for each round. Each round displays: Round number with completion status (e.g., "2/4 Complete"), Team matchups on one line (e.g., "Padelers vs HAWKS"), Match booking date (color-coded: yellow for "Yet to be scheduled", green for scheduled) with confirmation status badge (✓ = confirmed, ⏳ = awaiting confirmation), and Match scores (if posted by any team) with confirmation status (✓ = confirmed by both, ⏳ = awaiting confirmation from opponent). Scores display as soon as one team submits them, with awaiting confirmation icon if not yet verified. Walkovers display with orange badge showing "W - Team Name" indicating admin override. Rounds sorted by newest first. Within each round, matches sorted by earliest booking date. Desktop table view and mobile card view for responsive design. Fully collapsible with expand/collapse toggles. Compact table format with minimal row height for better overview.
- **Improved Walkover Display Clarity**: Added clear visual indicators for admin-override walkovers in both admin panel and public rounds page. Admin panel shows walkovers with orange "W - Team Name" badge instead of score. Public rounds page shows "Admin Override - Walkover" badge with winner name and notes for better transparency.
- **Fixed Admin Calendar for Rescheduled Matches**: Fixed issue where "Today's Matches" calendar in admin panel wasn't showing rescheduled matches. Problem was that `match.match_datetime` field wasn't being populated when reschedules were approved. Fixed reschedule approval code to properly set `match_datetime` during approval while preserving `match_date` format. Now rescheduled matches appear in today's calendar.
- **Fixed Challenge Authentication Flow**: Fixed issue where clicking challenge button from team page would redirect to login. Challenge form now passes team access token to `/ladder/challenge/create` route. Route updated to support both session-based and token-based authentication. Teams can now challenge directly from their team page without forced login redirect. Success redirects back to team page with token to keep users on their dashboard.
- **Ladder Score Confirmation Workflow**: Implemented improved UX where one team submits score, other team confirms or rejects. If rejected, second team submits own score. If both reject, escalates to admin dispute (rejection_count >= 2). New fields added to LadderMatch: `score_confirmed_by_a`, `score_confirmed_by_b`, `first_submitter_id`, `rejection_count`. New routes: `/ladder/score/confirm/<match_id>` and `/ladder/score/reject/<match_id>`. Rankings update immediately when both teams confirm scores via `verify_match_scores()` → `update_ladder_team_stats_from_match()` → `swap_ladder_ranks()`.
- **Fixed Calendar Timezone Issues**: Converted all date formatting from UTC (`toISOString()`) to local date format in JavaScript to prevent one-day offset. Fixed both Match Booking calendar (now correctly shows Nov 24-30 for Round 2) and Reschedule Request calendar (now correctly shows Dec 1-3).
- **Fixed Score Verification Bug**: Corrected verification logic that was incorrectly checking if scores were equal. System now accepts verified matches when both teams submit scores in the consistent format (scores stored same way regardless of submission order).
- **Resolved Match Dispute**: Manually resolved Serious Smash vs Midlife Crushers disputed match. Updated team statistics and rankings immediately: Midlife Crushers 1W-0L (Rank #1), Serious Smash 0W-1L (Rank #2). Updated `ladder_challenge` status to `completed`.
- **Accordion-Style Public Round View**: Applied accordion UI to rounds.html page - all public viewers can now see round matches organized in collapsible sections. Each round shows match count and completion status (e.g., "2/4 Complete"), sorting newest rounds first for easy navigation.
- **Accordion-Style Match Management UI**: Reorganized League Match Management section with collapsible round-based accordion. Each round now shows match count and completion status, expandable on demand for cleaner organization as more rounds are generated.
- **Fixed Generate Round Bug**: Added missing `/admin/generate-round` route that was causing blank page when trying to generate league rounds. Route now properly creates Swiss-format pairings and sends email notifications to teams.

## November 23, 2025
- **Penalty Control UI Enhancement**: Added clear ON/OFF visual indicators with green (✅ PENALTIES ON) and red (⛔ PENALTIES OFF) badges for penalty activation toggle in Ladder Settings
- **Court Booking Rule**: Added first rule in Ladder Tournament Rules section requiring teams to book and pay for courts themselves
- **Database Schema Update**: Added `penalties_active` boolean column to `ladder_settings` table (defaults to False for safe ladder launch)

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Core Framework
- **Backend**: Flask 3.0 with Jinja2 templating.
- **Database**: SQLAlchemy ORM, supporting PostgreSQL for production and SQLite for local development.
- **Session Management**: Flask sessions secured with a secret key.
- **WSGI Server**: Gunicorn for production deployments.

## Database Schema
A single PostgreSQL database managed via `models.py` containing:
- **League Models**: Team, Player, Match, Reschedule, Substitute, LeagueSettings.
- **Ladder Models**: LadderTeam, LadderFreeAgent, LadderChallenge, LadderMatch, AmericanoTournament, AmericanoMatch, LadderSettings.

## Authentication & Security
- **Admin Access**: Password-protected, session-based admin panel.
- **Team Access**: Unique token-based URLs for team-specific data.
- **Player Confirmation**: Two-factor confirmation for team registration.
- **Environment Variables**: All sensitive data (SECRET_KEY, ADMIN_PASSWORD, VERIFY_TOKEN) are managed via environment variables.

## Key Features Architecture

### Tournament Systems
- **Swiss Format Pairing**: Automated pairing based on standings, avoiding repeat matchups.
- **Ladder Tournament**: Challenge system allowing teams to challenge up to 3 ranks above, including holiday mode, activity monitoring, and separate divisions.
- **Americano Tournament System**: Monthly tournaments for free agent pairing with a smart round-robin algorithm, individual scoring, and admin management.

### Match Management
- **Scheduling & Deadlines**: Weekly rounds, reschedule deadlines, and automatic walkover enforcement.
- **Score Management**: Winning team submission, dual-team verification, and dispute resolution.

### UI/UX Decisions
- **Frontend**: Tailwind CSS (CDN-based) for styling.
- **Mobile Responsive**: Mobile-first design with dual desktop (tables) and mobile (card-based) views.
- **Theming**: Purple/indigo gradient theme with interactive elements and status badges.
- **Homepage Redesign**: Dual-card hero layout prioritizing Ladder, live stats dashboard, and clear registration paths.
- **Navigation Overhaul**: Dropdown menus for both desktop and mobile.
- **Leaderboard/Statistics Pages**: Tabbed interfaces for easy navigation between League and Ladder data.
- **Rules Page**: Accordion-style sections for different tournament rules.

## Deployment Configuration
- **Platform**: Replit with a custom domain (goeclectic.xyz).
- **Database Pooling**: Connection pre-ping, recycling, and timeout configurations.
- **Health Checks**: Dedicated `/health` endpoint.
- **Error Handling**: Custom 404/500 handlers and graceful session rollback.
- **Gunicorn Timeout**: 120 seconds (for long-running operations like round generation with email notifications).

# External Dependencies

## Required Services
- **PostgreSQL Database**: Primary production database (e.g., Neon, Render PostgreSQL).
- **SMTP Email Server**: For notifications (e.g., Gmail SMTP).
  - Environment Variables: `EMAIL_SENDER`, `EMAIL_PASSWORD`, `SMTP_SERVER`, `SMTP_PORT`.

## Optional Integrations
- **WhatsApp Business API**: For WhatsApp notifications.
  - Environment Variables: `WHATSAPP_API_KEY`, `WHATSAPP_PHONE_ID`, `ACCESS_TOKEN`.
- **Sentry**: Error monitoring.

## Python Package Dependencies
- `flask` (3.0.0)
- `flask-sqlalchemy` (3.1.1)
- `gunicorn` (21.2.0)
- `psycopg2-binary` (2.9.9)
- `apscheduler` (3.10.4)
- `requests` (2.31.0)
- `python-dotenv` (1.0.0)

## Environment Variables Required
- `SECRET_KEY`
- `ADMIN_PASSWORD`
- `VERIFY_TOKEN`
- `DATABASE_URL`
- `APP_BASE_URL`

## CDN Dependencies
- Tailwind CSS
- Google Fonts (Inter)