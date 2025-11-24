# Overview

BD Padel League is a web-based platform designed for managing competitive padel tournaments, built using Flask and SQLAlchemy. It supports two main tournament systems: a Swiss-format League with playoff management and a challenge-based Ladder Tournament for both men's and women's divisions. The platform streamlines team/player registration, automates pairings, facilitates match scheduling, enables score submission, maintains leaderboards, and provides secure team access. The business vision is to provide a robust, user-friendly solution for padel clubs and communities to organize and run their leagues efficiently, enhancing player engagement and competition.

# Recent Changes

## November 24, 2025
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