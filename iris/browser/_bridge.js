(() => {
  if (window.__irisBrowser) return;

  function textOf(el) {
    return (el.innerText || el.textContent || el.getAttribute("aria-label") || "").trim();
  }

  function matchesText(el, text, exact) {
    const t = textOf(el);
    if (!t) return false;
    return exact ? t === text : t.toLowerCase().includes(String(text).toLowerCase());
  }

  function resolve(target) {
    if (!target || typeof target !== "object") return null;
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

  function landmarks() {
    const out = [];
    const nodes = document.querySelectorAll("a[href], button, [role='button'], h1, h2, input, textarea");
    for (const el of nodes) {
      if (out.length >= 40) break;
      const name = textOf(el) || el.getAttribute("placeholder") || el.getAttribute("name") || "";
      if (!name) continue;
      const role =
        el.tagName === "A"
          ? "link"
          : el.tagName === "BUTTON" || el.getAttribute("role") === "button"
            ? "button"
            : el.tagName === "INPUT" || el.tagName === "TEXTAREA"
              ? "textbox"
              : el.tagName.toLowerCase();
      const r = el.getBoundingClientRect();
      out.push({
        role,
        name: String(name).slice(0, 120),
        bbox: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
      });
    }
    return out;
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
      return {
        url: String(location.href || ""),
        title: String(document.title || ""),
        scrollX: Math.round(window.scrollX || 0),
        scrollY: Math.round(window.scrollY || 0),
        readyState: String(document.readyState || ""),
        landmarks: landmarks(),
      };
    },
  };
})();
