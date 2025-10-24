# Overview

BD Padel League is a comprehensive web-based platform for managing competitive padel tournaments using the Swiss format. Built with Flask and SQLAlchemy, it handles team/player registration, automated round pairings, match scheduling, score submission, leaderboards, reschedule requests, and substitute player management. The system provides secure team-specific access via unique tokens and supports both complete teams and free agent matching.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Core Framework
- **Backend**: Flask 3.0 with Jinja2 templating
- **Database**: SQLAlchemy ORM with dual support:
  - PostgreSQL for production (primary)
  - SQLite fallback for local development
- **Session Management**: Flask sessions with secure secret key handling
- **WSGI Server**: Gunicorn for production deployment

## Database Schema
Key models tracked in `models.py`:
- **Team**: Team registration, player details, match statistics (wins/losses/draws), points, sets/games differentials, reschedule/substitute usage tracking, secure access tokens
- **Player**: Individual player statistics across all matches participated in (handles substitutions separately from team stats)
- **Match**: Round-based match records, scheduling, booking times, score storage, status tracking (scheduled/completed/bye/walkover/disputed)
- **FreeAgent**: Solo player registration with skill level for pairing
- **Reschedule**: Reschedule request tracking with deadlines and approval workflow
- **Substitute**: Substitute player management with admin approval

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