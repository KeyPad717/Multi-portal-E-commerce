# OWL Semantic Pipeline — IIITB Faculty Profile
**Single-page scrape → LLM enrichment → RDF triples → OWL (Protégé-ready)**

Target: `https://www.iiitb.ac.in/faculty/debabrata-das`

---

## Project Structure

```
DM_API/
├── main.py            # Orchestrator (run this)
├── scraper.py         # Fetch + parse faculty page
├── chunker.py         # Token-aware data splitter
├── enricher.py        # OpenRouter LLM enrichment
├── triple_builder.py  # RDF triple + OWL graph builder
├── owl_writer.py      # Serialize to .owl and .ttl
├── checkpoint.py      # Save/resume pipeline state
├── verify.py          # Pre-run sanity checks
├── requirements.txt
├── .env               # Your API key goes here
└── output/
    ├── checkpoint.json       # Pipeline state (auto-created)
    ├── scraped_data.json     # Raw extracted data
    ├── chunks.json           # Token-split chunks
    ├── enriched_data.json    # LLM-enriched entities + rels
    ├── faculty_RC.owl       # ← Open this in Protégé
    └── faculty_RC.ttl       # Human-readable Turtle
```

---

## Step-by-Step: How to Run

### Step 1 — Open terminal and go to project folder

```bash
cd ~/Desktop/dm/DM_API
```

### Step 2 — Install all dependencies

```bash
pip install -r requirements.txt
```

If you get permission errors, try:
```bash
pip install --user -r requirements.txt
```

### Step 3 — Get a FREE OpenRouter API key

1. Open browser → go to: https://openrouter.ai/keys
2. Sign in or create an account
3. Click **"Create Key"**
4. Copy the key

### Step 4 — Set your API key in .env

Open `.env` file in any text editor:
```bash
nano .env
```

Replace `your_openrouter_api_key` with your actual key:
```
OPENROUTER_API_KEY=sk-or-v1-XXXXXXXXXXXXXXXXXXXXXXXXXXXXX
TARGET_URL=https://www.iiitb.ac.in/faculty/debabrata-das
TOKEN_LIMIT=12000
CHUNK_SIZE=2000
```

Save: `Ctrl+O` → Enter → `Ctrl+X`

### Step 5 — Run verification checks (recommended)

```bash
python verify.py
```

This checks: API key, all packages, URL reachability, scraper, chunker, OpenRouter connection.
You should see: `✅ ALL CHECKS PASSED`

### Step 6 — Run the full pipeline

```bash
python main.py
```

You will see output like:
```
══════════════════════════════════════════════════════════
  OWL PIPELINE — IIITB Faculty Profile
══════════════════════════════════════════════════════════
► STAGE 1: Scraping webpage...
► STAGE 2: Tokenising and chunking...
► STAGE 3: LLM semantic enrichment (OpenRouter Gemini 1.5 Flash)...
► STAGE 4: Building RDF triples...
► STAGE 5: Writing OWL file...
══════════════════════════════════════════════════════════
  ✅  PIPELINE COMPLETE
  OWL file : output/faculty_RC.owl
══════════════════════════════════════════════════════════
```

### Step 7 — Open OWL in Protégé

1. Open Protégé
2. **File → Open...**
3. Navigate to: `~/Desktop/dm/DM_API/output/faculty_RC.owl`
4. Click **Open**
5. In Protégé, explore:
   - **Classes tab** → Person, Faculty, Publication, ResearchArea, etc.
   - **Object Properties tab** → hasResearchArea, authorOf, supervisesStudent, etc.
   - **Data Properties tab** → fullName, emailAddress, publicationYear, etc.
   - **Individuals tab** → All extracted entities (Debabrata Das + all related)

---

## If Token Limit is Hit (Pipeline Pauses)

The pipeline automatically pauses if OpenRouter's free tier limit is near.
All progress is saved in `output/checkpoint.json`.

```
⏸  PIPELINE PAUSED
Reason: Token budget exhausted. Wait for quota reset then re-run.
```

**To resume next day:**
```bash
python main.py
# → "Pipeline was previously paused. Resume now? (y/n):"
# Type: y
```

**To check current status:**
```bash
python main.py --status
```

**To start completely fresh:**
```bash
python main.py --reset
python main.py
```

---

## OWL Classes Generated

| Class | Description |
|-------|-------------|
| `Faculty` | subClassOf Person — the professor |
| `Person` | any human entity |
| `ResearchArea` | research topic/domain |
| `Publication` | journal/conference paper |
| `Project` | funded research project |
| `Organization` | university, company, funding agency |
| `Award` | honor, fellowship, prize |
| `Degree` | PhD, MTech, BTech qualification |
| `Student` | PhD/research student |
| `Course` | academic course taught |

## Key Object Properties (with Domain → Range)

| Property | Domain → Range |
|----------|---------------|
| `hasResearchArea` | Faculty → ResearchArea |
| `authorOf` | Faculty → Publication |
| `worksAt` | Faculty → Organization |
| `supervisesStudent` | Faculty → Student |
| `receivedAward` | Person → Award |
| `teaches` | Faculty → Course |
| `worksOnProject` | Faculty → Project |
| `hasEducation` | Person → Degree |
| `fundedBy` | Project → Organization |

## Key Datatype Properties

| Property | Domain | Range |
|----------|--------|-------|
| `fullName` | Person | xsd:string |
| `emailAddress` | Person | xsd:string |
| `publicationYear` | Publication | xsd:gYear |
| `degreeLevel` | Degree | xsd:string |
| `institution` | Degree | xsd:string |

---

## Troubleshooting

**`ModuleNotFoundError`** → Run `pip install -r requirements.txt`

**`429 Resource exhausted`** → Free tier limit hit. Wait 1 minute (per-minute limit) or check OpenRouter credits. Pipeline auto-resumes.

**`Connection error`** → Check internet connection. IIITB site may be down temporarily.

**Protégé shows empty ontology** → Make sure you open `faculty_RC.owl` not the `.ttl` file.
