#!/usr/bin/env bash
# Idempotently add tenant_id to known WordPress custom tables.
# Required env: WP_DB_HOST, WP_DB_USER, WP_DB_PASS, WP_DB_NAME

set -euo pipefail

: "${WP_DB_HOST:?WP_DB_HOST is required}"
: "${WP_DB_USER:?WP_DB_USER is required}"
: "${WP_DB_PASS:?WP_DB_PASS is required}"
: "${WP_DB_NAME:?WP_DB_NAME is required}"

WP_TABLES=(
  "wp_sh_analytics"
  "wp_pi_leads"
  "wp_pi_chat_logs"
  "wp_pi_seo_audits"
  "wp_pi_forms"
  "wp_pi_form_submissions"
)

for tbl in "${WP_TABLES[@]}"; do
  echo "Migrating ${tbl}..."
  mysql -h"${WP_DB_HOST}" -u"${WP_DB_USER}" -p"${WP_DB_PASS}" "${WP_DB_NAME}" <<SQL
SET @table_exists := (
  SELECT COUNT(*) FROM information_schema.tables
  WHERE table_schema = '${WP_DB_NAME}' AND table_name = '${tbl}'
);
SET @col_exists := (
  SELECT COUNT(*) FROM information_schema.columns
  WHERE table_schema = '${WP_DB_NAME}'
    AND table_name = '${tbl}'
    AND column_name = 'tenant_id'
);
SET @sql := IF(@table_exists = 1 AND @col_exists = 0,
  'ALTER TABLE ${tbl} ADD COLUMN tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1, ADD INDEX idx_${tbl}_tenant (tenant_id)',
  CONCAT('SELECT "Skipped ${tbl}" AS status')
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
SQL
done

echo "Done."

