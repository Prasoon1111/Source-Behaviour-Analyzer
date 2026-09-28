const form = document.querySelector("#search-form");
const queryInput = document.querySelector("#query");
const demoButton = document.querySelector("#demo-button");
const statusLine = document.querySelector("#status");
const results = document.querySelector("#results");
let currentResults = null;

form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadResults("/api/analyse", { query: queryInput.value.trim() });
});

demoButton.addEventListener("click", () => loadResults("/api/demo"));
document.querySelector("#cross-check").addEventListener("click", () => {
  const query = currentResults?.search_details?.query || "";
  window.open(`https://www.google.com/search?q=${encodeURIComponent(query)}&tbm=nws`, "_blank", "noopener");
});
document.querySelector("#download-json").addEventListener("click", () => downloadEvidence("json"));
document.querySelector("#download-csv").addEventListener("click", () => downloadEvidence("csv"));

async function loadResults(url, body) {
  statusLine.textContent = "Fetching latest news...";
  results.hidden = true;
  form.querySelector("button[type='submit']").disabled = true;
  demoButton.disabled = true;

  try {
    const options = body
      ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      : {};
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || "No articles found. Try 2-3 short keywords. The free news plan may also delay articles by up to 12 hours.");
    showResults(data);
    statusLine.textContent = "";
  } catch (error) {
    statusLine.textContent = error.message || "No articles found. Try 2-3 short keywords. The free news plan may also delay articles by up to 12 hours.";
  } finally {
    form.querySelector("button[type='submit']").disabled = false;
    demoButton.disabled = false;
  }
}

function showResults(data) {
  currentResults = data;
  const { indicators, total } = data;
  document.querySelector("#neutral-sentence").textContent = data.neutral_sentence;
  document.querySelector("#result-count").textContent = data.count_summary;
  const windowNote = document.querySelector("#window-note");
  windowNote.hidden = !data.window_note;
  windowNote.textContent = data.window_note || "";
  document.querySelector("#newest-age").textContent = data.newest_age_hours === null
    ? "Newest article age is unavailable."
    : `Newest article is ${data.newest_age_hours} hours old.`;
  const delayNote = document.querySelector("#data-delay-note");
  delayNote.hidden = !data.data_delay_note;
  delayNote.textContent = data.data_delay_note ? `Data delay note: ${data.data_delay_note}` : "";
  document.querySelector("#demo-label").hidden = !data.is_demo;
  document.querySelector("#source-domains").textContent = data.source_domains.join(", ");
  document.querySelector("#disclaimer").textContent = `Based on headlines and snippets from ${data.count_summary}. This shows source behaviour only, not whether the claim is true.`;
  const indiaNote = document.querySelector("#india-note");
  indiaNote.hidden = !data.india_note;
  indiaNote.textContent = data.india_note || "";
  document.querySelector("#footer-note").textContent = `Patterns are descriptive summaries across ${data.count_summary}.`;

  drawBars("#age-chart", indicators.source_age.counts);
  drawHours(indicators.posting_hours_ist);
  ["#age-sample-size", "#hours-sample-size", "#text-sample-size", "#burst-sample-size"].forEach((selector) => {
    document.querySelector(selector).textContent = data.count_summary;
  });
  document.querySelector("#identical-stat").textContent = `${indicators.identical_text.count} of ${indicators.identical_text.total} sources carry near-identical text.`;
  document.querySelector("#burst-stat").textContent = `${indicators.burst_profile.count} of ${total} articles fall within one 2-hour window. Newest article is ${data.newest_age_hours ?? "unknown"} hours old. Articles span ${indicators.burst_profile.time_span_hours} hours.`;
  document.querySelector("#age-calculation").textContent = data.calculations.source_age
    .map((item) => `${item.domain}: ${item.registration_date || item.unknown_reason} (${item.bucket})`).join("; ");
  document.querySelector("#age-calculation").textContent = `How this was calculated: ${document.querySelector("#age-calculation").textContent}`;
  document.querySelector("#hours-calculation").textContent = Object.entries(data.calculations.posting_hours_ist)
    .map(([hour, numbers]) => `${hour}:00 IST: articles ${numbers.join(", ")}`).join("; ") || "No article times available.";
  document.querySelector("#hours-calculation").textContent = `How this was calculated: ${document.querySelector("#hours-calculation").textContent}`;
  document.querySelector("#text-calculation").textContent = data.calculations.identical_text.groups.length
    ? `Matching near-identical snippet groups: ${data.calculations.identical_text.groups.map((group) => `articles ${group.join(", ")}`).join("; ")}.`
    : "No repeated snippets were found.";
  document.querySelector("#text-calculation").textContent = `How this was calculated: ${document.querySelector("#text-calculation").textContent}`;
  document.querySelector("#burst-calculation").textContent = data.calculations.burst_profile.article_numbers.length
    ? `Busiest two-hour window: articles ${data.calculations.burst_profile.article_numbers.join(", ")}.`
    : "No publication times were available.";
  document.querySelector("#burst-calculation").textContent = `How this was calculated: ${document.querySelector("#burst-calculation").textContent}`;
  renderEvidence(data.articles);
  renderSearchDetails(data.search_details);
  document.querySelector("#raw-response").textContent = JSON.stringify(data.raw_response, null, 2);
  results.hidden = false;
}

