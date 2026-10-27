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

  function topRect(el) {
    const r = el.getBoundingClientRect();
    let top = r.top;
    let left = r.left;
    let win = el.ownerDocument && el.ownerDocument.defaultView;
    while (win && win !== window) {
      const frame = win.frameElement;
      if (!frame) break;
      const fr = frame.getBoundingClientRect();
      top += fr.top;
      left += fr.left;
      win = frame.ownerDocument && frame.ownerDocument.defaultView;
    }
    return { top, left, bottom: top + r.height, right: left + r.width, width: r.width, height: r.height };
  }

  function inViewport(el) {
    const r = topRect(el);
    const vh = window.innerHeight || 0;
    const vw = window.innerWidth || 0;
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
  }

  function frameDoc(iframe) {
    try {
      return iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document) || null;
    } catch (err) {
      // SecurityError on contentDocument is why cross-origin frames stay unreachable.
      return null;
    }
  }

  function frameOrigin(iframe) {
    try {
      const loc = iframe.contentWindow && iframe.contentWindow.location;
      if (loc && loc.origin) return String(loc.origin);
    } catch (err) {}
    const src = String((iframe.getAttribute && iframe.getAttribute("src")) || iframe.src || "");
    if (!src) return "";
    try {
      return new URL(src, location.href).origin;
    } catch (err2) {
      return "";
    }
  }

  function describeFrame(iframe, id) {
    const doc = frameDoc(iframe);
    const origin = frameOrigin(iframe);
    if (doc) {
      return { id, origin: origin || String(location.origin || ""), reachable: true, reason: "" };
    }
    if (origin && origin !== String(location.origin || "")) {
      return { id, origin, reachable: false, reason: "cross_origin" };
    }
    return { id, origin: origin || "", reachable: false, reason: origin ? "cross_origin" : "opaque" };
  }

  function collectFrames() {
    const frames = [];
    const iframes = Array.from(document.querySelectorAll("iframe"));
    iframes.forEach((iframe, i) => {
      frames.push(describeFrame(iframe, "f" + i));
    });
    return frames;
  }

  function inArticle(el) {
    return !!(el.closest && el.closest("article, [role='article'], main, [role='main']"));
  }

  function resolve(target) {
    if (!target || typeof target !== "object") return null;
    if (target.kind === "ref") {
      const index = Number(target.index);
      if (!Number.isInteger(index) || index < 0) return null;
      const el = lastEls[index] || null;
      if (!el || !el.isConnected) return null;
      return el;
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

  function namedControls(doc) {
    return Array.from(
      doc.querySelectorAll("a[href], button, [role='button'], h1, h2, input, textarea, [role='link']")
    );
  }

  function accName(el) {
    const type = String(el.type || "").toLowerCase();
    const labelled = (el.getAttribute("aria-labelledby") || "").trim();
    if (labelled) {
      const doc = el.ownerDocument || document;
      const parts = labelled.split(/\s+/).map((id) => {
        const node = doc.getElementById(id);
        return node ? textOf(node) : "";
      });
      const joined = parts.join(" ").replace(/\s+/g, " ").trim();
      if (joined) return joined;
    }
    const aria = (el.getAttribute("aria-label") || "").trim();
    if (aria) return aria;
    const doc = el.ownerDocument || document;
    if (el.id) {
      const labels = doc.querySelectorAll("label[for]");
      for (let i = 0; i < labels.length; i++) {
        if (labels[i].htmlFor === el.id) {
          const t = textOf(labels[i]).trim();
          if (t) return t;
        }
      }
    }
    const wrap = el.closest && el.closest("label");
    if (wrap) {
      const t = textOf(wrap).trim();
      if (t) return t;
    }
    const alt = (el.getAttribute("alt") || "").trim();
    if (alt) return alt;
    const img = el.querySelector && el.querySelector("img[alt], input[type='image']");
    if (img) {
      const childAlt = (img.getAttribute("alt") || "").trim();
      if (childAlt) return childAlt;
    }
    const visible = String(el.innerText || el.textContent || "").trim();
    if (visible.length > 1) return visible;
    const title = (el.getAttribute("title") || "").trim();
    if (title) return title;
    if (visible) return visible;
    const placeholder = (el.getAttribute("placeholder") || "").trim();
    if (placeholder) return placeholder;
    const named = (el.getAttribute("name") || "").trim();
    if (named) return named;
    if (el.tagName === "INPUT" && (type === "submit" || type === "button" || type === "reset")) {
      const native = (el.getAttribute("value") || "").trim();
      if (native) return native;
    }
    return "";
  }

  function contextOf(el, ownName) {
    const own = String(ownName || "");
    function take(text) {
      const t = String(text || "").replace(/\s+/g, " ").trim();
      if (!t || t === own) return "";
      return t;
    }
    const fieldset = el.closest && el.closest("fieldset");
    if (fieldset) {
      const legend = fieldset.querySelector("legend");
      const t = take(legend ? textOf(legend) : "");
      if (t) return t;
    }
    const group = el.closest && el.closest("[role='group'], [role='radiogroup']");
    if (group) {
      const labelled = (group.getAttribute("aria-labelledby") || "").trim();
      if (labelled) {
        const gdoc = group.ownerDocument || document;
        const parts = labelled.split(/\s+/).map((id) => {
          const node = gdoc.getElementById(id);
          return node ? textOf(node) : "";
        });
        const t = take(parts.join(" "));
        if (t) return t;
      }
      const t = take(group.getAttribute("aria-label") || "");
      if (t) return t;
    }
    const form = el.closest && el.closest("form");
    if (form) {
      const t = take(form.getAttribute("aria-label") || form.getAttribute("name") || form.id || "");
      if (t) return t;
    }
    const scope =
      (el.closest && el.closest("article, section, form")) ||
      (el.ownerDocument && el.ownerDocument.body);
    if (scope) {
      const headings = scope.querySelectorAll("h1, h2, h3");
      let found = "";
      for (let i = 0; i < headings.length; i++) {
        const heading = headings[i];
        if (heading === el) continue;
        if (heading.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) {
          found = textOf(heading);
        }
      }
      const t = take(found);
      if (t) return t;
    }
    return "";
  }

  function flagState(el) {
    const ariaDisabled = String(el.getAttribute("aria-disabled") || "").toLowerCase();
    const ariaChecked = String(el.getAttribute("aria-checked") || "").toLowerCase();
    const ariaSelected = String(el.getAttribute("aria-selected") || "").toLowerCase();
    const doc = el.ownerDocument || document;
    return {
      disabled: !!(el.disabled || ariaDisabled === "true"),
      checked: !!(el.checked || ariaChecked === "true" || ariaChecked === "mixed"),
      selected: !!(el.selected || ariaSelected === "true"),
      focused: !!(doc.activeElement === el),
    };
  }

  function roleOf(el) {
    const tag = el.tagName;
    if (tag === "A") return "link";
    if (el.getAttribute("role") === "link") return "link";
    if (tag === "BUTTON") return "button";
    if (el.getAttribute("role") === "button") return "button";
    if (tag === "H1" || tag === "H2") return tag.toLowerCase();
    if (tag === "TEXTAREA") return "textbox";
    if (tag === "INPUT") {
      const type = String(el.type || "text").toLowerCase();
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "submit" || type === "button" || type === "reset" || type === "image") return "button";
      return "textbox";
    }
    return tag.toLowerCase();
  }

  function collectNodes() {
    const items = namedControls(document).map((el) => ({ el, frame: "" }));
    const iframes = Array.from(document.querySelectorAll("iframe"));
    iframes.forEach((iframe, i) => {
      const doc = frameDoc(iframe);
      if (!doc) return;
      const frame = "f" + i;
      namedControls(doc).forEach((el) => items.push({ el, frame }));
    });
    items.sort((a, b) => {
      const av = inViewport(a.el) ? 0 : 1;
      const bv = inViewport(b.el) ? 0 : 1;
      if (av !== bv) return av - bv;
      const aa = inArticle(a.el) ? 0 : 1;
      const ba = inArticle(b.el) ? 0 : 1;
      if (aa !== ba) return aa - ba;
      return 0;
    });
    const out = [];
    lastEls = [];
    for (const item of items) {
      if (out.length >= 40) break;
      const el = item.el;
      const type = String(el.type || "").toLowerCase();
      if (el.tagName === "INPUT" && type === "hidden") continue;
      const name = accName(el);
      if (!name) continue;
      const heading = el.tagName === "H1" || el.tagName === "H2";
      const flags = flagState(el);
      out.push({
        role: roleOf(el),
        name: String(name).slice(0, 80),
        interactive: !heading,
        index: out.length,
        frame: item.frame,
        in_view: inViewport(el),
        disabled: flags.disabled,
        checked: flags.checked,
        selected: flags.selected,
        focused: flags.focused,
        context: contextOf(el, name),
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
      if (!el) {
        const miss = target && target.kind === "ref" ? "stale_ref" : "element not found";
        return { ok: false, error: miss };
      }
      el.click();
      return { ok: true };
    },
    type(target, text, clear) {
      const el = resolve(target);
      if (!el) {
        const miss = target && target.kind === "ref" ? "stale_ref" : "element not found";
        return { ok: false, error: miss };
      }
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
    scrollTo(target) {
      const el = resolve(target);
      if (!el) return { ok: false, error: "stale_ref" };
      el.scrollIntoView({ block: "nearest", inline: "nearest" });
      return { ok: true, in_view: inViewport(el) };
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
        frames: collectFrames(),
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
