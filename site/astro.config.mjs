import { defineConfig } from "astro/config";

// GitHub Pages serves the project at /antstreet/. CSS is inlined so the first view needs no
// stylesheet request and its relative font URLs resolve against the page.
export default defineConfig({
  site: "https://kgorle1111.github.io",
  base: "/antstreet",
  trailingSlash: "ignore",
  build: { inlineStylesheets: "always", format: "directory" },
  devToolbar: { enabled: false },
});
