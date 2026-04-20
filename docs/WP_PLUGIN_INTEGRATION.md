# WordPress plugin integration guide

Drop-in PHP client for calling Pi Backend from any Pi plugin.

## 1. Create a shared API client class

Put this in `pi-dashboard/includes/Api/PiBackendClient.php` (or similar — anywhere once, then `require_once` from each plugin).

```php
<?php
namespace Pi\Dashboard\Api;

if (!defined('ABSPATH')) exit;

/**
 * Pi Backend API client — shared across all Pi plugins.
 *
 * Usage:
 *   $client = PiBackendClient::forPlugin('pi-seo-pro');
 *   $res = $client->post('/v1/seo-bot/generate', ['post_id' => 42, ...]);
 */
class PiBackendClient {

    private const DEFAULT_BASE = 'https://api.piwebagency.com';
    private const OPTION_KEY   = 'pi_license_key_%s';  // e.g. pi_license_key_pi-seo-pro

    private string $base_url;
    private string $license_key;
    private string $plugin_slug;

    public function __construct(string $plugin_slug, string $license_key, string $base_url = '') {
        $this->plugin_slug = $plugin_slug;
        $this->license_key = $license_key;
        $this->base_url    = rtrim($base_url ?: self::DEFAULT_BASE, '/');
    }

    public static function forPlugin(string $plugin_slug): self {
        $key = (string) get_option(sprintf(self::OPTION_KEY, $plugin_slug), '');
        $base = (string) get_option('pi_backend_base_url', '') ?: self::DEFAULT_BASE;
        return new self($plugin_slug, $key, $base);
    }

    public function isConfigured(): bool {
        return $this->license_key !== '';
    }

    public function get(string $path, array $query = []): array {
        return $this->request('GET', $path, null, $query);
    }

    public function post(string $path, array $body = []): array {
        return $this->request('POST', $path, $body);
    }

    private function request(string $method, string $path, ?array $body = null, array $query = []): array {
        if (!$this->isConfigured()) {
            return ['success' => false, 'code' => 'no_license', 'message' => 'License key not set'];
        }

        $url = $this->base_url . $path;
        if (!empty($query)) $url = add_query_arg($query, $url);

        $args = [
            'method'  => $method,
            'timeout' => 30,
            'headers' => [
                'Authorization' => 'Bearer ' . $this->license_key,
                'X-Pi-Site'     => $this->siteDomain(),
                'X-Pi-Plugin'   => $this->plugin_slug,
                'Accept'        => 'application/json',
            ],
        ];
        if ($body !== null) {
            $args['headers']['Content-Type'] = 'application/json';
            $args['body'] = wp_json_encode($body);
        }

        $resp = wp_remote_request($url, $args);
        if (is_wp_error($resp)) {
            return [
                'success' => false,
                'code'    => 'http_error',
                'message' => $resp->get_error_message(),
            ];
        }

        $code = wp_remote_retrieve_response_code($resp);
        $raw  = (string) wp_remote_retrieve_body($resp);
        $data = json_decode($raw, true);

        if ($code >= 200 && $code < 300) {
            return is_array($data) ? $data : ['success' => true, 'raw' => $raw];
        }

        return [
            'success' => false,
            'code'    => is_array($data) ? ($data['code'] ?? 'api_error') : 'api_error',
            'message' => is_array($data) ? ($data['message'] ?? 'API error') : ('HTTP ' . $code),
            'status'  => $code,
        ];
    }

    private function siteDomain(): string {
        $host = (string) wp_parse_url(home_url(), PHP_URL_HOST);
        return strtolower(preg_replace('/^www\./', '', $host));
    }
}
```

## 2. Replace Pi SEO's SEOBot class

In `pi-seo/includes/SEOBot.php`:

```php
use Pi\Dashboard\Api\PiBackendClient;

class SEOBot {

    public static function generate(int $post_id, array $options = []): array {
        $post = get_post($post_id);
        if (!$post) return ['success' => false, 'message' => 'Post not found'];

        $client = PiBackendClient::forPlugin('pi-seo-pro');
        if (!$client->isConfigured()) {
            return ['success' => false, 'message' => 'Chưa nhập license key Pi SEO Pro.'];
        }

        $body = [
            'site_url'       => home_url(),
            'post_id'        => $post_id,
            'post_title'     => $post->post_title,
            'focus_keyword'  => (string) get_post_meta($post_id, '_pi_seo_focus_keyword', true),
            'excerpt'        => wp_trim_words(wp_strip_all_tags($post->post_content), 250),
            'content_snippet'=> wp_trim_words(wp_strip_all_tags($post->post_content), 500),
            'tone'           => $options['tone']     ?? 'professional',
            'audience'       => $options['audience'] ?? 'general',
            'language'       => $options['language'] ?? 'auto',
            'variants'       => max(1, min(5, (int) ($options['variants'] ?? 1))),
        ];

        $res = $client->post('/v1/seo-bot/generate', $body);
        if (empty($res['success'])) {
            return $res;
        }

        $v = $res['variants'][0] ?? null;
        if ($v && !empty($options['auto_save'])) {
            if (!empty($v['title']))       update_post_meta($post_id, '_pi_og_title',       $v['title']);
            if (!empty($v['description'])) update_post_meta($post_id, '_pi_og_description', $v['description']);
        }

        return $res;
    }
}
```

