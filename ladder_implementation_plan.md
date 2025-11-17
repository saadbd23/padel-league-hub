# Ladder Tournament System - Implementation Plan

**Created:** November 17, 2025  
**Status:** Planning Phase

---

## Overview

A parallel ladder tournament system running alongside the existing league. The ladder is open to all players without skill-based entry requirements, featuring separate Men's and Women's divisions with a challenge-based ranking system.

---

## Key Principles

- **Completely separate** from league (different teams/players - no overlap)
- **Open entry** - no skill requirements
- **Gender-based divisions** - Men's and Women's ladders
- **Simplified management** - teams coordinate directly, no reschedule/substitute workflows
- **Challenge system** - teams can challenge up to 3 ranks above
- **Rolling registration** - teams join at the bottom anytime
- **Americano tournaments** - monthly events for free agents to find partners

---

## Database Models

### ☐ **LadderTeam**
```python
- id (primary key)
- team_name (string, unique across league AND ladder)
- team_name_canonical (string, indexed - for duplicate detection)
- player1_name, player1_phone, player1_email
- player2_name, player2_phone, player2_email
- gender (string: 'men' or 'women') - determines which ladder
- ladder_type (string: 'men' or 'women') - redundant but clear
- current_rank (integer) - position in ladder
- contact_preference_email (boolean)
- contact_preference_whatsapp (boolean)
- access_token (string, unique) - for secure team pages

# Stats
- matches_played, wins, losses, draws
- sets_for, sets_against, games_for, games_against

# Activity tracking
- last_match_date (datetime)
- matches_this_month (integer)

# Holiday mode
- holiday_mode_active (boolean)
- holiday_mode_start (datetime)
- holiday_mode_end (datetime)

# Metadata
- created_at, updated_at
```

### ☐ **LadderFreeAgent**
```python
- id (primary key)
- name, phone, email
- gender (string: 'men' or 'women')
- contact_preference_email (boolean)
- contact_preference_whatsapp (boolean)
- access_token (string, unique)
- skill_level, playstyle, availability (optional info)
- partner_requested (boolean) - after Americano
- partner_request_deadline (datetime) - 3 days after tournament
- created_at
```

### ☐ **LadderChallenge**
```python
- id (primary key)
- challenger_team_id (foreign key to LadderTeam)
- challenged_team_id (foreign key to LadderTeam)
- ladder_type (string: 'men' or 'women')
- status (string: pending_acceptance, accepted, completed, expired, defaulted)
- acceptance_deadline (datetime) - 2 days from challenge
- completion_deadline (datetime) - 1 week from acceptance
- no_show_reported_by (integer, nullable) - team_id that reported no-show
- no_show_dispute (boolean)
- created_at, accepted_at, completed_at
```

### ☐ **LadderMatch**
```python
- id (primary key)
- challenge_id (foreign key to LadderChallenge)
- team_a_id, team_b_id (foreign keys to LadderTeam)
- ladder_type (string: 'men' or 'women')

# Score submission (same format as league)
- score_a (string: "6-4, 6-3")
- score_b (string: "6-4, 6-3")
- score_submission_a (text) - Team A's submitted score
- score_submission_b (text) - Team B's submitted score
- score_submitted_by_a (boolean)
- score_submitted_by_b (boolean)

# Calculated stats
- winner_id (integer)
- sets_a, sets_b, games_a, games_b (integers)

# Verification
- verified (boolean)
- disputed (boolean)
- stats_calculated (boolean)

# Metadata
- match_date (string)
- created_at, completed_at
```

### ☐ **AmericanoTournament**
```python
- id (primary key)
- tournament_date (datetime)
- gender (string: 'men' or 'women')
- status (string: setup, in_progress, completed)
- total_rounds (integer)
- participating_free_agents (text/json) - list of free agent IDs
- created_at, completed_at
```

### ☐ **AmericanoMatch**
```python
- id (primary key)
- tournament_id (foreign key to AmericanoTournament)
- round_number (integer)
- court_number (integer)
- player1_id, player2_id (foreign keys to LadderFreeAgent)
- player3_id, player4_id (foreign keys to LadderFreeAgent)
- score_team_a (string: "6-4")
- score_team_b (string: "4-6")
- winner_team (string: 'a' or 'b')
- points_player1, points_player2, points_player3, points_player4 (integers)
- created_at
```

