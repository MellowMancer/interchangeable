# What an EMC product page exposes

A field inventory of `medicines.org.uk`, verified directly against server-rendered HTML on
**2026-08-21**. This is the authority on *what is available to extract*;
`docs/BRIGHT_DATA.md` remains the authority on the CLI that does the extracting.

Written so the product collector can be extended without re-investigating the page. Every
row below was confirmed by fetching the page, not inferred.

## Sample set

| Product | Company | URL |
|---|---|---|
| 7142 | Aurobindo Pharma - Milpharm Ltd. | `/emc/product/7142` |
| 14717 | Wockhardt UK Ltd | `/emc/product/14717` |
| 8066 | Zentiva | `/emc/product/8066` |

All three are current, prescription-only, oral ramipril generics. Anything that depends on
a product being discontinued, or on a legal category other than POM, is flagged as
unconfirmed below.

## Access

`/emc/product/{id}` 302-redirects to `/emc/product/{id}/smpc`. A plain request with a
default user agent returns HTTP 200 and the complete document — **JavaScript is not
required**. Sections are `<details>`/`<summary>` elements, visually collapsed but fully
present in the DOM.

`<meta name="robots" content="noarchive">` is set. Nothing observed blocked automated
fetching, but that is an observation about one day, not a licence — the Bright Data
collector remains the sanctioned path, and local code still must not parse this HTML.

## Already captured

The product collector's current schema, from its `bdheal` baseline:

```
product_name · active_substance · ma_holder · last_updated
section_4_3_contraindications · section_4_4_warnings
section_4_5_interactions · section_4_6_pregnancy_lactation
```

## Available and worth adding

Ordered by what they change about what the product can claim.

### 1. Canonical MA-holder identity — the important one

`ma_holder` is free text today, so two spellings of one company become two manufacturers.
Since a column *is* a manufacturer, that produces phantom columns and **false
divergences** — and it gets worse as the corpus grows.

- Location: `<div class="product-header-item product-header-company">`, label `Company:`
- Shape: `<a class="emc-link" href="/emc/company/{id}">`
- Confirmed: 7142 → `3006` · 14717 → `35` · 8066 → `3185`
- The company page resolves and lists that holder's products.

**Two different company values exist on one page.** The header carries EMC's account name
(`Aurobindo Pharma - Milpharm Ltd.`); SmPC section 7 carries the legal MA holder
(`Milpharm Limited`). Capture the id, and decide deliberately which name to display —
they are not interchangeable.

### 2. Active-ingredient identity

- Shape: `/emc/ingredient/{id}` — ramipril is `1065`, **identical across all three products**
- Why it matters: EMC itself asserting these share an active substance. A guard on the
  substance grouping rather than trusting our own slug.

### 3. ATC code

- Location: `<div id="about-medicine" class="product-header-item product-header-atc-code">`,
  label `ATC code:`, value in a bare `<div>`
- Confirmed: `C09AA05` on all three
- A dedicated labelled field — do not dig it out of section 5.1 prose.
- Same use as above: two products with different ATC codes are not comparable, and the
  comparison should be able to say so rather than assume.

### 4. Section 6.1 excipients

- Anchor: `id="EXCIPIENTS"` on the `<summary>`; heading `6.1 List of excipients`
- Confirmed (7142): *"Capsule Fill: Hydrophobic colloidal anhydrous silica, Pregelatinized
  starch (maize). Capsule Shell: Gelatin, Sodium lauryl sulfate, Iron oxide yellow (E172),
  Ponceau 4R (E124), Titanium dioxide (E171)…"*
- Easy to capture, **hard to normalise**: free prose with company-chosen sub-headings and
  no list markup. Expect the clause splitter and lexicon to need work before excipient
  differences can be compared, not just the collector.
- The strongest *product* addition here. Different excipients between otherwise identical
  generics — lactose, sucrose, soya — is a real interchangeability finding and directly on
  the project's thesis.

### 5. Section 3 appearance — the substitute for product photography

**No product photograph of any UK generic in this corpus exists, anywhere.** See
"Product imagery" below before spending any time looking. What exists instead is the
manufacturer's own regulated description of what the product looks like.

