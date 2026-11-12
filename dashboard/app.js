/* Reads findings.json and the small CSV tables, then draws each section. */
(async function () {
  const C = window.Charts;
  const TOP = "var(--s2)", AVG = "var(--s1)";
  let f;
  try {
    const res = await fetch("data/findings.json");
    if (!res.ok) throw new Error(res.status);
    f = await res.json();
  } catch (e) {
    document.getElementById("meta").textContent = "";
    document.getElementById("loadError").hidden = false;
    return;
  }
  const csv = async name => {
    const t = (await (await fetch(`data/${name}.csv`)).text()).trim().split("\n");
    const head = t[0].split(",");
    return t.slice(1).map(line => Object.fromEntries(line.split(",").map((v, i) => [head[i], v])));
  };
  const n = v => Math.round(v).toLocaleString("en-US");
  const one = v => (+v).toFixed(1);
  const set = (id, html) => { document.getElementById(id).innerHTML = html; };

  const z = f.size, c = f.controlled, r = f.raw;
  set("meta", `${n(z.seller_months)} seller-months, ${n(z.sellers)} sellers in ${z.teams} teams, ${z.branches} branches and ${z.regions} regions, ${f.window[0]} to ${f.window[1]}.`);
  set("kpiTop", one(c.rate_top));
  set("kpiAvg", one(c.rate_average));
  set("kpiGap", `+${one(c.gap)}`);
  set("planted", `These are synthetic records. The generator gives sellers under top-seller leaders a ${f.params.leader_effect}x higher chance of resigning each month. The page tests whether the method finds an effect that was put in on purpose.`);

  const draw = async () => {
    const regions = await csv("region_rates");
    C.hbars(document.getElementById("chartRegion"), regions.map(d => ({
      label: d.region, value: +d.exits_per_100_per_year, color: "var(--muted-mark)",
      tipHtml: `<strong>${d.region}</strong><br>${one(d.exits_per_100_per_year)} exits per 100 a year<br>${Math.round(d.share_under_top_seller_leaders * 100)}% of seller-months under top-seller leaders`
    })), { aria: "Exits per 100 sellers a year by region" });
    const hi = regions[0], lo = regions[regions.length - 1], bo = f.branch_overlap;
    set("capRegion", `Exits per 100 sellers a year. ${hi.region} is highest at ${one(hi.exits_per_100_per_year)} and ${lo.region} lowest at ${one(lo.exits_per_100_per_year)}. In the 30% of branches with the most exits, ${Math.round(bo.top_share_high_exit_branches * 100)}% of seller-months are under top-seller leaders, against ${Math.round(bo.top_share_other_branches * 100)}% in the rest.`);

    C.legend(document.getElementById("legRoute"), [{ name: "Leader promoted as a top seller", color: TOP }, { name: "Leader who was an average seller", color: AVG }]);
    C.hbars(document.getElementById("chartRoute"), [
      { label: "Raw, top", value: r.rate_top, color: TOP },
      { label: "Raw, average", value: r.rate_average, color: AVG },
      { label: "Controlled, top", value: c.rate_top, color: TOP },
      { label: "Controlled, average", value: c.rate_average, color: AVG }
    ], { aria: "Exits per 100 sellers a year by leader route, raw and after controls" });
    set("capRoute", `Exits per 100 sellers a year, by leader route ("top" means the leader was promoted as a top seller). The raw gap is ${one(r.gap)}. After branch, tenure, team size and month it is ${one(c.gap)} (95% interval ${one(c.gap_ci[0])} to ${one(c.gap_ci[1])}). It shrinks because busy branches promote top sellers more often. It does not go away. Teams under leaders already in post when the records start, or hired from outside, are left out because their route can't be read: ${z.leaders_unknown_route} of ${z.leaders_unknown_route + z.leaders_with_known_route} leaders.`);

    const surv = await csv("survival");
    const xs = [...new Set(surv.map(d => d.tenure_month))];
    const series = [["top seller", TOP, "Top-seller leader"], ["average seller", AVG, "Average-seller leader"]].map(([k, col, name]) => ({
      name, color: col, values: surv.filter(d => d.route === k).map(d => Math.round(d.still_in_post * 1000) / 10)
    }));
    C.legend(document.getElementById("legSurv"), series);
    C.lines(document.getElementById("chartSurv"), xs.map(x => `${x}`), series, { aria: "Percent of new hires still in post by month of tenure", right: 150 });
    set("capSurv", `Percent still in post, by month of tenure. After 12 months, ${Math.round(f.survival_12m["top seller"] * 100)}% of new hires under top-seller leaders are still there, against ${Math.round(f.survival_12m["average seller"] * 100)}% under average-seller leaders.`);

    const rs = await csv("exit_reasons");
    const reasons = ["Personal growth", "Career path", "Unsupportive scope of work", "Leadership"];
    const short = { "Personal growth": "Growth", "Career path": "Career path", "Unsupportive scope of work": "Work scope", "Leadership": "Leadership" };
    const items = [];
    reasons.forEach(reason => [["top seller", TOP, "top"], ["average seller", AVG, "average"]].forEach(([k, col, who]) => {
      const row = rs.find(d => d.route === k && d.reason === reason);
      items.push({ label: `${short[reason]}, ${who}`, value: row ? Math.round(row.share * 1000) / 10 : 0, color: col });
    }));
    C.legend(document.getElementById("legReason"), [{ name: "Leader promoted as a top seller", color: TOP }, { name: "Leader who was an average seller", color: AVG }]);
    C.hbars(document.getElementById("chartReason"), items, { aria: "Percent of exit forms by stated reason and leader route" });
    set("capReason", `Percent of exit forms by stated reason, by leader route. "Work scope" is the form's "unsupportive scope of work". ${n(f.reasons.forms_matched)} forms match ${n(f.reasons.resign_exits_known_route)} resignations. "Leadership" is ${Math.round(f.reasons.leadership_share * 100)}% of all forms.`);

    const k = f.cost;
    set("costLine", `About ${n(k.full_time_sellers_of_sales_lost_per_year)} sellers' full-year sales, every year`);
    set("costNote", `The controlled gap means about ${n(k.extra_exits_per_year)} extra exits a year across ${n(k.seller_years_under_top_seller_leaders_per_year)} seller-years under top-seller leaders. Each exit is counted as ${k.assumptions.vacancy_months} month with the seat empty plus ${k.assumptions.ramp_months} months at ${Math.round(k.assumptions.ramp_output_share * 100)}% output while the new hire ramps up: ${k.sales_months_lost_per_exit} months of one seller's sales. These are assumptions, set in one place in the code, applied to a synthetic gap.`);

    const nc = f.null_calibration;
    set("checkNull", nc
      ? `<strong>Does the method invent a gap?</strong> I generated ${nc.runs} datasets with no team leader effect and ran the same steps on each. The average gap was ${one(nc.mean_gap)} exits per 100 a year, and ${nc.intervals_including_zero} of ${nc.runs} intervals included zero. A fair method misses about 1 run in 20 by chance. Here ${nc.misses_above_zero} of the misses ${nc.misses_above_zero === 1 ? "is" : "are"} above zero and ${nc.misses_below_zero} below, so they don't lean one way.`
      : "Null calibration not run yet.");
    C.table(document.getElementById("tblSens"), ["Check", "Top seller", "Average seller", "Gap", "95% interval"],
      [["Main result", one(c.rate_top), one(c.rate_average), one(c.gap), `${one(c.gap_ci[0])} to ${one(c.gap_ci[1])}`]]
        .concat(f.sensitivity.map(s => [s.check, one(s.rate_top), one(s.rate_average), one(s.gap), `${one(s.gap_ci[0])} to ${one(s.gap_ci[1])}`])),
      [false, true, true, true, true]);
    const gaps = f.checks.incomplete_region_months;
    C.table(document.getElementById("tblGaps"), ["Region", "Month", "Left the roster", "No resignation row"],
      gaps.length ? gaps.map(g => [g.region, g.month, g.roster_exits, g.unrecorded]) : [["None", "", "", ""]], [false, false, true, true]);
  };
  try { await draw(); } catch (e) { document.getElementById("loadError").hidden = false; }
  let t;
  window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(draw, 150); });
})();