### ☐ **LadderSettings**
```python
- id (primary key)
- challenge_acceptance_hours (integer, default: 48) - 2 days
- challenge_completion_days (integer, default: 7) - 1 week
- max_challenge_rank_difference (integer, default: 3)
- acceptance_penalty_ranks (integer, default: 1)
- no_show_penalty_ranks (integer, default: 1)
- min_matches_per_month (integer, default: 2)
- inactivity_penalty_ranks (integer, default: 3)
- holiday_mode_grace_weeks (integer, default: 2)
- holiday_mode_weekly_penalty_ranks (integer, default: 1)
- free_agent_partner_selection_days (integer, default: 3)
- team_registration_open (boolean)
- free_agent_registration_open (boolean)
```

---

## Features Breakdown

### **1. Team Registration** ☐
**Route:** `/ladder/register-team`

**Features:**
- Gender selection (required) - determines Men's/Women's ladder
- Player 1 & 2 details (name, phone, email)
- Contact preferences (Email and/or WhatsApp - at least one required)
- Team name uniqueness check across BOTH league AND ladder
  - Use same canonical name logic: `normalize_team_name()`
  - Check against both `Team` and `LadderTeam` tables
  - **If duplicate found: REJECT registration with error message (no numbering allowed)**
- Simple confirmation: email sent to both players with team details
- Access token generated for `/ladder/my-team/<token>`
- Team added at bottom of appropriate ladder

**Implementation checklist:**
- [ ] Create registration form template
- [ ] Add gender dropdown (Men/Women)
- [ ] Add contact preference checkboxes
- [ ] Implement cross-table name uniqueness check (League + Ladder)
- [ ] Reject duplicate names with clear error message
- [ ] Generate access token
- [ ] Send confirmation emails
- [ ] Add team at bottom rank of ladder
- [ ] Create success page with access link

---

### **2. Free Agent Registration** ☐
**Route:** `/ladder/register-freeagent`

**Features:**
- Personal details (name, phone, email)
- Gender selection (required)
- Contact preferences (Email and/or WhatsApp)
- Optional: skill level, playstyle, availability
- Access token for `/ladder/my-freeagent/<token>`
- Rolling pool - stays until partnered

**Implementation checklist:**
- [ ] Create free agent registration form
- [ ] Add gender selection
- [ ] Add contact preference checkboxes
- [ ] Check for duplicate registrations (phone/email)
- [ ] Generate access token
- [ ] Send confirmation email
- [ ] Create success page with access link

---

### **3. Public Ladder Pages** ☐
**Routes:** `/ladder/men/` and `/ladder/women/`

**Features:**
- Display current rankings (rank, team name, record, sets diff, games diff)
- Show contact preferences (email/WhatsApp icons)
- Active challenges indicator (team is locked)
- Holiday mode indicator
- Challenge button for teams (if logged in via token or session)
- Recent match results
- Top performers section

**Implementation checklist:**
- [ ] Create men's ladder template
- [ ] Create women's ladder template
- [ ] Display rankings table with stats
- [ ] Show locked status for active challenges
- [ ] Show holiday mode status
- [ ] Display contact preference icons
- [ ] Add challenge interface for logged-in teams
- [ ] Show recent matches section

---

### **4. Team-Specific Pages** ☐
**Route:** `/ladder/my-team/<token>`

**Features:**
- View team's current rank and stats
- Active challenges (sent/received)
- Match history
- Submit scores for completed matches
- Holiday mode management:
  - Activate/deactivate
  - Show days remaining in grace period
  - Show penalty warning if exceeding 2 weeks
- Report no-show

**Implementation checklist:**
- [ ] Create team dashboard template
- [ ] Display current rank and stats
- [ ] Show active challenges with deadlines
- [ ] Match history with score submission forms
- [ ] Holiday mode toggle with grace period calculator
- [ ] No-show reporting interface
- [ ] Score submission form (both teams must confirm)

---

### **5. Challenge System** ☐

**Workflow:**
1. Team A views ladder, clicks "Challenge" on teams ranked 1-3 positions higher
2. System validates:
   - Team A not already in a challenge
   - Team B not already in a challenge
   - Team B not on holiday mode
   - Rank difference ≤ 3
