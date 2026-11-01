// Public planning metadata. Edit the JSON object; keep IDs stable.
// Steps express order only, never calendar dates, durations or effort.
window.SMARTINI_ROADMAP = {
  "schemaVersion": 2,
  "phases": [
    {
      "id": "p1",
      "title": "01 / Foundation · Delivered"
    },
    {
      "id": "p2",
      "title": "02 / Product Validation & Showcase · Provisional"
    },
    {
      "id": "p3",
      "title": "03 / Groceries-list product · Intentionally undefined"
    },
    {
      "id": "p4",
      "title": "04 / Agent horizons · TBD"
    }
  ],
  "tasks": [
    {
      "id": "chat",
      "phase": "p1",
      "title": "Local chat",
      "description": "Delivered local chat foundation.",
      "status": "delivered",
      "dependsOn": [],
      "milestone": false,
      "step": null
    },
    {
      "id": "audio",
      "phase": "p1",
      "title": "Audio 2.7.1",
      "description": "Delivered reviewed audio transcription and recap workflow.",
      "status": "delivered",
      "dependsOn": [],
      "milestone": false,
      "step": null
    },
    {
      "id": "notes",
      "phase": "p1",
      "title": "Notes 0.3.0",
      "description": "Delivered handwritten Notes workflow.",
      "status": "delivered",
      "dependsOn": [],
      "milestone": false,
      "step": null
    },
    {
      "id": "text",
      "phase": "p1",
      "title": "Text 0.1.0",
      "description": "Delivered direct Text entry workflow.",
      "status": "delivered",
      "dependsOn": [],
      "milestone": false,
      "step": null
    },
    {
      "id": "dashboard",
      "phase": "p1",
      "title": "Shared dashboard",
      "description": "Delivered shared Audio, Notes and Text dashboard.",
      "status": "delivered",
      "dependsOn": [],
      "milestone": false,
      "step": null
    },
    {
      "id": "approvals",
      "phase": "p1",
      "title": "Human approvals",
      "description": "Delivered review and separate approval gates before Knowledge.",
      "status": "delivered",
      "dependsOn": [],
      "milestone": false,
      "step": null
    },
    {
      "id": "ingestion",
      "phase": "p1",
      "title": "Nightly ingestion",
      "description": "Delivered nightly ingestion of approved knowledge.",
      "status": "delivered",
      "dependsOn": [],
      "milestone": false,
      "step": null
    },
    {
      "id": "telegram",
      "phase": "p1",
      "title": "Telegram",
      "description": "Delivered readiness and ingestion notifications.",
      "status": "delivered",
      "dependsOn": [],
      "milestone": false,
      "step": null
    },
    {
      "id": "traffic",
      "phase": "p1",
      "title": "Traffic Control",
      "description": "Delivered queue monitoring and waiting-job cancellation.",
      "status": "delivered",
      "dependsOn": [],
      "milestone": false,
      "step": null
    },
    {
      "id": "recovery",
      "phase": "p1",
      "title": "Recovery foundation",
      "description": "Delivered workflow recovery and archive/state restore drill. Full-platform recovery is not yet certified.",
      "status": "delivered",
      "dependsOn": [],
      "milestone": false,
      "step": null
    },
    {
      "id": "population",
      "phase": "p2",
      "title": "Knowledge population",
      "description": "Populate representative Audio, Notes and Text privately. Public examples must be synthetic.",
      "status": "provisional",
      "dependsOn": [
        "ingestion",
        "approvals"
      ],
      "milestone": false,
      "step": 0
    },
    {
      "id": "lifecycle",
      "phase": "p2",
      "title": "Indexed revision / retract / restore",
      "description": "Validate indexed revisions, withdrawal and explicit restoration across sources. Existing lifecycle capabilities are the baseline.",
      "status": "provisional",
      "dependsOn": [
        "population"
      ],
      "milestone": false,
      "step": 1
    },
    {
      "id": "rag",
      "phase": "p2",
      "title": "Cross-source RAG & absent answers",
      "description": "Evaluate grounded cross-source answers, citations, conflicts and clear absent or insufficient-evidence answers.",
      "status": "provisional",
      "dependsOn": [
        "lifecycle"
      ],
      "milestone": false,
      "step": 2
    },
    {
      "id": "aging",
      "phase": "p2",
      "title": "Knowledge aging & temporal truth",
      "description": "Validate supersession, dated facts, historical queries and stale knowledge handling.",
      "status": "provisional",
      "dependsOn": [
        "rag"
      ],
      "milestone": false,
      "step": 3
    },
    {
      "id": "retrieval",
      "phase": "p2",
      "title": "Retrieval / Obsidian decision",
      "description": "Compare retrieval quality and the role of Obsidian. Record an evidence-backed architecture decision.",
      "status": "provisional",
      "dependsOn": [
        "aging"
      ],
      "milestone": false,
      "step": 4
    },
    {
      "id": "ssd",
      "phase": "p2",
      "title": "SSD capacity planning",
      "description": "Measure growth and headroom privately; decide capacity and retention needs.",
      "status": "provisional",
      "dependsOn": [
        "recovery"
      ],
      "milestone": false,
      "step": 0
    },
    {
      "id": "backup",
      "phase": "p2",
      "title": "Backup & full-platform recovery",
      "description": "Extend the archive/state drill to verified full-platform restore, including configuration and dependencies. Keep backups private.",
      "status": "provisional",
      "dependsOn": [
        "ssd",
        "recovery"
      ],
      "milestone": false,
      "step": 1
    },
    {
      "id": "security",
      "phase": "p2",
      "title": "Security & reliability",
      "description": "Review access boundaries, dependency risks, failures, rollback and reliability. Cloud CI uses synthetic fixtures only.",
      "status": "provisional",
      "dependsOn": [
        "backup",
        "lifecycle"
      ],
      "milestone": false,
      "step": 3
    },
    {
      "id": "cicd",
      "phase": "p2",
      "title": "CI/CD in GitHub Actions",
      "description": "CI/CD configuration is running on GitHub: pinned GitHub Actions for repository-wide fatal lint, synthetic offline tests, security and secrets scans, source-only package and public Pages builds. Pages delivery requires manual confirmation and environment gates. The initial hosted test run exposed a missing Pillow test dependency; CI now installs the existing pinned image dependency before the synthetic suites. A successful hosted rerun and branch/environment protections remain to be verified. No private server access, meeting data, runtime credentials or backups.",
      "status": "provisional",
      "dependsOn": [
        "recovery"
      ],
      "milestone": false,
      "step": 0
    },
    {
      "id": "showcase",
      "phase": "p2",
      "title": "Public demo / video / docs",
      "description": "Create a synthetic interactive showcase, video and documentation. This roadmap is the first static artifact; full demo/video remain future work. Review every public asset.",
      "status": "provisional",
      "dependsOn": [
        "retrieval",
        "security",
        "cicd"
      ],
      "milestone": false,
      "step": 5
    },
    {
      "id": "release",
      "phase": "p2",
      "title": "Final release checkpoint",
      "description": "Manual go/no-go review of retrieval evidence, recovery, capacity, security, CI gates and showcase. Optional LoRA is not a release dependency.",
      "status": "provisional",
      "dependsOn": [
        "showcase",
        "backup",
        "ssd",
        "aging",
        "security"
      ],
      "milestone": true,
      "step": 6
    },
    {
      "id": "lora",
      "phase": "p2",
      "title": "Optional LoRA feasibility",
      "description": "Optional feasibility only: establish value, compute cost and privacy constraints. Training and cloud data transfer are not approved.",
      "status": "optional",
      "dependsOn": [
        "retrieval"
      ],
      "milestone": false,
      "step": 4
    },
    {
      "id": "groceries",
      "phase": "p3",
      "title": "Groceries-list product",
      "description": "Intentionally undefined. Scope and validation criteria await a future product decision.",
      "status": "tbd",
      "dependsOn": [
        "release"
      ],
      "milestone": false,
      "step": null
    },
    {
      "id": "web",
      "phase": "p4",
      "title": "Web research agent",
      "description": "Future horizon. Scope, permissions and evidence standards TBD.",
      "status": "tbd",
      "dependsOn": [
        "groceries"
      ],
      "milestone": false,
      "step": null
    },
    {
      "id": "coding",
      "phase": "p4",
      "title": "Coding agent",
      "description": "Future horizon. Scope TBD.",
      "status": "tbd",
      "dependsOn": [
        "groceries"
      ],
      "milestone": false,
      "step": null
    },
    {
      "id": "assistant",
      "phase": "p4",
      "title": "Personal assistant",
      "description": "Future horizon. Scope TBD. Dependencies are provisional sequencing assumptions.",
      "status": "tbd",
      "dependsOn": [
        "web",
        "coding"
      ],
      "milestone": false,
      "step": null
    }
  ],
  "steps": [
    "Populate",
    "Validate",
    "Evaluate",
    "Refine",
    "Decide",
    "Showcase",
    "Release",
    "Future"
  ]
};
