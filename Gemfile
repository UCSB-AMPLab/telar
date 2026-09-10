source "https://rubygems.org"

# The lock resolves gems that need this — public_suffix 7.0.5, pulled in by
# addressable, declares `>= 3.2`. Without this line bundler on an older Ruby
# does not fail: it quietly resolves public_suffix down to 6.0.2 and rewrites
# Gemfile.lock, so a locally-constrained lock can be committed back without
# anyone noticing. Declared as a floor rather than an exact version so a
# newer Ruby is not blocked; .ruby-version names the one CI builds with.
ruby ">= 3.2", "< 4.0"

# Jekyll
gem "jekyll", "~> 4.3"

# Plugins
gem "jekyll-seo-tag", "~> 2.9"

# GitHub Pages (optional, uncomment for GitHub Pages deployment)
# gem "github-pages", group: :jekyll_plugins

# Development dependencies
group :development do
  gem "webrick", "~> 1.9" # Required for Ruby 3.0+
end
