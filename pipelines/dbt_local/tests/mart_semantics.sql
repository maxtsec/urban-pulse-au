select area_id, window_start from {{ ref('mart_area_tram_15m') }}
where (successful_capture_count = 0 and observed_vehicle_count is not null)
    or median_position_age_seconds < 0 or max_success_gap_seconds not between 0 and 900
    or observed_vehicle_count < 0
