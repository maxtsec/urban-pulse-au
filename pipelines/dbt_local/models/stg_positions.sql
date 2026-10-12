select p.*,
    case when quality_issue is null
         then date_diff('microsecond', observed_at, received_at) / 1000000.0
    end as position_age_seconds
from {{ input_table('positions') }} p
