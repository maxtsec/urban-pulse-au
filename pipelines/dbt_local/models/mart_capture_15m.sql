with feeds as (
    select unnest(['vehicle-positions', 'trip-updates', 'service-alerts']) as feed
), grid as (
    select w.*, f.feed from {{ ref('int_windows') }} w cross join feeds f
), counts as (
    select g.window_start, g.feed,
        count(c.record_key) as capture_count,
        count(c.record_key) filter (where c.successful) as successful_capture_count,
        count(c.record_key) filter (where not c.successful) as failed_capture_count
    from grid g left join {{ ref('stg_captures') }} c
        on c.feed = g.feed and c.capture_at >= g.window_start and c.capture_at < g.window_end
    group by g.window_start, g.feed
), points as (
    select window_start, feed, window_start as point_at from grid
    union all select window_start, feed, window_end as point_at from grid
    union all
    select g.window_start, g.feed, c.capture_at as point_at
    from grid g join {{ ref('stg_captures') }} c
        on c.feed = g.feed and c.successful
        and c.capture_at >= g.window_start and c.capture_at < g.window_end
), intervals as (
    select *, date_diff('microsecond', lag(point_at) over (
        partition by window_start, feed order by point_at), point_at) / 1000000.0 as gap_seconds
    from points
), gaps as (
    select window_start, feed, max(gap_seconds) as max_success_gap_seconds
    from intervals group by window_start, feed
)
select g.dataset_kind, g.window_start, g.window_end, g.feed,
    c.capture_count, c.successful_capture_count, c.failed_capture_count,
    gaps.max_success_gap_seconds,
    case when c.successful_capture_count = 0 then 'no_successful_capture'
         else 'captures_available' end as coverage
from grid g join counts c using (window_start, feed) join gaps using (window_start, feed)
