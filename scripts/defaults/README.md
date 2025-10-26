# Telar System Defaults

## ⚠️ DO NOT EDIT FILES IN THIS DIRECTORY

This directory contains **protected fallback copies** of critical system files used by Telar. These files serve as a final level of protection against accidental modifications or deletions.

### Purpose

When Telar encounters problems loading user-editable configuration files (e.g., themes in `_data/themes/`), it falls back to these protected copies to ensure the site continues to function with basic default styling and behavior.

### How It Works

The fallback system operates in tiers:

1. **Primary**: Load the user's configured file (e.g., from `_data/themes/`)
2. **Secondary**: If that fails, load the default file from `_data/themes/paisajes.yml`
3. **Tertiary**: If that also fails, load the protected copy from `scripts/defaults/`
4. **Ultimate**: If all else fails, use hardcoded values in the CSS/templates

### What's Stored Here

- **`themes/paisajes.yml`**: Protected copy of the default Paisajes theme
- *(Additional system defaults may be added in future versions)*

### If You Need to Restore Defaults

If you've accidentally broken your configuration files and need to restore them:

1. **From Git**: `git checkout _data/themes/paisajes.yml`
2. **From this directory**: Copy from `scripts/defaults/themes/` to `_data/themes/`

**Do not modify files in this directory** - they are meant to remain pristine copies for emergency fallback purposes only.

---

**Telar Digital Storytelling Framework**
For more information, see the [main documentation](../../README.md).
