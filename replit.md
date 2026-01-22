# Overview

BD Padel League is a web-based platform built with Flask and SQLAlchemy for managing competitive padel tournaments. It supports Swiss-format leagues with playoff management and challenge-based ladder tournaments for men's and women's divisions. The platform automates team/player registration, pairings, match scheduling, score submission, and leaderboard maintenance, providing secure team access. The vision is to offer a robust, user-friendly solution for padel clubs and communities to organize and run leagues efficiently, enhancing player engagement and competition.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Core Framework
- **Backend**: Flask 3.0 with Jinja2 templating.
- **Database**: SQLAlchemy ORM, supporting PostgreSQL for production and SQLite for local development.
- **Session Management**: Flask sessions secured with a secret key.
- **WSGI Server**: Gunicorn for production deployments.

## Database Schema
A single PostgreSQL database is managed via `models.py` and includes models for:
- **League**: Team (with status field for active/inactive), Player, Match, Reschedule, Substitute, LeagueSettings.
- **Ladder**: LadderTeam, LadderFreeAgent, LadderChallenge, LadderMatch, AmericanoTournament, AmericanoMatch, LadderSettings.

## Authentication & Security
- **Admin Access**: Password-protected, session-based admin panel.
- **Team Access**: Unique token-based URLs for team-specific data.
- **Player Confirmation**: Two-factor confirmation for team registration.
- **Environment Variables**: All sensitive data (SECRET_KEY, ADMIN_PASSWORD, VERIFY_TOKEN) are managed via environment variables.

## Key Features Architecture

### Tournament Systems
- **Swiss Format Pairing**: Automated pairing based on standings, avoiding repeat matchups. Only active teams are eligible for pairing in future rounds. Inactive teams retain their stats but don't get paired. **CRITICAL: Pairing algorithm now uses IDENTICAL ranking logic to public leaderboard (Points > Sets Diff > Games Diff > Wins > Team Name) to ensure consistency.**
- **Team Status Management**: Teams can be marked as 'active' or 'inactive' via admin panel. Inactive teams appear at bottom of leaderboard with "✗" badge (red) instead of confirmation badge.
- **Ladder Tournament**: Challenge system allowing teams to challenge up to 3 ranks above, including holiday mode, activity monitoring, and separate divisions.
- **Americano Tournament System**: Monthly tournaments for free agent pairing with a smart round-robin algorithm, individual scoring, and admin management.

### Match Management
- **Scheduling & Deadlines**: Weekly rounds, reschedule deadlines, and automatic walkover enforcement.
- **Score Management**: Winning team submission, dual-team verification, and dispute resolution.
- **Team Deactivation**: Admin can toggle team status to inactive, automatically excluding them from pairing in future rounds while preserving their historical match stats.

