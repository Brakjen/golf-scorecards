# Golf Scorecards Implementation Plan

## Goal

Build a modular web app that lets a user:

- choose a predefined golf course and tee
- prefill player name, date, and course details
- generate a printable scorecard for keeping score on the course
- include per-hole metrics columns on the printed scorecard
- download the scorecard as a PDF

## Product Boundaries

This plan reflects the current product decision:

- no external golf course API
- no digital round storage
- no persistence of played rounds
- the printed scorecard is the primary output
- score and metrics are recorded on paper during play

That means the application is a stateless scorecard generator, not a round-tracking database.

## Current Repo Baseline

The repository already contains:

- a FastAPI app entrypoint in `src/golf_scorecards/main.py`
- local course data loader code in `src/golf_scorecards/course_data.py`
- packaged course catalog data in `src/golf_scorecards/data/courses/no/manual_courses.json`
- basic tests for app health and course data loading

This is enough to build the first vertical slice without changing the core stack.

## Recommended Stack

- FastAPI for application and routing
- Jinja2 templates for server-rendered HTML
- local JSON package data for the course catalog
- CSS print styles for printable scorecards
- Playwright for PDF generation from HTML

## Architecture Principles

- keep course catalog access separate from rendering
- validate form input before building scorecards
- build one scorecard view model used by both browser preview and PDF generation
- keep PDF generation isolated from routing and catalog lookup
- keep modules small and explicit rather than hiding logic in templates

## Proposed Module Structure

### Application bootstrap

- `src/golf_scorecards/main.py`
  Creates the FastAPI app and wires routers, templates, and startup config.

- `src/golf_scorecards/config.py`
  Holds environment-backed app settings such as debug mode and PDF options.

### Catalog layer

- `src/golf_scorecards/catalog/models.py`
  Typed models for course catalog data.
  Suggested models:
  - `Hole`
  - `Tee`
  - `Course`
  - `CourseCatalog`

- `src/golf_scorecards/catalog/repository.py`
  Reads packaged JSON data and returns typed catalog objects.

- `src/golf_scorecards/catalog/service.py`
  Provides lookup methods such as:
  - list available courses
  - get course by slug
  - get tee by name for a course

### Scorecard input layer

- `src/golf_scorecards/scorecards/forms.py`
  Defines validated input schemas for:
  - player name
  - round date
  - course slug
  - tee name

- `src/golf_scorecards/scorecards/validators.py`
  Holds any validation or normalization helpers that do not belong in routes.

### Scorecard builder layer

- `src/golf_scorecards/scorecards/models.py`
  Typed view models for printable scorecards.
  Suggested models:
  - `ScorecardMeta`
  - `ScorecardHoleRow`
  - `ScorecardFrontSide`
  - `ScorecardBackSide`
  - `PrintableScorecard`

- `src/golf_scorecards/scorecards/builder.py`
  Builds a printable scorecard from course data plus user form input.

Responsibilities:

- prefill player name
- prefill date
- prefill club name
- prefill course name
- prefill tee name
- map holes into printable rows
- expose blank fields for handwritten score and metric entry
- calculate static front-9, back-9, and total par and distance summaries

### PDF layer

- `src/golf_scorecards/pdf/service.py`
  Renders printable HTML to PDF.

- `src/golf_scorecards/pdf/templates.py`
  Optional helper layer if PDF-specific rendering settings need to stay separate.

### Web layer

- `src/golf_scorecards/web/routes.py`
  Main page and scorecard workflow routes.

- `src/golf_scorecards/web/dependencies.py`
  Shared dependency wiring for catalog services and template environment.

- `src/golf_scorecards/templates/base.html`
  Shared layout.

- `src/golf_scorecards/templates/home.html`
  Course and tee selection form.

- `src/golf_scorecards/templates/scorecard_preview.html`
  Browser preview of the scorecard.

- `src/golf_scorecards/templates/scorecard_print.html`
  Print-optimized HTML used for browser print and PDF generation.

- `src/golf_scorecards/static/styles/app.css`
  Screen styles.

- `src/golf_scorecards/static/styles/print.css`
  Print layout styles.

## Data Model Direction

### Catalog data

The manual course JSON should remain the source of truth for:

- club name
- course name
- course slug
- tee definitions
- hole number
- par
- distance
- handicap

### Printable scorecard model

The printable scorecard should be assembled into a dedicated view model rather than passing raw catalog JSON into templates.

Suggested structure:

```python
class ScorecardMeta:
    player_name: str
    round_date: date
    club_name: str
    course_name: str
    tee_name: str


class ScorecardHoleRow:
    hole_number: int
    handicap: int
    par: int
    distance: int


class PrintableScorecard:
    meta: ScorecardMeta
    front_nine: list[ScorecardHoleRow]
    back_nine: list[ScorecardHoleRow]
    front_par_total: int
    back_par_total: int
    total_par: int
    front_distance_total: int
    back_distance_total: int
    total_distance: int
```

The printed template can then layer empty handwritten fields for:

- score
- putts
- FIR
- GIR
- penalties
- miss direction
- up and down
- sand save
- scoring zone entry
- down in 3
- missed short putt
- made long putt
- notes

