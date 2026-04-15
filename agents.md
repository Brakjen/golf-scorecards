# Golf Scorecard App — V1 Product Specification

## 1. Product Goal

Build a web app that lets a golfer choose a predefined golf course and tee, keep score hole by hole, track key performance metrics for each hole, and generate a downloadable PDF scorecard for the round.

This is a scorekeeping and round-tracking app first.
The PDF scorecard is an important output, but it is generated from the round data the user enters.

---

## 2. V1 Scope

The v1 application must support four core workflows:

1. Select a course and tee from a built-in course catalog.
2. Create a round with player and date details.
3. Enter score and metrics for each hole.
4. Generate and download a printable PDF scorecard.

The application should not depend on an external golf course API for v1.
Course definitions are stored locally in the application.

---

## 3. Primary Use Cases

### UC-1: Create a New Round

**Actor:** User (golfer)  
**Goal:** Start a round using a predefined course and tee.

### Flow

1. User opens the app.
2. User selects a golf course from the local course catalog.
3. User selects a tee.
4. User enters round details:
   - Player name
   - Date
5. System loads the selected course and tee data.
6. System creates a round with a course snapshot.
7. System shows the hole-by-hole score entry screen.

### UC-2: Enter Hole-by-Hole Round Data

**Actor:** User (golfer)  
**Goal:** Record score and performance metrics while playing or after the round.

For each hole, the user can enter:

#### Core scoring

- Score
- Putts

#### Tee-to-green metrics

- Fairway hit
- Green in regulation
- Penalty strokes
- Miss direction

#### Short game metrics

- Up-and-down success
- Sand save success

#### Scoring-zone metrics

- Entered scoring zone in regulation
- Down in 3 from scoring zone
- Missed putt inside 4 ft
- Made putt over 4 ft

#### Optional qualitative notes

- Drive quality
- Approach quality
- Notes

### UC-3: View Scorecard

**Actor:** User (golfer)  
**Goal:** View a structured scorecard for the current round.

### Flow

1. User opens an existing or in-progress round.
2. System displays the selected course information.
3. System shows score and metrics for each hole.
4. System calculates front 9, back 9, and total summaries.
5. System calculates aggregate performance metrics for the round.

### UC-4: Download PDF Scorecard

**Actor:** User (golfer)  
**Goal:** Download a printable PDF version of the round scorecard.

### Flow

1. User selects download or export.
2. System renders the scorecard in print layout.
3. System generates a PDF.
4. User downloads the PDF.

---

## 4. Scorecard Requirements

### Front Side: Scorekeeping View

The front side should contain:

- Player name
- Date
- Course name
- Tee name

The main score table should contain:

- Hole number
- Handicap index
- Par
- Distance
- Score
- Putts
- FIR
- GIR
- Penalties

The front side should also show:

- Front 9 total
- Back 9 total
- Overall total

### Back Side: Performance Metrics View

The back side should contain performance tracking sections.

#### Section 1: Scoring Zone

Definition:
Scoring zone = 100 yards and in.

Rules:

- Par 3: enter scoring zone in 1 shot
- Par 4: enter scoring zone in 2 shots
- Par 5: enter scoring zone in 3 shots

Suggested columns:

- Hole
- Entered scoring zone in regulation
- Down in 3
- Birdie chance
- Conversion success

#### Section 2: Tee-to-Green

Suggested columns:

- Hole
- FIR
- GIR
- Miss direction
- Penalty strokes
- Recovery success

#### Section 3: Short Game and Putting

Suggested columns:

- Hole
- Up-and-down
- Sand save
- Putts
- Miss under 4 ft
- Made over 4 ft

#### Section 4: Round Summary Metrics

The system should auto-calculate:

- Total score
- Total putts
- FIR percentage
- GIR percentage
- Up-and-down percentage
- Sand save percentage
- Total penalty strokes
- Scoring zone entries
- Down-in-3 rate
- Birdie chances
- 3-putts

---

## 5. Data Source Strategy

### Course Catalog

For v1, course data is stored locally in the application.

The local catalog includes:

- Club name
- Course name
- Tee definitions
- Hole definitions
- Par
- Distance
- Handicap index

### Round Snapshotting

When a round is created, the application should save a snapshot of the selected course and tee data with the round.

This ensures:

- The scorecard remains stable even if local course definitions change later.
- Historical rounds remain accurate.

---

## 6. Core Data Model

### Course

- id
- country_code
- club_name
- course_name
- course_slug

### Tee

