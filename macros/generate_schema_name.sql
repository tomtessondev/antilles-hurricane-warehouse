{# Datasets are named after their layer (staging, intermediate, marts), as created by
   Terraform, instead of dbt's default "<target>_<layer>". The `ci` target puts every model
   in its own dataset, so pull requests never touch the real tables. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if target.name == "ci" or custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name }}
    {%- endif -%}
{%- endmacro %}
