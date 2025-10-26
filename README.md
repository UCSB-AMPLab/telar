# Telar

![Version](https://img.shields.io/badge/version-0.3.0--beta-orange) ![License](https://img.shields.io/badge/license-MIT-blue) [![Trigger Build](https://img.shields.io/badge/▶_Trigger-Build-blue)](https://github.com/UCSB-AMPLab/telar/actions/workflows/build.yml)

A minimal computing framework for creating visual narrative exhibitions with IIIF images and scrollytelling.

> **⚠️ Beta Release - v0.3.0-beta**
> Beta Release - v0.3.0-beta This release introduces comprehensive error messaging, Google Sheets integration for easier content management, and improved copy functionality for IIIF coordinates. Choose between CSV-based or Google Sheets workflows.
> This release introduces breaking changes. If upgrading from v0.2.0, see [Migration Guide](#migrating-from-v020) below.

## Overview

Telar (Spanish for "loom") is a static site generator built on Jekyll that weaves together IIIF images, narrative text, and layered contextual information into interactive visual narrative exhibitions. It follows minimal computing principles: plain text authoring, static generation, and sustainable hosting.

Telar is developed by Adelaida Ávila, Juan Cobo Betancourt, Santiago Muñoz, and students and scholars at the [UCSB Archives, Memory, and Preservation Lab](https://ampl.clair.ucsb.edu), the UT Archives, Mapping, and Preservation Lab, and [Neogranadina](https://neogranadina.org).

## Key Features

- **IIIF integration**: Support for both local images (auto-generated tiles) and external IIIF resources
- **Scrollytelling**: Discrete step-based scrolling with support for multiple IIIF objects in a single story - each object preloaded in its own viewer card
- **Layered panels**: Progressive disclosure with three content layers plus glossary
- **Objects gallery**: Browsable object grid with detail pages
- **Minimal computing**: Plain text, static generation, GitHub Pages hosting

---

## Quick Start

### Before You Begin: Plan Your Narrative

Telar narratives are built around a layered storytelling structure. Understanding this model will help you plan your content effectively.

Each page in your Telar site contains one or more stories, which can be independent narratives or chapters of a longer piece. Stories unfold through successive steps that show an image (or a detail of an image) alongside brief text. Each step follows a question/answer/invitation pattern: a question draws viewers in, a brief answer (1-2 sentences) responds, and an invitation to "learn more" opens a layer panel with extended information. You can provide up to two of these layer panels in each step, allowing viewers who want to go deeper to obtain even more detail.

Layer panels are where you can really expand on your narrative. They are written in [markdown format](https://www.markdownguide.org/getting-started/), allowing you to include headings, bold and italic text, links, lists, and other formatting. You can also insert additional images, and embed videos, 3D renderings, or other resources.

Before you start gathering materials or building your site, take time to sketch out your story's structure. Ask yourself: What stories do you want to tell? What are the key moments in each story? What images or details will anchor each step? What information belongs in the brief answer and what in the deeper layers? Planning this out on paper or in a digital tool of your choice will make the implementation much easier.

For inspiration, browse the [example site](https://ampl.clair.ucsb.edu/telar) to see this structure in action. More sites built with Telar will be available soon in our directory.

Once you're ready, choose one of the workflows below based on your needs and technical knowledge.

### Content Management Options

Telar offers two ways to weave your materials together:

#### Google Sheets (Recommended)
Manage content through a familiar spreadsheet interface. Ideal for teams and most users. Simply configure two URLs in `_config.yml` and the system automatically fetches your content. See the `google_sheets` section in [`_config.yml`](_config.yml) for setup instructions, or [`docs/google_sheets_integration/README.md`](docs/google_sheets_integration/README.md) for local development.

#### CSV Files (Optional)
Edit CSV files directly in your repository using GitHub's web interface or a local text editor. This approach provides full control and works entirely through GitHub without requiring external services.

---

### Track 1: GitHub Web Interface Only (Recommended for Storytellers)

**No installation required!** Follow these phases to build your narrative.

> **Quick start:** If you're eager to experiment or already know your story, skip ahead to [Phase 2: Quick Setup](#phase-2-quick-setup-get-your-workspace-ready) to get your workspace ready, then jump to [Phase 4: Structure Your Story](#phase-4-structure-your-story).

#### Phase 1: Narrative Planning

**Before diving in, plan your story:**

- Browse the [Telar example site](https://ampl.clair.ucsb.edu/telar) for inspiration
- What story do you want to tell?
- What are the key steps or moments in your story?
- For each step, draft a **question** (heading) and **answer** (brief 1-2 sentence response)
- What image or images can you use to anchor your story?
- What details in these images matter most and when?
- Sketch your narrative structure on paper before using tools

#### Phase 2: Get Your Telar Workspace Ready

**Create your workspace:**

1. **Create GitHub repository**: Click the green "Use this template" button above to create your own copy. If you can't see the button, make sure you are logged in. You will need to createa GitHub account if you don't have one.
2. **Duplicate Google Sheets template**: Go to https://bit.ly/telar-template
   - Click **File** → **Make a copy**
   - Save to your Google Drive and give it a name that makes sense for your project
3. **You're ready!** Now you have places to upload images and organize content

#### Phase 3: Gather Materials

**Collect and organize your content:**

Telar lets you upload your own images or insert them directly from digital repositories hosted by museums, libraries, and other institutions using [IIIF](https://en.wikipedia.org/wiki/International_Image_Interoperability_Framework). You can also mix and match.

**To Upload Your Own Images**

1. Navigate to `components/images/objects/` in your GitHub repository
2. Click **Add file** → **Upload files**
3. Drag images into upload area
4. Name files with simple object IDs (e.g., `textile-001.jpg`, `ceramic-002.jpg`). Make sure to avoid spaces in your filenames.
5. Add the object ID (with or without the file extension) to the "objects" tab of your spreadsheet
6. Commit changes to save

**To Use IIIF Images**

1. Find IIIF resources from institutions ([IIIF Guide to Finding Resources](https://iiif.io/guides/finding_resources/))
2. Copy the URL for the manifest into the "objects" tab of your spreadsheet (e.g., `https://iiif.io/api/cookbook/recipe/0001-mvm-image/manifest.json`)
3. Give it a simple object_id in the same sheet(e.g., `museum-textile-001`)

**Add other details to your objects sheet as you collect your images:**
- Fill as many of the other fields in the objects tab of your spreadsheet as you like
- Make sure you've included the IIIF manifest URLs for all external resources
- Make sure that the filenames of images you are uploading match the object_id column of your spreadsheet, and that you haven't put any spaces in them.

**Create Narrative Texts**

Write markdown files for your story layer content (the detailed text that appears in slide-out panels):

1. Navigate to `components/texts/stories/story1/` in your GitHub repository
2. Click **Add file** → **Create new file**
3. Name the file - you can call it whatever you like (e.g., `step1-layer1.md`, `weaving-techniques.md`, `context.md`)
   - Avoid spaces in filenames (use hyphens or underscores instead)
   - Use `.md` extension for markdown files
4. Add frontmatter and content:
   ```markdown
   ---
   title: "Weaving Techniques"
   ---

   The interlocking warp pattern visible here indicates...
   ```
5. Commit the file
6. Repeat for each layer of content you want to add
7. **Important**: Keep a note of your filenames and their locations. You can organize the files inside the "texts" folder how you like, for example by creating subfolders for each story as we have for our demo, but this is not required. Either way, you'll need to make a note of the exact paths and filenames (e.g., `story1/weaving-techniques.md`) to include in your story spreadsheet in Phase 4, below

#### Phase 4: Structure Your Story

**Connect everything in your Google Sheets story sheet:**

1. **Add story steps**: For each step in your story, add a row with:
   - **Question**: The heading text (e.g., "What is this textile?")
   - **Answer**: A brief 1-2 sentence response
   - **Object ID**: The object to display (matching your objects sheet)
   - **Coordinates**: Use placeholders for now (0.5, 0.5, 1.0) - you'll refine in Phase 6

2. **Connect your narrative content**: Reference the markdown files you created in Phase 3:
   - In the `layer1_file` column, add the path (e.g., `story1/step1-layer1.md`)
   - In the `layer2_file` column, add the path if you have a second layer
   - Leave blank if a step doesn't need a panel

3. **Customize panel buttons** (optional):
   - Add custom button text in `layer1_button` and `layer2_button` columns
   - Leave blank to use defaults ("Learn more" and "Go deeper")

4. **You can tell the system to ignore a row or column, e.g. for a draft, or a note to yourself or a collaborator**: Just add a `#` prefix, e.g.:
   - `# TODO: verify this date`
   - The template includes a `# Instructions` column for field guidance

#### Phase 5: Connect and Publish

**Make your site live:**

1. **Enable GitHub Pages**:
   - Go to repository **Settings** → **Pages**
   - Source: **GitHub Actions**
   - Click **Save**

2. **Share your Google Sheet**:
   - Click **Share** button → Anyone with the link (Viewer)
   - Copy the shared URL

3. **Publish your Google Sheet**:
   - **File** → **Share** → **Publish to web**
   - Click **Publish**
   - Copy the published URL

4. **Configure `_config.yml`**:
   - Navigate to `_config.yml` in your repository
   - Click pencil icon to edit
   - Find `google_sheets` section
   - Set `enabled: true`
   - Paste shared URL into `shared_url`
   - Paste published URL into `published_url`
   – **Choose your theme** (optional): Telar includes 4 preset visual themes. The default is Paisajes Coloniales, but you can switch to Neogranadina, Santa Barbara, or Austin.
     - In your GitHub repository, navigate to `_config.yml`
     - Find the line `telar_theme: "paisajes"` (around line 11)
     - Change to `"neogranadina"`, `"santa-barbara"`, or `"austin"` if desired
   - Commit your changes

5. **Wait 2-5 minutes** for automatic build
6. **View your site** at `https://[username].github.io/[repository]/`

#### Phase 6: Refine

**Polish your narrative:**

1. **Review your live site** - Browse through pages and stories
2. **Check warning messages** - Telar shows helpful warnings for configuration issues
   - The home page of your site will show you a summary of issues
   - The story pages themselves will display warnings for missing objects and texts
   - You will also see error messages for any invalid IIIF manifests in the objects pages
3. **Fix configuration issues** - Update Google Sheets based on warnings, then trigger rebuild (see below)
4. **Use coordinate identification tool**:
   - Navigate to any object page
   - Click "Identify coordinates" button below viewer
   - Pan and zoom to find the perfect view for each story step
   - Copy and paste the correct values for X, Y, and Zoom into your story sheet
5. **Trigger rebuild** (see [Manual Build Trigger](#manual-build-trigger) section below)
6. **Add additional content layers**: Add any other layer panels, glossary terms, or other information as needed
7. **Iterate and polish** until your story shines

---

## Migrating from v0.2.0

**⚠️ Important: Breaking Changes**

This release includes breaking changes that require updates to existing projects. See migration instructions below.

### Migration Guide

**1. Update project.csv structure**

Old format (key-value pairs):
```csv
key,value
project_title,Your Exhibition Title
tagline,A brief description
...
STORIES,
1,Story One
2,Story Two
```

New format (columns):
```csv
order,title,subtitle
1,Story One,Optional subtitle
2,Story Two,
```

The `project_title`, `tagline`, `author`, `email`, and `logo` fields are now configured in `_config.yml` instead of project.csv.

**2. Migrate theme customization**

If you had `primary_color`, `secondary_color`, `font_headings`, or `font_body` in project.csv, remove them and configure theming via `_config.yml`:

```yaml
telar_theme: "paisajes"  # or neogranadina, santa-barbara, austin
```

For custom colors/fonts, create `_data/themes/custom.yml` and set `telar_theme: "custom"` in `_config.yml`.

---

### Track 2: Local Development (For Developers)

**Best for:** Developers and people with more experience with running Jekyll locally and who want to preview changes locally before publishing

#### Setup

```bash
# Clone the repository
git clone https://github.com/UCSB-AMPLab/telar.git
cd telar

# Install Ruby dependencies
bundle install

# Install Python dependencies (for IIIF generation)
pip install -r requirements.txt
```

**Configure your site settings:**

Edit `_config.yml` and update:
- `title`: Your narrative title
- `description`: A brief description of your narrative
- `baseurl`: `"/your-repository-name"` for GitHub Pages, or `""` for root domain
- `url`: Your site URL (e.g., `"https://your-username.github.io"`)
- `author` and `email` (optional)

#### Core Commands

After setup, you'll use these commands throughout your workflow:

```bash
# Convert CSVs to JSON (run after editing CSVs)
python3 scripts/csv_to_json.py

# Generate IIIF tiles (run after adding/updating images)
python3 scripts/generate_iiif.py --source-dir components/images/objects --base-url http://localhost:4000

# Serve with live reload
bundle exec jekyll serve --livereload

# View at http://localhost:4000
```

#### Step 1: Gather Your Images

You have two options for adding images:

**Option A: Upload Your Own Images**

1. **Add high-res images** to `components/images/objects/` directory
2. **Name files** to match object IDs (e.g., `textile-001.jpg`)
3. **Generate IIIF tiles**:
   ```bash
   python3 scripts/generate_iiif.py --source-dir components/images/objects --base-url http://localhost:4000
   ```

**Option B: Use External IIIF Manifests**

1. **Find IIIF resources** - See the [IIIF Guide to Finding Resources](https://iiif.io/guides/finding_resources/)
2. **Copy the info.json URL** (e.g., `https://example.org/iiif/image/abc123/info.json`)
3. **Create an object_id** - Choose a simple ID (e.g., `museum-textile-001`)
4. **Save for next step** - You'll add this URL to objects.csv in Step 3

#### Step 2: Write Your Narrative Text

Create markdown files for your story layers:

1. **Create directory** for your story: `mkdir -p components/texts/stories/story1`
2. **Create markdown files** for each layer (e.g., `step1-layer1.md`, `step1-layer2.md`)
3. **Add frontmatter and content**:
   ```markdown
   ---
   title: "Weaving Techniques"
   ---

   The interlocking warp pattern visible here indicates...
   ```

#### Step 3: Catalog Your Objects

Add metadata to the objects catalog:

1. **Edit** `components/structures/objects.csv`
2. **Add a row** for each object with columns: `object_id,title,description,creator,date,medium,dimensions,location,credit,thumbnail,iiif_manifest`

   **For Option A (uploaded images):**
   ```
   textile-001,Colonial Textile Fragment,"A woven textile from...",Unknown Artist,circa 1650-1700,Wool,45 x 60 cm,,,
   ```

   **For Option B (external IIIF):**
   ```
   museum-textile-001,Colonial Textile Fragment,"A woven textile from...",Unknown Artist,circa 1650-1700,Wool,45 x 60 cm,,https://example.org/iiif/image/abc123/info.json,
   ```

3. **Convert to JSON**:
   ```bash
   python3 scripts/csv_to_json.py
   ```

#### Step 4: Preview Your Objects

Build and view your site locally:

```bash
bundle exec jekyll serve --livereload
```

Then:
1. **Visit** `http://localhost:4000`
2. **Click "Objects"** in the navigation
3. **Verify** all your images appear with their metadata

#### Step 5: Find Coordinates for Story Moments

Use the coordinate identification tool:

1. **Navigate to an object page**: `http://localhost:4000/objects/{object_id}`
2. **Click "Identify coordinates"** button below the IIIF viewer
3. **Pan and zoom** to the area you want to feature
4. **Copy values**: Click "Copy entire row" for a CSV template with coordinates

#### Step 6: Build Your Story

Connect your narrative to your objects:

1. **Create CSV file** in `components/structures/` (e.g., `story-1.csv`)
2. **Add header row**:
   ```
   step,question,answer,object,x,y,zoom,layer1_button,layer1_file,layer2_button,layer2_file
   ```
3. **Add story steps**:
   ```
   1,"What is this textile?","This fragment shows...","textile-001",0.5,0.5,1.0,"","story1/step1-layer1.md","",""
   2,"Notice the pattern","The geometric motifs...","textile-001",0.3,0.4,2.5,"","story1/step2-layer1.md","",""
   ```
4. **Add to project setup**: Edit `components/structures/project.csv`, scroll to `STORIES` section, add row: `1,Your Story Title`
5. **Convert to JSON**:
   ```bash
   python3 scripts/csv_to_json.py
   ```
6. **Rebuild and test**:
   ```bash
   bundle exec jekyll serve
   ```

#### Step 7: Add Glossary Terms (Optional)

Enhance your narrative with term definitions:

1. **Create markdown file** in `components/texts/glossary/` (e.g., `colonial-period.md`)
2. **Add frontmatter and definition**:
   ```markdown
   ---
   term_id: colonial-period
   title: "Colonial Period"
   related_terms: encomienda,viceroyalty
   ---

   The Colonial Period in the Americas began with...
   ```
3. **Generate collection**:
   ```bash
   python3 scripts/generate_collections.py
   ```
4. **Build and test**:
   ```bash
   bundle exec jekyll serve
   ```

---

## Installation (For Local Development)

### Prerequisites

- Ruby 3.0+ (for Jekyll)
- Bundler
- Python 3.9+ (for IIIF generation)

### Setup Steps

1. **Install Ruby and Bundler**:
   ```bash
   # macOS (using Homebrew)
   brew install ruby
   gem install bundler

   # Ubuntu/Debian
   sudo apt-get install ruby-full build-essential
   gem install bundler
   ```

2. **Install Jekyll dependencies**:
   ```bash
   bundle install
   ```

3. **Install Python dependencies** (for IIIF generation):
   ```bash
   pip install -r requirements.txt
   ```

See Track 2 above for the complete local development workflow.

## Content Structure

Telar uses a **components-based architecture** that separates content from generated files:

### Components Folder (Source of Truth)

The `components/` folder contains all **editable source content**:

```
components/
├── structures/           # CSV files with organizational data
│   ├── project.csv       # Site settings and story list
│   ├── objects.csv       # Object catalog metadata
│   └── story-1.csv       # Story structure with step coordinates
├── images/
│   ├── objects/          # Source images for IIIF processing
│   └── additional/       # Other images used around the site
└── texts/
    ├── stories/          # Story layer content (markdown)
    │   └── story1/       # You can add subfolders like this to group text files together, but this is optional 
    │       ├── step1-layer1.md
    │       ├── step1-layer2.md
    │       └── ...
    └── glossary/         # Glossary definitions (markdown)
        ├── term1.md
        └── ...
```

**Key principles:**
- CSV files contain structural data (coordinates, file references)
- Markdown files contain long-form narrative content
- Images are processed into IIIF tiles automatically

### Structure Data Files

CSV files in `components/structures/` define your site's structure and reference content files. If using Google Sheets (recommended), the scripts will create these CSV files on the basis of your Google Sheet. If not, you can create them manually

#### Story CSV Structure (for users not using Google Sheets)

Each story CSV (e.g., `story-1.csv`) contains step-by-step navigation data:

```csv
step,question,answer,object,x,y,zoom,layer1_button,layer1_file,layer2_button,layer2_file
1,"Question text","Brief answer","obj-001",0.5,0.5,1.0,"","story1/step1-layer1.md","","story1/step1-layer2.md"
```

**Columns:**
- `step`: Step number
- `question`: Heading displayed in story
- `answer`: Brief answer text
- `object`: Object ID from objects.csv
- `x, y, zoom`: IIIF viewer coordinates (0-1 normalized)
- `layer1_button`: Custom button text (empty = "Learn more")
- `layer1_file`: Path to markdown file in `components/texts/stories/`
- `layer2_button`: Custom button text (empty = "Go deeper")
- `layer2_file`: Path to markdown file in `components/texts/stories/`

**Button behavior:** If button columns are empty, default text appears. If you provide text, it will be used instead.

#### Glossary Terms

No CSV needed! Create markdown files directly in `components/texts/glossary/`:

```markdown
---
term_id: colonial-period
title: "Colonial Period"
related_terms: encomienda,viceroyalty
---

The Colonial Period in the Americas began with...
```

### Jekyll Collections

Auto-generated in `_jekyll-files/` directory:

- `_jekyll-files/_stories/`: Scrollytelling narratives (from project.csv + story CSVs)
- `_jekyll-files/_objects/`: Object metadata (from objects.json)
- `_jekyll-files/_glossary/`: Glossary terms (from components/texts/glossary/)

**Note:** Files in `_jekyll-files/` are auto-generated. Edit source files in `components/` or `_data/` instead.

## IIIF Integration

### Option 1: Local Images

1. Add high-resolution images to `components/images/objects/` directory
2. Name files to match object IDs (e.g., `example-bogota-1614.jpg`)
3. Run `python scripts/generate_iiif.py` to generate IIIF tiles
4. Tiles are saved to `iiif/objects/[object-id]/`

**File Size Limits:**
- Individual images: Up to 100 MB
- Total repository: Keep under 1 GB
- For larger collections, use external IIIF or Git LFS

### Option 2: External IIIF

Reference external IIIF resources in object metadata:

```yaml
iiif_manifest: https://example.org/iiif/image/abc123/info.json
```

## Configuration

### Site Settings (_config.yml)

```yaml
title: Your Narrative Title
baseurl: /repository-name  # For GitHub Pages
url: https://username.github.io

telar:
  project_title: "Narrative Title"
  primary_color: "#2c3e50"
  font_headings: "Playfair Display, serif"
```

## GitHub Actions Workflow

When you deploy via GitHub Pages, the build process is **fully automated**. Here's what happens:

### What YOU Do (User Actions)

Edit content directly on GitHub or push from local:

1. **Edit Google Sheets or CSVs** in `components/structures/` (story structure, object metadata)
2. **Edit markdown** in `components/texts/` (narrative content)
3. **Add images** to `components/images/objects/` (IIIF source images)
4. **Commit and push** to main branch

### What GitHub Actions Does (Automated)

The workflow (`.github/workflows/build.yml`) automatically:

1. **Convert CSVs to JSON**: Runs `scripts/csv_to_json.py`
   - Reads CSVs from `components/structures/`
   - Embeds markdown content from `components/texts/`
   - Generates JSON files in `_data/` for Jekyll
2. **Generate IIIF tiles**: Runs `scripts/generate_iiif.py`
   - Processes images from `components/images/objects/`
   - Creates tiled image pyramids in `iiif/objects/`
3. **Build Jekyll site**: Runs `bundle exec jekyll build`
   - Compiles site from templates and data
   - Outputs to `_site/` directory
4. **Deploy to GitHub Pages**: Publishes `_site/` directory

**Triggers:**
- Push to main branch
- Manual workflow dispatch (Actions tab)

### Manual Build Trigger

After editing your Google Sheet, trigger a rebuild without making code changes:

1. Click the build badge at top of this README (or go to your repository's Actions tab)
2. Click **Build and Deploy** workflow
3. Click **Run workflow** button (top right)
4. Select branch (usually `main`)
5. Click green **Run workflow** button
6. Wait 2-5 minutes for completion

**When to trigger manually:**
- After editing Google Sheets content
- After adding objects or story steps
- To rebuild without code changes

**Automatic triggers:**
- Any push to main branch
- Changes to `_config.yml`, CSVs, or markdown files

## Customization

### Themes

Telar includes 4 preset themes that can be easily switched via `_config.yml`:

1. **Paisajes Coloniales** (default) - Earth tones with terracotta and olive
2. **Neogranadina** - Colonial burgundy and gold
3. **Santa Barbara** - Modern teal and coral
4. **Austin** - Burnt orange and slate blue

To change themes, edit the `telar_theme` setting in `_config.yml`:
```yaml
telar_theme: "santa-barbara"  # Options: paisajes, neogranadina, santa-barbara, austin
```

For advanced customization, create `_data/themes/custom.yml` with your own colors and fonts. See existing theme files for structure.

### Advanced Styling

For deeper customization beyond themes, edit `assets/css/telar.scss`:
- CSS variables (colors, fonts)
- Layout spacing and responsive breakpoints
- Component-specific styles

### Layouts

Modify layouts in `_layouts/`:
- `default.html`: Base template
- `story.html`: Scrollytelling page
- `object.html`: Object detail page
- `glossary.html`: Term definition page

### JavaScript

Core functionality in `assets/js/`:
- `telar.js`: Base utilities
- `story.js`: UniversalViewer + custom step-based scrolling system

## Development

### Local Development Workflow

When developing locally, you need to manually run the build pipeline:

```bash
# 1. Edit content
# - CSVs in components/structures/
# - Markdown in components/texts/
# - Images in components/images/objects/

# 2. Convert CSVs to JSON (run after editing CSVs)
python3 scripts/csv_to_json.py

# 3. Generate IIIF tiles (run after adding/updating images)
python3 scripts/generate_iiif.py --source-dir components/images/objects --base-url http://localhost:4000

# 4. Serve with live reload
bundle exec jekyll serve --livereload

# Build only (output to _site/)
bundle exec jekyll build

# Clean build artifacts
bundle exec jekyll clean
```

---

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

## Performance

- Static HTML generation
- CDN delivery via GitHub Pages
- Progressive IIIF tile loading

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

**Note:** This license covers the Telar framework code and documentation. It does NOT cover user-created content (stories, images, object metadata, narrative text) which remains the property of content creators and may have separate licenses.

## Credits

Telar is developed by Adelaida Ávila, Juan Cobo Betancourt, Santiago Muñoz, and students and scholars at the [UCSB Archives, Memory, and Preservation Lab](https://ampl.clair.ucsb.edu), the UT Archives, Mapping, and Preservation Lab, and [Neogranadina](https://neogranadina.org).

Telar is built with:
- [Jekyll](https://jekyllrb.com/) - Static site generator
- [UniversalViewer](https://universalviewer.io/) - IIIF viewer
- [Bootstrap 5](https://getbootstrap.com/) - CSS framework
- [iiif-static](https://github.com/bodleian/iiif-static-choices) - IIIF tile generator

It is based on [Paisajes Coloniales](https://paisajescoloniales.com/), and inspired by:
- [Wax](https://minicomp.github.io/wax/) - Minimal computing for digital exhibitions
- [CollectionBuilder](https://collectionbuilder.github.io/) - Static digital collections

## Support

For issues, questions, or contributions:
- GitHub Issues: https://github.com/UCSB-AMPLab/telar/issues
- Documentation: https://github.com/UCSB-AMPLab/telar

## Roadmap

### Recently Completed (v0.3.0-beta)

- [x] **Google Sheets integration**: Edit content via spreadsheet interface with automatic CSV fetching
- [x] **Comprehensive error messaging**: User-friendly warnings for configuration issues
- [x] **IIIF manifest copy functionality**: One-click copying of manifest URLs and coordinates
- [x] **Theme system**: 4 preset themes (Paisajes, Neogranadina, Santa Barbara, Austin) with customizable colors and fonts, plus support for custom themes
- [x] **Theme fallback protection**: Multi-tier error detection and automatic fallback to prevent broken styling

### Future Features

- [ ] **Improved documentation**: Video tutorials and examples
- [ ] **Visual story editor**: Point-and-click coordinate selection with live preview
- [ ] **Annotation support**: Clickable markers on IIIF images that open panels with additional information (IIIF annotations)
- [ ] **Glossary auto-linking**: Automatic detection and linking of terms within narrative text
- [ ] **Mobile-optimized responsive design**: Improved mobile and tablet experience
- [ ] **Accessibility improvements**: Comprehensive ARIA labels, keyboard navigation, and color contrast verification
- [ ] **Image lazy loading**: Improved performance for object galleries
- [ ] **Multi-language support**: Internationalization and localization
- [ ] **3D object support**: Integration with 3D viewers
- [ ] **Timeline visualizations**: Temporal navigation for chronological narratives