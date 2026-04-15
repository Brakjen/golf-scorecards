/* Golf Scorecards — client-side scorecard builder */
"use strict";

/* ── Course catalog helpers ── */

function listCourseOptions() {
  return COURSE_CATALOG.map((c) => ({
    course_slug: c.course_slug,
    club_name: c.club_name,
    course_name: c.course_name,
    display_name: `${c.club_name} - ${c.course_name}`,
    tees: c.tees.map((t) => t.tee_name),
  }));
}

function getCourse(slug) {
  const course = COURSE_CATALOG.find((c) => c.course_slug === slug);
  if (!course) throw new Error(`Unknown course slug: ${slug}`);
  return course;
}

function getTee(slug, teeName) {
  const course = getCourse(slug);
  const tee = course.tees.find((t) => t.tee_name === teeName);
  if (!tee) throw new Error(`Unknown tee '${teeName}' for course '${slug}'`);
  return tee;
}

/* ── Handicap computation (WHS formula) ── */

function getTeeRating(slug, teeName, gender) {
  const tee = getTee(slug, teeName);
  return (tee.ratings || []).find((r) => r.gender === gender) || null;
}

function listProfileOptions(slug, teeName) {
  const tee = getTee(slug, teeName);
  return (tee.ratings || []).map((r) => ({ key: r.gender, label: capitalise(r.gender) }));
}

function hasRatings(slug, teeName) {
  const tee = getTee(slug, teeName);
  return (tee.ratings || []).length > 0;
}

function computePlayingHandicap(slug, teeName, profileKey, handicapIndex) {
  const rating = getTeeRating(slug, teeName, profileKey);
  if (!rating) throw new Error(`No slope data for ${slug}/${teeName}/${profileKey}`);
  const tee = getTee(slug, teeName);
  const par = tee.par_total || tee.holes.slice(0, 18).reduce((s, h) => s + h.par, 0);
  const ph = Math.round(handicapIndex * (rating.slope_rating / 113) + (rating.course_rating - par));
  return { tee_rating: rating, handicap_index: handicapIndex, playing_handicap: ph };
}

/* ── Scorecard builder ── */

