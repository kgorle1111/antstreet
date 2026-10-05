// The page reads in full without this file: it only adds motion, the lazy demo and two extras.
(() => {
  const root = document.documentElement;
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // The terminal replay starts when its chapter is reached, so its 26-second loop begins on screen.
  const demo = document.querySelector("img[data-src]");
  const loadDemo = () => { if (demo && !demo.src) demo.src = demo.dataset.src; };

  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      e.target.classList.add("in");
      if (e.target.contains(demo)) loadDemo();
      io.unobserve(e.target);
    }
  }, { threshold: 0.2 });
  document.querySelectorAll(".reveal").forEach((el) => io.observe(el));
  if (still) loadDemo();

  if (!still) {
    root.classList.add("motion");
    const scenes = [...document.querySelectorAll("[data-scene]")];
    let queued = false;
    const frame = () => {
      queued = false;
      const vh = innerHeight;
      const max = Math.max(root.scrollHeight - vh, 1);
      root.style.setProperty("--y", String(scrollY));
      root.style.setProperty("--page", (scrollY / max).toFixed(4));
      for (const s of scenes) {
        const r = s.getBoundingClientRect();
        // 0 when the scene top is 60% down the screen, 1 when a pinned stage is about to scroll away.
        const k = Math.min(1, Math.max(0, (vh * 0.6 - r.top) / Math.max(r.height - vh * 0.4, 1)));
        s.style.setProperty("--k", k.toFixed(3));
        s.classList.toggle("late", k > 0.5);
      }
    };
    const queue = () => { if (!queued) { queued = true; requestAnimationFrame(frame); } };
    addEventListener("scroll", queue, { passive: true });
    addEventListener("resize", queue);
    frame();
  }

  // Optional launch video: the slot stays hidden unless the file is really there.
  fetch("assets/brag.mp4", { method: "HEAD" })
    .then((r) => { if (r.ok) document.getElementById("video").hidden = false; })
    .catch(() => {});

  // Copy button for the quickstart; hidden where the clipboard API is missing.
  for (const btn of document.querySelectorAll("[data-copy]")) {
    if (!navigator.clipboard) continue;
    btn.hidden = false;
    btn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(document.getElementById(btn.dataset.copy).innerText);
        btn.textContent = "Copied";
      } catch {
        btn.textContent = "Select and copy";
      }
      setTimeout(() => { btn.textContent = "Copy"; }, 2000);
    });
  }
})();