## Recent Changes (January 22, 2026)
- **Fixed Ladder Ranking Consistency Site-Wide**: Resolved issue where ladder rankings displayed inconsistently across different pages (Team BI showing as #3 on public page but #4 on team dashboard).
- **Root Cause**: Teams with identical `current_rank` values in database (e.g., Team BI and Grinders both had rank 4) were sorted differently: public ladder used Python sort with creation-order tiebreaker, team page used SQL ORDER BY which gives arbitrary order for tied values.
- **Solution**: All pages now use EXACT same sorting logic as public ladder: (1) filter by gender + payment_received=True, (2) calculate initial ranks from creation order, (3) sort by current_rank with creation order as tiebreaker.
- **View Matches Page Fix**: Admin ladder matches "Recently Completed" table now displays correct team ranks using display_rank calculation, matching public ladder rankings.
- **Display Rank Calculation**: All ladder pages (public men/women/mixed, admin matches, team page) now calculate sequential `display_rank` (1..N) from sorted team order for consistent rendering. No DB writes on read-only page views.
- **Sequential Rank-Based Challenge Logic**: Challenge eligibility uses index-based lookups from the sorted ladder list instead of querying by stored rank values. This ensures displayed ranks match actual ladder positions.
- **Display Rank Field**: Added `display_rank` field to challengeable teams dict to show the correct sequential rank in the UI.
- **Holiday Team Skip Logic**: When a holiday team is encountered in the challenge range, the algorithm now skips it and looks one rank higher, properly expanding the search range.
- **Separation of Display vs Storage**: Templates now use `display_rank` for rendering everywhere, while `current_rank` in DB is only modified by match outcomes and admin rank adjustments.

## Previous Changes (January 13, 2026)
- **Read-Only Bracket Visualization**: Knockout bracket now calculates SF/Finals slots purely in-memory from QF/SF winners without modifying database. Prevents accidental Round 7/8 creation during page renders.
- **Derived Slot Architecture**: `derived_sf_slots` and `derived_final_slot` dictionaries passed to template, allowing bracket to show progression before admin explicitly generates those rounds.
- **Round Deadline Calendar Fix**: Match booking calendar now respects custom `round_deadline` field set by admin when generating rounds.

## Previous Changes (January 8, 2026)
- **Redesigned Bracket with CSS Grid**: Rebuilt knockout bracket using CSS Grid with fixed row heights for proper vertical alignment. SF matches are now correctly positioned at the vertical midpoint of their QF pairs.
- **Grid-Based Bracket Architecture**: 4-row × 5-column grid layout (QF column, connector column, SF column, connector column, Finals column). QF matches occupy individual rows, SF slots span 2 rows each, Finals spans all 4 rows.
- **Connector Pseudo-Elements**: Horizontal arms (::after) and vertical spines (::before) on connector columns draw lines from QF pairs to SF matches and from SF pair to Finals. All sizing uses CSS custom properties (--match-height, --pair-gap, --arm-length).
- **Mobile Responsive Bracket**: Connector columns and pseudo-elements hidden on mobile (≤768px), matches stack vertically with mobile-round-labels visible.
- **Visual Knockout Bracket**: Bracket visualization showing QF → SF → Finals progression with seed badges and winner highlighting.
- **Bracket Schema Fields**: Added `bracket_slot`, `seed_a`, `seed_b` fields to Match model for proper bracket positioning and visual ordering.
- **Proper Bracket Seeding**: Bracket ordering follows standard single-elimination format: QF1 (1v8), QF2 (4v5), QF3 (2v7), QF4 (3v6). This ensures seeds 1 and 2 are on opposite bracket halves and can only meet in Finals.
- **Bracket Progression Flow**: QF1+QF2 winners → SF1, QF3+QF4 winners → SF2, SF winners → Finals.
- **Admin Knockout Controls**: New "Knockout Bracket" section in admin panel shows bracket progress (QF/SF/Finals status) and smart "Generate Next Round" buttons that appear only when previous round is complete.
- **Rounds Page Redesign**: Swiss rounds (1-5) displayed in collapsed accordion, knockout rounds (6+) shown in unified visual bracket view.

## Previous Changes (January 3, 2026)
- **Flexible Round Deadlines**: Added `round_deadline` DateTime field to Match model. Admins can set custom deadlines when generating rounds via date picker in admin panel.
- **Deadline Cascading Logic**: Reschedule request cutoff = round_deadline - 2 days; Makeup match deadline = round_deadline + 3 days. All deadline checks now prioritize `round_deadline` with fallback to legacy week-based calculations.
- **Extend Deadline Feature**: Admin can extend deadlines for any round via modal in Round Summary section. Only affects active/draft matches (not completed/walkover).
- **Dynamic Email Notifications**: Round confirmation and reschedule emails now display dynamically calculated deadlines based on `round_deadline`.
- **Deadline Violation Checks**: Both regular and makeup deadline checks updated to use `round_deadline` when available.
- **Knockout Round Restrictions**: Disabled Substitution and Reschedule requests for teams once knockout rounds (Round 6+) begin. Added backend validation and UI feedback on team pages.

## Previous Changes (December 2, 2025)
- **League Score Entry UI Improvement**: Changed score submission form from text input (e.g., "6-4") to separate number boxes for each team per set. Clear headers show team names. Format: Team A vs Team B scores for Set 1, Set 2, Set 3 (optional).
- **Score Preview & Confirmation Popup**: Teams now see a preview modal showing the exact scores they entered and the calculated winner before final submission. Options to Edit or Confirm.
- **Cancel Pending Challenges**: Challengers can now cancel (withdraw) their pending challenges from the "Challenges Sent" section. Challenged teams receive notification and become unlocked.

## Previous Changes (December 1, 2025)
- **Fixed Pairing Algorithm Ranking**: Updated `generate_round_pairings()` to use identical ranking logic as public leaderboard: Points → Sets Diff → Games Diff → Wins → Team Name (previously used: Wins → Sets Diff → Games Diff → Team ID)
- **Enhanced Pairing Explanations**: Improved logging to show ALL skipped candidates with reasons (e.g., "Already played in previous round") even when a match is found
- **Walkovers Admin Section**: Added compact UI section in League admin panel showing all walkovers awarded with round, matchup details, and player names
- **Cancel Challenge for Both Teams**: Both challenger and challenged teams can now cancel accepted challenges without penalty, with proper authorization checks

## Previous Changes (November 29, 2025)
- **Round Preview Workflow**: Implemented draft-based round generation with preview before sending emails. Generate → Preview pairings with reasons → Confirm (sends emails) or Discard (delete drafts)
- **Match Draft System**: Added `is_draft` boolean field to Match model. Draft matches are excluded from leaderboards, round summaries, and current round calculations
- **New Admin Endpoints**: `/admin/round-preview/<round>` (show preview), `/admin/confirm-round/<round>` (approve + send emails), `/admin/discard-round/<round>` (delete drafts)
- **Pairing Reasoning Display**: Preview page shows why each pairing was made (standings, avoiding repeats, etc.)
- **Admin Panel Enhancement**: Warning banner for pending draft rounds with link to preview page

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
- **PostgreSQL Database**: Primary production database.
- **SMTP Email Server**: For notifications.

## Optional Integrations
- **WhatsApp Business API**: For WhatsApp notifications.
- **Sentry**: Error monitoring.

## Python Package Dependencies
- `flask`
- `flask-sqlalchemy`
- `gunicorn`
- `psycopg2-binary`
- `apscheduler`
- `requests`
- `python-dotenv`

## Environment Variables Required
- `SECRET_KEY`
- `ADMIN_PASSWORD`
- `VERIFY_TOKEN`
- `DATABASE_URL`
- `APP_BASE_URL`
- `EMAIL_SENDER`
- `EMAIL_PASSWORD`
- `SMTP_SERVER`
- `SMTP_PORT`
- `WHATSAPP_API_KEY` (Optional)
- `WHATSAPP_PHONE_ID` (Optional)
- `ACCESS_TOKEN` (Optional)

## CDN Dependencies
- Tailwind CSS
- Google Fonts (Inter)
