(function () {
  "use strict";

  const API = Object.freeze({
    test: "/api/test",
    progress: "/api/progress",
    answer: "/api/answer",
    finalize: "/api/finalize",
    results: "/api/results"
  });

  const FLAG_LABELS = Object.freeze({
    brief_mismatch: "Brief-tévesztés",
    genre_mismatch: "Műfajidegenség",
    false_peter_voice: "Hamis Péter-hang",
    mannerism_caricature: "Modorosság / karikatúra",
    hard_guard_problem: "Hard-guard probléma"
  });

  function normalizeFlags(values) {
    if (!Array.isArray(values)) return [];
    return Array.from(new Set(values.filter((value) => Object.hasOwn(FLAG_LABELS, value))));
  }

  function deriveState({ started, finalized, answeredCount, itemCount }) {
    if (finalized) return "finalized";
    if (!started) return "start";
    if (itemCount > 0 && answeredCount >= itemCount) return "review";
    return "compare";
  }

  function validateAnswer({ choice, reason }) {
    const normalizedReason = typeof reason === "string" ? reason.trim() : "";
    if (!["left", "right", "tie"].includes(choice)) {
      return { valid: false, message: "Válassz a Bal, Jobb vagy Döntetlen lehetőségek közül." };
    }
    if (normalizedReason.length < 10) {
      return { valid: false, message: "Az indoklás legalább 10 karakter legyen." };
    }
    return { valid: true, message: "" };
  }

  function buildAnswerPayload(itemId, fields) {
    const clean = (value) => typeof value === "string" ? value.trim() : "";
    return {
      item_id: itemId,
      choice: fields.choice,
      reason: clean(fields.reason),
      flags: normalizeFlags(fields.flags),
      left_highlight: clean(fields.leftHighlight),
      left_note: clean(fields.leftNote),
      right_highlight: clean(fields.rightHighlight),
      right_note: clean(fields.rightNote),
      general_note: clean(fields.generalNote)
    };
  }

  function navigationAvailability({ currentIndex, busy }) {
    return { backEnabled: !busy && currentIndex > 0 };
  }

  function scrollBehavior(reducedMotion) {
    return reducedMotion ? "auto" : "smooth";
  }

  function focusTargetForState(view) {
    return {
      loading: "loading-title",
      error: "error-title",
      start: "start-title",
      compare: "compare-title",
      review: "review-title",
      finalized: "results-title"
    }[view] || "main-content";
  }

  const publicApi = {
    deriveState, validateAnswer, buildAnswerPayload, normalizeFlags, navigationAvailability,
    scrollBehavior, focusTargetForState
  };
  if (typeof module !== "undefined" && module.exports) module.exports = publicApi;
  if (typeof document === "undefined") return;

  const state = {
    started: false,
    view: "loading",
    currentIndex: 0,
    test: null,
    progress: null,
    results: null,
    busy: false
  };

  const elements = {};

  function byId(id) {
    return document.getElementById(id);
  }

  function collectElements() {
    for (const id of [
      "header-progress", "save-status", "progress-bar", "error-message", "retry-button",
      "start-button", "brief-text", "answer-form", "left-candidate", "right-candidate",
      "left-highlight", "left-note", "right-highlight", "right-note", "reason", "reason-help",
      "general-note", "back-button", "item-progress", "next-button", "review-items",
      "review-back-button", "finalize-button", "overall-results", "item-results"
    ]) elements[id] = byId(id);
    elements.views = Array.from(document.querySelectorAll("[data-view]"));
  }

  async function requestJson(url, options) {
    const response = await fetch(url, options);
    let payload;
    try {
      payload = await response.json();
    } catch (_error) {
      throw new Error(`Érvénytelen szerverválasz (${response.status}).`);
    }
    if (!response.ok) throw new Error(payload.error || `Szerverhiba (${response.status}).`);
    return payload;
  }

  function answersFromSnapshot(snapshot) {
    const answers = {};
    for (const item of snapshot.items || []) {
      if (item.answer) answers[item.item_id] = item.answer;
    }
    return answers;
  }

  function normalizedProgress(snapshot) {
    if (snapshot.answers) return snapshot;
    return {
      item_count: snapshot.item_count,
      answered_count: snapshot.answered_count,
      finalized: snapshot.finalized,
      answers: answersFromSnapshot(snapshot)
    };
  }

  function firstUnansweredIndex() {
    const answers = state.progress ? state.progress.answers : {};
    const index = state.test.items.findIndex((item) => !answers[item.item_id]);
    return index === -1 ? Math.max(0, state.test.items.length - 1) : index;
  }

  function setView(name) {
    state.view = name;
    for (const view of elements.views) view.hidden = view.dataset.view !== name;
    updateHeader();
    focusActiveView(name);
  }

  function focusActiveView(name) {
    const target = byId(focusTargetForState(name)) || byId("main-content");
    if (!target) return;
    try {
      target.focus({ preventScroll: true });
    } catch (_error) {
      target.focus();
    }
  }

  function scrollToTop() {
    const reducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: scrollBehavior(reducedMotion) });
  }

  function updateHeader() {
    const total = state.test ? state.test.item_count : 30;
    const answered = state.progress ? state.progress.answered_count : 0;
    const current = state.view === "compare" ? state.currentIndex + 1 : answered;
    elements["header-progress"].textContent = `${Math.min(current, total)} / ${total}`;
    elements["progress-bar"].style.width = total ? `${(answered / total) * 100}%` : "0%";
  }

  function showError(error) {
    elements["error-message"].textContent = error instanceof Error ? error.message : String(error);
    setView("error");
  }

  function itemAnswer(item) {
    return (state.progress && state.progress.answers[item.item_id]) || null;
  }

  function setCandidateText(target, text) {
    target.textContent = text;
  }

  function restoreForm(answer) {
    elements["answer-form"].reset();
    if (answer) {
      const radio = document.querySelector(`input[name="choice"][value="${answer.choice}"]`);
      if (radio) radio.checked = true;
      for (const flag of normalizeFlags(answer.flags)) {
        const checkbox = document.querySelector(`input[name="flags"][value="${flag}"]`);
        if (checkbox) checkbox.checked = true;
      }
      elements.reason.value = answer.reason || "";
      elements["left-highlight"].value = answer.left_highlight || "";
      elements["left-note"].value = answer.left_note || "";
      elements["right-highlight"].value = answer.right_highlight || "";
      elements["right-note"].value = answer.right_note || "";
      elements["general-note"].value = answer.general_note || "";
    }
    refreshValidation();
  }

  function currentFields() {
    const choice = document.querySelector('input[name="choice"]:checked');
    return {
      choice: choice ? choice.value : "",
      reason: elements.reason.value,
      flags: Array.from(
        document.querySelectorAll('input[name="flags"]:checked'),
        (checkbox) => checkbox.value
      ),
      leftHighlight: elements["left-highlight"].value,
      leftNote: elements["left-note"].value,
      rightHighlight: elements["right-highlight"].value,
      rightNote: elements["right-note"].value,
      generalNote: elements["general-note"].value
    };
  }

  function refreshValidation(showMessage = false) {
    const validation = validateAnswer(currentFields());
    elements["next-button"].disabled = state.busy || !validation.valid;
    elements["reason-help"].textContent = showMessage && !validation.valid
      ? validation.message
      : "A döntés és a legalább 10 karakteres indoklás után léphetsz tovább.";
    elements["reason-help"].classList.toggle("is-error", showMessage && !validation.valid);
    return validation;
  }

  function refreshNavigation() {
    const availability = navigationAvailability({ currentIndex: state.currentIndex, busy: state.busy });
    elements["back-button"].disabled = !availability.backEnabled;
  }

  function renderComparison() {
    const item = state.test.items[state.currentIndex];
    elements["brief-text"].textContent = item.brief;
    setCandidateText(elements["left-candidate"], item.left_text);
    setCandidateText(elements["right-candidate"], item.right_text);
    elements["item-progress"].textContent = `${state.currentIndex + 1} / ${state.test.item_count}`;
    refreshNavigation();
    elements["next-button"].textContent = state.currentIndex === state.test.item_count - 1
      ? "Mentés és ellenőrzés"
      : "Mentés és tovább";
    restoreForm(itemAnswer(item));
    setView("compare");
    scrollToTop();
  }

  function choiceLabel(choice) {
    return { left: "Bal", right: "Jobb", tie: "Döntetlen" }[choice] || "Nincs döntés";
  }

  function renderReview() {
    elements["review-items"].replaceChildren();
    state.test.items.forEach((item, index) => {
      const answer = itemAnswer(item);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "review-item";
      button.append(
        Object.assign(document.createElement("strong"), { textContent: `${index + 1}.` }),
        Object.assign(document.createElement("span"), { textContent: item.brief }),
        Object.assign(document.createElement("span"), { textContent: choiceLabel(answer && answer.choice) })
      );
      button.addEventListener("click", () => {
        state.currentIndex = index;
        renderComparison();
      });
      elements["review-items"].append(button);
    });
    elements["finalize-button"].disabled = state.progress.answered_count !== state.test.item_count;
    setView("review");
    scrollToTop();
  }

  function systemLabel(system) {
    return system === "tie" ? "Döntetlen" : system;
  }

  function paragraph(text, fallback = "Nincs megjegyzés.") {
    const node = document.createElement("p");
    node.textContent = text || fallback;
    return node;
  }

  function flagsParagraph(flags) {
    const labels = normalizeFlags(flags).map((flag) => FLAG_LABELS[flag]);
    return paragraph(
      labels.length ? `Hibajelölések: ${labels.join(", ")}` : "",
      "Nincs hibajelölés."
    );
  }

  function renderResults() {
    elements["overall-results"].replaceChildren();
    for (const [system, count] of Object.entries(state.results.overall || {})) {
      const section = document.createElement("section");
      section.className = "overall-result";
      section.append(
        Object.assign(document.createElement("strong"), { textContent: String(count) }),
        Object.assign(document.createElement("span"), { textContent: systemLabel(system) })
      );
      elements["overall-results"].append(section);
    }

    elements["item-results"].replaceChildren();
    for (const item of state.results.items || []) {
      const article = document.createElement("article");
      article.className = "item-result";
      const title = document.createElement("h3");
      title.textContent = `${item.item_id} · ${item.genre} · ${item.chosen_system || "Döntetlen"}`;
      const decision = paragraph(`Döntés: ${choiceLabel(item.choice)} — ${item.reason}`);
      const feedback = document.createElement("div");
      feedback.className = "feedback-list";
      for (const [system, notes] of Object.entries(item.candidate_feedback || {})) {
        const section = document.createElement("section");
        const heading = document.createElement("h4");
        heading.textContent = system;
        section.append(heading, paragraph(notes.highlight, "Nincs kiemelt részlet."), paragraph(notes.note));
        feedback.append(section);
      }
      article.append(title, decision, flagsParagraph(item.flags), feedback, paragraph(item.general_note));
      elements["item-results"].append(article);
    }
    setView("finalized");
    scrollToTop();
  }

  async function saveCurrent(event) {
    event.preventDefault();
    const validation = refreshValidation(true);
    if (!validation.valid || state.busy) return;
    state.busy = true;
    refreshValidation();
    elements["save-status"].textContent = "Mentés…";
    try {
      const item = state.test.items[state.currentIndex];
      const snapshot = await requestJson(API.answer, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildAnswerPayload(item.item_id, currentFields()))
      });
      state.progress = normalizedProgress(snapshot);
      elements["save-status"].textContent = "Folyamat mentve";
      if (state.progress.answered_count >= state.test.item_count) {
        renderReview();
      } else {
        state.currentIndex = Math.min(state.currentIndex + 1, state.test.item_count - 1);
        renderComparison();
      }
    } catch (error) {
      elements["save-status"].textContent = "Mentési hiba";
      showError(error);
    } finally {
      state.busy = false;
      if (state.view === "compare") {
        refreshValidation();
        refreshNavigation();
      }
    }
  }

  async function finalizeRun() {
    if (state.busy || state.progress.answered_count !== state.test.item_count) return;
    if (!window.confirm("Biztosan véglegesíted a tesztet? A válaszok ezután nem módosíthatók.")) return;
    state.busy = true;
    setView("loading");
    try {
      state.results = await requestJson(API.finalize, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}"
      });
      state.progress.finalized = true;
      renderResults();
    } catch (error) {
      showError(error);
    } finally {
      state.busy = false;
    }
  }

  function renderDerivedState() {
    const name = deriveState({
      started: state.started,
      finalized: Boolean(state.progress && state.progress.finalized),
      answeredCount: state.progress ? state.progress.answered_count : 0,
      itemCount: state.test ? state.test.item_count : 0
    });
    if (name === "start") setView("start");
    else if (name === "compare") renderComparison();
    else if (name === "review") renderReview();
    else renderResults();
  }

  async function initialize() {
    setView("loading");
    try {
      const [test, progress] = await Promise.all([
        requestJson(API.test), requestJson(API.progress)
      ]);
      state.test = test;
      state.progress = normalizedProgress(progress);
      state.started = state.progress.answered_count > 0 || state.progress.finalized;
      state.currentIndex = firstUnansweredIndex();
      if (state.progress.finalized) state.results = await requestJson(API.results);
      elements["save-status"].textContent = state.progress.answered_count > 0 ? "Folyamat mentve" : "Helyi értékelés";
      renderDerivedState();
    } catch (error) {
      showError(error);
    }
  }

  function bindEvents() {
    elements["retry-button"].addEventListener("click", initialize);
    elements["start-button"].addEventListener("click", () => {
      state.started = true;
      state.currentIndex = firstUnansweredIndex();
      renderComparison();
    });
    elements["answer-form"].addEventListener("submit", saveCurrent);
    elements["answer-form"].addEventListener("input", () => refreshValidation());
    elements["answer-form"].addEventListener("change", () => refreshValidation());
    elements["back-button"].addEventListener("click", () => {
      if (state.currentIndex > 0) {
        state.currentIndex -= 1;
        renderComparison();
      }
    });
    elements["review-back-button"].addEventListener("click", () => {
      state.currentIndex = state.test.item_count - 1;
      renderComparison();
    });
    elements["finalize-button"].addEventListener("click", finalizeRun);
  }

  collectElements();
  bindEvents();
  initialize();
})();
