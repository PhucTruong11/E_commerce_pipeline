SELECT
    region_code,
    city,
    state,
    country,
    country_latitude,
    country_longitude,
    region,
    market,
    {{ extraction_lineage() }}
FROM {{ source('raw', 'region') }}
