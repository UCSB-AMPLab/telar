# Telar

![Version](https://img.shields.io/badge/version-0.2.0--beta-orange) ![License](https://img.shields.io/badge/license-MIT-blue)

A minimal computing framework for creating digital storytelling exhibitions with IIIF images and scrollytelling narratives.

> **⚠️ Beta Release - v0.3.0-beta**
> This release introduces comprehensive error messaging, Google Sheets integration for easier content management, and improved copy functionality for IIIF coordinates. Choose between CSV-based or Google Sheets workflows.

## Overview

Telar (Spanish for "loom") is a static site generator built on Jekyll that weaves together IIIF images, narrative text, and layered contextual information into interactive digital exhibitions. It follows minimal computing principles: plain text authoring, static generation, and sustainable hosting.

Telar is developed by Adelaida Ávila, Juan Cobo Betancourt, Santiago Muñoz, and students and scholars at the [UCSB Archives, Memory, and Preservation Lab](https://ampl.clair.ucsb.edu), the UT Archives, Mapping, and Preservation Lab, and [Neogranadina](https://neogranadina.org).

## Key Features

- **IIIF integration**: Support for both local images (auto-generated tiles) and external IIIF resources
- **Scrollytelling**: Discrete step-based scrolling with support for multiple IIIF objects in a single story - each object preloaded in its own viewer card
- **Layered panels**: Progressive disclosure with three content layers plus glossary
- **Objects gallery**: Browsable object grid with detail pages
- **Minimal computing**: Plain text, static generation, GitHub Pages hosting

---

## Quick Start

### Before You Begin: Plan Your Exhibition

Telar exhibitions are built around a layered storytelling structure. Understanding this model will help you plan your content effectively.

Each page in your Telar site contains one or more stories, which can be independent narratives or chapters of a longer piece. Stories unfold through successive steps that show an image (or a detail of an image) alongside brief text. Each step follows a question/answer/invitation pattern: a question draws viewers in, a brief answer (1-2 sentences) responds, and an invitation to "learn more" opens a layer panel with extended information. You can provide up to two of these layer panels in each step, allowing viewers who want to go deeper to obtain even more detail.

Layer panels are where you can really expand on your narrative. They are written in [markdown format](https://www.markdownguide.org/getting-started/), allowing you to include headings, bold and italic text, links, lists, and other formatting. You can also insert additional images, and embed videos, 3D renderings, or other resources.

Before you start gathering materials or building your site, take time to sketch out your story's structure. Ask yourself: What stories do you want to tell? What are the key moments in each story? What images or details will anchor each step? What information belongs in the brief answer and what in the deeper layers? Planning this out on paper or in a digital tool of your choice will make the implementation much easier.

For inspiration, browse the [example site](https://ampl.clair.ucsb.edu/telar) to see this structure in action. More sites built with Telar will be available soon in our directory.

Once you're ready, choose one of the workflows below based on your needs and technical knowledge.

### Content Management Options

Telar offers two ways to manage your exhibition content:

#### CSV Files (Default)
Edit CSV files directly in your repository using GitHub's web interface or a local text editor. This approach provides full control and works entirely through GitHub.

#### Google Sheets (Optional)
Manage content through a familiar spreadsheet interface with helper scripts for validation and formatting. Ideal for teams or those who prefer spreadsheet editing. See [`docs/google_sheets_integration/README.md`](docs/google_sheets_integration/README.md) for setup instructions.

---

### Track 1: GitHub Web Interface Only (Recommended for Storytellers)

**No installation required!** Edit everything directly on GitHub.

#### Initial Setup

1. **Use this template** - Click the green "Use this template" button above to create your own copy
2. **Configure site settings**:
   - Navigate to `_config.yml` in your repository
   - Click the pencil icon to edit
   - Update these settings:
     - `title`: Your exhibition name
     - `description`: A brief description of your exhibition
     - `baseurl`: `"/your-repository-name"` (include the quotes)
     - `url`: `"https://your-username.github.io"` (include the quotes)
     - `author` and `email` (optional)
   - Commit changes
3. **Enable GitHub Pages**:
   - Go to your new repository
   - Click **Settings** tab
   - Click **Pages** in left sidebar
   - Under "Source", select **GitHub Actions**
   - Click **Save**
4. **Wait 2-5 minutes** for the initial build to complete
5. **View your site** at `https://[your-username].github.io/[repository-name]/`

#### Step 1: Gather Your Images

You have two options for adding images to your exhibition:

**Option A: Upload Your Own Images**

If you have your own high-resolution images:

1. **Navigate to** `components/images/objects/`
2. **Click "Add file"** → **"Upload files"**
3. **Drag your images** into the upload area
4. **Name files** with simple IDs (e.g., `textile-001.jpg`, `ceramic-002.jpg`)
5. **Commit changes**
6. **Remember these filenames** - you'll use them as `object_id` values in Step 3

**Option B: Use External IIIF Manifests**

If you want to use images from institutional collections (museums, libraries, archives):

1. **Find IIIF resources** - Many institutions publish their collections with IIIF support. See the [IIIF Guide to Finding Resources](https://iiif.io/guides/finding_resources/) for help locating collections
2. **Copy the info.json URL** - Look for the IIIF Image API info.json URL (e.g., `https://example.org/iiif/image/abc123/info.json`)
3. **Create an object_id** - Choose a simple ID for this object (e.g., `museum-textile-001`)
4. **Save for next step** - You'll add this URL to the `iiif_manifest` column in objects.csv in Step 3

**Note:** Both options work equally well. You can even mix both approaches in the same exhibition.

#### Step 2: Write Your Narrative Text

Create markdown files for your story layers:

1. **Navigate to** `components/texts/stories/story1/`
2. **Click "Add file"** → **"Create new file"**
3. **Name the file** (e.g., `step1-layer1.md`)
4. **Add frontmatter and content**:
   ```markdown
   ---
   title: "Weaving Techniques"
   ---

   The interlocking warp pattern visible here indicates...
   ```
5. **Commit the file**
6. **Repeat** for each layer of content you want to add

#### Step 3: Catalog Your Objects

Add metadata about your images in the objects catalog:

1. **Navigate to** `components/structures/`
2. **Click on** `objects.csv`
3. **Click the ✏️ pencil icon** (top right) to edit
4. **Add a new row** for each object:

   **For Option A (uploaded images):**
   ```
   textile-001,Colonial Textile Fragment,"A woven textile from...",Unknown Artist,circa 1650-1700,Wool,45 x 60 cm,,,
   ```
   The `object_id` (first column) must match your uploaded image filename.

   **For Option B (external IIIF):**
   ```
   museum-textile-001,Colonial Textile Fragment,"A woven textile from...",Unknown Artist,circa 1650-1700,Wool,45 x 60 cm,,https://example.org/iiif/image/abc123/info.json,
   ```
   Add the info.json URL in the second-to-last column (`iiif_manifest`).

5. **Commit changes**
6. **Wait 2-5 minutes** for GitHub Actions to rebuild your site

#### Step 4: Preview Your Objects

Once the build completes:

1. **Visit your site** at `https://[username].github.io/[repository]/`
2. **Click "Objects"** in the navigation
3. **Verify** all your images appear with their metadata
4. **Click on any object** to see it in the IIIF viewer

#### Step 5: Find Coordinates for Story Moments

Use the built-in coordinate tool to identify specific areas of your images:

1. **Navigate to an object page** (click any object from the gallery)
2. **Click "Identify coordinates"** button below the viewer
3. **Pan and zoom** to the area you want to feature in your story
4. **Watch coordinates update** in real-time (x, y, zoom)
5. **Click "Copy entire row"** to copy a CSV template with the coordinates
6. **Save these coordinates** - you'll paste them into your story CSV

**Coordinate system:**
- `x, y`: 0-1 normalized coordinates (0,0 = top-left)
- `zoom`: 1 = full view, 2 = 2x zoom, etc.

**Tip:** Keep the object page open in one tab while editing your story CSV in another.

#### Step 6: Build Your Story

Now connect your narrative to your objects with coordinates:

1. **Navigate to** `components/structures/`
2. **Click "Add file"** → **"Create new file"**
3. **Name it** `story-1.csv` (or `story-2.csv`, etc.)
4. **Add the header row**:
   ```
   step,question,answer,object,x,y,zoom,layer1_button,layer1_file,layer2_button,layer2_file
   ```
5. **Add story steps**, one row per step:
   ```
   1,"What is this textile?","This fragment shows...","textile-001",0.5,0.5,1.0,"","story1/step1-layer1.md","",""
   2,"Notice the pattern","The geometric motifs...","textile-001",0.3,0.4,2.5,"","story1/step2-layer1.md","",""
   ```
6. **Commit the file**
7. **Add story to project**:
   - Edit `components/structures/project.csv`
   - Scroll to the `STORIES` section
   - Add a new row: `1,Your Story Title`
8. **Commit** and wait for rebuild

#### Step 7: Add Glossary Terms (Optional)

Enhance your exhibition with term definitions:

1. **Navigate to** `components/texts/glossary/`
2. **Click "Add file"** → **"Create new file"**
3. **Name it** `term-name.md`
4. **Add frontmatter and definition**:
   ```markdown
   ---
   term_id: colonial-period
   title: "Colonial Period"
   related_terms: encomienda,viceroyalty
   ---

   The Colonial Period in the Americas began with...
   ```
5. **Commit the file**

**Note:** In v0.1.0-beta, glossary terms appear as standalone pages at `/glossary/{term_id}/`. In v0.2, we plan for automatic linking within narrative text.

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
- `title`: Your exhibition name
- `description`: A brief description of your exhibition
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

Enhance your exhibition with term definitions:

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
    │   └── story1/
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

### CSV Data Files

CSV files in `components/structures/` define your site's structure and reference content files.

#### Story CSV Structure

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
title: Your Exhibition Title
baseurl: /repository-name  # For GitHub Pages
url: https://username.github.io

telar:
  project_title: "Exhibition Title"
  primary_color: "#2c3e50"
  font_headings: "Playfair Display, serif"
```

## GitHub Actions Workflow

When you deploy via GitHub Pages, the build process is **fully automated**. Here's what happens:

### What YOU Do (User Actions)

Edit content directly on GitHub or push from local:

1. **Edit CSVs** in `components/structures/` (story structure, object metadata)
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

## Customization

### Styling

Edit `assets/css/telar.css` to customize:
- Colors (CSS variables in `:root`)
- Typography
- Layout spacing
- Responsive breakpoints

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

### Future Features

- [ ] **Google Sheets integration (v0.3)**: Edit content via web interface without CSV files
- [ ] **Improved documentation**: Video tutorials and examples
- [ ] **Theme system**: Customizable color schemes, typography, and layout options via project.csv configuration
- [ ] **Visual story editor**: Point-and-click coordinate selection
- [ ] **Annotation support**: Clickable markers on IIIF images that open panels with additional information (IIIF annotations)
- [ ] **Glossary auto-linking**: Automatic detection and linking of terms within narrative text
- [ ] **Mobile-optimized responsive design**: Improved mobile and tablet experience
- [ ] **Accessibility improvements**: Comprehensive ARIA labels, keyboard navigation, and color contrast verification
- [ ] **Image lazy loading**: Improved performance for object galleries
- [ ] **Multi-language support**: Internationalization and localization
- [ ] **3D object support**: Integration with 3D viewers
- [ ] **Timeline visualizations**: Temporal navigation for chronological narratives
- [ ] **Advanced theming options**: Customizable design templates