- Anchor: `id="FORM"`; heading `3. Pharmaceutical form`
- **Coverage: 31 of 31 ramipril products carry one — 100% of the corpus.**
- Confirmed values:
  - 7142 — *"Orange/White size '4' hard gelatin capsules imprinted with 'D' on orange cap and '41' on white body with black edible ink"*
  - 14717 — *"Red opaque body and red opaque cap. The body has 'RP 5' printed in black."*
  - 8066 — *"Pale red oblong tablet with dimensions of 8 x 4 mm with score-line. Upper stamp: 5 & logo. Lower stamp: HMP & 5"*

Colour, shape, size in millimetres and imprint, in the label's own words. Parsed, these
drive a generated dosage-form glyph per manufacturer — which makes "same drug, different
manufacturer" literal and visual, stays citable back to the label like every other claim
here, and carries no licensing exposure because every pixel is our own drawing.

Note the prose is company-authored and inconsistent: 8066's begins
`Tablets mg 5mg Pale red oblong tablet…`. Expect parsing work, and expect to publish the
descriptions that could not be parsed rather than dropping them.

### 6. PL / marketing authorisation number

- Anchor: `id="NUMBER"`; heading `8. Marketing authorisation number(s)`
- Confirmed: `PL 16363/0356` · `PL 29831/0623` · `PL 17780/1028`
- The actual regulatory identity. `external_id` is EMC's internal surrogate.

### 7. Marketing status — binary, not an enumeration

- Shape: presence of `<div class="discontinued-info …">Discontinued</div>` in the product
  header, above `Active Ingredient:`
- **Absent on all three samples** (they are current). Confirmed present on `/emc/product/10819`.
- Only two states exist: Discontinued, or no badge. **No suspended or withdrawn state was
  found anywhere on the site.** Do not model this as a status enum.
- Site-wide filter exists: `/emc/search?filters=attributes[isdiscontinued]&type=dc`
- Why it matters: a one-sided divergence coming from a discontinued product is a different
  claim than one from a live product, and the UI can only say so if this is stored.

### 8. Legal status

- Location: `<div class="legal-categories-content"><span class="product-about-medicine-item-text">`
  in the sidebar `About Medicine` block. **No label text** — the value stands alone.
- Confirmed: "Prescription only medicine" on all three.
- **Not in the SmPC body.** Section 9 is *Date of first authorisation/renewal*; section 10
  is the revision date. An earlier assumption that legal status was section 9 was wrong.
- Unconfirmed: whether "P" and "GSL" render in the same slot. Likely, untested.

## Not available

### Product imagery — absent from every source checked

Verified 2026-08-21 across EMC, MHRA, NHS dm+d, NLM, DailyMed/openFDA, DrugBank,
Wikimedia, all three manufacturers' own sites and UK online pharmacies. **Do not
re-investigate this without new information.**

- **EMC has no image concept at all.** `sitemap.xml` carries 20,371 URLs of exactly two
  kinds — 10,280 `/smpc` and 10,091 `/pil`. There is no media path for any product.
  Every `<img>` on a product page is site chrome.
- **PIL PDFs contain no images.** `pdfimages -list` reports zero embedded images for all
  three products, and for 12 of 14 further EMC PILs sampled; the two exceptions were a
  monitoring symbol and a logo. UK PILs are typographic documents.
- **MHRA Products** is a document index; its own GraphQL schema has no image field.
- **NLM Pillbox / RxImage / C3PI are dead and were US-only.** `pillbox.nlm.nih.gov` no
  longer resolves; the API ceased 2021-12-31.
