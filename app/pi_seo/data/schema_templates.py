"""Curated JSON-LD schema template library.

These are the 'Pro' templates — free tier gets a subset.
Tier-gated by `tier_required` on each template.
"""

from app.pi_seo.schemas import SchemaTemplate

SCHEMA_TEMPLATES: list[SchemaTemplate] = [
    # ───── FREE tier ─────
    SchemaTemplate(
        id="article-basic",
        label="Article — Basic",
        category="Content",
        schema_type="Article",
        description="Bài viết tin tức / blog cơ bản.",
        tier_required="free",
        json_ld="""{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "%%title%%",
  "image": "%%og_image%%",
  "datePublished": "%%date_published%%",
  "dateModified": "%%date_modified%%",
  "author": { "@type": "Person", "name": "%%author_name%%" },
  "publisher": {
    "@type": "Organization",
    "name": "%%site_name%%",
    "logo": { "@type": "ImageObject", "url": "%%site_logo%%" }
  }
}""",
    ),
    SchemaTemplate(
        id="faq-basic",
        label="FAQ — Basic",
        category="Support",
        schema_type="FAQPage",
        description="Câu hỏi thường gặp (Q&A).",
        tier_required="free",
        json_ld="""{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "Câu hỏi mẫu?",
      "acceptedAnswer": { "@type": "Answer", "text": "Trả lời mẫu." }
    }
  ]
}""",
    ),
    SchemaTemplate(
        id="breadcrumb-basic",
        label="Breadcrumb",
        category="Navigation",
        schema_type="BreadcrumbList",
        description="Điều hướng breadcrumb.",
        tier_required="free",
        json_ld="""{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    { "@type": "ListItem", "position": 1, "name": "Home", "item": "%%home_url%%" },
    { "@type": "ListItem", "position": 2, "name": "%%category%%", "item": "%%category_url%%" },
    { "@type": "ListItem", "position": 3, "name": "%%title%%" }
  ]
}""",
    ),
    # ───── PRO tier ─────
    SchemaTemplate(
        id="article-rich",
        label="Article — Rich (Pro)",
        category="Content",
        schema_type="Article",
        description="Article đầy đủ với speakable, wordCount, articleSection.",
        tier_required="pro",
        json_ld="""{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "%%title%%",
  "alternativeHeadline": "%%subtitle%%",
  "image": ["%%og_image%%", "%%og_image_square%%"],
  "datePublished": "%%date_published%%",
  "dateModified": "%%date_modified%%",
  "author": {
    "@type": "Person",
    "name": "%%author_name%%",
    "url": "%%author_url%%",
    "sameAs": ["%%author_twitter%%"]
  },
  "publisher": {
    "@type": "Organization",
    "name": "%%site_name%%",
    "logo": { "@type": "ImageObject", "url": "%%site_logo%%" }
  },
  "mainEntityOfPage": { "@type": "WebPage", "@id": "%%permalink%%" },
  "articleSection": "%%category%%",
  "wordCount": %%word_count%%,
  "keywords": "%%tags%%",
  "speakable": {
    "@type": "SpeakableSpecification",
    "cssSelector": ["h1", "h2", ".summary"]
  }
}""",
    ),
    SchemaTemplate(
        id="product-full",
        label="Product — Full (Pro)",
        category="E-commerce",
        schema_type="Product",
        description="Sản phẩm WooCommerce với price, rating, SKU, brand.",
        tier_required="pro",
        json_ld="""{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "%%title%%",
  "image": ["%%og_image%%"],
  "description": "%%description%%",
  "sku": "%%sku%%",
  "brand": { "@type": "Brand", "name": "%%brand%%" },
  "offers": {
    "@type": "Offer",
    "url": "%%permalink%%",
    "priceCurrency": "%%currency%%",
    "price": "%%price%%",
    "availability": "https://schema.org/%%availability%%",
    "itemCondition": "https://schema.org/NewCondition"
  },
  "aggregateRating": {
    "@type": "AggregateRating",
    "ratingValue": "%%rating%%",
    "reviewCount": "%%review_count%%"
  }
}""",
    ),
    SchemaTemplate(
        id="howto-full",
        label="HowTo — Full (Pro)",
        category="Content",
        schema_type="HowTo",
        description="Hướng dẫn step-by-step với time, image, tool.",
        tier_required="pro",
        json_ld="""{
  "@context": "https://schema.org",
  "@type": "HowTo",
  "name": "%%title%%",
  "description": "%%description%%",
  "totalTime": "PT30M",
  "supply": [{ "@type": "HowToSupply", "name": "Nguyên liệu A" }],
  "tool":   [{ "@type": "HowToTool",   "name": "Công cụ A" }],
  "step": [
    {
      "@type": "HowToStep",
      "name": "Bước 1",
      "text": "Mô tả bước 1.",
      "image": "%%step_1_image%%"
    }
  ]
}""",
    ),
    SchemaTemplate(
        id="event-full",
        label="Event — Full (Pro)",
        category="Commerce",
        schema_type="Event",
        description="Sự kiện online/offline với địa điểm, vé, performer.",
        tier_required="pro",
        json_ld="""{
  "@context": "https://schema.org",
  "@type": "Event",
  "name": "%%title%%",
  "startDate": "%%start_date%%",
  "endDate": "%%end_date%%",
  "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
  "eventStatus": "https://schema.org/EventScheduled",
  "location": {
    "@type": "Place",
    "name": "%%venue%%",
    "address": "%%address%%"
  },
  "offers": {
    "@type": "Offer",
    "url": "%%ticket_url%%",
    "price": "%%price%%",
    "priceCurrency": "%%currency%%"
  }
}""",
    ),
    SchemaTemplate(
        id="localbusiness",
        label="LocalBusiness",
        category="Business",
        schema_type="LocalBusiness",
        description="Doanh nghiệp địa phương — NAP + giờ mở cửa.",
        tier_required="pro",
        json_ld="""{
  "@context": "https://schema.org",
  "@type": "LocalBusiness",
  "name": "%%site_name%%",
  "image": "%%site_logo%%",
  "telephone": "%%phone%%",
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "%%street%%",
    "addressLocality": "%%city%%",
    "addressRegion": "%%region%%",
    "postalCode": "%%postal%%",
    "addressCountry": "VN"
  },
  "geo": { "@type": "GeoCoordinates", "latitude": "%%lat%%", "longitude": "%%lng%%" },
  "openingHoursSpecification": [
    {
      "@type": "OpeningHoursSpecification",
      "dayOfWeek": ["Monday","Tuesday","Wednesday","Thursday","Friday"],
      "opens": "08:00",
      "closes": "18:00"
    }
  ]
}""",
    ),
    SchemaTemplate(
        id="recipe-full",
        label="Recipe — Full (Pro)",
        category="Food",
        schema_type="Recipe",
        description="Công thức nấu ăn với nutrition, rating.",
        tier_required="pro",
        json_ld="""{
  "@context": "https://schema.org",
  "@type": "Recipe",
  "name": "%%title%%",
  "author": { "@type": "Person", "name": "%%author_name%%" },
  "datePublished": "%%date_published%%",
  "image": "%%og_image%%",
  "recipeYield": "4 phần",
  "prepTime": "PT15M",
  "cookTime": "PT30M",
  "totalTime": "PT45M",
  "recipeIngredient": ["Nguyên liệu 1", "Nguyên liệu 2"],
  "recipeInstructions": [
    { "@type": "HowToStep", "text": "Bước 1..." }
  ],
  "nutrition": { "@type": "NutritionInformation", "calories": "300 kcal" }
}""",
    ),
    SchemaTemplate(
        id="video",
        label="VideoObject (Pro)",
        category="Media",
        schema_type="VideoObject",
        description="Video với thumbnail, duration, upload date.",
        tier_required="pro",
        json_ld="""{
  "@context": "https://schema.org",
  "@type": "VideoObject",
  "name": "%%title%%",
  "description": "%%description%%",
  "thumbnailUrl": ["%%thumbnail%%"],
  "uploadDate": "%%date_published%%",
  "duration": "PT5M30S",
  "contentUrl": "%%video_url%%",
  "embedUrl": "%%embed_url%%"
}""",
    ),
]


def templates_for_tier(tier: str) -> list[SchemaTemplate]:
    """Return templates visible to this tier.

    Tier hierarchy: agency > pro > free
    """
    if tier == "agency":
        return SCHEMA_TEMPLATES
    if tier == "pro":
        return [t for t in SCHEMA_TEMPLATES if t.tier_required in ("free", "pro")]
    return [t for t in SCHEMA_TEMPLATES if t.tier_required == "free"]
