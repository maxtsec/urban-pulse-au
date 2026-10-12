select *, coalesce(received_at, requested_at) as capture_at,
    outcome = 'captured' and payload_valid as successful
from {{ input_table('captures') }}
