select
    island,
    div(season, 10) * 10 as decade,
    coalesce(category, 'Unknown') as category,
    count(*) as passages
from {{ ref("fct_storm_passages") }}
group by island, decade, category
