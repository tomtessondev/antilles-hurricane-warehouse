-- The latest season's passages near the Antilles.
select *
from {{ ref("fct_storm_passages") }}
where season = (select max(season) from {{ ref("stg_tracks") }})
