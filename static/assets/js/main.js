/**
 * Wahlplattform – Frontend Logic (multi-tenant)
 * Reads slug from body[data-slug]. No cookies, localStorage for duplicate prevention.
 */
(function () {
  "use strict";

  var SLUG = document.body.dataset.slug || "";
  if (!SLUG) return; // landing page – no tracking

  var BASE = "/" + SLUG;
  var API = "/api/" + SLUG;

  // Current page slug from URL
  var path = window.location.pathname.replace(BASE, "").replace(/^\/|\/$/g, "");
  var currentPage = path || "home";

  // ── Helpers ──────────────────────────────────────────────────
  function escapeHtml(text) {
    var d = document.createElement("div");
    d.textContent = text;
    return d.innerHTML;
  }

  function post(url, data) {
    return fetch(API + url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    });
  }

  // ── Visit Tracking ──────────────────────────────────────────
  function trackVisit() {
    post("/event/visit", {
      page: currentPage,
      ref: document.referrer || null,
    }).catch(function () {});
  }

  // ── Poll ─────────────────────────────────────────────────────
  function initPoll() {
    var section = document.querySelector(".poll-section");
    if (!section) return;

    var pollId = section.dataset.pollId;
    var page = section.dataset.page;
    var buttons = section.querySelectorAll(".option-btn");
    var resultsDiv = section.querySelector(".results");
    var storageKey = "poll_" + SLUG + "_" + pollId;

    if (localStorage.getItem(storageKey)) {
      disableButtons(buttons, localStorage.getItem(storageKey));
      loadPollResults(pollId, resultsDiv, buttons);
      return;
    }

    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var option = btn.dataset.option;
        localStorage.setItem(storageKey, option);
        disableButtons(buttons, option);

        post("/poll/vote", {
          page: page,
          poll_id: pollId,
          option: option,
        })
          .then(function (data) {
            showPollResults(data, resultsDiv, buttons);
          })
          .catch(function () {
            resultsDiv.classList.remove("hidden");
            resultsDiv.innerHTML =
              '<p class="result-total">Ergebnis konnte nicht geladen werden.</p>';
          });
      });
    });
  }

  function disableButtons(buttons, selectedOption) {
    buttons.forEach(function (b) {
      b.disabled = true;
      if (b.dataset.option === selectedOption) b.classList.add("selected");
    });
  }

  function loadPollResults(pollId, resultsDiv, buttons) {
    fetch(API + "/poll/results/" + encodeURIComponent(pollId))
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        showPollResults(data, resultsDiv, buttons);
      })
      .catch(function () {});
  }

  function showPollResults(data, resultsDiv, buttons) {
    var results = data.results || {};
    var total = data.total || 0;
    var html = "";

    buttons.forEach(function (btn) {
      var option = btn.dataset.option;
      var info = results[option] || { count: 0, percent: 0 };
      html +=
        '<div class="result-bar">' +
        '<span class="result-label">' + escapeHtml(option) + "</span>" +
        '<div class="result-track"><div class="result-fill" style="width:' + info.percent + '%"></div></div>' +
        '<span class="result-pct">' + info.percent + "%</span>" +
        "</div>";
    });

    html += '<p class="result-total">' + total + " Stimme" + (total !== 1 ? "n" : "") + "</p>";
    resultsDiv.innerHTML = html;
    resultsDiv.classList.remove("hidden");
  }

  // ── Quiz ─────────────────────────────────────────────────────
  function initQuiz() {
    var section = document.querySelector(".quiz-section");
    if (!section) return;

    var quizId = section.dataset.quizId;
    var page = section.dataset.page;
    var buttons = section.querySelectorAll(".option-btn");
    var feedback = section.querySelector(".quiz-feedback");
    var storageKey = "quiz_" + SLUG + "_" + quizId;

    var saved = localStorage.getItem(storageKey);
    if (saved) {
      try {
        var s = JSON.parse(saved);
        buttons.forEach(function (b) {
          b.disabled = true;
          if (b.dataset.option === s.correct) b.classList.add("correct");
          if (b.dataset.option === s.selected && !s.is_correct) b.classList.add("wrong");
        });
        feedback.textContent = s.explain || (s.is_correct ? "Richtig!" : "Leider falsch.");
        feedback.className = "quiz-feedback " + (s.is_correct ? "correct" : "wrong");
      } catch (e) {}
      return;
    }

    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var option = btn.dataset.option;
        buttons.forEach(function (b) { b.disabled = true; });

        post("/quiz/answer", {
          page: page,
          quiz_id: quizId,
          option: option,
        })
          .then(function (data) {
            localStorage.setItem(storageKey, JSON.stringify({
              selected: option,
              correct: data.correct_answer,
              is_correct: data.is_correct,
              explain: data.explain,
            }));

            buttons.forEach(function (b) {
              if (b.dataset.option === data.correct_answer) b.classList.add("correct");
              if (b.dataset.option === option && !data.is_correct) b.classList.add("wrong");
            });

            feedback.textContent = data.explain || (data.is_correct ? "Richtig!" : "Leider falsch.");
            feedback.className = "quiz-feedback " + (data.is_correct ? "correct" : "wrong");
          })
          .catch(function () {
            feedback.textContent = "Antwort konnte nicht gesendet werden.";
            feedback.className = "quiz-feedback wrong";
            buttons.forEach(function (b) { b.disabled = false; });
          });
      });
    });
  }

  // ── Feedback Form ────────────────────────────────────────────────
  function initFeedback() {
    var form = document.querySelector(".feedback-form");
    if (!form) return;

    var textarea = form.querySelector("textarea");
    var btn = form.querySelector(".submit-btn");
    var success = form.querySelector(".feedback-success");
    var page = form.dataset.page;
    var charCount = form.querySelector(".char-count");

    textarea.addEventListener("input", function () {
      if (charCount) charCount.textContent = textarea.value.length + " / 1000";
    });

    btn.addEventListener("click", function () {
      var msg = textarea.value.trim();
      if (!msg) return;
      btn.disabled = true;

      post("/feedback", { page: page, message: msg })
        .then(function (data) {
          if (data.ok) {
            textarea.value = "";
            success.textContent = "Danke für deine Rückmeldung!";
            success.classList.remove("hidden");
            if (charCount) charCount.textContent = "0 / 1000";
            setTimeout(function () { btn.disabled = false; }, 3000);
          } else {
            success.textContent = data.error || "Fehler";
            success.classList.remove("hidden");
            btn.disabled = false;
          }
        })
        .catch(function () {
          success.textContent = "Konnte nicht gesendet werden.";
          success.classList.remove("hidden");
          btn.disabled = false;
        });
    });
  }

  // ── Init ─────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    trackVisit();
    initPoll();
    initQuiz();
    initFeedback();
  });
})();
