SELECT
    customer_id,
    first_name,
    last_name,
    birth_date,
    marital_status,
    gender,
    email_address,
    annual_income,
    education_level,
    occupation,
    home_owner,
    {{ extraction_lineage() }}
FROM {{ source('raw', 'customer') }}