function renderEvidence(articles) {
  const body = document.querySelector("#evidence-rows");
  body.replaceChildren();
  articles.forEach((article) => {
    const row = document.createElement("tr");
    const values = [article.number, article.source_name, article.source_domain, article.origin, article.title, article.published_at_ist];
    values.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value ?? "";
      row.append(cell);
    });
    const linkCell = document.createElement("td");
    const link = document.createElement("a");
    link.href = article.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "Open article";
    linkCell.append(link);
    row.append(linkCell);
    const snippet = document.createElement("td");
    snippet.textContent = article.snippet;
    row.append(snippet);
    body.append(row);
  });
}

function renderSearchDetails(details) {
  const list = document.querySelector("#search-details-list");
  list.replaceChildren();
  const entries = [
    ["Exact query", details.query],
    ["Query sent", details.search_query || details.query],
    ["Provider", details.provider],
    ["Parameters", JSON.stringify(details.parameters)],
    ["Search window", details.window_used || "Demo"],
    ["Time of search", details.searched_at],
  ];
  entries.forEach(([label, value]) => {
    const term = document.createElement("dt");
    const description = document.createElement("dd");
    term.textContent = label;
    description.textContent = value ?? "";
    list.append(term, description);
  });
}

function downloadEvidence(format) {
  if (!currentResults) return;
  const payload = { articles: currentResults.articles, search_details: currentResults.search_details };
  let content;
  let mimeType;
  if (format === "json") {
    content = JSON.stringify(payload, null, 2);
    mimeType = "application/json";
  } else {
    const columns = ["number", "source_name", "source_domain", "origin", "title", "published_at_ist", "url", "snippet"];
    const escape = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
    content = [columns.join(","), ...payload.articles.map((article) => columns.map((column) => escape(article[column])).join(","))].join("\r\n");
    content += `\r\n\r\n${escape("Search details")},${escape(JSON.stringify(payload.search_details))}`;
    mimeType = "text/csv;charset=utf-8";
  }
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([content], { type: mimeType }));
  link.download = `news-evidence.${format}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

function drawBars(selector, values) {
  const container = document.querySelector(selector);
  const maximum = Math.max(1, ...Object.values(values));
  container.replaceChildren();
  Object.entries(values).forEach(([label, value]) => {
    const row = document.createElement("div");
    row.className = "bar-row";
    row.innerHTML = `<span class="bar-label"></span><span class="bar-track"><span class="bar-fill"></span></span><span class="bar-value"></span>`;
    row.querySelector(".bar-label").textContent = label;
    row.querySelector(".bar-fill").style.width = `${(value / maximum) * 100}%`;
    row.querySelector(".bar-value").textContent = value;
    container.append(row);
  });
}

function drawHours(values) {
  const container = document.querySelector("#hour-chart");
  const maximum = Math.max(1, ...Object.values(values));
  container.replaceChildren();
  Object.entries(values).forEach(([hour, count]) => {
    const item = document.createElement("div");
    item.className = "hour-item";
    item.title = `${hour}:00 IST: ${count} articles`;
    item.innerHTML = `<span class="hour-count"></span><span class="hour-track"><span class="hour-fill"></span></span><span></span>`;
    item.querySelector(".hour-count").textContent = count;
    item.querySelector(".hour-fill").style.height = `${(count / maximum) * 100}%`;
    item.lastElementChild.textContent = `${hour}:00`;
    container.append(item);
  });
  if (!Object.keys(values).length) container.textContent = "No publishing times available.";
}