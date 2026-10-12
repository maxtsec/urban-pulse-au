select start_at, end_at, dataset_kind, t.window_start,
    t.window_start + interval '15 minutes' as window_end
from {{ input_table('analysis_run') }},
    lateral generate_series(start_at, end_at - interval '15 minutes', interval '15 minutes') t(window_start)
