{% macro input_table(name) -%}
read_parquet('{{ env_var("URBANPULSE_PARQUET_DIR") | replace("\\", "/") | replace("'", "''") }}/{{ name }}.parquet')
{%- endmacro %}