## 3. License settings UI

In any Pi plugin's settings tab, add:

```php
<form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
    <?php wp_nonce_field('pi_save_license', '_pi_license_nonce'); ?>
    <input type="hidden" name="action" value="pi_save_license">
    <input type="hidden" name="plugin_slug" value="pi-seo-pro">

    <label>License key:</label>
    <input type="password"
           name="license_key"
           class="regular-text"
           value="<?php echo esc_attr(get_option('pi_license_key_pi-seo-pro', '')); ?>"
           placeholder="pi_xxxxxxxxxxxxxxxx">

    <button type="submit" class="button button-primary">Activate</button>
</form>
```

Handler:

```php
add_action('admin_post_pi_save_license', function () {
    if (!current_user_can('manage_options')) wp_die('No permission', 403);
    check_admin_referer('pi_save_license', '_pi_license_nonce');

    $slug = sanitize_key($_POST['plugin_slug'] ?? '');
    $key  = trim((string) ($_POST['license_key'] ?? ''));

    update_option('pi_license_key_' . $slug, $key, false);

    // Immediately activate against backend
    $client = \Pi\Dashboard\Api\PiBackendClient::forPlugin($slug);
    $res = $client->post('/v1/license/activate', [
        'site_url'       => home_url(),
        'plugin_version' => defined('PI_SEO_VERSION') ? PI_SEO_VERSION : '',
        'wp_version'     => get_bloginfo('version'),
        'php_version'    => PHP_VERSION,
    ]);

    $ok = !empty($res['success']);
    wp_safe_redirect(add_query_arg([
        'page' => 'pi-dashboard',
        'tab'  => 'seo-settings',
        'pi_license_' . ($ok ? 'activated' : 'error') => 1,
    ], admin_url('admin.php')));
    exit;
});
```

## 4. Daily heartbeat via WP Cron

```php
// Schedule once on plugin activate
register_activation_hook(PI_SEO_FILE, function () {
    if (!wp_next_scheduled('pi_seo_daily_ping')) {
        wp_schedule_event(time(), 'daily', 'pi_seo_daily_ping');
    }
});

add_action('pi_seo_daily_ping', function () {
    $client = \Pi\Dashboard\Api\PiBackendClient::forPlugin('pi-seo-pro');
    if (!$client->isConfigured()) return;

    $client->post('/v1/telemetry/ping', [
        'site_url'       => home_url(),
        'plugin_slug'    => 'pi-seo',
        'plugin_version' => PI_SEO_VERSION,
        'wp_version'     => get_bloginfo('version'),
        'php_version'    => PHP_VERSION,
        'active_users'   => count_users()['total_users'] ?? 0,
        'posts_count'    => (int) wp_count_posts('post')->publish,
    ]);
});
```

## 5. Update check hook

Replace `wp_update_plugins` filter to call Pi Backend:

```php
add_filter('site_transient_update_plugins', function ($transient) {
    if (empty($transient)) return $transient;

    $client = \Pi\Dashboard\Api\PiBackendClient::forPlugin('pi-seo-pro');
    if (!$client->isConfigured()) return $transient;

    $res = $client->get('/v1/updates/check/pi-seo', [
        'current' => PI_SEO_VERSION,
    ]);
    if (empty($res['update_available'])) return $transient;

    $transient->response['pi-seo/pi-seo.php'] = (object) [
        'slug'        => 'pi-seo',
        'plugin'      => 'pi-seo/pi-seo.php',
        'new_version' => $res['latest_version'],
        'url'         => 'https://pi-ecosystem.com/seo',
        'package'     => $res['download_url'],  // signed URL from backend
    ];
    return $transient;
});
```

---

## Error handling UX

Backend always returns this shape on errors:

```json
{
  "success": false,
  "code": "quota_exceeded",
  "message": "Monthly quota: 20 requests exhausted",
  "request_id": "abc123def456"
}
```

Map these to Vietnamese notices in the plugin:

```php
$error_messages = [
    'no_license'         => 'Chưa nhập license key. Vào Settings để kích hoạt.',
    'license_invalid'    => 'License key không hợp lệ hoặc đã bị revoke.',
    'rate_limit_exceeded'=> 'Gọi API quá nhanh, thử lại sau 1 phút.',
    'quota_exceeded'     => 'Đã hết quota tháng này. Upgrade lên Pro để dùng thêm.',
    'ai_provider_error'  => 'AI backend tạm thời lỗi, thử lại sau vài phút.',
];
$msg = $error_messages[$res['code'] ?? ''] ?? ($res['message'] ?? 'Lỗi không xác định');
```
