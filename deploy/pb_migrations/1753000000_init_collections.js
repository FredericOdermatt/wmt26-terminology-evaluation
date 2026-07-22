/// <reference path="../pb_data/types.d.ts" />
// All rules stay null (superuser only): the FastAPI backend is the sole client.
migrate(
  (app) => {
    const autodates = [
      { name: "created", type: "autodate", onCreate: true },
      { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
    ];

    const systems = new Collection({
      name: "systems",
      type: "base",
      fields: [
        { name: "name", type: "text", required: true, max: 32 },
        { name: "email", type: "text", max: 200 },
        { name: "token_hash", type: "text", required: true, max: 64 },
        { name: "blocked", type: "bool" },
        ...autodates,
      ],
      indexes: ["CREATE UNIQUE INDEX idx_systems_name ON systems (name)"],
    });
    app.save(systems);
    const systemsId = app.findCollectionByNameOrId("systems").id;

    const submissionFiles = new Collection({
      name: "submission_files",
      type: "base",
      fields: [
        { name: "system", type: "relation", required: true, collectionId: systemsId, maxSelect: 1, cascadeDelete: true },
        { name: "track", type: "number", required: true },
        { name: "mode", type: "text", required: true, max: 16 },
        { name: "domain", type: "text", required: true, max: 64 },
        { name: "direction", type: "text", required: true, max: 8 },
        { name: "valid", type: "bool" },
        { name: "error", type: "text", max: 1000 },
        { name: "file", type: "file", required: true, maxSelect: 1, maxSize: 15000000 },
        ...autodates,
      ],
      indexes: [
        "CREATE UNIQUE INDEX idx_submission_slot ON submission_files (system, track, mode, domain, direction)",
      ],
    });
    app.save(submissionFiles);

    const evaluations = new Collection({
      name: "evaluations",
      type: "base",
      fields: [
        { name: "system", type: "relation", required: true, collectionId: systemsId, maxSelect: 1, cascadeDelete: true },
        { name: "track", type: "number", required: true },
        { name: "status", type: "text", required: true, max: 16 },
        { name: "stage", type: "text", max: 32 },
        { name: "percentage", type: "number" },
        { name: "error", type: "text", max: 500 },
        ...autodates,
      ],
    });
    app.save(evaluations);

    const scores = new Collection({
      name: "scores",
      type: "base",
      fields: [
        { name: "system", type: "relation", required: true, collectionId: systemsId, maxSelect: 1, cascadeDelete: true },
        { name: "track", type: "number", required: true },
        { name: "domain", type: "text", required: true, max: 64 },
        { name: "direction", type: "text", required: true, max: 8 },
        { name: "mode", type: "text", required: true, max: 16 },
        { name: "metrics", type: "json" },
        ...autodates,
      ],
      indexes: ["CREATE UNIQUE INDEX idx_scores_unit ON scores (system, track, domain, direction, mode)"],
    });
    app.save(scores);
  },
  (app) => {
    for (const name of ["scores", "evaluations", "submission_files", "systems"]) {
      app.delete(app.findCollectionByNameOrId(name));
    }
  }
);
