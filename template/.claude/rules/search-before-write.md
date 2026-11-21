---
name: search-before-write
description: Before writing new code, search for existing code.
---

# Search before writing

Before creating a new procedure, function or metadata object:
1. Find existing analogues via `code_index` (`search_terms`).
2. Check the metadata composition and structure via `code_index` (`get_object_structure`, if needed `bsl_sql` over `metadata_objects`).
3. Reuse or extend the existing one if appropriate.

Duplicating logic is a reason to stop and search again.