- id
- course_id
- tee_name
- tee_category
- gender_category
- number_of_holes
- par_total
- total_distance
- course_rating
- slope_rating

### Hole

- id
- tee_id
- hole_number
- par
- distance
- handicap

### Round

- id
- course_id
- tee_id
- player_name
- date
- course_snapshot

### RoundHole

- id
- round_id
- hole_number
- score
- putts
- fir
- gir
- penalties
- miss_direction
- up_and_down
- sand_save
- entered_sz_regulation
- down_in_3
- miss_short_putt
- made_long_putt
- drive_quality
- approach_quality
- notes

---

## 7. Functional Requirements

### FR-1: Course Selection

- User can browse or search the local course catalog.
- User can open a specific course.

### FR-2: Tee Selection

- User can select from the tees available for the chosen course.

### FR-3: Round Creation

- User can start a round with player name and date.
- System stores a snapshot of the selected course and tee.

### FR-4: Score Entry

- User can enter score hole by hole.
- User can edit hole data after entry.
- UI should support fast mobile use with low-friction inputs.

### FR-5: Metrics Entry

- User can track per-hole performance metrics alongside score.
- Metric inputs should support booleans, enums, integers, and notes.

### FR-6: Scorecard Rendering

- System renders a complete scorecard from the round snapshot and round data.
- Scorecard layout must support both screen and print views.

### FR-7: PDF Export

- System generates a downloadable PDF scorecard.
- PDF output should use a clean A4 print layout.

---

## 8. Non-Functional Requirements

### Performance

- Course selection should feel immediate.
- Scorecard render should feel near-instant for a single round.

### Usability

- Mobile-first input design.
- Large tap targets.
- Minimal typing during round entry.

### Reliability

- App should not depend on external golf course APIs.
- Course data used for a round must remain stable after round creation.

---

## 9. Technical Direction

### Backend

- Python backend using FastAPI.
- Local course catalog loaded from package data.
- Round and scorecard services exposed through application endpoints.

### Frontend

- Web UI for course selection, round entry, scorecard viewing, and PDF download.
- Mobile-friendly layout.

### PDF Generation

- Render scorecard as HTML/CSS.
- Generate PDF from the rendered scorecard.

---

## 10. Constraints and Design Decisions

- Do not rely on an external course API for v1.
- Use locally stored course definitions.
- Save a course snapshot when a round starts.
- Use HTML/CSS for scorecard rendering.
- Do not use plotting libraries for the scorecard layout.

---

## 11. Out of Scope for V1

- Shot-level tracking
- GPS or hole maps
- Club tracking
- AI-generated insights
- Multi-player rounds
- Advanced strokes-gained analytics

---

## 12. Definition of Done

V1 is complete when a user can:

- Select a predefined golf course
- Select a tee
- Start a round
- Enter hole-by-hole score
- Enter hole-by-hole performance metrics
- View a structured scorecard
- Download a printable PDF scorecard generated from that round
# Golf Scorecard & Metrics App — Use Case Specification

## 1. Overview

Build a web application that allows a golfer to:

- Select a golf course and tee
- Automatically retrieve course data (holes, yardage, par, stroke index)
- Generate a **course-specific scorecard**
- Track **hole-by-hole performance metrics**
- Export a **printable A4 scorecard (front + back)**

The system combines:
- External course data (API)
- User-entered round data
- Custom performance metrics (scoring-zone focused)

---

## 2. Primary Use Case

### UC-1: Create a New Round

**Actor:** User (golfer)  
**Goal:** Start a new round with a pre-filled scorecard

### Flow

1. User opens app
2. User selects:
   - Course (searchable)
   - Tee (e.g. White, Yellow, Blue)
   - Date
   - Player name
3. System fetches course data from API
4. System displays:
   - Hole list (1–18)
   - Par
   - Yardage
   - Stroke index
5. User confirms → round is created
6. System stores a **local snapshot** of course + tee data

---

## 3. Secondary Use Cases

### UC-2: Enter Round Data

**Goal:** Track performance hole-by-hole

For each hole, user can input:

#### Core scoring
- Score (strokes)
- Putts

#### Tee-to-green
- Fairway hit (boolean)
- Green in regulation (boolean)
- Penalty strokes (integer)
- Miss direction (L / R / Short / Long)

#### Short game
- Up-and-down success (boolean)
- Sand save success (boolean)

#### Scoring-zone metrics (key feature)
- Entered scoring zone in regulation (boolean)
- Down in 3 from scoring zone (boolean)
- Missed putt inside 4 ft (boolean)
- Made putt over 4 ft (boolean)