function buildScorecard(formData) {
  const course = getCourse(formData.course_slug);
  const tee = formData.tee_name ? getTee(formData.course_slug, formData.tee_name) : null;
  const structureTee = tee || (course.tees.length ? course.tees[0] : null);
  const holes = structureTee ? structureTee.holes.slice(0, 18) : [];
  const coursePar = tee
    ? (tee.par_total || holes.reduce((s, h) => s + h.par, 0))
    : holes.reduce((s, h) => s + h.par, 0);
  const showDistance = tee !== null;

  const isStableford = formData.scoring_mode === "stableford";
  const showAdjustedPar = formData.scoring_mode === "stroke" && formData.target_score != null;
  const showStablefordColumns = isStableford;

  /* Handicap */
  let handicap = null;
  if (formData.handicap_index != null && formData.tee_name) {
    const profileKey = formData.handicap_profile || "men";
    if (hasRatings(formData.course_slug, formData.tee_name)) {
      handicap = computePlayingHandicap(
        formData.course_slug, formData.tee_name, profileKey, formData.handicap_index
      );
    }
  }

  const adjustedPars = buildAdjustedParMap(holes, coursePar, showAdjustedPar ? formData.target_score : null);
  const playingStrokes = handicap ? handicap.playing_handicap : (isStableford ? 0 : null);
  const strokesReceived = buildStrokesReceivedMap(holes, playingStrokes);
  const twoPointTargets = buildTwoPointTargetMap(holes, strokesReceived, isStableford);

  const allHoles = holes.map((h) => ({
    hole_number: h.hole_number,
    handicap: h.handicap,
    par: h.par,
    adjusted_par: adjustedPars[h.hole_number] ?? null,
    distance: showDistance ? h.distance : null,
    strokes_received: strokesReceived[h.hole_number] ?? null,
    two_points_score: twoPointTargets[h.hole_number] ?? null,
  }));

  const frontNine = allHoles.slice(0, 9);
  const backNine = allHoles.slice(9, 18);
  const frontTotals = buildTotals(frontNine);
  const backTotals = buildTotals(backNine);

  const overallTotals = {
    par_total: frontTotals.par_total + backTotals.par_total,
    distance_total: (frontTotals.distance_total != null && backTotals.distance_total != null)
      ? frontTotals.distance_total + backTotals.distance_total : null,
    adjusted_par_total: (showAdjustedPar && frontTotals.adjusted_par_total != null && backTotals.adjusted_par_total != null)
      ? frontTotals.adjusted_par_total + backTotals.adjusted_par_total : null,
  };

  const mainColumns = buildMainColumns(formData.scoring_mode, showAdjustedPar, showStablefordColumns);

  const scoringZoneRuleLabel = isStableford
    ? "Scoring-zone regulation uses the 2-point target minus 2."
    : showAdjustedPar
      ? "Scoring-zone regulation uses adjusted par minus 2."
      : "Scoring-zone regulation uses par minus 2.";

  return {
    meta: {
      player_name: formData.player_name,
      round_date: formData.round_date,
      club_name: course.club_name,
      course_name: course.course_name,
      course_slug: course.course_slug,
      tee_name: tee ? tee.tee_name : null,
      scoring_mode: formatScoringMode(formData.scoring_mode),
      target_score: formData.target_score,
      handicap_index_label: formatHandicapIndex(formData.handicap_index),
      handicap_index_raw: formData.handicap_index != null ? String(formData.handicap_index) : null,
      handicap_profile_label: handicap ? capitalise(handicap.tee_rating.gender) : null,
      handicap_profile_raw: formData.handicap_profile,
      course_rating: handicap ? handicap.tee_rating.course_rating : null,
      slope_rating: handicap ? handicap.tee_rating.slope_rating : null,
      playing_strokes_total: handicap ? handicap.playing_handicap : null,
    },
    all_holes: allHoles,
    front_nine: frontNine,
    back_nine: backNine,
    front_totals: frontTotals,
    back_totals: backTotals,
    overall_totals: overallTotals,
    main_columns: mainColumns,
    show_adjusted_par: showAdjustedPar,
    show_stableford_columns: showStablefordColumns,
    summary_blank_colspan: buildSummaryBlankColspan(formData.scoring_mode, showAdjustedPar),
    scoring_zone_rule_label: scoringZoneRuleLabel,
  };
}

/* ── Builder internals ── */

function buildMainColumns(scoringMode, showAdjustedPar, showStablefordColumns) {
  const cols = ["Hole", "HCP", "Par"];
  if (showAdjustedPar) cols.push("Adjusted Par");
  cols.push("Distance");
  if (showStablefordColumns && scoringMode === "stableford") {
    cols.push("Strokes", "2 Pts @", "Net", "Pts");
  }
  cols.push("Score", "Putts", "Pen", "FIR", "FW Miss", "Green Miss", "Up and Down", "SZ in Reg", "Down in 3", "Putt <=4 ft");
  return cols;
}

function buildTotals(holes) {
  const hasAdj = holes.some((h) => h.adjusted_par != null);
  const hasDist = holes.some((h) => h.distance != null);
  return {
    par_total: holes.reduce((s, h) => s + h.par, 0),
    distance_total: hasDist ? holes.reduce((s, h) => s + (h.distance || 0), 0) : null,
    adjusted_par_total: hasAdj ? holes.reduce((s, h) => s + (h.adjusted_par || 0), 0) : null,
  };
}

function buildAdjustedParMap(holes, coursePar, targetScore) {
  if (targetScore == null) return {};
  const diff = targetScore - coursePar;
  const sign = diff >= 0 ? 1 : -1;
  const absBase = Math.floor(Math.abs(diff) / holes.length);
  const remainder = Math.abs(diff) % holes.length;
  const map = {};
  holes.forEach((h) => { map[h.hole_number] = h.par + sign * absBase; });
  const sorted = [...holes].sort((a, b) => sign < 0 ? b.handicap - a.handicap : a.handicap - b.handicap);
  sorted.slice(0, remainder).forEach((h) => { map[h.hole_number] += sign; });
  return map;
}

