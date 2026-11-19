{# Datasets are named after their layer (staging, intermediate, marts), as created by
   Terraform, instead of dbt's default "<target>_<layer>". #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name is not none else target.schema }}
{%- endmacro %}
