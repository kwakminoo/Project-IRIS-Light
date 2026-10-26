(() => {
  if (window.__irisBrowser && window.__irisBrowser.mediaState) return;

  function textOf(el) {
    return (el.innerText || el.textContent || el.getAttribute("aria-label") || "").trim();
  }

  function matchesText(el, text, exact) {
    const t = textOf(el);
    if (!t) return false;
    return exact ? t === text : t.toLowerCase().includes(String(text).toLowerCase());
  }

  let lastEls = [];

  function inViewport(el) {
    const r = el.getBoundingClientRect();
    const vh = window.innerHeight || 0;
    const vw = window.innerWidth || 0;
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
  }

  function inArticle(el) {
    return !!(el.closest && el.closest("article, [role='article'], main, [role='main']"));
  }

  function resolve(target) {
    if (!target || typeof target !== "object") return null;
    if (target.kind === "ref") {
      const index = Number(target.index);
      if (!Number.isInteger(index) || index < 0) return null;
      return lastEls[index] || null;
    }
    const nth = Math.max(0, Number(target.nth) || 0);
    if (target.kind === "css") {
      const list = Array.from(document.querySelectorAll(target.css || ""));
      return list[nth] || null;
    }
    if (target.kind === "text") {
      const candidates = Array.from(
        document.querySelectorAll("a, button, [role='button'], input, textarea, [onclick], summary")
      ).filter((el) => matchesText(el, target.text || "", !!target.exact));
      return candidates[nth] || null;
    }
    if (target.kind === "role") {
      const role = String(target.role || "").toLowerCase();
      let list = [];
      if (role === "link") list = Array.from(document.querySelectorAll("a[href]"));
      else if (role === "button") {
        list = Array.from(document.querySelectorAll("button, [role='button'], input[type='submit']"));
      } else if (role === "textbox" || role === "searchbox") {
        list = Array.from(document.querySelectorAll("input, textarea, [contenteditable='true']"));
      } else {
        list = Array.from(document.querySelectorAll(`[role='${role}']`));
      }
      if (target.name) {
        list = list.filter((el) => matchesText(el, target.name, !!target.exact));
      }
      return list[nth] || null;
    }
    return null;
  }

  function collectNodes() {
    const raw = Array.from(
      document.querySelectorAll("a[href], button, [role='button'], h1, h2, input, textarea, [role='link']")
    );
    raw.sort((a, b) => {
      const av = inViewport(a) ? 0 : 1;
      const bv = inViewport(b) ? 0 : 1;
      if (av !== bv) return av - bv;
      const aa = inArticle(a) ? 0 : 1;
      const ba = inArticle(b) ? 0 : 1;
      if (aa !== ba) return aa - ba;
      return 0;
    });
    const out = [];
    lastEls = [];
    for (const el of raw) {
      if (out.length >= 40) break;
      const name = textOf(el) || el.getAttribute("placeholder") || el.getAttribute("name") || "";
      if (!name) continue;
      const heading = el.tagName === "H1" || el.tagName === "H2";
      const role =
        el.tagName === "A" || el.getAttribute("role") === "link"
          ? "link"
          : el.tagName === "BUTTON" || el.getAttribute("role") === "button"
            ? "button"
            : el.tagName === "INPUT" || el.tagName === "TEXTAREA"
              ? "textbox"
              : el.tagName.toLowerCase();
      out.push({
        role,
        name: String(name).slice(0, 80),
        interactive: !heading,
        index: out.length,
      });
      lastEls.push(el);
    }
    return out;
  }

  function excerptText() {
    const root =
      document.querySelector("article, [role='article'], main, [role='main']") || document.body;
    const t = (root && root.innerText) || "";
    return String(t).replace(/\s+/g, " ").trim().slice(0, 800);
  }

  function extract(opts) {
    const options = opts || {};
    const maxChars = Math.max(1, Math.min(Number(options.maxChars) || 4000, 8000));
    let root = null;
    if (typeof options.index === "number" && lastEls[options.index]) {
      root = lastEls[options.index];
    } else if (options.scope === "document") {
      root = document.body;
    } else {
      root = document.querySelector("article, [role='article'], main, #content") || document.body;
    }
    const t = (root && root.innerText) || "";
    return { ok: true, text: String(t).replace(/\s+/g, " ").trim().slice(0, maxChars) };
  }

  function pageBlock() {
    const href = String(location.href || "").toLowerCase();
    const title = String(document.title || "").toLowerCase();
    if (href.includes("/sorry/")) return "captcha";
    if (href.includes("consent.youtube.") || href.includes("consent.google.")) return "consent";
    if (title.includes("before you continue")) return "consent";
    if (href.includes("accounts.google.") || href.includes("signin/identifier")) return "signin";
    if (title.includes("sign in to confirm") || title.includes("연령 제한")) return "signin";
    if (href.includes("age-restricted") || title.includes("age-restricted")) return "age";
    return "";
  }

  function adShowing() {
    const player = document.querySelector(".html5-video-player");
    if (player && player.classList.contains("ad-showing")) return true;
    return !!document.querySelector(".ytp-ad-player-overlay, .ytp-ad-module .ytp-ad-player-overlay");
  }

  function firstVideoIdFromData() {
    const data = window.ytInitialData;
    if (!data) return "";
    try {
      const text = JSON.stringify(data);
      const m = text.match(/"videoId":"([a-zA-Z0-9_-]{11})"/);
      return m ? m[1] : "";
    } catch (err) {
      return "";
    }
  }

  function firstWatchUrl() {
    const anchors = Array.from(document.querySelectorAll("a[href]"));
    for (const a of anchors) {
      const href = a.href || a.getAttribute("href") || "";
      if (/[?&]v=[\w-]{11}/.test(href) && href.indexOf("/shorts/") < 0) {
        try {
          return new URL(href, location.origin).href;
        } catch (err) {
          /* keep looking */
        }
      }
    }
    const id = firstVideoIdFromData();
    if (id) return "https://www.youtube.com/watch?v=" + id;
    return "";
  }

  function mediaState() {
    const v = document.querySelector("video");
    if (!v) {
      return {
        playing: false,
        paused: true,
        currentTime: 0,
        readyState: 0,
        block: pageBlock() || "no_video",
        ad: false,
        kind: "",
      };
    }
    const playing = !v.paused && !v.ended && v.readyState > 0;
    return {
      playing,
      paused: !!v.paused,
      currentTime: Number(v.currentTime) || 0,
      readyState: Number(v.readyState) || 0,
      block: pageBlock(),
      ad: adShowing(),
      kind: "video",
    };
  }

  function clickPlayButton() {
    const btn = document.querySelector(
      "button.ytp-large-play-button, button.ytp-play-button, .ytp-large-play-button"
    );
    if (btn) btn.click();
  }

  function playerBox() {
    const el =
      document.querySelector("button.ytp-large-play-button") ||
      document.querySelector("video") ||
      document.querySelector(".html5-video-player");
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)];
  }

  window.__irisBrowser = {
    resolve,
    click(target) {
      const el = resolve(target);
      if (!el) return { ok: false, error: "element not found" };
      el.click();
      return { ok: true };
    },
    type(target, text, clear) {
      const el = resolve(target);
      if (!el) return { ok: false, error: "element not found" };
      el.focus();
      if (clear) {
        if ("value" in el) el.value = "";
        else el.textContent = "";
      }
      if ("value" in el) {
        el.value = (el.value || "") + String(text ?? "");
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        el.textContent = (el.textContent || "") + String(text ?? "");
      }
      return { ok: true };
    },
    scrollBy(dx, dy) {
      window.scrollBy(Number(dx) || 0, Number(dy) || 0);
      return {
        ok: true,
        scrollX: Math.round(window.scrollX || 0),
        scrollY: Math.round(window.scrollY || 0),
      };
    },
    snapshot() {
      const media = mediaState();
      return {
        url: String(location.href || ""),
        title: String(document.title || ""),
        scrollX: Math.round(window.scrollX || 0),
        scrollY: Math.round(window.scrollY || 0),
        readyState: String(document.readyState || ""),
        nodes: collectNodes(),
        excerpt: excerptText(),
        media,
      };
    },
    mediaState,
    extract,
    firstWatchUrl,
    playerBox,
    tryPlay() {
      const blocked = pageBlock();
      if (blocked) return Promise.resolve({ ok: false, error: blocked, block: blocked });
      const deadline = Date.now() + 8000;
      const attempt = (video) => {
        const already = !video.paused && !video.ended && video.readyState > 0;
        if (already) return Promise.resolve({ ok: true, playing: true, ...mediaState() });
        const playOnce = () => {
          const p = video.play();
          if (p && typeof p.then === "function") return p;
          return Promise.resolve();
        };
        return playOnce()
          .catch(() => {
            clickPlayButton();
            const muted = video.muted;
            video.muted = true;
            return playOnce()
              .then(() => {
                video.muted = muted;
                return playOnce();
              })
              .catch((err) => {
                video.muted = muted;
                throw err;
              });
          })
          .then(() => {
            const st = mediaState();
            if (st.playing) return { ok: true, ...st };
            if (Date.now() >= deadline) return { ok: false, error: "autoplay", block: "autoplay", ...st };
            return new Promise((resolve) => setTimeout(() => resolve(attempt(video)), 300));
          })
          .catch((err) => ({
            ok: false,
            error: String(err && err.message ? err.message : err),
            block: "autoplay",
            ...mediaState(),
          }));
      };
      const waitVideo = () => {
        const v = document.querySelector("video");
        if (v) return attempt(v);
        clickPlayButton();
        if (Date.now() >= deadline) {
          return Promise.resolve({ ok: false, error: "no video element", block: "no_video", ...mediaState() });
        }
        return new Promise((resolve) => setTimeout(() => resolve(waitVideo()), 300));
      };
      return waitVideo();
    },
    tryPause() {
      const v = document.querySelector("video");
      if (!v) return { ok: false, error: "no video element", block: "no_video" };
      try {
        v.pause();
      } catch (err) {
        return { ok: false, error: String(err && err.message ? err.message : err) };
      }
      const st = mediaState();
      return { ok: !!st.paused, ...st };
    },
  };
})();
