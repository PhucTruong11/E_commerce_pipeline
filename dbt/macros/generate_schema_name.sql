{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set schema_name = (custom_schema_name or target.schema) | trim -%}
    {# dbt resolves this internal test schema even with store_failures=false.
       Permit it only for test nodes; models still cannot write raw. #}
    {%- set test_audit = node.resource_type == 'test' and schema_name == 'dbt_test__audit' -%}
    {%- if schema_name not in ['bronze', 'silver', 'gold'] and not test_audit -%}
        {{ exceptions.raise_compiler_error('Use bronze, silver or gold in this project; isolate runs by DuckDB file.') }}
    {%- endif -%}
    {{ schema_name }}
{%- endmacro %}
