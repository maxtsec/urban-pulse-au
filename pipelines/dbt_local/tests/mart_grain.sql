select area_id, window_start from {{ ref('mart_area_tram_15m') }}
group by area_id, window_start having count(*) != 1
