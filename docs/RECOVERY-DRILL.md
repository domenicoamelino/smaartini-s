# Recovery drill

A private off-device archive/state recovery drill passed on 31 October 2026: 516 matching file hashes, coherent jobs/reviews SQLite integrity and table counts, seven Audio sources, 23 Audio revisions/five approvals, four Notes images, 13 Notes revisions/one approval, two Text originals/revisions including one approved revision, four ledger versions and two pending withdrawal states. Owner identities and source/hash references were retained. Production records and services were not changed.

The initial checkpoint predated the user’s new approved Text entry. The final refreshed checkpoint includes it and its original, revision, owner and approval hashes passed. A self-contained PC archive was independently re-extracted and all 516 hashes matched; the initial checkpoint is not required to use it. Open WebUI volumes, account/Function data, Knowledge/vector store, models and virtual environments are outside this drill. Full-platform recovery remains separate.

Create a snapshot only when Audio/Notes/review processing is idle. tools/create_recovery_snapshot.py is a Linux operations helper for the current MINISFORUM layout; it obtains the existing ingestion/heavy-slot locks, briefly reserves SQLite writes, backs up databases through SQLite backup, captures archive/config/source and records SHA-256 hashes. It does not stop services or change records. It uses the existing private deployment-plan location; adapt that trusted path deliberately for another installation. Keep the resulting archive private: worker/ingestion configuration contains credentials.

Transfer recovery.tar.gz, MANIFEST.json and TRANSFER.json to a trusted off-device location. Run the standard-library verifier in isolation:

```bash
python tools/verify_recovery.py --snapshot PRIVATE_SNAPSHOT --restored NEW_RESTORE_DIRECTORY --extract --report result.json
```

The target must be new. The verifier refuses traversal, links, case collisions, hash mismatches and overwrite. It checks all bytes, database integrity/counts, source ownership, original images, revisions/approvals, withdrawal states and ledger source fingerprints. It does not contact a network or start restored services. Rechecking without --extract is read-only. Run python tools/check_recovery.py for the four synthetic safety tests.

Do not run recovered configuration against live endpoints as a test. Before a real rebuild, recover Open WebUI identity/data as well, preserve cancelled/withdrawn states, reconcile destination/ledger identities and explicitly control scheduling and notifications. Never overwrite newer production databases or blindly replay retained approvals.
