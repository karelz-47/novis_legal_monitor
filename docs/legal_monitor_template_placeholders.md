# Legal Monitor template placeholders

Use double-curly placeholders and replace them before DOCX generation or before PDF conversion.

- `{{GENERATED_AT}}` — formatted report generation timestamp, for example `06 May 2026, 21:13 UTC`
- `{{SEARCH_TARGET}}` — monitored entity or query name
- `{{PERIOD_FROM}}` — formatted start date/time
- `{{PERIOD_TO}}` — formatted end date/time
- `{{RECORDS_REVIEWED}}` — total records checked
- `{{RELEVANT_FINDINGS}}` — number of findings included in the report
- `{{FINDING_HEADLINE}}` — short finding title
- `{{ENTITY_NAME}}` — legal entity name shown in the finding
- `{{NOTICE_TYPE}}` — business-friendly description of the notice
- `{{COURT_NAME}}` — court or issuing authority
- `{{REFERENCE}}` — case or registry reference
- `{{PUBLICATION_DATE}}` — formatted publication date
- `{{UPDATED_AT}}` — formatted most recent update timestamp
- `{{RELEVANT_PARTY}}` — proposer / debtor / relevant party label
- `{{MANAGEMENT_SUMMARY}}` — concise senior-management wording, ideally 2–4 sentences
- `{{SOURCE_EXTRACT}}` — cleaned source extract from the registry

## Formatting recommendation

Prefer these formats in the app:

- Date only: `31 March 2026`
- Date and time: `06 May 2026, 21:13 UTC`
- Counts: plain integers without technical prefixes

## Multi-finding use

For reports with more than one finding, duplicate the full `Finding details` + `Management summary` + `Source extract` block for each additional item.
