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

  const trackRows = $derived(
    [1, 2].map((track) => ({
      track,
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

{#each trackRows as { track, rows } (track)}
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
                <th>chrF++ (doc)</th>
                <th>chrF++ (para)</th>
                <th>Exact Term Success</th>
                <th>Lemmatized Term Success</th>
              </tr>
            </thead>
            <tbody>
              {#each rows.toSorted((a, b) => (b.lemma_term_success ?? b.exact_term_success ?? 0) - (a.lemma_term_success ?? a.exact_term_success ?? 0)) as row (row.system)}
                <tr>
                  <td class="font-medium">{row.system}</td>
                  <td>{row.chrf_doc ?? "-"}</td>
                  <td>{row.chrf_para ?? "-"}</td>
                  <td>{row.exact_term_success != null ? (row.exact_term_success * 100).toFixed(1) + "%" : "-"}</td>
                  <td>{row.lemma_term_success != null ? (row.lemma_term_success * 100).toFixed(1) + "%" : "-"}</td>
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
