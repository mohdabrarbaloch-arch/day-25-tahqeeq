/* ─────────────────────────────────────────────────────────────
   Tahqeeq — frontend
   Vanilla JS, no framework, no build step. One file.
   ───────────────────────────────────────────────────────────── */

(() => {
  "use strict";

  // ── state ──────────────────────────────────────────────────
  const state = {
    token: localStorage.getItem("tahqeeq_token") || null,
    user: null,
    lastResult: null,
    lastPayload: null,
    authMode: "login",
  };

  // ── element helpers ────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const views = {
    analyse: $("view-analyse"),
    result: $("view-result"),
    history: $("view-history"),
    auth: $("view-auth"),
  };

  function showView(name) {
    Object.entries(views).forEach(([key, node]) => {
      node.hidden = key !== name;
    });
    window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
  }

  // ── toast ──────────────────────────────────────────────────
  let toastTimer = null;
  function toast(message) {
    const node = $("toast");
    node.textContent = message;
    node.hidden = false;
    requestAnimationFrame(() => node.classList.add("is-visible"));
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      node.classList.remove("is-visible");
      setTimeout(() => { node.hidden = true; }, 220);
    }, 2600);
  }

  // ── api ────────────────────────────────────────────────────
  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (state.token) headers.Authorization = `Bearer ${state.token}`;

    const response = await fetch(path, { ...options, headers });
    let body = null;
    if (response.status !== 204) {
      const text = await response.text();
      if (text) {
        try { body = JSON.parse(text); } catch { body = { detail: text }; }
      }
    }

    if (!response.ok) {
      const message = (body && body.detail) || `Request failed (${response.status})`;
      const error = new Error(message);
      error.status = response.status;
      throw error;
    }
    return body;
  }

  // ── error display ──────────────────────────────────────────
  function showError(node, message) {
    node.textContent = message;
    node.hidden = false;
  }
  function clearError(node) {
    node.textContent = "";
    node.hidden = true;
  }

  // ── auth UI ────────────────────────────────────────────────
  function renderAuthState() {
    const loggedIn = Boolean(state.token && state.user);
    $("nav-login").hidden = loggedIn;
    $("nav-signup").hidden = loggedIn;
    $("nav-logout").hidden = !loggedIn;
    $("nav-history").hidden = !loggedIn;
    $("btn-save").hidden = !loggedIn;
  }

  async function loadUser() {
    if (!state.token) { state.user = null; renderAuthState(); return; }
    try {
      state.user = await api("/api/auth/me");
    } catch {
      state.token = null;
      state.user = null;
      localStorage.removeItem("tahqeeq_token");
    }
    renderAuthState();
  }

  function openAuth(mode) {
    state.authMode = mode;
    const isLogin = mode === "login";
    $("auth-title").textContent = isLogin ? "Log in" : "Create an account";
    $("auth-sub").textContent = isLogin
      ? "Save your analyses and come back to them."
      : "Free, and it only takes an email.";
    $("auth-submit").textContent = isLogin ? "Log in" : "Sign up";
    $("auth-switch-text").textContent = isLogin ? "No account?" : "Already have one?";
    $("auth-switch").textContent = isLogin ? "Sign up" : "Log in";
    $("auth-hint").hidden = isLogin;
    $("auth-password").autocomplete = isLogin ? "current-password" : "new-password";
    clearError($("auth-error"));
    $("form-auth").reset();
    showView("auth");
  }

  $("nav-login").addEventListener("click", () => openAuth("login"));
  $("nav-signup").addEventListener("click", () => openAuth("signup"));
  $("auth-switch").addEventListener("click", () => {
    openAuth(state.authMode === "login" ? "signup" : "login");
  });

  $("nav-logout").addEventListener("click", () => {
    state.token = null;
    state.user = null;
    localStorage.removeItem("tahqeeq_token");
    renderAuthState();
    toast("Logged out");
    showView("analyse");
  });

  $("form-auth").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("auth-submit");
    const errorBox = $("auth-error");
    clearError(errorBox);

    const email = $("auth-email").value.trim();
    const password = $("auth-password").value;

    button.disabled = true;
    button.textContent = "Working…";
    try {
      const path = state.authMode === "login" ? "/api/auth/login" : "/api/auth/register";
      const result = await api(path, {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      state.token = result.access_token;
      localStorage.setItem("tahqeeq_token", state.token);
      await loadUser();
      toast(state.authMode === "login" ? "Welcome back" : "Account created");
      showView("analyse");
    } catch (error) {
      showError(errorBox, error.message);
    } finally {
      button.disabled = false;
      button.textContent = state.authMode === "login" ? "Log in" : "Sign up";
    }
  });

  // ── tabs ───────────────────────────────────────────────────
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => {
        t.classList.remove("is-active");
        t.setAttribute("aria-selected", "false");
      });
      tab.classList.add("is-active");
      tab.setAttribute("aria-selected", "true");
      const which = tab.dataset.tab;
      $("form-text").hidden = which !== "text";
      $("form-url").hidden = which !== "url";
      clearError($("error-box"));
    });
  });

  // ── character counter ──────────────────────────────────────
  $("input-text").addEventListener("input", (event) => {
    $("char-count").textContent = event.target.value.length.toLocaleString();
  });

  // ── sample ─────────────────────────────────────────────────
  const SAMPLE_HEADLINE = "Inflation eases to 4.2 percent in October";
  const SAMPLE_TEXT = `ISLAMABAD — The Ministry of Finance said on Monday that inflation eased to 4.2 percent in October, down from 5.1 percent the previous month, according to data released by the Pakistan Bureau of Statistics.

"The decline reflects lower food prices and a stable rupee," said a spokesperson for the ministry in a statement. The bureau reported that food inflation fell 1.8 percentage points, while core inflation, which excludes food and energy, was roughly unchanged at 6.4 percent.

Economists cautioned that the improvement may be temporary. "One month does not make a trend," said Dr. Ayesha Khan, an economist at the Lahore School of Economics, in an interview with Reuters. She noted that the figures could be revised next quarter.

The State Bank of Pakistan is expected to review its policy rate at its next meeting on 2 December. Analysts surveyed by Bloomberg estimated a 50 basis point cut is likely, though the central bank declined to comment.`;

  $("btn-sample").addEventListener("click", () => {
    $("input-headline").value = SAMPLE_HEADLINE;
    $("input-text").value = SAMPLE_TEXT;
    $("char-count").textContent = SAMPLE_TEXT.length.toLocaleString();
    $("input-text").focus();
  });

  // ── analyse ────────────────────────────────────────────────
  $("form-text").addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = $("error-box");
    clearError(errorBox);

    const text = $("input-text").value.trim();
    const headline = $("input-headline").value.trim();

    if (text.length < 80) {
      showError(errorBox, "Paste at least 80 characters — there is nothing to judge below that.");
      return;
    }

    const button = $("btn-analyse");
    button.disabled = true;
    button.textContent = "Analysing…";
    try {
      const payload = { text, headline };
      const result = await api("/api/analyses/preview", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.lastResult = result;
      state.lastPayload = payload;
      renderResult(result);
      showView("result");
    } catch (error) {
      showError(errorBox, error.message);
    } finally {
      button.disabled = false;
      button.textContent = "Analyse";
    }
  });

  $("form-url").addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = $("error-box");
    clearError(errorBox);

    const url = $("input-url").value.trim();
    if (!url) return;

    const button = $("btn-analyse-url");
    button.disabled = true;
    button.textContent = "Fetching…";
    try {
      // Logged in: save it. Anonymous: score it without storing anything.
      if (state.token) {
        const saved = await api("/api/analyses/from-url", {
          method: "POST",
          body: JSON.stringify({ url }),
        });
        state.lastResult = saved.result;
        state.lastPayload = null;
        renderResult(saved.result);
        showView("result");
        toast("Saved to history");
      } else {
        const fetched = await api("/api/analyses/preview-url", {
          method: "POST",
          body: JSON.stringify({ url }),
        });
        state.lastResult = fetched;
        state.lastPayload = null;
        renderResult(fetched);
        showView("result");
      }
    } catch (error) {
      showError(errorBox, error.message);
    } finally {
      button.disabled = false;
      button.textContent = "Fetch & analyse";
    }
  });

  // ── render result ──────────────────────────────────────────
  function scoreClass(score) {
    if (score >= 70) return "good";
    if (score >= 45) return "mid";
    return "bad";
  }

  function renderResult(result) {
    const score = Math.round(result.score);
    $("score-number").textContent = score;
    $("score-number").style.color =
      score >= 70 ? "var(--accent)" : score >= 45 ? "var(--warn)" : "var(--bad)";

    $("band-pill").textContent = result.band.label;
    $("band-desc").textContent = result.band.description;
    $("confidence-line").textContent = `Confidence: ${result.confidence.label} — ${result.confidence.reason}`;

    const fill = $("score-fill");
    fill.style.width = "0%";
    requestAnimationFrame(() => { fill.style.width = `${score}%`; });

    // concerns / strengths
    const applied = result.signals.filter((s) => s.applies);
    const byScore = [...applied].sort((a, b) => a.score - b.score);
    const concerns = byScore.slice(0, 3);
    const strengths = [...applied].sort((a, b) => b.score - a.score).slice(0, 3);

    const concernList = $("concerns");
    concernList.innerHTML = "";
    concerns.forEach((signal) => {
      const li = el("li");
      li.appendChild(el("strong", null, `${signal.label} (${Math.round(signal.score)})`));
      li.appendChild(document.createTextNode(` — ${signal.summary}`));
      concernList.appendChild(li);
    });

    const strengthList = $("strengths");
    strengthList.innerHTML = "";
    strengths.forEach((signal) => {
      const li = el("li");
      li.appendChild(el("strong", null, `${signal.label} (${Math.round(signal.score)})`));
      li.appendChild(document.createTextNode(` — ${signal.summary}`));
      strengthList.appendChild(li);
    });

    // signals
    const container = $("signals");
    container.innerHTML = "";
    result.signals.forEach((signal) => {
      const wrapper = el("div", "signal");

      const head = el("button", "signal-head");
      head.type = "button";
      head.setAttribute("aria-expanded", "false");

      const name = el("span", "signal-name", signal.label);
      if (!signal.applies) name.appendChild(el("span", "signal-na", "  not applicable"));

      const scoreBadge = el(
        "span",
        `signal-score ${signal.applies ? scoreClass(signal.score) : "na"}`,
        signal.applies ? String(Math.round(signal.score)) : "n/a"
      );

      head.appendChild(name);
      head.appendChild(scoreBadge);
      head.appendChild(el("span", "signal-chev", "▶"));

      const body = el("div", "signal-body");
      body.appendChild(el("p", "signal-summary", signal.summary));
      body.appendChild(
        el("div", "signal-weight", `Weight in the total score: ${(signal.weight * 100).toFixed(0)}%`)
      );

      if (signal.evidence && signal.evidence.length) {
        const evidenceWrap = el("div", "evidence");
        signal.evidence.forEach((item) => {
          const block = el("div", "evidence-item");
          block.appendChild(el("span", "evidence-label", item.label));
          block.appendChild(el("div", "evidence-detail", item.detail));
          if (item.span) block.appendChild(el("code", "evidence-span", item.span));
          evidenceWrap.appendChild(block);
        });
        body.appendChild(evidenceWrap);
      }

      head.addEventListener("click", () => {
        const open = wrapper.classList.toggle("is-open");
        head.setAttribute("aria-expanded", open ? "true" : "false");
      });

      wrapper.appendChild(head);
      wrapper.appendChild(body);
      container.appendChild(wrapper);
    });

    // stats
    const stats = result.stats;
    const statDefs = [
      ["Words", stats.word_count],
      ["Sentences", stats.sentence_count],
      ["Paragraphs", stats.paragraph_count],
      ["Avg words / sentence", stats.avg_sentence_words],
      ["Avg word length", stats.avg_word_length],
      ["Unique word ratio", stats.unique_word_ratio],
      ["Exclamations", stats.exclamation_count],
      ["Shouted words", stats.all_caps_count],
      ["Numbers", stats.number_count],
    ];
    const statsWrap = $("stats");
    statsWrap.innerHTML = "";
    statDefs.forEach(([label, value]) => {
      const box = el("div", "stat");
      box.appendChild(el("span", "stat-value", String(value)));
      box.appendChild(el("span", "stat-label", label));
      statsWrap.appendChild(box);
    });
  }

  // ── back / copy / save ─────────────────────────────────────
  $("btn-back").addEventListener("click", () => showView("analyse"));

  $("btn-copy").addEventListener("click", async () => {
    if (!state.lastResult) return;
    const r = state.lastResult;
    const lines = [
      `Tahqeeq — ${Math.round(r.score)}/100 (${r.band.label})`,
      `Confidence: ${r.confidence.label}`,
      "",
      "Signals:",
      ...r.signals
        .filter((s) => s.applies)
        .map((s) => `  ${s.label}: ${Math.round(s.score)} — ${s.summary}`),
      "",
      "This measures how the text is written, not whether its claims are true.",
    ];
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      toast("Summary copied");
    } catch {
      toast("Could not copy — your browser blocked it");
    }
  });

  $("btn-save").addEventListener("click", async () => {
    if (!state.lastPayload) {
      toast("This one is already saved");
      return;
    }
    const button = $("btn-save");
    button.disabled = true;
    try {
      await api("/api/analyses", {
        method: "POST",
        body: JSON.stringify(state.lastPayload),
      });
      state.lastPayload = null;
      toast("Saved to history");
    } catch (error) {
      toast(error.message);
    } finally {
      button.disabled = false;
    }
  });

  // ── history ────────────────────────────────────────────────
  $("nav-history").addEventListener("click", async () => {
    showView("history");
    const list = $("history-list");
    const empty = $("history-empty");
    list.innerHTML = "";
    empty.hidden = true;

    try {
      const data = await api("/api/analyses?limit=50");
      if (!data.items.length) {
        empty.hidden = false;
        return;
      }
      data.items.forEach((item) => {
        const row = el("button", "history-item");
        row.type = "button";

        const score = el("span", "history-score", String(Math.round(item.score)));
        score.style.color =
          item.score >= 70 ? "var(--accent)" : item.score >= 45 ? "var(--warn)" : "var(--bad)";

        const body = el("span", "history-body");
        body.appendChild(el("span", "history-title", item.title || "Untitled"));
        const when = new Date(item.created_at).toLocaleString();
        body.appendChild(
          el("span", "history-meta", `${item.word_count} words · ${when}`)
        );

        const del = el("button", "history-del", "×");
        del.type = "button";
        del.title = "Delete";
        del.addEventListener("click", async (event) => {
          event.stopPropagation();
          try {
            await api(`/api/analyses/${item.id}`, { method: "DELETE" });
            row.remove();
            toast("Deleted");
            if (!list.children.length) empty.hidden = false;
          } catch (error) {
            toast(error.message);
          }
        });

        row.appendChild(score);
        row.appendChild(body);
        row.appendChild(del);

        row.addEventListener("click", async () => {
          try {
            const full = await api(`/api/analyses/${item.id}`);
            state.lastResult = full.result;
            state.lastPayload = null;
            renderResult(full.result);
            showView("result");
          } catch (error) {
            toast(error.message);
          }
        });

        list.appendChild(row);
      });
    } catch (error) {
      toast(error.message);
    }
  });

  $("nav-analyse").addEventListener("click", () => showView("analyse"));

  // ── boot ───────────────────────────────────────────────────
  loadUser();
})();
