SELECT
    row_id,
    order_id,
    order_date,
    customer_id,
    segment,
    region_code,
    product_code,
    quantity,
    sales,
    discount,
    profit,
    {{ extraction_lineage() }}
FROM {{ source('raw', 'ecom_sales') }}
