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

/* ── PDF export (jsPDF + autotable) ── */

function exportPdf() {
  if (!window._currentScorecard) return;
  const sc = window._currentScorecard;

  /* Page: 216mm × 140mm landscape */
  const { jsPDF } = window.jspdf;
  const doc = new jsPDF({ orientation: "landscape", unit: "mm", format: [140, 216] });
  const pageW = 216;
  const margin = 4;
  const contentW = pageW - margin * 2;

  const green = [26, 92, 46];
  const white = [255, 255, 255];
  const lightGreen = [232, 240, 232];
  const writeGray = [247, 249, 247];

  /* ── Header ── */
  let y = margin;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(9);
  doc.setTextColor(...green);
  const title = `${sc.meta.club_name} \u2014 ${sc.meta.course_name}`;
  doc.text(title, margin, y + 3);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(5.5);
  doc.setTextColor(85, 85, 85);
  const subtitle = (sc.meta.tee_name ? `Tee ${sc.meta.tee_name} \u00b7 ` : "") + sc.meta.scoring_mode;
  doc.text(subtitle, margin, y + 6);

  /* Meta fields on the right side of header */
  const metaPairs = [];
  metaPairs.push(["Player", sc.meta.player_name || ""]);
  metaPairs.push(["Date", ""]);
  metaPairs.push(["Par", String(sc.overall_totals.par_total)]);
  if (sc.overall_totals.distance_total != null) {
    metaPairs.push(["Dist", sc.overall_totals.distance_total + "m"]);
  }
  if (sc.meta.target_score != null) {
    metaPairs.push(["Target", String(sc.meta.target_score)]);
  }
  if (sc.meta.handicap_index_label) {
    metaPairs.push(["HCP", sc.meta.handicap_index_label]);
    metaPairs.push(["CR/Slope", `${sc.meta.course_rating}/${sc.meta.slope_rating}`]);
    metaPairs.push(["Strokes", String(sc.meta.playing_strokes_total)]);
  }

  let metaX = pageW - margin;
  doc.setFontSize(4.5);
  for (let i = metaPairs.length - 1; i >= 0; i--) {
    const [label, value] = metaPairs[i];
    const valW = doc.getTextWidth(value);
    const lblW = doc.getTextWidth(label.toUpperCase());
    const cellW = Math.max(valW, lblW) + 3;
    metaX -= cellW;
    doc.setFont("helvetica", "normal");
    doc.setTextColor(136, 136, 136);
    doc.text(label.toUpperCase(), metaX + cellW, y + 2, { align: "right" });
    doc.setFont("helvetica", "bold");
    doc.setFontSize(5.5);
    doc.setTextColor(17, 17, 17);
    doc.text(value, metaX + cellW, y + 5, { align: "right" });
    doc.setFontSize(4.5);
  }

  /* Header divider */
  y += 8;
  doc.setDrawColor(...green);
  doc.setLineWidth(0.3);
  doc.line(margin, y, pageW - margin, y);
  y += 1.5;

  /* ── Build table data ── */
  const head = [sc.main_columns];

  function holeRow(h) {
    const cells = [String(h.hole_number), String(h.handicap), String(h.par)];
    if (sc.show_adjusted_par) cells.push(h.adjusted_par != null ? String(h.adjusted_par) : "");
    cells.push(h.distance != null ? String(h.distance) : "");
    if (sc.show_stableford_columns) {
      cells.push(String(h.strokes_received ?? ""), String(h.two_points_score ?? ""));
      cells.push("", ""); /* Net, Pts — writable */
    }
    cells.push("", "", ""); /* Score, Putts, Pen */
    cells.push("", "", "", "", "", "", ""); /* FIR, FW Miss, Green Miss, Up&Down, SZ Reg, Dn3, Putt<=4ft */
    return cells;
  }

  function totalsRow(label, totals) {
    const cells = [label, "", String(totals.par_total)];
    if (sc.show_adjusted_par) cells.push(totals.adjusted_par_total != null ? String(totals.adjusted_par_total) : "");
    cells.push(totals.distance_total != null ? String(totals.distance_total) : "");
    const remaining = sc.main_columns.length - cells.length;
    for (let i = 0; i < remaining; i++) cells.push("");
    return cells;
  }

  const body = sc.all_holes.map(holeRow);
  const foot = [
    totalsRow("Front", sc.front_totals),
    totalsRow("Back", sc.back_totals),
    totalsRow("Total", sc.overall_totals),
  ];

  /* Determine which columns are pre-filled vs writable */
  let prefilledCount = 3; /* Hole, HCP, Par */
  if (sc.show_adjusted_par) prefilledCount++;
  prefilledCount++; /* Distance */
  if (sc.show_stableford_columns) prefilledCount += 2; /* Strokes, 2Pts@ */
  const writableStart = prefilledCount;
  const totalCols = sc.main_columns.length;

  /* Column styles: pre-filled columns get fixed widths, writable stretch to fill */
  const preW = [5.5, 5, 5]; /* Hole, HCP, Par */
  if (sc.show_adjusted_par) preW.push(6);
  preW.push(10); /* Distance */
  if (sc.show_stableford_columns) preW.push(8, 6); /* Strokes, 2Pts@ */
  const fixedSum = preW.reduce((a, b) => a + b, 0);
  const writableCols = totalCols - prefilledCount;
  const writableW = writableCols > 0 ? (contentW - fixedSum) / writableCols : 5;

  const columnStyles = {};
  for (let i = 0; i < totalCols; i++) {
    columnStyles[i] = {
      cellWidth: i < prefilledCount ? preW[i] : writableW,
      halign: "center",
    };
  }
  /* First column in footer rows spans 2 */
  columnStyles[0] = { ...columnStyles[0] };

  doc.autoTable({
    startY: y,
    margin: { left: margin, right: margin },
    tableWidth: contentW,
    head: head,
    body: body,
    foot: foot,
    theme: "grid",
    styles: {
      font: "helvetica",
      fontSize: 5,
      cellPadding: { top: 0.8, right: 0.3, bottom: 0.8, left: 0.3 },
      lineColor: [187, 187, 187],
      lineWidth: 0.15,
      halign: "center",
      valign: "middle",
      textColor: [17, 17, 17],
      fontStyle: "bold",
      minCellHeight: 4.5,
    },
    headStyles: {
      fillColor: green,
      textColor: white,
      fontStyle: "bold",
      fontSize: 4.5,
    },
    footStyles: {
      fillColor: lightGreen,
      textColor: green,
      fontStyle: "bold",
      fontSize: 5,
    },
    columnStyles: columnStyles,
    didParseCell: function (data) {
      /* Writable cells get a light background */
      if (data.section === "body" && data.column.index >= writableStart) {
        data.cell.styles.fillColor = writeGray;
        data.cell.styles.fontStyle = "normal";
      }
      /* Turn row (hole 10) gets green top border + tinted bg */
      if (data.section === "body" && data.row.index === 9) {
        data.cell.styles.fillColor = [240, 247, 240];
      }
    },
    didDrawCell: function (data) {
      /* Thicker top border on hole 10 row */
      if (data.section === "body" && data.row.index === 9) {
        doc.setDrawColor(...green);
        doc.setLineWidth(0.4);
        doc.line(data.cell.x, data.cell.y, data.cell.x + data.cell.width, data.cell.y);
      }
    },
  });

  /* ── Download ── */
  const teePart = sc.meta.tee_name ? `_${sc.meta.tee_name}` : "";
  const filename = `scorecard_${sc.meta.course_name}${teePart}.pdf`.replace(/ /g, "_");
  doc.save(filename);
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
