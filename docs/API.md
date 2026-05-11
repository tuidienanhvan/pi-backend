# API Documentation

## Base URL

```
https://api.pi.direct/pi/v1/
```

## Endpoints

### License API (`/license`)

#### POST `/verify`
Verify license validity. Called every 12-24h by plugin.

**Body:**
```json
{ "key": "pi_xxx", "site_url": "https://example.com", "plugin_version": "1.0.0", "wp_version": "6.4", "php_version": "8.2" }
```

#### POST `/activate`
Activate license for a site.

#### POST `/deactivate`
Deactivate license for a site.

#### GET `/stats`
Get license statistics.

### Content API (`/content`)
GET `/pi/v1/content?type=post&status=publish&page=1&per_page=25`

### AI API (`/ai`)
POST `/usage` - Report token usage

### Updates API (`/updates`)
GET `/latest?plugin_slug=pi-seo&current_version=1.0.0`