# API Reference

## License Endpoints

### POST /pi/v1/license/verify
Check license validity and get features.

### POST /pi/v1/license/activate
Activate license for a WordPress site.

### POST /pi/v1/license/deactivate
Deactivate site from license.

### GET /pi/v1/license/stats
Get license status, usage, package info.

---

## Content Endpoints

### GET /pi/v1/content
List posts/pages.
Params: type, status, search, page, per_page

---

## AI Endpoints

### POST /pi/v1/ai/usage
Report token consumption.

### GET /pi/v1/ai/packages
List available packages.

---

## Updates

### GET /pi/v1/updates/latest
Check for new plugin versions.