/* DrawQuest — small progressive-enhancement layer. The site works without it. */
(() => {
  "use strict";
  document.documentElement.classList.add("js");
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Mobile nav
  const toggle = $(".nav-toggle");
  const links = $("#navLinks");
  if (toggle && links) {
    toggle.addEventListener("click", () => {
      const open = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open);
    });
  }

  // Toasts auto-dismiss
  $$(".toast").forEach((t, i) => {
    setTimeout(() => {
      t.classList.add("leaving");
      setTimeout(() => t.remove(), 450);
    }, 4500 + i * 600);
  });

  // Scroll reveal (staggered within each parent)
  const items = $$(".reveal");
  if ("IntersectionObserver" in window && !reduce) {
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      }),
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    items.forEach((el, i) => {
      el.style.setProperty("--d", `${(i % 6) * 70}ms`);
      io.observe(el);
    });
  } else {
    items.forEach((el) => el.classList.add("in"));
  }

  // Count-up numbers
  const fmt = (n, d) => n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
  $$("[data-count]").forEach((el) => {
    const target = parseFloat(el.dataset.count);
    const d = parseInt(el.dataset.decimals || "0", 10);
    if (isNaN(target) || reduce) { if (!isNaN(target)) el.textContent = fmt(target, d); return; }
    const run = () => {
      const t0 = performance.now(), dur = 1200;
      const tick = (now) => {
        const p = Math.min((now - t0) / dur, 1);
        el.textContent = fmt(target * (1 - Math.pow(1 - p, 3)), d);
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    };
    if ("IntersectionObserver" in window) {
      const o = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { run(); o.disconnect(); } }));
      o.observe(el);
    } else run();
  });

  // Cursor spotlight on cards
  document.addEventListener("pointermove", (e) => {
    const card = e.target.closest && e.target.closest(".card");
    if (!card) return;
    const r = card.getBoundingClientRect();
    card.style.setProperty("--mx", `${e.clientX - r.left}px`);
    card.style.setProperty("--my", `${e.clientY - r.top}px`);
  }, { passive: true });

  // Drag & drop upload with live preview
  $$("[data-dropzone]").forEach((zone) => {
    const input = $("input[type=file]", zone);
    const preview = $(".dz-preview", zone);
    if (!input || !preview) return;
    const show = () => {
      const f = input.files && input.files[0];
      if (!f || !f.type.startsWith("image/")) { zone.classList.remove("has-file"); preview.hidden = true; return; }
      preview.src = URL.createObjectURL(f);
      preview.hidden = false;
      zone.classList.add("has-file");
    };
    input.addEventListener("change", show);
    ["dragenter", "dragover"].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("is-over"); }));
    ["dragleave", "drop"].forEach((ev) => zone.addEventListener(ev, () => zone.classList.remove("is-over")));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      if (e.dataTransfer && e.dataTransfer.files.length) { input.files = e.dataTransfer.files; show(); }
    });
  });

  // Copy-to-clipboard buttons (e.g. wallet address)
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-copy]");
    if (!btn) return;
    const text = btn.dataset.copy;
    const done = () => {
      const old = btn.textContent;
      btn.textContent = "Copied ✓";
      setTimeout(() => { btn.textContent = old; }, 1800);
    };
    try {
      await navigator.clipboard.writeText(text);
      done();
    } catch (_) {
      // Fallback for older browsers / non-secure contexts
      const ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); done(); } catch (__) { /* user can still select the text */ }
      ta.remove();
    }
  });

  // Confirm dialogs for sensitive buttons
  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-confirm]");
    if (el && !confirm(el.dataset.confirm)) e.preventDefault();
  });

  // Prevent double submits
  $$("form").forEach((f) => f.addEventListener("submit", () => {
    setTimeout(() => $$("button[type=submit]", f).forEach((b) => { b.disabled = true; b.style.opacity = ".6"; }), 0);
  }));
})();