function buildStrokesReceivedMap(holes, playingStrokes) {
  if (playingStrokes == null) return {};
  const sign = playingStrokes >= 0 ? 1 : -1;
  const absBase = Math.floor(Math.abs(playingStrokes) / holes.length);
  const remainder = Math.abs(playingStrokes) % holes.length;
  const map = {};
  holes.forEach((h) => { map[h.hole_number] = sign * absBase; });
  [...holes].sort((a, b) => a.handicap - b.handicap).slice(0, remainder).forEach((h) => { map[h.hole_number] += sign; });
  return map;
}

function buildTwoPointTargetMap(holes, strokesReceived, isStableford) {
  if (!isStableford) return {};
  const map = {};
  holes.forEach((h) => { map[h.hole_number] = h.par + (strokesReceived[h.hole_number] || 0); });
  return map;
}

function buildSummaryBlankColspan(scoringMode, showAdjustedPar) {
  const cols = buildMainColumns(scoringMode, showAdjustedPar, scoringMode === "stableford");
  const used = 4 + (showAdjustedPar ? 1 : 0);
  return cols.length - used;
}

/* ── Formatters ── */

function formatScoringMode(mode) {
  return mode === "stableford" ? "Stableford" : "Stroke play";
}

function formatHandicapIndex(hi) {
  if (hi == null) return null;
  if (hi < 0) return `+${Math.abs(hi).toFixed(1)}`;
  return hi.toFixed(1);
}