- **DailyMed has a near-miss worth knowing.** Aurobindo has a US ramipril SPL with 11
  images, but they are carton die-line artwork and Kaplan-Meier charts, not photographs —
  and it is a *different capsule*: the US 2.5 mg is orange/orange `D`/`06`, the UK
  PL 16363/0356 is orange/**white** `D`/`41`. Using it would misrepresent the product.
- **The manufacturers have chosen not to publish photographs.** Milpharm publishes none
  for any product; Wockhardt has no ramipril page at all and photographs only its branded
  insulin range; Zentiva's own site config sets `doNotShowImageOnList: true`.

The structural reason: branded medicines get photography, POM generics get a row in a
table. This is not a gap more effort can close.

The one per-product image EMC does serve is a company logo —
`/emc/images/logo/{companyId}` (verified 200). Manufacturer trademarks, not products, and
not reusable.

### Machine-readable revision date — absent

Verified absent on all three: no `<time datetime=…>`, no ISO string, no JSON-LD, no
microdata, no RDFa, no Open Graph. Any date must be parsed from display text.

**There are two different revision dates on every page, and they disagree:**

| Product | `Last updated on emc:` (`.last-updated`) | §10 *Date of revision of the text* (`id="DOCREVISION"`) |
|---|---|---|
| 7142 | 10 Jul 2026 | 07/07/2026 |
| 14717 | 18 Apr 2023 | 05/05/2021 |
| 8066 | 22 Jul 2026 | 14/07/2026 |

`documents.last_updated` currently holds the **section 10** value. The two answer different
questions — when the publisher revised the text, versus when emc last touched the record —
and the UI's staleness caveat is computed from whichever is stored. Pick one deliberately,
and consider storing both rather than silently preferring one.

Note the formats differ (`10 Jul 2026` vs `07/07/2026`), which is why `revision_date()`
accepts several shapes. Keep publishing the publisher's own string: parsing month-precision
text into a date invents a day nobody published.

### Structured strength and pharmaceutical form — absent as fields

No strength field, no form field. Only:

- `<h1 class="product-header-heading">` — e.g. `Ramipril  5mg Tablets` (8066 contains a
  double space; titles are dirty)
- `id="COMPOSITION"` → *"Each hard capsule contains ramipril 2.5 mg."*
- `id="FORM"` → `Capsules, hard` (7142), but 8066 reads
  `Tablets mg 5mg Pale red oblong tablet with dimensions of 8 x 4 mm with score-line`

So `variant()`'s regex over the product name cannot simply be replaced by a clean field.
Section 3 is company-authored prose and inconsistent between labels.

**This is not a reason to skip §3** — see *Section 3 appearance* above. As a source of a
clean strength or form value it is unusable; as the manufacturer's own description of what
the product looks like it is complete across the corpus and is the only substitute for the
product photography that does not exist. Capture the prose; do not expect fields.

### Structured data — absent

No JSON-LD, microdata, RDFa or Open Graph on any page. The only useful meta is
`<meta name="description">`, which is product title plus company name. `<title>` carries the
product id: `Ramipril 2.5mg Capsule - … - (emc) | 7142`.

## The most valuable extraction hook

**Every SmPC section carries a stable semantic anchor id** on its `<summary>`:

```
COMPOSITION · FORM · INDICATIONS · POSOLOGY · CONTRAINDICATIONS · INTERACTIONS
PREGNANCY · UNDESIRABLE_EFFECTS · OVERDOSE · PHARMACODYNAMIC_PROPS
PHARMACOKINETIC_PROPS · EXCIPIENTS · INCOMPATIBILITIES · SHELF_LIFE · STORAGE
PACKAGE · USEHANDLING · NUMBER · AUTHDATE · DOCREVISION
```

These are structural rather than presentational, so they survive restyling in a way class
names do not. Anchoring section extraction on them should make the collector materially
harder to break — and makes adding §6.1 cheap.

## Before changing the collector — read this

**A collector change is not sufficient on its own.** Adding fields has three downstream
consequences:

1. **Schema.** `adapters/sqlite/schema.sql` is `PRAGMA user_version = 3`, create-only,
   with **no migration runner**. Company id, ATC code, PL number, legal status and
   marketing status all need columns on `products` or `documents`, which means a schema
   version bump and a decision about existing databases.
2. **`bdheal` drift detection.** A changed collector schema is exactly what the detector is
   built to notice. §4.5 was added by heal with the collector id unchanged (see M12 in
   `docs/interchangeable.md`), so there is precedent — but note a heal is only persisted
   with `--auto-save`.
3. **`scanned` semantics.** Every absence claim in the UI is scoped to the sections
   actually read. Adding §6.1 widens that scope, which is correct, but it changes what
   `absent` means for every previously stored document until they are re-fetched.

## Licensing — escalate before this is more than a demo

Datapharm's terms for EMC prohibit reproducing its content for commercial benefit,
building databases from it, and systematically tracking changes to third-party
information. **That applies to the corpus already stored, not only to any imagery.**
Datapharm offers a licensing route. Nothing here needs to change for a demo or a
hackathon submission, but it should be a conscious decision rather than an oversight.

Separately, EMC product pages carry a third-party analytics beacon
(`https://secure.perk0mean.com/177801.png`). Harmless to us — noted only so it is not
mistaken for product imagery by whoever extends the collector.

## Confidence and limits

Everything marked confirmed was read from the served HTML of all three products on
2026-08-21. The discontinued badge was confirmed on a fourth product outside the sample
set. Legal categories other than POM are unconfirmed. All three samples share one
substance, one route and one legal category, so generalisation beyond that is untested.
