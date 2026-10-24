{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set schema_name = (custom_schema_name or target.schema) | trim -%}
    {%- if schema_name not in ['bronze', 'silver', 'gold'] -%}
        {{ exceptions.raise_compiler_error('Use bronze, silver or gold in this project; isolate runs by DuckDB file.') }}
    {%- endif -%}
    {{ schema_name }}
{%- endmacro %}