3. LadderChallenge created (status: pending_acceptance)
4. Both teams locked (can't send/receive other challenges)
5. Notification sent to Team B
6. **Acceptance deadline: 2 days**
   - If accepted: status → accepted, completion_deadline set (1 week)
   - If no response: Team B gets -1 rank penalty, challenge expired
7. **Completion deadline: 1 week from acceptance**
   - Teams coordinate match directly
   - Both submit scores via their team pages
   - If both scores match: verified, ranks swap, teams unlocked
   - If scores conflict: disputed, both teams locked until resolved
   - If no-show: reporting team can flag, other team can dispute

**Implementation checklist:**
- [ ] Create challenge creation logic
- [ ] Validate challenge eligibility (rank, locks, holiday)
- [ ] Lock both teams on challenge creation
- [ ] Send challenge notification
- [ ] Acceptance deadline check (background job)
- [ ] Apply acceptance penalty if expired
- [ ] Completion deadline check (background job)
- [ ] Score submission interface
- [ ] Score verification and rank swap logic
- [ ] Dispute handling (lock teams, admin can override)
- [ ] No-show reporting and penalty system
- [ ] Unlock teams after completion

---

### **6. Match Score Submission & Verification** ☐

**Process:**
1. After match completion, both teams go to their team page
2. Each team submits score (same format as league: "6-4, 6-3")
3. If scores match:
   - Match verified
   - Calculate sets/games (use existing league logic)
   - Update team stats
   - Swap ranks (winner gets challenged team's rank, loser drops)
   - Unlock both teams
4. If scores don't match:
   - Mark as disputed
   - Lock both teams
   - Both teams can't challenge until resolved
   - Teams must resolve directly (no admin intervention)

**Implementation checklist:**
- [ ] Score submission form on team page
- [ ] Store both teams' submissions
- [ ] Compare submissions
- [ ] Calculate sets/games using league's parse_score logic
- [ ] Update team stats
- [ ] Implement rank swapping logic
- [ ] Handle disputes (lock and notify)
- [ ] Allow score resubmission if disputed

---

### **7. Rank Management** ☐

**Ranking logic:**
- Initial order: Registration order (first registered = rank 1)
- New teams always join at bottom
- After match: Winner takes loser's rank, loser and all below shift down 1
- Penalties (acceptance, no-show, inactivity, holiday) drop team N ranks, others shift up

**Implementation checklist:**
- [ ] Initialize rank on team registration
- [ ] Rank swap function after match completion
- [ ] Rank drop function for penalties
- [ ] Reorder all teams after any rank change
- [ ] Display rank history (optional)

---

### **8. Holiday Mode** ☐

**Features:**
- Teams can activate holiday mode anytime
- Grace period: 2 weeks, no penalty
- Teams locked during holiday (can't challenge or be challenged)
- After 2 weeks: -1 rank per additional week
- Teams can deactivate anytime

**Implementation checklist:**
- [ ] Holiday mode activation/deactivation UI
- [ ] Set start/end dates
- [ ] Lock team during holiday
- [ ] Background job to check duration weekly
- [ ] Apply penalties after 2-week grace period
- [ ] Notification emails before/after grace period

---

### **9. Activity Monitoring** ☐

**Rules:**
- Minimum 2 matches per month
- Checked monthly (background job)
- Teams with <2 matches: -3 rank penalty
- Warning email sent 1 week before deadline

**Implementation checklist:**
- [ ] Track matches_this_month counter
- [ ] Monthly background job to check all teams
- [ ] Send warning emails at 3-week mark
- [ ] Apply -3 rank penalty if not met
- [ ] Reset monthly counters

---

### **10. Admin Interface** ☐

**Structure:** Tabbed admin panel at `/admin`
- **LEAGUE tab** - existing admin panel (unchanged)
- **LADDER tab** - new ladder management

**Ladder Admin Sections:**

**Men's Ladder Management:**
- View all teams with ranks, stats, status
- Monitor active challenges
- View challenge history
- Override disputed matches (reluctantly)
- Delete teams
- Manual rank adjustments (if needed)

**Women's Ladder Management:**
- Same as Men's

**Free Agents & Americano:**
- View all free agents (Men/Women)
- Create new Americano tournament
- Manage active/past Americanos
- Enter match results
- View individual leaderboards
- Pair free agents (create LadderTeam)

**Activity & Penalties:**
- View teams on holiday mode
- View upcoming activity deadlines
- Manual penalty application/removal

**Implementation checklist:**
- [ ] Modify existing admin.html to add tabs
- [ ] Create ladder admin template
- [ ] Men's ladder management page
- [ ] Women's ladder management page
- [ ] Challenge monitoring dashboard
- [ ] Team deletion functionality
- [ ] Manual rank adjustment tool
- [ ] Free agent management page
- [ ] Americano tournament creation
- [ ] Americano match entry interface
- [ ] Pairing interface
- [ ] Activity monitoring dashboard

---

### **11. Americano Tournament Management** ☐

**Workflow:**
1. Admin creates tournament (selects gender, date)
2. System lists all unpartnered free agents of that gender
3. Admin selects participants
4. System generates round-robin pairings:
   - Each player partners with every other player once
   - Each player opposes every other player once
   - Rotates courts
5. Admin enters scores after each round
6. System calculates individual points
7. Final leaderboard shows player rankings
8. Free agents have 3 days to request partner
9. Admin pairs them → creates LadderTeam at bottom rank
10. Paired free agents removed from pool (unpaired stay)

**Americano Format Reference:** https://www.padel.fyi/articles/what-is-a-padel-americano/
- Players rotate partners each round
- Individual scoring (win = +1 point, typically)
- Helps players find compatible partners

**Implementation checklist:**
- [ ] Tournament creation form (date, gender)
- [ ] Participant selection interface
- [ ] Round-robin pairing algorithm
- [ ] Order of play display (court, round, players)
- [ ] Score entry form for each match
- [ ] Individual points calculation
- [ ] Leaderboard display
- [ ] Partner request deadline (3 days)
- [ ] Partner selection interface for free agents
- [ ] Admin pairing confirmation
- [ ] Create LadderTeam at bottom rank
- [ ] Remove paired free agents from pool

---

### **12. Background Jobs & Automation** ☐

**Daily jobs:**
- Check challenge acceptance deadlines (2 days)
  - Apply -1 rank penalty if not accepted
  - Mark challenge as expired
  - Unlock both teams
- Check challenge completion deadlines (1 week)
  - Send reminder at 5 days
  - Check at 7 days, handle no-show if reported
- Check holiday mode durations
  - Send warning at 2-week mark
  - Apply -1 rank penalty per week after grace period
- Check free agent partner request deadlines (3 days after Americano)

**Monthly jobs:**
- Activity monitoring
  - Send warning at 3-week mark
  - Check all teams at month-end
  - Apply -3 rank penalty if <2 matches

**Implementation checklist:**
- [ ] Set up APScheduler jobs (or use existing scheduled_tasks.py)
- [ ] Challenge acceptance deadline checker
- [ ] Challenge completion deadline checker
- [ ] Holiday mode duration checker
- [ ] Free agent deadline checker
- [ ] Monthly activity checker
- [ ] Email notification templates for all events

---

### **13. Email Notifications** ☐

**Notification types:**
- Challenge sent (to challenged team)
- Challenge accepted (to challenger)
- Challenge acceptance deadline approaching (1 day before)
- Challenge completion deadline approaching (2 days before)
- Score submission confirmation (both teams)
- Score dispute notification (both teams)
- No-show reported (both teams)
- Penalty applied (affected team)
- Holiday mode warnings (approaching 2-week mark)
- Activity warning (3 weeks into month)
- Americano invitation
- Partner request deadline reminder
- Team registration confirmation

**Implementation checklist:**
- [ ] Create email templates for all notification types
- [ ] Integrate with existing email system
- [ ] Respect contact preferences (email/WhatsApp)
- [ ] Add unsubscribe handling (if needed)

---

### **14. URL Structure** ☐

**Public routes:**
```
/ladder/men/ - Men's ladder rankings
/ladder/women/ - Women's ladder rankings
/ladder/register-team - Team registration
/ladder/register-freeagent - Free agent registration
/ladder/my-team/<token> - Team dashboard
/ladder/my-freeagent/<token> - Free agent dashboard
/ladder/rules - Ladder rules and FAQ (optional)
```

**Admin routes:**
```
/admin - Main admin (with LEAGUE/LADDER tabs)
/ladder/admin/men - Men's ladder admin
/ladder/admin/women - Women's ladder admin
/ladder/admin/freeagents - Free agent management
/ladder/admin/americano - Americano tournaments
/ladder/admin/challenges - Challenge monitoring
```

**League routes (UNCHANGED):**
```
/register-team
/register-freeagent
/admin
/my-matches/<token>
... all existing routes remain the same
```

---

## Implementation Phases

### **Phase 1: Database & Models**
- [ ] Create all 6 database models
- [ ] Add migration scripts
- [ ] Test model relationships

### **Phase 2: Registration & Basic Pages**
- [ ] Team registration with uniqueness checks
- [ ] Free agent registration
- [ ] Public ladder pages (men/women)

### **Phase 3: Challenge System**
- [ ] Challenge creation and validation
- [ ] Score submission and verification
- [ ] Rank swapping logic
- [ ] Dispute handling

### **Phase 4: Advanced Features**
- [ ] Holiday mode
- [ ] Activity monitoring
- [ ] No-show reporting

### **Phase 5: Admin Interface**
- [ ] Tabbed admin structure
- [ ] Ladder management pages
- [ ] Challenge monitoring

### **Phase 6: Americano System**
- [ ] Tournament creation
- [ ] Pairing algorithm
- [ ] Score entry and leaderboards
- [ ] Free agent pairing

### **Phase 7: Automation**
- [ ] Background jobs
- [ ] Email notifications
- [ ] Deadline enforcement

### **Phase 8: Testing & Polish**
- [ ] End-to-end testing
- [ ] Bug fixes
- [ ] UI/UX improvements

---

## Important Implementation Notes

### **Team Name Uniqueness (CRITICAL)**
- Use existing `normalize_team_name()` function from `utils.py`
- Check against BOTH `Team` (league) and `LadderTeam` (ladder) tables
- **If duplicate found: REJECT registration with clear error message**
- **NO automatic numbering allowed** (e.g., "Team Name 2" is NOT allowed)
- Store canonical name in `team_name_canonical` field (indexed for fast lookup)
- Error message example: "This team name is already taken. Please choose a different name."

### **Score Format**
- Use same format as league: "6-4, 6-3" or "6-4, 3-6, 10-8"
- Reuse existing `parse_score()` function from league
- Calculate sets won and total games

### **Contact Preferences**
- Both email and WhatsApp can be selected
- At least one must be selected
- Display appropriate contact icons on public pages
- Use for notifications (respect preferences)

### **Rank Swapping Logic**
Example: Team at rank 5 challenges team at rank 2
- If rank 5 wins:
  - Rank 5 → Rank 2
  - Rank 2 → Rank 3
  - Rank 3 → Rank 4
  - Rank 4 → Rank 5
- If rank 2 wins:
  - Ranks stay the same

### **League vs Ladder Separation**
- NO player can be in both league AND ladder
- During registration, check if player (by phone/email) exists in:
  - `Team` table (league teams)
  - `LadderTeam` table (ladder teams)
- Block registration if found

---

## Testing Checklist

### **Registration Flow**
- [ ] Register team with unique name
- [ ] Attempt duplicate name (should reject with error)
- [ ] Register team with name from league (should reject)
- [ ] Register free agent
- [ ] Verify emails sent
- [ ] Access team page via token

### **Challenge Flow**
- [ ] Create challenge (rank +1, +2, +3)
- [ ] Verify both teams locked
- [ ] Accept challenge within deadline
- [ ] Submit matching scores → ranks swap
- [ ] Submit conflicting scores → dispute
- [ ] Report no-show → penalty applied
- [ ] Ignore acceptance deadline → penalty applied

### **Holiday Mode**
- [ ] Activate holiday mode
- [ ] Verify team locked
- [ ] Deactivate within 2 weeks (no penalty)
- [ ] Stay on holiday >2 weeks → penalties applied

### **Americano Flow**
- [ ] Create tournament
- [ ] Generate pairings
- [ ] Enter scores
- [ ] View leaderboard
- [ ] Free agents request partners
- [ ] Admin pairs → team created at bottom

### **Activity Monitoring**
- [ ] Play 2+ matches in month → no penalty
- [ ] Play <2 matches → -3 rank penalty
- [ ] Verify warning emails sent

---

## Future Enhancements (Post-MVP)

- [ ] Promotion/Relegation between League and Ladder
- [ ] Historical rank tracking and charts
- [ ] Player profile pages with detailed stats
- [ ] Auto-generated tournament brackets for special events
- [ ] Mobile app integration
- [ ] Live score updates
- [ ] Video upload for matches
- [ ] Automated court booking integration
- [ ] Ladder statistics dashboard (most active teams, longest win streaks, etc.)
- [ ] Season resets (optional yearly ladder reset)

---

## Questions & Decisions Log

**Q1: Free agents who don't partner within 3 days?**  
**A:** Stay in rolling pool for next month's Americano

**Q2: Admin interface structure?**  
**A:** Tabbed interface - LEAGUE | LADDER tabs in existing `/admin`

**Q3: Contact preferences?**  
**A:** Email and/or WhatsApp, at least one required

**Q4: Holiday mode duration?**  
**A:** 2 weeks grace, then -1 rank per week

**Q5: Team name uniqueness?**  
**A:** MUST be unique across BOTH league and ladder, reject duplicates (no numbering)

---

## Status Updates

**November 17, 2025:** Planning phase complete, implementation plan created

---

## Notes

- Maintain separation between league and ladder code where possible
- Reuse utility functions (normalize_team_name, parse_score, email sending)
- Keep admin interface clean with clear visual separation
- Ensure all deadlines are timezone-aware
- Test extensively before launch
- **CRITICAL:** Strictly enforce unique team names - no automatic numbering allowed