#### Optional qualitative
- Drive quality (good / neutral / poor)
- Approach quality (good / neutral / poor)
- Notes (text)

---

### UC-3: Generate Scorecard (Primary Output)

**Goal:** Produce a printable scorecard for the round

#### Output format:
- A4 landscape
- Two-sided layout

---

## 4. Scorecard Layout Specification

### Front Side (Course + Score Entry)

#### Header
- Player name
- Date
- Course name
- Tee name

#### Table (Front 9 + Back 9)

Rows:
- Hole (1–9 / 10–18)
- HCP (stroke index)
- Par
- Yardage
- Score
- Putts
- FIR
- GIR
- Penalties

Include:
- Front 9 total
- Back 9 total
- Overall total

---

### Back Side (Performance Metrics)

#### Section 1: Scoring Zone

Definition:
- Scoring zone = 100 yards and in

Rules:
- Par 3 → enter SZ in 1 shot
- Par 4 → enter SZ in 2 shots
- Par 5 → enter SZ in 3 shots

Table:
- Hole
- Entered SZ in regulation
- Down in 3
- Birdie chance
- Conversion success

---

#### Section 2: Tee-to-Green

- Hole
- FIR
- GIR
- Miss direction
- Penalty strokes
- Recovery success

---

#### Section 3: Short Game & Putting

- Hole
- Up-and-down
- Sand save
- Putts
- Miss < 4 ft
- Made > 4 ft

---

#### Section 4: Summary Metrics (Auto-calculated)

- Total score
- Total putts
- FIR %
- GIR %
- Up-and-down %
- Sand save %
- Penalty strokes total
- Scoring zone entries (count)
- Down-in-3 rate
- Birdie chances
- 3-putts

---

## 5. Data Sources

### External API (GolfCourseAPI)

Used for:
- Course name
- Tee boxes
- Hole data:
  - Par
  - Yardage
  - Handicap index

### Internal Storage

Must persist:
- Course snapshot per round (immutable)
- User-entered round data

---

## 6. Data Model (Core Entities)

### Course
- id
- provider_id
- club_name
- course_name

### Tee
- id
- course_id
- tee_name
- course_rating
- slope_rating
- total_yards
- total_meters

### Hole
- id
- tee_id
- hole_number
- par
- yardage
- handicap

### Round
- id
- course_id
- tee_id
- player_name
- date

### RoundHole
- id
- round_id
- hole_number

Fields:
- score
- putts
- fir
- gir
- penalties
- miss_direction
- up_and_down
- sand_save
- entered_sz_regulation
- down_in_3
- miss_short_putt
- made_long_putt
- drive_quality
- approach_quality
- notes

---

## 7. Functional Requirements

### FR-1: Course Search
- User can search courses via API
- Results include club + course name

### FR-2: Tee Selection
- User selects from available tee boxes

### FR-3: Data Normalization
- API response must be transformed into internal schema

### FR-4: Snapshotting
- Course/tee data must be saved at round creation
- Future API changes must not affect past rounds

### FR-5: Score Entry UI
- Must support fast mobile entry (on-course use)
- Minimal friction input (toggles, taps)

### FR-6: Scorecard Rendering
- Must render as HTML/CSS layout
- Must support print styling

### FR-7: PDF Export
- System generates PDF from rendered scorecard

---

## 8. Non-Functional Requirements

### Performance
- Course search < 1s
- Scorecard render < 200ms

### Usability
- Mobile-first input design
- Large tap targets
- Minimal typing

### Reliability
- Must work offline after round creation (optional future feature)

---

## 9. Technical Approach

### Frontend
- React / Next.js
- Component-based scorecard

### Backend
- API routes (Next.js or FastAPI)
- Postgres (via Supabase or similar)

### PDF Generation
- Playwright or Puppeteer
- Render HTML → export PDF

---

## 10. Constraints & Design Decisions

- Do NOT rely on external API at render time
- Always use locally stored course snapshot
- Do NOT use plotting libraries for scorecard layout
- Use HTML/CSS for layout, not canvas/SVG-first

---

## 11. Future Enhancements (Out of Scope for v1)

- Strokes gained calculations
- Shot-level tracking
- GPS / hole mapping
- Club tracking
- AI-based round insights
- Multi-player rounds

---

## 12. Definition of Done (v1)

A user can:

- Search and select a golf course
- Choose a tee
- Start a round
- Enter hole-by-hole data
- View a structured scorecard
- Export a clean, printable PDF with:
  - Course-specific front side
  - Metrics-based back side