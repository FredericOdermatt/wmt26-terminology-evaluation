<script>
  import { page } from "$app/state";
  import { onMount } from "svelte";

  let system = $state(null);
  let uploadErrors = $state([]);
  let dragOver = $state(false);
  let uploading = $state(false);
  let notFound = $state(false);

  const systemId = page.params.id;
  const token = () => localStorage.getItem(`wmt26-token-${systemId}`) ?? "";

  async function refresh() {
    const response = await fetch(`/api/v1/systems/${systemId}`);
    if (!response.ok) {
      notFound = true;
      return;
    }
    system = await response.json();
  }

  onMount(() => {
    refresh();
    // Poll while an evaluation is queued or running (grid + progress in one call).
    const interval = setInterval(() => {
      if (system?.evaluations?.some((e) => e.status === "QUEUED" || e.status === "RUNNING")) refresh();
    }, 1000);
    return () => clearInterval(interval);
  });

  async function uploadFiles(files) {
    uploading = true;
    uploadErrors = [];
    for (const file of files) {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch(`/api/v1/systems/${systemId}/files`, {
        method: "POST",
        headers: { authorization: `Bearer ${token()}` },
        body: form,
      });
      const body = await response.json();
      if (!response.ok) {
        uploadErrors = [...uploadErrors, `${file.name}: ${body.detail ?? "upload failed"}`];
      } else {
        if (!body.accepted) uploadErrors = [...uploadErrors, `${file.name}: ${body.error}`];
        system = body.system;
      }
    }
    uploading = false;
  }

  function onDrop(event) {
    event.preventDefault();
    dragOver = false;
    uploadFiles([...event.dataTransfer.files]);
  }

  // ETA assumes a ~50 min full evaluation, scaled by remaining percentage.
  const etaMinutes = (percentage) => Math.max(1, Math.ceil((50 * (100 - percentage)) / 100));

  const tracks = $derived(
    system
      ? [1, 2].map((track) => ({
          track,
          slots: system.slots.filter((slot) => slot.track === track),
          evaluation: system.evaluations.findLast((e) => e.track === track),
        }))
      : []
  );
</script>

{#if notFound}
  <div class="alert alert-error">Unknown system.</div>
{:else if system}
  <h1 class="mb-1 text-2xl font-bold">{system.pending ? "New system" : system.name}</h1>
  {#if system.pending}
    <p class="mb-6 text-sm opacity-70">
      Upload your files named <code>{"{system}"}.{"{mode}"}.{"{domain}"}.{"{direction}"}.json</code> —
      your system name is read from the first file. Files are validated immediately;
      scoring starts once a track is complete.
    </p>
  {:else}
    <p class="mb-6 text-sm opacity-70">
      Upload your files named <code>{system.name}.{"{mode}"}.{"{domain}"}.{"{direction}"}.json</code>.
      Files are validated immediately; scoring starts once a track is complete.
    </p>
  {/if}

  <label
    class="mb-8 flex h-32 cursor-pointer items-center justify-center rounded-lg border-2 border-dashed transition-colors
      {dragOver ? 'border-primary bg-primary/10' : 'border-base-300 bg-base-100'}"
    ondragover={(e) => {
      e.preventDefault();
      dragOver = true;
    }}
    ondragleave={() => (dragOver = false)}
    ondrop={onDrop}
  >
    <input
      type="file"
      class="hidden"
      multiple
      accept=".json"
      onchange={(e) => uploadFiles([...e.target.files])}
    />
    <span class="text-sm opacity-70">
      {uploading ? "Uploading…" : "Drop your .json files here or click to select"}
    </span>
  </label>

  {#if uploadErrors.length}
    <div class="alert alert-warning mb-6 block text-sm">
      {#each uploadErrors as message (message)}
        <div>{message}</div>
      {/each}
    </div>
  {/if}

  {#each tracks as { track, slots, evaluation } (track)}
    <div class="card mb-8 bg-base-100 shadow-sm">
      <div class="card-body">
        <div class="flex items-center justify-between">
          <h2 class="card-title">Track {track}</h2>
          <span class="text-sm opacity-70">
            {slots.filter((s) => s.status === "valid").length}/{slots.length} files
          </span>
        </div>
        {#if evaluation}
          <div class="mb-2 flex items-center gap-3 text-sm">
            <span class="badge {evaluation.status === 'DONE' ? 'badge-success' : evaluation.status === 'FAILED' ? 'badge-error' : 'badge-info'}">
              {evaluation.status}
            </span>
            {#if evaluation.status === "RUNNING" || evaluation.status === "QUEUED"}
              <svg class="working-ring" viewBox="0 0 24 24" aria-label="scoring in progress">
                <circle cx="12" cy="12" r="10" fill="none" stroke-width="2.5" stroke-linecap="round" />
              </svg>
              <progress class="progress progress-primary w-48" value={evaluation.percentage} max="100"></progress>
              <span class="opacity-70">
                {evaluation.percentage}% ({evaluation.stage}) — ~{etaMinutes(evaluation.percentage)} min remaining
              </span>
            {:else if evaluation.status === "FAILED"}
              <span class="opacity-70">{evaluation.error}</span>
            {/if}
          </div>
          {#if evaluation.status === "RUNNING" || evaluation.status === "QUEUED"}
            <p class="mb-2 text-xs opacity-60">
              Scoring runs on the server — you can close this page and come back later.
            </p>
          {/if}
        {/if}
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
          {#each slots as slot (slot.expected_filename)}
            <div
              class="rounded-lg border p-3 text-xs
                {slot.status === 'valid'
                  ? 'border-success/40 bg-success/10'
                  : slot.status === 'invalid'
                    ? 'border-error/40 bg-error/10'
                    : 'border-base-300 bg-base-200 opacity-70'}"
              title={slot.error ?? ""}
            >
              <div class="font-mono break-all">{slot.mode}.{slot.domain}.{slot.direction}</div>
              <div class="mt-1">
                {#if slot.status === "valid"}✓ valid
                {:else if slot.status === "invalid"}✗ {slot.error}
                {:else}missing{/if}
              </div>
            </div>
          {/each}
        </div>
      </div>
    </div>
  {/each}
{:else}
  <span class="loading loading-spinner"></span>
{/if}

<style>
  .working-ring {
    width: 1.4rem;
    height: 1.4rem;
    animation: ring-rotate 1.6s linear infinite;
  }
  .working-ring circle {
    stroke: #7c3aed;
    stroke-dasharray: 1, 62;
    stroke-dashoffset: 0;
    animation: ring-dash 1.4s ease-in-out infinite;
  }
  @keyframes ring-rotate {
    100% {
      transform: rotate(360deg);
    }
  }
  @keyframes ring-dash {
    0% {
      stroke-dasharray: 1, 62;
      stroke-dashoffset: 0;
    }
    50% {
      stroke-dasharray: 44, 62;
      stroke-dashoffset: -12;
    }
    100% {
      stroke-dasharray: 44, 62;
      stroke-dashoffset: -61;
    }
  }
</style>