## Route Plan

### `GET /`

Purpose:
Show the initial form.

Inputs:

- none

Outputs:

- list of available courses
- tee choices per selected course or dynamic follow-up after selection

### `POST /scorecards/preview`

Purpose:
Validate the submitted form and render the scorecard preview.

Inputs:

- player name
- round date
- course slug
- tee name

Outputs:

- rendered HTML preview using the printable scorecard model

### `POST /scorecards/pdf`

Purpose:
Generate and return a PDF for download.

Inputs:

- same validated form payload as preview

Outputs:

- PDF response with a stable file name such as `scorecard-sola-golfklubb-forus-63.pdf`

## UI Flow

### Step 1: Selection form

The user chooses:

- course
- tee
- player name
- date

### Step 2: Preview page

The app renders a preview with:

- player name filled in
- date filled in
- club name filled in
- course name filled in
- tee name filled in
- front-side scoring table
- back-side metrics table

### Step 3: Download or print

The user can:

- download the PDF
- print directly from the browser preview if desired

## Scorecard Layout Plan

### Front side

Header:

- player name
- date
- club name
- course name
- tee name

Main table columns:

- hole
- handicap
- par
- distance
- score
- putts
- FIR
- GIR
- penalties

Summary rows:

- front 9 totals
- back 9 totals
- overall totals

### Back side

Section 1: Scoring zone

- hole
- entered scoring zone in regulation
- down in 3
- birdie chance
- conversion success

Section 2: Tee to green

- hole
- FIR
- GIR
- miss direction
- penalty strokes
- recovery success

Section 3: Short game and putting

- hole
- up and down
- sand save
- putts
- miss under 4 ft
- made over 4 ft

Section 4: Notes or summary area

- a blank space for handwritten notes or round summary

Because the app is stateless, these fields should be visually optimized for handwriting rather than digital data entry.

## Milestones

### Milestone 1: Catalog and typed models

Deliverables:

- typed catalog models
- repository for loading local JSON
- catalog service for course and tee lookup
- tests for catalog parsing and lookup

Done when:

- the app can list all available courses
- a course can be retrieved by slug
- a tee can be retrieved for a selected course

### Milestone 2: Form and preview workflow

Deliverables:

- home form route
- validated form schema
- scorecard builder
- preview template

Done when:

- a user can choose course and tee
- a user can enter player name and date
- the app renders a browser preview with all metadata prefilled

### Milestone 3: Printable layout

Deliverables:

- print template
- print CSS
- A4-friendly layout for front and back sections

Done when:

- preview prints cleanly from the browser
- the layout is legible on A4 paper

### Milestone 4: PDF generation

Deliverables:

- PDF service
- download route
- file naming strategy

Done when:

- a user can download a PDF for any supported course and tee
- the PDF matches the print layout closely

### Milestone 5: Hardening

Deliverables:

- test coverage for builder and routes
- input validation edge-case handling
- error pages for missing course or tee
- README usage updates

Done when:

- invalid form submissions fail clearly
- unsupported course and tee combinations are handled safely
- the app can be run and understood without reading the source

## Testing Plan

### Unit tests

- catalog JSON parsing
- course lookup by slug
- tee lookup within course
- scorecard builder summaries for front 9, back 9, and totals
- file naming logic for generated PDFs

### Integration tests

- `GET /` returns the form page
- `POST /scorecards/preview` returns rendered preview HTML
- invalid course slug returns validation error
- invalid tee for course returns validation error
- `POST /scorecards/pdf` returns a PDF response

### Manual checks

- verify every configured course can render preview
- verify mobile form usability
- verify printed layout on A4 paper
- verify Norwegian course names render correctly

## Dependency Plan

Recommended additions:

- `jinja2` for HTML templates
- `python-multipart` if form posts need multipart handling
- `playwright` for PDF rendering

Possible optional additions:

- `pydantic` models for catalog and scorecard view models if not already used directly
- `beautifulsoup4` only if HTML assertions become cumbersome in tests

## Risks and Mitigations

### PDF rendering complexity

Risk:
Browser preview and generated PDF diverge.

Mitigation:
Generate the PDF from the same print template used for browser print.

### Template complexity

Risk:
Too much logic ends up in Jinja templates.

Mitigation:
Keep all transformations in builder and view-model code.

### Data quality issues in manual course catalog

Risk:
Missing or inconsistent tee and hole fields break rendering.

Mitigation:
Add typed parsing and validation tests for catalog integrity.

## Suggested Delivery Order

1. Refactor the catalog loader into typed models and lookup services.
2. Add the form schema and web routes.
3. Build the scorecard view model and preview page.
4. Add print-specific styling and front/back scorecard layout.
5. Add PDF generation and download.
6. Harden with tests and documentation.

## First Slice Recommendation

The first implementation slice should stop after browser preview.

Why:

- it proves the data model
- it proves course and tee selection
- it proves the scorecard layout direction
- it keeps PDF complexity out of the initial feedback loop

After that, add PDF generation as the second vertical slice.