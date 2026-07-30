<script>
  import { goto } from "$app/navigation";
  import { env } from "$env/dynamic/public";

  let { data } = $props();
  let dialog = $state(null);
  let email = $state("");
  let website = $state("");
  let creating = $state(false);
  let error = $state("");

  const sitekey = env.PUBLIC_TURNSTILE_SITEKEY ?? "";

  async function createSystem(event) {
    event.preventDefault();
    creating = true;
    error = "";
    const turnstileToken = sitekey
      ? (document.querySelector('[name="cf-turnstile-response"]')?.value ?? "")
      : "";
    const response = await fetch("/api/v1/systems", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email, website, turnstile_token: turnstileToken }),
    });
    const body = await response.json();
    creating = false;
    if (!response.ok) {
      error = body.detail ?? "creation failed";
      return;
    }
    localStorage.setItem(`wmt26-token-${body.id}`, body.token);
    goto(`/system/${body.id}`);
  }

  const metrics = [
    { key: "chrf_doc", label: "chrF++ (doc)", format: (v) => v.toFixed(1) },
    { key: "chrf_para", label: "chrF++ (para)", format: (v) => v.toFixed(1) },
    { key: "exact_term_success", label: "Exact Term Success", format: (v) => (v * 100).toFixed(1) + "%" },
    { key: "lemma_term_success", label: "Lemmatized Term Success", format: (v) => (v * 100).toFixed(1) + "%" },
    { key: "judge_score", label: "LLM Judge", format: (v) => v.toFixed(1) },
  ];

  const cell = (row, metric, directions) => ({
    overall: row.overall?.[metric.key] ?? null,
    perDirection: directions.map((d) => row.directions?.[d]?.[metric.key] ?? null),
  });

  const sortKey = (row) =>
    row.overall?.lemma_term_success ??
    row.overall?.exact_term_success ??
    Math.max(...Object.values(row.directions ?? {}).map((b) => b.lemma_term_success ?? b.exact_term_success ?? 0), 0);

  const trackRows = $derived(
    [1, 2].map((track) => ({
      track,
      directions: data.meta?.track_directions?.[track] ?? [],
      rows: (data.leaderboard ?? []).filter(
        (row) => row.track === track && row.mode === (track === 1 ? "proper" : "sample")
      ),
    }))
  );
</script>

<svelte:head>
  {#if sitekey}
    <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>
  {/if}
</svelte:head>

<div class="mb-8 flex items-center justify-between">
  <div>
    <h1 class="text-2xl font-bold">Leaderboard</h1>
    <p class="text-sm opacity-70">Document-level MT with terminology guidance</p>
  </div>
  <button class="btn btn-primary" onclick={() => dialog?.showModal()}>Add your system</button>
</div>

{#each trackRows as { track, rows, directions } (track)}
  <div class="card mb-8 bg-base-100 shadow-sm">
    <div class="card-body">
      <h2 class="card-title">
        {track === 1
          ? "Track №1: Document-Level Translation with Explicit Dictionary"
          : "Track №2: Document-Level Translation with Sample Bitexts"}
      </h2>
      <p class="text-xs opacity-60">scored on the {track === 1 ? "proper" : "sample"} mode translations</p>
      {#if rows.length === 0}
        <p class="text-sm opacity-60">No scored systems yet.</p>
      {:else}
        <div class="overflow-x-auto">
          <table class="table table-zebra table-sm">
            <thead>
              <tr>
                <th>system</th>
                {#each metrics as metric (metric.key)}
                  <th>
                    {metric.label}
                    <div class="text-[0.65em] font-normal opacity-60">[{directions.join(", ")}]</div>
                  </th>
                {/each}
              </tr>
            </thead>
            <tbody>
              {#each rows.toSorted((a, b) => sortKey(b) - sortKey(a)) as row (row.system)}
                <tr>
                  <td class="font-medium">{row.system}</td>
                  {#each metrics as metric (metric.key)}
                    {@const c = cell(row, metric, directions)}
                    <td>
                      {#if c.overall != null}
                        <div>{metric.format(c.overall)}</div>
                      {/if}
                      <div class="text-[0.65em] opacity-80">
                        [{c.perDirection.map((v) => (v != null ? metric.format(v) : "-")).join(", ")}]
                      </div>
                    </td>
                  {/each}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </div>
  </div>
{/each}

<dialog class="modal" bind:this={dialog}>
  <div class="modal-box">
    <h3 class="mb-4 text-lg font-bold">Add your system</h3>
    <p class="mb-3 text-sm opacity-70">
      Your system name is read automatically from your first uploaded file
      (<code>{"{system}"}.{"{mode}"}.{"{domain}"}.{"{direction}"}.json</code>).
    </p>
    <form onsubmit={createSystem} class="flex flex-col gap-3">
      <label class="form-control">
        <span class="label-text mb-1">Contact email</span>
        <input class="input input-bordered" type="email" bind:value={email} required />
      </label>
      <input class="hidden" tabindex="-1" autocomplete="off" bind:value={website} name="website" />
      {#if sitekey}
        <div class="cf-turnstile" data-sitekey={sitekey}></div>
      {/if}
      {#if error}
        <div class="alert alert-error text-sm">{error}</div>
      {/if}
      <div class="modal-action">
        <button type="button" class="btn btn-ghost" onclick={() => dialog?.close()}>Cancel</button>
        <button type="submit" class="btn btn-primary" disabled={creating}>
          {creating ? "Creating..." : "Create"}
        </button>
      </div>
    </form>
  </div>
</dialog>
