SELECT
    product_code,
    product,
    category,
    subcategory,
    {{ extraction_lineage() }}
FROM {{ source('raw', 'product')}}