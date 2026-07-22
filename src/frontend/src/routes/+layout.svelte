<script>
  import "../app.css";
  let { children } = $props();
</script>

<div class="min-h-screen bg-base-200">
  <div class="navbar bg-base-100 shadow-sm">
    <div class="mx-auto flex w-full max-w-5xl items-center justify-between px-4">
      <a href="/" class="text-lg font-semibold">WMT26 Terminology Shared Task</a>
      <a
        class="link link-hover text-sm opacity-70"
        href="https://www2.statmt.org/wmt26/terminology.html"
        target="_blank"
        rel="noreferrer">task page</a
      >
    </div>
  </div>
  <main class="mx-auto max-w-5xl px-4 py-8">
    {@render children()}
  </main>
</div>
