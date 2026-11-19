{# Category from the maximum sustained wind in knots (Saffir-Simpson; below hurricane force:
   tropical storm from 34 kt, depression below). Unknown wind, unknown category. #}
{% macro saffir_simpson(wind_kt) -%}
    case
        when {{ wind_kt }} is null then null
        when {{ wind_kt }} >= 137 then 'Cat 5'
        when {{ wind_kt }} >= 113 then 'Cat 4'
        when {{ wind_kt }} >= 96 then 'Cat 3'
        when {{ wind_kt }} >= 83 then 'Cat 2'
        when {{ wind_kt }} >= 64 then 'Cat 1'
        when {{ wind_kt }} >= 34 then 'Tropical storm'
        else 'Depression'
    end
{%- endmacro %}