function capitalise(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : "";
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

/* ── Render: preview scorecard into the page ── */

function renderPreview(sc) {
  const playerDisplay = sc.meta.player_name ? escapeHtml(sc.meta.player_name) : '';
  let metaHtml = `
    <div><p class="meta-label">Player</p><p>${playerDisplay}</p></div>
    <div><p class="meta-label">Date</p><p></p></div>
    <div><p class="meta-label">Club</p><p>${escapeHtml(sc.meta.club_name)}</p></div>
    <div><p class="meta-label">Course</p><p>${escapeHtml(sc.meta.course_name)}</p></div>
    <div><p class="meta-label">Tee</p><p>${escapeHtml(sc.meta.tee_name || '')}</p></div>
    <div><p class="meta-label">Mode</p><p>${escapeHtml(sc.meta.scoring_mode)}</p></div>
    <div><p class="meta-label">Total par</p><p>${sc.overall_totals.par_total}</p></div>
    <div><p class="meta-label">Total distance</p><p>${sc.overall_totals.distance_total != null ? sc.overall_totals.distance_total : ''}</p></div>`;

  if (sc.meta.target_score != null) {
    metaHtml += `<div><p class="meta-label">Target</p><p>${sc.meta.target_score}</p></div>`;
  }
  if (sc.meta.handicap_index_label) {
    metaHtml += `
      <div><p class="meta-label">Handicap</p><p>${escapeHtml(sc.meta.handicap_index_label)}</p></div>
      <div><p class="meta-label">Profile</p><p>${escapeHtml(sc.meta.handicap_profile_label)}</p></div>
      <div><p class="meta-label">CR / Slope</p><p>${sc.meta.course_rating} / ${sc.meta.slope_rating}</p></div>
      <div><p class="meta-label">Playing strokes</p><p>${sc.meta.playing_strokes_total}</p></div>`;
  }

  /* Table header */
  const thCells = sc.main_columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("");

  /* Table body */
  let stablefordNote = "";
  if (sc.show_stableford_columns) {
    stablefordNote = `<p class="panel-note">The 2 Pts @ column shows the gross score that secures 2 Stableford points on each hole.</p>`;
  }

  const bodyRows = sc.all_holes.map((h) => {
    const trClass = h.hole_number === 10 ? ' class="turn-row"' : "";
    let cells = `<td>${h.hole_number}</td><td>${h.handicap}</td><td>${h.par}</td>`;
    if (sc.show_adjusted_par) cells += `<td>${h.adjusted_par}</td>`;
    cells += `<td>${h.distance != null ? h.distance : ''}</td>`;
    if (sc.show_stableford_columns) {
      cells += `<td>${h.strokes_received}</td><td>${h.two_points_score}</td>`;
      cells += `<td class="blank-cell"></td><td class="blank-cell"></td>`;
    }
    cells += `<td class="blank-cell"></td><td class="blank-cell"></td><td class="blank-cell"></td>`;
    cells += `<td class="blank-cell blank-cell--check"></td>`;
    cells += `<td class="blank-cell blank-cell--note"></td>`;
    cells += `<td class="blank-cell blank-cell--note"></td>`;
    cells += `<td class="blank-cell blank-cell--check"></td>`;
    cells += `<td class="blank-cell blank-cell--check"></td>`;
    cells += `<td class="blank-cell blank-cell--check"></td>`;
    cells += `<td class="blank-cell blank-cell--check"></td>`;
    return `<tr${trClass}>${cells}</tr>`;
  }).join("\n");

  /* Footer */
  function footerRow(label, totals) {
    let cells = `<th colspan="2">${label}</th><th>${totals.par_total}</th>`;
    if (sc.show_adjusted_par) cells += `<th>${totals.adjusted_par_total}</th>`;
    cells += `<th>${totals.distance_total != null ? totals.distance_total : ''}</th>`;
    cells += `<th colspan="${sc.summary_blank_colspan}"></th>`;
    return `<tr>${cells}</tr>`;
  }

  const noteL = sc.show_adjusted_par ? "Adjusted Par" : (sc.show_stableford_columns ? "2-point target" : "Par");

  const html = `
    <section class="preview-toolbar">
      <a href="#" onclick="showForm(); return false;">← Back</a>
      <div class="toolbar-actions">
        <button class="btn-export" onclick="exportPdf()">Download PDF</button>
      </div>
    </section>
    <section class="scorecard-sheet">
      <header class="scorecard-header">${metaHtml}</header>
      <section class="table-layout">
        <article class="card-panel card-panel--full">
          <div class="panel-heading">
            <div>
              <h2>Score and per-hole metrics</h2>
              <p class="panel-note">Front and back are kept in one grid. The shaded divider marks the turn after hole 9.</p>
            </div>
            <div>
              <p class="panel-note">Use arrows for fairway miss and one of short, long, left, or right for green miss.</p>
              <p class="panel-note">${escapeHtml(sc.scoring_zone_rule_label)}</p>
            </div>
          </div>
          ${stablefordNote}
          <table class="scorecard-table">
            <thead><tr>${thCells}</tr></thead>
            <tbody>${bodyRows}</tbody>
            <tfoot>
              ${footerRow("Front", sc.front_totals)}
              ${footerRow("Back", sc.back_totals)}
              ${footerRow("Total", sc.overall_totals)}
            </tfoot>
          </table>
        </article>
      </section>
    </section>`;

  document.querySelector("#preview-area main").innerHTML = html;
  document.getElementById("form-area").style.display = "none";
  document.getElementById("preview-area").style.display = "block";
}

/* ── Render: print-optimised HTML for PDF ── */

function renderPrintHtml(sc) {
  const e = escapeHtml;

  let headerMeta = `
    <td class="meta-cell-name"><div class="meta-label">Player</div><div class="meta-value">${sc.meta.player_name ? e(sc.meta.player_name) : '&nbsp;'}</div></td>
    <td class="meta-cell"><div class="meta-label">Date</div><div class="meta-value">&nbsp;</div></td>
    <td class="meta-cell"><div class="meta-label">Par</div><div class="meta-value">${sc.overall_totals.par_total}</div></td>
    <td class="meta-cell"><div class="meta-label">Distance</div><div class="meta-value">${sc.overall_totals.distance_total != null ? sc.overall_totals.distance_total + 'm' : '&nbsp;'}</div></td>`;

  if (sc.meta.target_score != null) {
    headerMeta += `<td class="meta-cell"><div class="meta-label">Target</div><div class="meta-value">${sc.meta.target_score}</div></td>`;
  }
  if (sc.meta.handicap_index_label) {
    headerMeta += `
      <td class="meta-cell"><div class="meta-label">HCP</div><div class="meta-value">${e(sc.meta.handicap_index_label)}</div></td>
      <td class="meta-cell"><div class="meta-label">CR/Slope</div><div class="meta-value">${sc.meta.course_rating}/${sc.meta.slope_rating}</div></td>
      <td class="meta-cell"><div class="meta-label">Strokes</div><div class="meta-value">${sc.meta.playing_strokes_total}</div></td>`;
  }

  /* Colgroup */
  let colgroup = `<col class="col-hole"><col class="col-hcp"><col class="col-par">`;
  if (sc.show_adjusted_par) colgroup += `<col class="col-adj">`;
  colgroup += `<col class="col-dist">`;
  if (sc.show_stableford_columns) colgroup += `<col class="col-strk"><col class="col-2pt">`;

  /* Table head */
  const ths = sc.main_columns.map((c) => `<th>${e(c)}</th>`).join("");

  /* Table body */
  const rows = sc.all_holes.map((h) => {
    const cls = h.hole_number === 10 ? ' class="turn"' : "";
    let cells = `<td>${h.hole_number}</td><td>${h.handicap}</td><td>${h.par}</td>`;
    if (sc.show_adjusted_par) cells += `<td>${h.adjusted_par}</td>`;
    cells += `<td>${h.distance != null ? h.distance : ''}</td>`;
    if (sc.show_stableford_columns) {
      cells += `<td>${h.strokes_received}</td><td>${h.two_points_score}</td>`;
      cells += `<td class="wr"></td><td class="wr"></td>`;
    }
    cells += `<td class="wr"></td><td class="wr"></td><td class="wr"></td>`;
    cells += `<td class="wr-sm"></td><td class="wr-sm"></td><td class="wr-sm"></td>`;
    cells += `<td class="wr-sm"></td><td class="wr-sm"></td><td class="wr-sm"></td><td class="wr-sm"></td>`;
    return `<tr${cls}>${cells}</tr>`;
  }).join("\n");

  /* Footer */
  function frow(label, totals) {
    let c = `<th colspan="2">${label}</th><th>${totals.par_total}</th>`;
    if (sc.show_adjusted_par) c += `<th>${totals.adjusted_par_total}</th>`;
    c += `<th>${totals.distance_total != null ? totals.distance_total : ''}</th><th colspan="${sc.summary_blank_colspan}"></th>`;
    return `<tr>${c}</tr>`;
  }

  const legendParts = ["Hole", "HCP", "Par"];
  if (sc.show_adjusted_par) legendParts.push("Adj");
  legendParts.push("Dist");
  if (sc.show_stableford_columns) legendParts.push("Strokes", "2pt@", "Net", "Pts");
  legendParts.push("Score", "Putts", "Pen", "FIR", "FW Miss", "Grn Miss", "Up&Down", "SZ Reg", "Dn3", "Putt≤4ft");

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
@page{size:216mm 140mm;margin:4mm 5mm}
@media print{@page{margin:4mm 5mm}}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Helvetica Neue",Helvetica,Arial,sans-serif;font-size:5.5pt;line-height:1.2;color:#111;background:#fff;padding:4mm 5mm}
.sc-header{width:100%;border-bottom:0.4mm solid #1a5c2e;margin-bottom:1mm;padding-bottom:1mm}
.sc-header-table{width:100%;border-collapse:collapse}
.sc-header-table td{border:none;vertical-align:bottom;padding:0}
.sc-header-table .title-cell{text-align:left;width:40%}
.sc-header-table .title-cell h1{font-size:8pt;font-weight:800;color:#1a5c2e;margin:0;white-space:normal;word-wrap:break-word}
.sc-header-table .title-cell .subtitle{font-size:5.5pt;color:#555}
.sc-header-table .meta-cell{text-align:right;padding-left:2mm;white-space:nowrap}
.sc-header-table .meta-cell-name{text-align:right;padding-left:2mm;white-space:normal;word-wrap:break-word;max-width:30mm}
.meta-label{font-size:4.5pt;text-transform:uppercase;letter-spacing:0.04em;color:#888}
.meta-value{font-weight:700;font-size:5.5pt}
table{width:100%;border-collapse:collapse;table-layout:fixed}
th,td{border:0.2mm solid #bbb;text-align:center;padding:0.5mm 0.3mm;font-size:5pt;overflow:hidden}
thead th{background:#1a5c2e;color:#fff;font-size:4.5pt;font-weight:700;text-transform:uppercase;letter-spacing:0.03em;padding:0.6mm 0.3mm}
col.col-hole{width:5.5%}col.col-hcp{width:5%}col.col-par{width:5%}col.col-dist{width:6.5%}col.col-adj{width:5.5%}col.col-strk{width:5%}col.col-2pt{width:5.5%}
tbody td{height:4.5mm;font-weight:600}
.wr{background:#f7f9f7}.wr-sm{background:#f7f9f7;font-size:5pt}
.turn td{border-top:0.6mm solid #1a5c2e;background:rgba(26,92,46,0.06)}
tfoot th{background:#e8f0e8;color:#1a5c2e;font-weight:700;font-size:5pt;padding:0.5mm 0.3mm}
.sc-notes{margin-top:1mm;font-size:4.5pt;color:#666}
.sc-notes table{width:100%;border-collapse:collapse}
.sc-notes td{border:none;vertical-align:top;padding:0 1mm;text-align:left}
.sc-notes .note-label{font-weight:700;text-transform:uppercase;letter-spacing:0.04em;font-size:4pt;color:#888}
.sc-legend{margin-top:0.5mm;font-size:4pt;color:#999;text-align:center}
</style>
</head>
<body>
<div class="sc-header">
  <table class="sc-header-table"><tr>
    <td class="title-cell">
      <h1>${e(sc.meta.club_name)} — ${e(sc.meta.course_name)}</h1>
      <span class="subtitle">${sc.meta.tee_name ? `Tee ${e(sc.meta.tee_name)} · ` : ''}${e(sc.meta.scoring_mode)}</span>
    </td>
    ${headerMeta}
  </tr></table>
</div>
<table>
  <colgroup>${colgroup}</colgroup>
  <thead><tr>${ths}</tr></thead>
  <tbody>${rows}</tbody>
  <tfoot>
    ${frow("Front", sc.front_totals)}
    ${frow("Back", sc.back_totals)}
    ${frow("Total", sc.overall_totals)}
  </tfoot>
</table>
<div class="sc-notes">
  <table><tr>
    <td><span class="note-label">FW miss:</span> ← or → arrows</td>
    <td><span class="note-label">Green miss:</span> S / L / ← / →</td>
    <td><span class="note-label">${e(sc.scoring_zone_rule_label)}</span></td>
  </tr></table>
</div>
<div class="sc-legend">${e(legendParts.join(" · "))}</div>
</body>
</html>`;
}

/* ── PDF export ── */

function renderPrintBody(sc) {
  /* Returns just the inner body HTML + inline styles for the PDF container.
     Reuses the same content as renderPrintHtml but without the <html> wrapper. */
  const html = renderPrintHtml(sc);
  const styleMatch = html.match(/<style>([\s\S]*?)<\/style>/);
  const bodyMatch = html.match(/<body>([\s\S]*?)<\/body>/);
  if (!styleMatch || !bodyMatch) return null;

  /* Scope every CSS selector under #pdf-render to avoid leaking styles */
  const raw = styleMatch[1]
    .replace(/@page\{[^}]*\}/g, "")
    .replace(/@media[^{]*\{@page\{[^}]*\}\s*\}/g, "")
    .replace(/body\s*\{[^}]*\}/g, "");
  let scoped = "";
  const re = /([^{}]+)\{([^}]*)\}/g;
  let m;
  while ((m = re.exec(raw)) !== null) {
    const selectors = m[1].trim();
    if (!selectors || selectors.startsWith("@")) continue;
    const prefixed = selectors.split(",").map((s) => "#pdf-render " + s.trim()).join(",");
    scoped += prefixed + "{" + m[2] + "}\n";
  }

  return { css: scoped, body: bodyMatch[1] };
}

function exportPdf() {
  if (!window._currentScorecard) return;
  const sc = window._currentScorecard;
  const parts = renderPrintBody(sc);
  if (!parts) return;

  const teePart = sc.meta.tee_name ? `_${sc.meta.tee_name}` : "";
  const filename = `scorecard_${sc.meta.course_name}${teePart}.pdf`.replace(/ /g, "_");

  /* Overlay hides the render container from the user */
  const overlay = document.createElement("div");
  overlay.style.cssText = "position:fixed;inset:0;z-index:100001;background:#fff;display:flex;align-items:center;justify-content:center;font-family:system-ui;color:#333;font-size:1rem;";
  overlay.textContent = "Generating PDF…";
  document.body.appendChild(overlay);

  /* Container must be in-viewport for html2canvas to capture it */
  const container = document.createElement("div");
  container.id = "pdf-render";
  container.style.cssText =
    "position:fixed;top:0;left:0;z-index:100000;width:216mm;overflow:hidden;" +
    "font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-size:5.5pt;" +
    "line-height:1.2;color:#111;background:#fff;padding:4mm 5mm;box-sizing:border-box;";
  container.innerHTML = `<style>${parts.css}</style>${parts.body}`;
  document.body.appendChild(container);

  function cleanup() {
    if (container.parentNode) container.parentNode.removeChild(container);
    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
  }

  /* Wait for layout, then capture → blob → download link */
  requestAnimationFrame(() => {
    html2pdf()
      .set({
        margin: 0,
        image: { type: "jpeg", quality: 0.98 },
        html2canvas: { scale: 3, useCORS: true, scrollY: 0 },
        jsPDF: { unit: "mm", format: [216, 140], orientation: "landscape" },
      })
      .from(container)
      .outputPdf("blob")
      .then((blob) => {
        cleanup();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      })
      .catch((err) => {
        cleanup();
        alert("PDF generation failed: " + err.message);
      });
  });
}

/* ── Form logic ── */

function showForm() {
  document.getElementById("form-area").style.display = "block";
  document.getElementById("preview-area").style.display = "none";
}

function parseForm() {
  const form = document.getElementById("scorecard-form");
  const scoringMode = form.elements["scoring_mode"].value;
  const targetStr = form.elements["target_score"].value.trim();
  const hiStr = form.elements["handicap_index"].value.trim();
  let handicapIndex = null;
  if (hiStr !== "") {
    const cleaned = hiStr.replace(",", ".");
    handicapIndex = cleaned.startsWith("+") ? -parseFloat(cleaned.slice(1)) : parseFloat(cleaned);
    if (isNaN(handicapIndex)) handicapIndex = null;
  }
  const checkedTee = document.querySelector('input[name="tee_name"]:checked');
  const checkedProfile = document.querySelector('input[name="handicap_profile"]:checked');
  return {
    player_name: form.elements["player_name"].value.trim() || null,
    round_date: null,
    course_slug: form.elements["course_slug"].value,
    tee_name: checkedTee ? checkedTee.value : null,
    scoring_mode: scoringMode,
    target_score: (scoringMode !== "stableford" && targetStr !== "") ? parseInt(targetStr, 10) : null,
    handicap_index: handicapIndex,
    handicap_profile: "men",
  };
}

function handleSubmit(e) {
  e.preventDefault();
  try {
    const formData = parseForm();
    const sc = buildScorecard(formData);
    window._currentScorecard = sc;
    renderPreview(sc);
  } catch (err) {
    alert("Error: " + err.message);
  }
}

/* ── Init ── */

document.addEventListener("DOMContentLoaded", () => {
  const courseOptions = listCourseOptions();
  const courseSelect = document.getElementById("course-select");
  const teeSegmented = document.getElementById("tee-segmented");
  const scoringModeSegmented = document.getElementById("scoring-mode-segmented");
  const stablefordRadio = document.getElementById("mode-stableford");
  const targetScoreField = document.getElementById("target-score-field");
  const targetScoreInput = targetScoreField.querySelector("input");
  const handicapField = document.getElementById("handicap-field");
  const handicapInput = handicapField.querySelector("input");
  const form = document.getElementById("scorecard-form");

  function getSelectedRadio(name) {
    const checked = document.querySelector(`input[name="${name}"]:checked`);
    return checked ? checked.value : null;
  }

  /* Populate course dropdown */
  courseOptions.forEach((c, i) => {
    const opt = document.createElement("option");
    opt.value = c.course_slug;
    opt.textContent = c.display_name;
    if (i === 0) opt.selected = true;
    courseSelect.appendChild(opt);
  });

  function updateTeeOptions(slug) {
    const course = courseOptions.find((c) => c.course_slug === slug);
    teeSegmented.innerHTML = "";
    if (!course) return;
    course.tees.forEach((t, i) => {
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "tee_name";
      input.id = `tee-${t}`;
      input.value = t;
      const label = document.createElement("label");
      label.htmlFor = `tee-${t}`;
      label.textContent = t;
      teeSegmented.appendChild(input);
      teeSegmented.appendChild(label);
    });
  }

  function updateModeFields(mode) {
    const isStableford = mode === "stableford";
    targetScoreInput.disabled = isStableford;
    targetScoreField.classList.toggle("is-disabled", isStableford);
  }

  function updateTeeState() {
    const hasTee = !!getSelectedRadio("tee_name");
    stablefordRadio.disabled = !hasTee;
    handicapInput.disabled = !hasTee;
    handicapField.classList.toggle("is-disabled", !hasTee);
    if (!hasTee) {
      const currentMode = getSelectedRadio("scoring_mode");
      if (currentMode === "stableford") {
        document.getElementById("mode-stroke").checked = true;
        updateModeFields("stroke");
      }
      handicapInput.value = "";
    }
  }

  /* sessionStorage form cache */
  const STORAGE_KEY = "scorecard_form";

  function saveForm() {
    const data = {
      player_name: form.elements["player_name"].value,
      course_slug: form.elements["course_slug"].value,
      tee_name: getSelectedRadio("tee_name"),
      scoring_mode: getSelectedRadio("scoring_mode"),
      target_score: form.elements["target_score"].value,
      handicap_index: form.elements["handicap_index"].value,
    };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  }

  function restoreForm() {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    try {
      const data = JSON.parse(raw);
      if (data.course_slug) { courseSelect.value = data.course_slug; updateTeeOptions(data.course_slug); }
      if (data.tee_name) {
        const radio = document.getElementById(`tee-${data.tee_name}`);
        if (radio) radio.checked = true;
      }
      if (data.scoring_mode) {
        const modeRadio = document.getElementById(`mode-${data.scoring_mode}`);
        if (modeRadio) { modeRadio.checked = true; updateModeFields(data.scoring_mode); }
      }
      ["player_name", "target_score", "handicap_index"].forEach((n) => {
        if (data[n] != null && data[n] !== "") { const el = form.elements[n]; if (el) el.value = data[n]; }
      });
    } catch { /* ignore corrupt data */ }
  }

  /* Initialise */
  updateTeeOptions(courseSelect.value);
  updateModeFields(getSelectedRadio("scoring_mode") || "stroke");
  restoreForm();
  updateTeeState();

  /* Toggle behaviour for tee: click a selected radio to deselect it */
  teeSegmented.addEventListener("click", (e) => {
    const label = e.target.closest("label");
    if (!label) return;
    e.preventDefault();
    const input = document.getElementById(label.htmlFor);
    if (!input) return;
    input.checked = !input.checked;
    updateTeeState();
    saveForm();
  });

  /* Scoring mode: standard radio behaviour (no deselect) */
  scoringModeSegmented.addEventListener("click", (e) => {
    const label = e.target.closest("label");
    if (!label) return;
    e.preventDefault();
    const input = document.getElementById(label.htmlFor);
    if (!input || input.disabled) return;
    input.checked = true;
    updateModeFields(input.value);
    saveForm();
  });

  form.addEventListener("input", saveForm);
  form.addEventListener("change", saveForm);
  courseSelect.addEventListener("change", (e) => { updateTeeOptions(e.target.value); updateTeeState(); saveForm(); });
  form.addEventListener("submit", handleSubmit);
});
