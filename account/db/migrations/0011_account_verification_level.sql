-- lasteverLM-account: the judge preference becomes a verification level. Plain PostgreSQL,
-- safe to re-run.

-- users.preferences may hold judge_default (off|low|medium|high). It maps to
-- verification_level (off -> basic, low -> standard, medium -> thorough, high ->
-- bulletproof). Expand only: judge_default stays, so a pod of the previous release keeps
-- reading it during the rollout; the service drops it at the user's next preferences
-- write. A row that already has verification_level is never touched.
update users
set preferences = preferences || jsonb_build_object(
    'verification_level',
    case preferences ->> 'judge_default'
        when 'off' then 'basic'
        when 'low' then 'standard'
        when 'medium' then 'thorough'
        when 'high' then 'bulletproof'
    end
)
where preferences ? 'judge_default'
  and not preferences ? 'verification_level'
  and preferences ->> 'judge_default' in ('off', 'low', 'medium', 'high');
